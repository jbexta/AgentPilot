
import queue
import sys
import threading
import time
import traceback

import pyautogui
from PySide6.QtCore import QEvent, QObject, QRunnable, Qt, Signal, QTimer
from PySide6.QtWidgets import (QWidget, QGraphicsItem, QApplication, QLabel,
                               QPushButton, QTreeWidgetItemIterator,
                               QDialogButtonBox, QMessageBox)

from gui.gui_utils.layouts import CVBoxLayout, CHBoxLayout
from utils import sql
from utils.helpers import convert_to_safe_case
from plugins.workflows.utils.workflows import compute_workflow

SPEED_RUN = False
MAIN_THREAD_TIMEOUT = 60
_demo_cancelled = False
# Esc presses sent by the harness itself (closing modals) must not cancel.
_synthetic_esc_until = 0.0


class _EscCancelFilter(QObject):
    """Cancel the running demo/test when the user presses Esc."""
    def eventFilter(self, obj, event):
        if (event.type() == QEvent.KeyPress and event.key() == Qt.Key_Escape
                and time.monotonic() > _synthetic_esc_until):
            global _demo_cancelled
            _demo_cancelled = True
        return False


_esc_filter = None


def enable_esc_cancel():
    """Arm Esc-to-cancel for a new run. Must be called on the GUI thread."""
    global _esc_filter, _demo_cancelled
    _demo_cancelled = False
    if _esc_filter is None:
        _esc_filter = _EscCancelFilter()
        QApplication.instance().installEventFilter(_esc_filter)


def cancel_run():
    """Stop the running demo/test at its next checkpoint."""
    global _demo_cancelled
    _demo_cancelled = True


def check_alive():
    # Check if the main window is alive
    if _demo_cancelled:
        raise InterruptedError("Demo cancelled")
    return True
    if not QApplication.instance():
        sys.exit(0)
    if not QApplication.activeWindow():
        sys.exit(0)


# --- previous implementation kept for reference ---------------------------
# It called QMetaObject.invokeMethod from the worker, i.e. into shiboken/Qt
# off the GUI thread. That raced the main thread while it was inside a long
# C++ call (e.g. QTreeWidget.clear() on a big tree) and segfaulted
# intermittently.
# class _MainThreadInvoker(QObject):
#     """Runs a queued callable on the thread that owns this object (the GUI thread)."""
#     @Slot()
#     def _run(self):
#         try:
#             self._result = self._fn()
#             self._exc = None
#         except BaseException as e:  # re-raised on the calling (worker) thread
#             self._result = None
#             self._exc = e
#
#
# _main_invoker = None
#
#
# def _run_on_main(fn):
#     """Run ``fn`` on the GUI thread and return its result.
#
#     The demo/test driver runs on a worker thread. Reading or (worse) mutating
#     Qt widgets from there — e.g. ``expandItem`` / ``visualItemRect`` while
#     locating a tree cell — races the main thread that owns them and can corrupt
#     view state, surfacing later as a segfault inside an unrelated ``clear()``.
#     The Qt parts of the input helpers are funneled through here so they run on
#     the owning thread; only the pyautogui input itself stays on the worker (the
#     event loop must remain free to dispatch the synthesized events).
#     """
#     app = QApplication.instance()
#     if app is None:
#         return fn()
#     main_thread = app.thread()
#     if QThread.currentThread() is main_thread:
#         return fn()
#     global _main_invoker
#     if _main_invoker is None:
#         _main_invoker = _MainThreadInvoker()
#         _main_invoker.moveToThread(main_thread)
#     inv = _main_invoker
#     inv._fn = fn
#     inv._result = None
#     inv._exc = None
#     QMetaObject.invokeMethod(inv, "_run", Qt.BlockingQueuedConnection)
#     if inv._exc is not None:
#         raise inv._exc
#     return inv._result
# ---------------------------------------------------------------------------

_main_calls = queue.Queue()
_main_pump = None


def start_main_pump():
    """Start draining ``_run_on_main`` calls. Must be called on the GUI thread
    before a demo/test worker starts."""
    global _main_pump
    if _main_pump is not None:
        return
    _main_pump = QTimer()
    _main_pump.timeout.connect(_drain_main_calls)
    _main_pump.start(10)


def _drain_main_calls():
    while True:
        try:
            fn, call = _main_calls.get_nowait()
        except queue.Empty:
            return
        try:
            call['result'] = fn()
        except BaseException as e:  # re-raised on the calling (worker) thread
            call['exc'] = e
        call['done'].set()


def post_to_main(fn):
    """Queue ``fn`` to run on the GUI thread without waiting for it."""
    assert _main_pump is not None, "start_main_pump() was not called on the GUI thread"
    _main_calls.put((fn, {'done': threading.Event(), 'result': None, 'exc': None}))


def _run_on_main(fn):
    """Run ``fn`` on the GUI thread and return its result.

    The demo/test driver runs on a worker thread. Reading or (worse) mutating
    Qt widgets from there — e.g. ``expandItem`` / ``visualItemRect`` while
    locating a tree cell — races the main thread that owns them and can corrupt
    view state, surfacing later as a segfault inside an unrelated ``clear()``.
    The Qt parts of the input helpers are funneled through here so they run on
    the owning thread; only the pyautogui input itself stays on the worker (the
    event loop must remain free to dispatch the synthesized events).

    The hand-off is a plain Python queue drained by a GUI-thread timer, so the
    worker never calls into Qt at all.
    """
    if threading.current_thread() is threading.main_thread():
        return fn()
    assert _main_pump is not None, "start_main_pump() was not called on the GUI thread"
    call = {'done': threading.Event(), 'result': None, 'exc': None}
    _main_calls.put((fn, call))
    # call['done'].wait()
    # A blocked GUI thread would otherwise hang the run silently.
    if not call['done'].wait(timeout=MAIN_THREAD_TIMEOUT):
        frame = sys._current_frames().get(threading.main_thread().ident)
        stack = ''.join(traceback.format_stack(frame)) if frame else '(unknown)'
        raise TimeoutError(
            f"GUI thread blocked for {MAIN_THREAD_TIMEOUT}s; it is at:\n{stack}"
        )
    if call['exc'] is not None:
        raise call['exc']
    return call['result']


def resolve_widget(widget):
    """Resolve a QAction to its associated toolbar button widget."""
    from PySide6.QtGui import QAction
    from PySide6.QtWidgets import QToolBar
    if isinstance(widget, QAction):
        for w in widget.associatedObjects():
            if isinstance(w, QToolBar):
                return w.widgetForAction(widget)
    return widget


# def get_widget_coords(widget, top_left=False):
#     widget = resolve_widget(widget)
#     if isinstance(widget, QWidget):
#         point = widget.rect().center() if not top_left else widget.rect().topLeft()
#         global_point = widget.mapToGlobal(point)
#     elif isinstance(widget, QGraphicsItem):
#         center = widget.boundingRect().center()
#         scene_center = widget.mapToScene(center)
#         view = widget.scene().views()[0]
#         viewport_center = view.mapFromScene(scene_center)
#         if not view.viewport().rect().contains(viewport_center):
#             view.ensureVisible(widget.sceneBoundingRect(), 50, 50)
#             viewport_center = view.mapFromScene(scene_center)
#         global_point = view.viewport().mapToGlobal(viewport_center)
#     else:
#         raise ValueError("Unsupported widget type")
#     return global_point.x(), global_point.y()


def get_widget_coords(widget, top_left=False):
    # The Qt geometry reads must happen on the GUI thread; the caller (worker)
    # only uses the returned (x, y) to drive pyautogui.
    def _impl():
        w = resolve_widget(widget)
        if isinstance(w, QWidget):
            # Scroll every enclosing scroll area so the point is on screen.
            from PySide6.QtWidgets import QScrollArea
            parent = w.parentWidget()
            while parent is not None:
                if isinstance(parent, QScrollArea):
                    parent.ensureWidgetVisible(w)
                parent = parent.parentWidget()
            point = w.rect().center() if not top_left else w.rect().topLeft()
            global_point = w.mapToGlobal(point)
        elif isinstance(w, QGraphicsItem):
            center = w.boundingRect().center()
            scene_center = w.mapToScene(center)
            view = w.scene().views()[0]
            viewport_center = view.mapFromScene(scene_center)
            if not view.viewport().rect().contains(viewport_center):
                view.ensureVisible(w.sceneBoundingRect(), 50, 50)
                viewport_center = view.mapFromScene(scene_center)
            global_point = view.viewport().mapToGlobal(viewport_center)
        else:
            raise ValueError("Unsupported widget type")
        return global_point.x(), global_point.y()

    return _run_on_main(_impl)


def click_widget(widget, double=False, nb=False):
    x, y = get_widget_coords(widget)
    click_coords(x, y, double)


def hover_widget(widget):
    x, y = get_widget_coords(widget)
    move_mouse(x, y)


def move_mouse(x, y, speed=1000):  # speed is px/s
    current_pos = pyautogui.position()
    duration = ((x - current_pos.x) ** 2 + (y - current_pos.y) ** 2) ** 0.5 / speed
    check_alive()
    if SPEED_RUN:
        duration = 0.0
    pyautogui.moveTo(x, y, duration=duration)


def type_text(text, interval=20):
    for c in text:
        check_alive()
        pyautogui.typewrite(c)
        pyautogui.sleep(interval/1000)


def click_coords(x, y, double=False):
    check_alive()
    move_mouse(x, y)
    pyautogui.click(x, y)
    if double:
        pyautogui.sleep(0.1)
        pyautogui.click(x, y)

    pyautogui.sleep(0.2)


# def click_tree_item_cell(tree_widget, index, column, double=False, only_hover=False):
#     # If tree has a header, it is included in the index
#     if isinstance(column, str):
#         columns = [convert_to_safe_case(item.get('key', item['text'])) for item in tree_widget.parent.schema]
#         if column not in columns:
#             raise ValueError(f'Column {column} not found in tree widget')
#         column = columns.index(column)
#
#     if isinstance(index, str):
#         match = None
#         it = QTreeWidgetItemIterator(tree_widget)
#         while it.value():
#             if it.value().text(column) == index:
#                 match = it.value()
#                 break
#             it += 1
#         if match is None:
#             raise ValueError(f'Item {index} not found in column {column}')
#
#         parent = match.parent()
#         while parent is not None:
#             tree_widget.expandItem(parent)
#             parent = parent.parent()
#
#         item_rect = tree_widget.visualItemRect(match)
#     else:
#         item_rect = tree_widget.visualRect(tree_widget.model().index(index, column))
#     center = item_rect.center()
#     global_center = tree_widget.mapToGlobal(center)
#     if only_hover:
#         move_mouse(global_center.x(), global_center.y())
#     else:
#         click_coords(global_center.x(), global_center.y(), double)
#         time.sleep(0.5)


def click_tree_item_cell(tree_widget, index, column, double=False, only_hover=False):
    # The tree lookup / expand / geometry (Qt reads + mutations) must run on the
    # GUI thread — doing them on the worker corrupts the view and segfaults a
    # later rebuild. Only the pyautogui input runs here on the worker.
    def _resolve_coords():
        col = column
        # If tree has a header, it is included in the index
        if isinstance(col, str):
            columns = [convert_to_safe_case(item.get('key', item['text'])) for item in tree_widget.parent.schema]
            if col not in columns:
                raise ValueError(f'Column {col} not found in tree widget')
            col = columns.index(col)

        if isinstance(index, str):
            # findItems, not QTreeWidgetItemIterator: shiboken parents every
            # iterator to the tree and never frees it, and the leaked
            # iterators crash a later clear().
            match = next(
                (i for i in tree_widget.findItems('', Qt.MatchContains | Qt.MatchRecursive)
                 if i.text(col) == index),
                None,
            )
            if match is None:
                raise ValueError(f'Item {index} not found in column {col}')

            parent = match.parent()
            while parent is not None:
                tree_widget.expandItem(parent)
                parent = parent.parent()

            tree_widget.scrollToItem(match)
            item_rect = tree_widget.visualItemRect(match)
        else:
            item_rect = tree_widget.visualRect(tree_widget.model().index(index, col))
        center = item_rect.center()
        # Item rects are in viewport coords (below the header, if shown).
        global_center = tree_widget.viewport().mapToGlobal(center)
        return global_center.x(), global_center.y()

    x, y = _run_on_main(_resolve_coords)
    if only_hover:
        move_mouse(x, y)
    else:
        click_coords(x, y, double)
        time.sleep(0.5)


def wait_until(condition, timeout=3.0, interval=0.05, message=None):
    """Poll ``condition`` on the GUI thread until truthy; return its value."""
    deadline = time.monotonic() + timeout
    while True:
        check_alive()
        value = _run_on_main(condition)
        if value:
            return value
        if time.monotonic() >= deadline:
            raise AssertionError(message or f"Timed out after {timeout}s waiting for {condition}")
        time.sleep(interval)


def wait_for_modal(cls=None, timeout=3.0):
    """Wait for a modal dialog (optionally of type ``cls``) and return it."""
    def find():
        dialog = QApplication.activeModalWidget()
        if dialog is not None and (cls is None or isinstance(dialog, cls)):
            return dialog
        return None
    name = cls.__name__ if cls else 'modal dialog'
    return wait_until(find, timeout, message=f"No {name} opened within {timeout}s")


def confirm(button=QMessageBox.Yes, timeout=3.0):
    """Click ``button`` on the QMessageBox that is (or is about to be) open.

    Holds only the box's id and the button's coordinates: message boxes are
    Python-owned, and if this worker dropped the last reference, shiboken
    would defer the C++ delete to the main thread and crash there.
    """
    def find_button():
        box = QApplication.activeModalWidget()
        btn = box.button(button) if isinstance(box, QMessageBox) else None
        if btn is None:
            return None
        center = btn.mapToGlobal(btn.rect().center())
        return id(box), center.x(), center.y()
    box_id, x, y = wait_until(find_button, timeout, message=f"No QMessageBox opened within {timeout}s")
    click_coords(x, y)
    wait_until(lambda: id(QApplication.activeModalWidget()) != box_id,
               message="Message box did not close after clicking its button")


def press(key):
    """Press a key (pyautogui key name, e.g. 'enter', 'esc')."""
    check_alive()
    _send_key(key)


def _send_key(key):
    global _synthetic_esc_until
    if key == 'esc':
        _synthetic_esc_until = time.monotonic() + 0.5
    pyautogui.press(key)


def dismiss_modals(attempts=3):
    """Close any open popup or modal so it can't block later tests."""
    def open_widget():
        return QApplication.activePopupWidget() or QApplication.activeModalWidget()
    for _ in range(attempts):
        if _run_on_main(open_widget) is None:
            return
        _send_key('esc')
        time.sleep(0.2)
    widget = _run_on_main(open_widget)
    if widget is not None:
        _run_on_main(widget.close)


def tree_names(tree, column=0):
    """Text of every row in ``tree`` (folders included)."""
    def _impl():
        items = tree.findItems('', Qt.MatchContains | Qt.MatchRecursive)
        return [item.text(column) for item in items]
    return _run_on_main(_impl)


def choose_menu_action(text, timeout=3.0):
    """Click the action labelled ``text`` in the open popup menu."""
    from PySide6.QtWidgets import QMenu

    def open_menu():
        popup = QApplication.activePopupWidget()
        return popup if isinstance(popup, QMenu) else None
    menu = wait_until(open_menu, timeout, message=f"No popup menu opened within {timeout}s")

    def action_coords():
        action = next((a for a in menu.actions() if a.text() == text), None)
        if action is None:
            labels = [a.text() for a in menu.actions() if a.text()]
            raise AssertionError(f"No menu action {text!r}; menu has {labels}")
        center = menu.mapToGlobal(menu.actionGeometry(action).center())
        return center.x(), center.y()
    click_coords(*_run_on_main(action_coords))


class DemoOverlay(QWidget):
    """Floating top-right status panel shown while the demo or tests run.

    The run executes on a worker thread, so updates arrive through Qt
    signals which Qt delivers as queued calls on the GUI thread.
    """

    segment_signal = Signal(str)
    narration_signal = Signal(str)
    finished_signal = Signal()

    def __init__(self, main, on_stop, on_finished=None,
                 title='AgentPilot Demo'):
        super().__init__(parent=main)
        self.main = main
        self._stop_callback = on_stop
        self._finish_callback = on_finished
        self.setObjectName('demoOverlay')
        self.setWindowFlags(
            Qt.Tool | Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint
        )
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setAttribute(Qt.WA_ShowWithoutActivating)
        self.setFixedWidth(360)

        self.layout = CVBoxLayout(self)

        self.card = QWidget()
        self.card.setObjectName('demoOverlayCard')
        self.card_layout = CVBoxLayout(self.card)
        self.card_layout.setContentsMargins(16, 14, 16, 16)
        self.card_layout.setSpacing(8)
        self.layout.addWidget(self.card)

        header = CHBoxLayout()
        self.title_label = QLabel(title)
        self.title_label.setObjectName('demoOverlayTitle')
        self.stop_button = QPushButton('Stop')
        self.stop_button.setObjectName('demoOverlayStop')
        self.stop_button.setCursor(Qt.PointingHandCursor)
        self.stop_button.clicked.connect(self._on_stop)
        header.addWidget(self.title_label)
        header.addStretch(1)
        header.addWidget(self.stop_button)
        self.card_layout.addLayout(header)

        self.segment_label = QLabel('Starting…')
        self.segment_label.setObjectName('demoOverlaySegment')
        self.card_layout.addWidget(self.segment_label)

        self.narration_label = QLabel('')
        self.narration_label.setObjectName('demoOverlayNarration')
        self.narration_label.setWordWrap(True)
        self.card_layout.addWidget(self.narration_label)

        self.segment_signal.connect(self._apply_segment)
        self.narration_signal.connect(self._apply_narration)
        self.finished_signal.connect(self._apply_finished)

        self._drag_anchor = None
        self._user_moved = False
        self.adjustSize()
        self._reposition()

    def show_segment(self, name, index, total):
        """Thread-safe: called from the demo worker thread."""
        self.segment_signal.emit(f'{name}   ·   {index} / {total}')

    def show_status(self, text):
        """Thread-safe: called from the worker thread."""
        self.segment_signal.emit(text)

    def show_narration(self, text):
        """Thread-safe: called from the demo worker thread."""
        self.narration_signal.emit(text)

    def finish(self):
        """Thread-safe: called from the demo worker thread."""
        self.finished_signal.emit()

    def _on_stop(self):
        self.stop_button.setEnabled(False)
        self.stop_button.setText('Stopping…')
        self.segment_label.setText('Stopping…')
        self.narration_label.setText('')
        self._refit()
        self._stop_callback()

    def _apply_segment(self, text):
        self.segment_label.setText(text)
        self._refit()

    def _apply_narration(self, text):
        self.narration_label.setText(text)
        self._refit()

    def _apply_finished(self):
        if getattr(self.main, '_demo_overlay', None) is self:
            self.main._demo_overlay = None
        self.close()
        self.deleteLater()
        if self._finish_callback:
            self._finish_callback()

    def _refit(self):
        self.adjustSize()
        self._reposition()

    def _reposition(self):
        if self._user_moved:
            return
        screen = QApplication.primaryScreen().availableGeometry()
        margin = 20
        self.move(screen.right() - self.width() - margin,
                  screen.top() + margin)

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self._drag_anchor = event.globalPosition().toPoint() - self.pos()
        event.accept()

    def mouseMoveEvent(self, event):
        if self._drag_anchor is not None:
            self.move(event.globalPosition().toPoint() - self._drag_anchor)
            self._user_moved = True
        event.accept()

    def mouseReleaseEvent(self, event):
        self._drag_anchor = None
        event.accept()


# ========================================================================= #
# DEMO SCRIPT: "A day with Agent Pilot"
#
# One continuous story instead of a feature tour. A solo developer uses
# Agent Pilot to plan their day, build a side project, extend the app
# itself and make a phone call. Every feature appears because the story
# needs it. [Square brackets] are on-screen actions; the rest is narration.
# ------------------------------------------------------------------------- #
#
# 1. COLD OPEN
#   [App opens on a blank chat]
#   "This is Agent Pilot. It looks like a chat app, but everything you're
#    about to see, every agent, page and button, is a module you can
#    change, even while it's running. Let's spend a day with it."
#
# 2. FIRST CONVERSATION
#   [Settings > Models: hover the API key column of a provider]
#   "First, bring your own keys. Any provider, any model."
#   [Chat page: click the chat name to open its settings, pick a model]
#   [Type "Morning! What should I focus on today?" and send]
#   "Every chat is really a workflow. Right now it's just me and one agent."
#   [Edit the first message, add "I have 3 hours", resend]
#   "Changed my mind? Edit and resend. The old reply isn't lost, it's a
#    branch."
#   [Flip between branches with the arrows on the bubble]
#
# 3. GIVING IT A PERSONALITY
#   [Agents page: double-click "Ayva" to start a chat with her]
#   [Open chat settings, click into the system message]
#   "Agents are saved workflows with their own defaults. See this
#    {known-personality} in curly braces? That's a block."
#   [Blocks page: select "known-personality"]
#   "Blocks are reusable snippets: text, code, a prompt or a whole workflow.
#    Write one once and use it in any agent or any text field."
#
# 4. BUILDING A TEAM
#   "One opinion isn't enough for today's plan. Let's build a small team."
#   [Chat settings: + > Agent > Empty agent, drop it on the canvas, twice,
#    stacked vertically]
#   "Members run left to right. Stack two vertically and they run at the
#    same time."
#   [Connect the user to both agents, set different models, hide their
#    bubbles, give each an output placeholder]
#   [Add a third agent whose system message combines {planner} and
#    {critic}]
#   "Two drafts in parallel, one agent to merge them."
#   [Send "Plan my day"; toggle hidden bubbles to show the drafts]
#   [Save icon > Save as Agent > "Day Planner"]
#   "Saved. Now it's an agent like any other: Agent, Block, Tool or Task,
#    all built on the same engine."
#
# 5. TOOLS
#   [Tools page: select a tool]
#   "Agents act through tools. A tool is a code block, or a whole workflow.
#    Pages expose their own methods as tools too, so agents can drive the
#    app itself."
#
# 6. THE SIDE PROJECT
#   "The plan says: work on the landing page. That's a project."
#   [Projects page: + "Landing Page", pick its folder, project type
#    Website]
#   "Projects are workspaces with their own files, chats, skills, blocks
#    and plans. Website projects add a live preview."
#   [Project Chat tab: new chat, "Add a pricing section"]
#   "Project chats use Claude Code inside the project folder. The file
#    tree shows what changed, and chats are grouped by the files they
#    touched."
#   [Block Maps tab: map the "readme" block to README.md, hover Bake]
#   "Block maps keep files on disk in sync with your block library."
#
# 7. THE APP EDITS ITSELF
#   "I want to jot notes while I work, and Agent Pilot has no notes page.
#    So let's write one, from inside the app."
#   [Hover the sidebar, click +, name the page "Notes"]
#   [The page editor opens beside it]
#   "This is the Application project, Agent Pilot's own source code. The
#    coding agent knows which page I'm looking at."
#   [Type "Make this a notes page with a title and a big text box", send]
#   [Agent finishes; the page reloads in place]
#   "No restart. The changed modules hot-reload the moment the agent
#    finishes its turn."
#   [Type a note into the new page]
#
# 8. NOT FORGETTING THINGS
#   [Tasks page: calendar + > "Morning briefing", 08:00, Daily]
#   "Tasks are workflows on a schedule. A background scheduler runs them,
#    and every run is saved as a chat."
#   [Task list: + "Call the dentist", no schedule]
#   "Tasks without a schedule are just to-dos, with a status: to do,
#    running, review, done."
#   [Back in chat: "Add 'buy milk' to my to-dos and show me what's left"]
#   "Agents manage tasks with the built-in task tools, so you can just ask."
#   [When column: type "every weekday at 9am"]
#   "Schedules can be typed in plain English."
#   [Goals: + "Launch the landing page", description, Run goal]
#   "Bigger, open-ended work becomes a goal that Claude Code works toward
#    and tracks."
#
# 9. PICKING UP THE PHONE
#   "Speaking of the dentist..."
#   [Settings > Telephony: hover provider, number, answering agent]
#   "Connect Telnyx or Twilio and a live voice agent can make and answer
#    real phone calls. A webhook daemon opens a secure tunnel, so there's
#    no server to configure."
#   [Contacts: + "Dentist", add phone number, Call options > agent, Call]
#   "The agent makes the call and books the appointment. The whole
#    conversation lands in a chat as a transcript."
#   [Tasks: "Call the dentist" flips to done]
#
# 10. CLOSE
#   [Settings > Modules: scroll the module list]
#   "Pages, widgets, fields, daemons, even the managers that run the app,
#    are all modules, bundled into plugins you can share. That was one day.
#    What you build with it is up to you."
#   [Fade out on the Notes page we made earlier]
# ========================================================================= #


class DemoRunnable(QRunnable):
    def __init__(self, main, overlay=None, on_finished=None):
        super().__init__()
        start_main_pump()
        self.main = main
        self.overlay = overlay
        self.on_finished = on_finished
        self._cancelled = False
        self._segment_index = 0
        self._segment_total = 0

    def set_segment(self, name):
        if not self.overlay:
            return
        self._segment_index += 1
        self.overlay.show_segment(
            name, self._segment_index, self._segment_total
        )

    def get_first_chat_bubble_container(self):
        page_chat = self.main.main_pages.get('chat')
        first_chat_bubble_container = page_chat.message_collection.chat_bubbles[0]
        return first_chat_bubble_container

    def goto_page(self, page_name, parent_widget=None):
        main_pages = self.main.main_pages
        if not parent_widget:
            page_in_main = main_pages.pages.get(page_name, None)
            if page_in_main:
                parent_widget = main_pages
            else:
                settings_page = main_pages.pages['settings']
                if main_pages.content.currentWidget() is not settings_page:
                    click_widget(main_pages.settings_sidebar.page_buttons['settings'])
                parent_widget = settings_page

        page = parent_widget.pages.get(page_name, None)
        if parent_widget.content.currentWidget() is page:
            return page

        sidebar = getattr(parent_widget, 'settings_sidebar', None)
        if sidebar:
            btn = sidebar.page_buttons.get(page_name, None)
            if not btn:
                raise ValueError(f'Page {page_name} not found')
            click_widget(btn)
        else:
            tab_bar = parent_widget.content.tabBar()
            tab_index = list(parent_widget.pages.keys()).index(page_name)
            tab_rect = tab_bar.tabRect(tab_index)
            center = tab_rect.center()
            global_center = tab_bar.mapToGlobal(center)
            click_coords(global_center.x(), global_center.y())

        return page

    def toggle_chat_settings(self, state):
        page_chat = self.main.main_pages.get('chat')
        currently_visible = page_chat.workflow_settings.splitter.isVisible()
        if state != currently_visible:
            widget = page_chat.workflow_settings.header_widget.btn_collapse
            click_widget(widget)
            # self.sleep(0.5)

    def click_context_menu_item(self, source_widget, item_index, row_height=24):
        source_widget = resolve_widget(source_widget)
        bx, by = get_widget_coords(source_widget)
        by += source_widget.height() / 2
        click_coords(bx + 60, by + (item_index * row_height))

    def click_workflow_coords(self, workflow_settings, x, y, double=False):
        vx, vy = get_widget_coords(workflow_settings.workflow_buttons, top_left=True)
        vy += workflow_settings.workflow_buttons.height()
        vx += x
        vy += y
        click_coords(vx, vy, double=double)

    def cancel(self):
        """Request the demo to stop at the next checkpoint."""
        global _demo_cancelled
        _demo_cancelled = True
        self._cancelled = True

    def check_cancelled(self):
        if self._cancelled:
            raise InterruptedError("Demo cancelled")

    def sleep(self, seconds):
        if SPEED_RUN:
            return
        self.check_cancelled()
        time.sleep(seconds)

    def send_message(self, message, chat_widget=None, timeout=None):
        chat_widget = chat_widget or self.main.page_chat
        click_widget(chat_widget.input_widget.message_text)
        type_text(message)
        click_widget(chat_widget.input_widget.send_button)
        self.wait_for_response(chat_widget.workflow, timeout)

    def wait_for_response(self, workflow, timeout=None):
        from plugins.workflows.utils.runs import get_run_manager
        run_manager = get_run_manager()
        started = time.time()
        time.sleep(0.5)
        while workflow.responding or run_manager.is_running(workflow.context_id):
            self.check_cancelled()
            if timeout and time.time() - started > timeout:
                return
            time.sleep(0.1)

    def wait_for_modal(self, timeout=3.0):
        waited = 0.0
        while waited < timeout:
            modal = _run_on_main(QApplication.activeModalWidget)
            if modal is not None:
                return modal
            time.sleep(0.1)
            waited += 0.1
        return None

    def dismiss_modals(self):
        for _ in range(3):
            if _run_on_main(QApplication.activeModalWidget) is None:
                return
            pyautogui.press('esc')
            time.sleep(0.3)

    def confirm_yes(self):
        """Click Yes on the modal confirm box (fallback: Enter)."""
        box = self.wait_for_modal()
        if box is None:
            return
        yes_button = _run_on_main(
            lambda: box.button(QMessageBox.Yes) if hasattr(box, 'button') else None
        )
        if yes_button is not None:
            click_widget(yes_button)
        else:
            pyautogui.press('enter')
        self.sleep(1)

    def add_tree_item(self, page, name):
        """Click a ConfigDBTree's add button and answer its name prompt."""
        click_widget(page.tree_buttons.inner_widget.btn_add)
        if self.wait_for_modal():
            type_text(name)
            pyautogui.press('enter')
        self.sleep(1.5)

    def right_click_widget(self, widget):
        x, y = get_widget_coords(widget)
        move_mouse(x, y)
        pyautogui.rightClick(x, y)
        time.sleep(0.5)

    def click_menu_action(self, *texts, timeout=3.0):
        """Click the first action of the open popup menu matching `texts`.

        Returns the matched text, or None (closing the menu) if none match.
        """
        def _find():
            from PySide6.QtWidgets import QMenu
            menu = QApplication.activePopupWidget()
            if not isinstance(menu, QMenu):
                return None
            actions = {a.text(): a for a in menu.actions()}
            for text in texts:
                action = actions.get(text)
                if action and action.isEnabled():
                    center = menu.actionGeometry(action).center()
                    point = menu.mapToGlobal(center)
                    return text, point.x(), point.y()
            return False

        waited = 0.0
        while waited < timeout:
            found = _run_on_main(_find)
            if found:
                text, x, y = found
                click_coords(x, y)
                return text
            if found is False:
                break
            time.sleep(0.1)
            waited += 0.1
        pyautogui.press('esc')
        return None

    def first_item_name(self, tree):
        """Name of the first non-folder row in a tree."""
        def _find():
            it = QTreeWidgetItemIterator(tree)
            while it.value():
                if it.value().data(0, Qt.UserRole) != 'folder':
                    return it.value().text(0)
                it += 1
            return None
        return _run_on_main(_find)

    def text_to_speech(self, text, blocking=False, wait_percent=0.0):
        if self.overlay and text.strip():
            self.overlay.show_narration(text)

        if SPEED_RUN:
            return

        if wait_percent > 0.0:
            blocking = True

        voice_model = sql.get_scalar("""
            SELECT json_extract(value, '$."system.default_voice_model"')
            FROM settings WHERE field = 'app_config'
        """, load_json=True) or {}
        voice_model['model_params'] = {
            **voice_model.get('model_params', {}),
            'text': text,
        }

        wf_config = {
            "_TYPE": "workflow",
            "config": {
                "autorun": True,
            },
            "inputs": [],
            "members": [
                {
                    "config": {
                        "_TYPE": "audio",
                        "mode": "Model",
                        "model": voice_model,
                        "use_cache": True,
                        # Must always wait for the file: the voice provider
                        # (e.g. fal) is an async queue that first returns only a
                        # request_id. Without this the audio is never downloaded
                        # and there's no filepath to play. `blocking` only
                        # governs whether *playback* below waits.
                        "wait_until_finished": True,
                        "wait_percent": wait_percent,
                    },
                    "id": "1",
                    "loc_x": 105,
                    "loc_y": 57
                }
            ],
            "params": []
        }
        # {
        #         "_TYPE": "audio",
        #         "mode": "Model",
        #         "model": {
        #             "kind": "AUDIO",
        #             "model_name": "minimax/music-2.5",
        #             "model_params": {
        #                 "bitrate": 256000,
        #                 "lyrics": "[Instrumental intro – jungle night ambience, shacapa rhythm, low ceremonial drum heartbeat]\r\n\r\n[Verse – soft, almost whispered]\r\nMadre selva, estoy aquí\r\nAbre el camino dentro de mí\r\nQuita el miedo, quita el dolor\r\nLimpia mi sangre con tu canción\r\n\r\n[Verse]\r\nBajo la luna me dejo caer\r\nComo hoja que aprende a volver\r\nNo soy mi nombre, no soy mi piel\r\nSoy solo espíritu en tu poder\r\n\r\n[Pre-Chorus – drum pulse deepens]\r\nSana, sana, corazón\r\nSana, sana, corazón\r\nLuz antigua, dame visión\r\nLuz antigua, dame visión\r\n\r\n[Chorus – call and response energy]\r\nMuero, muero en la oscuridad\r\n[Nazco, nazco en claridad]\r\nCaigo, caigo sin resistir\r\n[Fluyo, fluyo hacia ti]\r\n\r\n[Instrumental – shacapa faster, layered tribal drums]\r\n\r\n[Verse – stronger vocal]\r\nEspíritu del río, ven\r\nEspíritu del fuego, ven\r\nEspíritu del viento, ven\r\nJaguar sagrado, ven\r\n\r\n[Bridge – almost whispered again]\r\nRompe mi ego, rompe mi voz\r\nVacía mi cuerpo de todo temor\r\nHaz de mi herida medicina\r\nHaz de mi sombra bendición\r\n\r\n[Build – drums intensify, chanting layered]\r\n\r\n[Final Chorus – full ceremonial energy]\r\nMuero en la noche\r\nNazco en la luz\r\nRegreso al origen\r\nRegreso a la cruz\r\n\r\nSoy tierra\r\nSoy río\r\nSoy fuego\r\nSoy Dios\r\n\r\n[Outro – drums slow, jungle ambience returns, distant chanting]",
        #                 "prompt": "",
        #                 "sample_rate": 16000
        #             },
        #             "provider": "wavespeed"
        #         },
        #         "name": "Audio",
        #         "preview.pending": [],
        #         "preview.results": []
        #     },
        check_alive()
        with sql.write_to_file(None):
            # None uses default path, this computes with the users database not the demo one
            # This is so voice cache isn't erased
            result = compute_workflow(wf_config)
            print(text)

        if result:
            import json
            from utils.media import play_file
            filepath = json.loads(result).get('filepath')
            if filepath:
                play_file(filepath, blocking=blocking,
                          wait_percent=wait_percent, interrupt=False)

    def run(self):
        global _demo_cancelled
        _demo_cancelled = False
        while not self.main.main_pages.isVisible():
            time.sleep(0.1)
        time.sleep(0.5)  # Let layout settle
        try:
            self._run_demo()
        except InterruptedError:
            pass
        finally:
            if self.overlay:
                self.overlay.finish()
            elif self.on_finished:
                # QTimer.singleShot(0, self.on_finished)
                # A timer started on this worker never fires (no event loop).
                post_to_main(self.on_finished)

    def _run_demo(self):
        demo_segments = {
            'Intro': False,
            'Models': False,
            'Chat': True,
            'Agents': True,
            'Blocks': True,
            'Workflows': True,
            'Workflows 2': True,
            'Tools': True,
            'Modules': True,
            'Builder': True,
            'Projects': True,
            'Live Coding': True,
            'Tasks': True,
            'Telephony': True,
        }
        enable_all = False
        if enable_all:
            demo_segments = {k: True for k in demo_segments.keys()}

        segment_order = ['Intro', 'Models', 'Chat', 'Agents', 'Blocks',
                         'Workflows', 'Workflows 2', 'Tools', 'Projects',
                         'Live Coding', 'Tasks', 'Telephony']
        self._segment_total = sum(
            1 for k in segment_order if demo_segments.get(k)
        )
        self._segment_index = 0

        # self.text_to_speech(dedent('''
        #     In this video we'll be showing you the key concepts of Agent Pilot,
        #     starting with the basics and then moving on to more advanced features like multi-member chats,
        #     nested workflows, tool calling, structured outputs and other powerful features.
        # '''),
        # blocking=True)
        global SPEED_RUN
        # SPEED_RUN = True

        if demo_segments['Intro']:
            self.set_segment('Intro')
            self.text_to_speech(blocking=True,
                text="""Agent Pilot is a generative, fully customizable desktop application.""")
            self.text_to_speech(blocking=True,
                text="""At it's core is a powerful workflow engine and builder, you can design modular, nestable workflows with a graph-based editor. """)
            self.text_to_speech(blocking=True,
                text="""There are different collections of workflows: Agents, Blocks, Tools and Tasks.""")
            self.text_to_speech(blocking=True,
                text="""Here is the Agent collection, these are workflows intended for the user to interact with. """)
            self.text_to_speech(blocking=True,
                text="""The User and Agent workflow members are conversational, Agents can see messages from previous turns, and the User member pauses and waits for user input.""")
            self.text_to_speech(blocking=True,
                text="""This is the block collection, these can be used from any other workflow, or text field such as an agent's system message.""")
            self.text_to_speech(blocking=True,
                text="""The app comes bundled with pre-built Agents and Blocks that power the intelligence of the application.""")
            self.text_to_speech(blocking=True,
                text="""One of these uses a member from the Claude Code plugin, this is a wrapper for Claude Code installed on your system.""")
            self.text_to_speech(blocking=True,
                text="""You can manage projects from this page, these are different workspaces, with their own files, chats, and block mappings.""")
            self.text_to_speech(blocking=True,
                text="""This Application project is a special project that points to the actual running source code of Agent Pilot itself.""")
            self.text_to_speech(blocking=True,
                text="""When this project is modified, the application will instantly reload the source code, allowing you to see changes reflected instantly without restarting.""")
            self.text_to_speech(blocking=True,
                text="""Pages can be added or deleted within the application, right-click and delete to remove, and click this plus button to add a new page.""")
            self.text_to_speech(blocking=True,
                text="""When on a page, you can edit it by clicking this icon.""")
            self.text_to_speech(blocking=True,
                text="""This opens a popup, showing the same special application project.""")
            self.text_to_speech(blocking=True,
                text="""The default coding agent knows which page is currently open, allowing quick edits to the page.""")

            pass

        if demo_segments['Models']:
            self.set_segment('Models')
            self.text_to_speech(blocking=True,
                text="""Let's start by adding an API key in the settings."""
            )
            self.text_to_speech(blocking=False,
                text="""Go to the settings page, then click Models."""
            )
            page_settings = self.goto_page('settings')
            page_models = self.goto_page('models', page_settings)
            self.text_to_speech(blocking=True, wait_percent=0.75,
                text="""Here you can manage the models under each provider. Find the provider you want to use, then enter the API key for it here."""
            )
            click_tree_item_cell(page_models.tree, 6, 'API_Key')
            # wait_until_finished_speaking()
            self.sleep(2)

        if demo_segments['Chat']:
            self.set_segment('Chat')
            # # # # # # # # # # # # # # # # # # # # #
            SPEED_RUN = False
            # # # # # # # # # # # # # # # # # # # # #

            self.text_to_speech(blocking=False,
                text="""Head back to the chat page by clicking this Chat icon."""
            )
            self.goto_page('chat')
            page_chat = self.goto_page('chat')  # 2 ensure blank chat
            self.sleep(1.5)
            # wait_until_finished_speaking()
            self.text_to_speech(blocking=True,  # , wait_percent=0.3,
                text="""To open the settings for the chat, click the chat name. This is just a chat with a single Agent, but it can be an entire workflow.."""
            )
            self.toggle_chat_settings(True)
            # wait_until_finished_speaking()
            self.sleep(3)
            self.text_to_speech(blocking=False, wait_percent=0.6,
                text="""We'll go over that soon, but first let's set the model for the agent, go to the `Chat` tab and set the chat model, here."""
            )

            chat_workflow_settings = page_chat.workflow_settings
            chat_agent_settings = chat_workflow_settings.member_config_widget.config_widget
            chat_agent_settings.content.setCurrentIndex(0)
            agent_model_combo = chat_agent_settings.pages['Messages'].model_wgt

            click_widget(agent_model_combo)  # BLOCKING
            self.sleep(2)
            pyautogui.press('esc')
            # pyautogui.moveTo(cb_x, cb_y, duration=0.3)
            # QTest.qWait(500)

            self.text_to_speech(blocking=False, wait_percent=0.6,
                text="""Try chatting with it."""
            )
            self.send_message('Hello world')

            self.toggle_chat_settings(False)
            # time.sleep(1.5)

            self.text_to_speech(blocking=True,
                text="""You can edit messages and resend them, this creates a branch."""
            )
            first_chat_bubble_container = self.get_first_chat_bubble_container()  # page_chat.message_collection.chat_bubbles[0]
            first_chat_bubble = first_chat_bubble_container.bubble
            click_widget(first_chat_bubble)

            pyautogui.press('end')
            type_text('!!!!!!!')

            resend_button = getattr(first_chat_bubble_container, 'btn_resend', None)
            if resend_button:
                click_widget(resend_button)

            page_chat = self.main.main_pages.get('chat')
            while page_chat.workflow.responding:
                print('Waiting for response...')
                time.sleep(0.1)

            self.sleep(1)
            self.text_to_speech(blocking=True,
                text="""You can cycle between these branches with these buttons."""
            )
            first_chat_bubble_container = self.get_first_chat_bubble_container()
            first_chat_bubble = first_chat_bubble_container.bubble

            hover_widget(first_chat_bubble)
            click_widget(first_chat_bubble.branch_buttons.btn_back)
            first_chat_bubble = self.get_first_chat_bubble_container().bubble
            click_widget(first_chat_bubble.branch_buttons.btn_next)
            first_chat_bubble = self.get_first_chat_bubble_container().bubble
            click_widget(first_chat_bubble.branch_buttons.btn_back)
            first_chat_bubble = self.get_first_chat_bubble_container().bubble
            click_widget(first_chat_bubble.branch_buttons.btn_next)
            self.sleep(1.5)

            self.goto_page('chat')  # New chat
            self.text_to_speech(blocking=True,
                text="""To start a new chat, click this plus button. This will create a new chat with the exact same settings as the previous one."""
            )
            # time.sleep(0.8)
            # wait_until_finished_speaking()

            self.text_to_speech(blocking=False,
                text="""All your chats are saved in the Chats page - here - so you can continue or refer back to them."""
            )
            self.goto_page('contexts')
            self.sleep(3)
            self.goto_page('chat')
            self.sleep(1)

            # self.text_to_speech(blocking=False,
            #     text="""You can quickly cycle between chats by using these navigation buttons"""
            # )
            self.text_to_speech(blocking=False,
                text="""Any chat workflow can be saved for reuse."""
            )
            self.toggle_chat_settings(True)
            chat_save_button = chat_workflow_settings.workflow_buttons.inner_widget.btn_save_as
            click_widget(chat_save_button)  # BLOCKING
            self.sleep(1)
            self.text_to_speech(blocking=True,
                text="""Click this save icon, we can see there's multiple options. We can save as an Agent, Block, Tool or Task. All of these fundamentally use the same workflow engine. But each are used by the system slightly differently."""
            )
            self.text_to_speech(blocking=True,
                text="""Agents are Workflows intended for the user to interact with. This can be anything from a single LLM to a multi-member workflow."""
            )
            self.text_to_speech(blocking=True,
                text="""Blocks are workflows that run behind the scenes. They can be used in any workflow, or text field such as an agent's system message. These allow re-usability and consistency across multiple entities."""
            )
            self.text_to_speech(blocking=True,
                text="""Tools are workflows that can be called by a language model to execute particular actions or retrieve specific information. These often interact with external systems or APIs."""
            )
            # press escape
            pyautogui.press('esc')

        if demo_segments['Agents']:
            self.set_segment('Agents')
            # pyautogui.press('esc')
            page_agents = self.goto_page('agents')
            self.text_to_speech(blocking=True,
                text="""Let's go to the Agents page, these are the workflows you interact with. They can be Agent workflows or just a single LLM, or just a snippet of code you want to run."""
            )

            click_tree_item_cell(page_agents.tree, 'Claude Code', 'name')
            self.text_to_speech(blocking=True,
                text="""Selecting an agent will open its settings, this is not tied to any chat, these settings will be the default whenever the agent is added to a workflow."""
            )
            # sleep
            self.sleep(1)
            self.text_to_speech(blocking=True,
                text="""Start a new chat with an agent by double clicking on it."""
            )
            click_tree_item_cell(page_agents.tree, 'Ayva', 'name', double=True)

            self.text_to_speech(blocking=True,
                text="""Let's open the chat settings again, here there's a field to set the system message for the agent."""
            )
            self.toggle_chat_settings(True)
            self.sleep(3)
            page_chat = self.main.main_pages.get('chat')
            chat_wf_settings = page_chat.workflow_settings
            chat_agent_settings = chat_wf_settings.member_config_widget.config_widget
            chat_agent_settings.content.setCurrentIndex(0)
            sys_msg = chat_agent_settings.pages['Messages'].sys_msg_wgt
            click_widget(sys_msg)
            self.text_to_speech(blocking=True,
                text="""You can write custom instructions here to make it behave how you want."""
            )
            self.text_to_speech(blocking=True,
                text="""Here you can see it says "known personality" enclosed in curly braces."""
            )
            self.text_to_speech(blocking=True,
                text="""This is actually the name of a Block we have in our block collection which you can access here."""
            )

        if demo_segments['Blocks']:
            self.set_segment('Blocks')
            self.text_to_speech(blocking=False,
                text="""Go to "known personality", and you can see it contains a block of text, the placeholder from the system message will be substituted with the output of this block."""
            )
            page_blocks = self.goto_page('blocks')
            click_tree_item_cell(page_blocks.tree, 'known-personality', 'name')
            # click_tree_item_cell(page_blocks.tree, 'known-personality', 'name')
            block_page_workflow_settings = page_blocks.config_widget.workflow_settings
            block_settings = block_page_workflow_settings.member_config_widget.config_widget
            click_widget(block_settings.data_wgt)
            self.sleep(3.5)
            click_widget(block_page_workflow_settings.workflow_buttons.inner_widget.btn_add)
            self.text_to_speech(blocking=True,
                text="""Blocks can either be Text, Code, Prompt or even an entire workflow."""
            )

        if demo_segments['Workflows']:
            self.set_segment('Workflows')
            self.text_to_speech(blocking=True,
                text="""Lets go over the mechanics of multi-member workflows, and then we'll touch on how to use them practically."""
            )
            self.text_to_speech(blocking=False,
                text="""Go to the chat page and open the settings."""
            )
            self.goto_page('chat')
            page_chat = self.goto_page('chat')  # dbl click
            self.toggle_chat_settings(True)

            chat_workflow_settings = page_chat.workflow_settings
            chat_buttons = chat_workflow_settings.workflow_buttons
            click_widget(chat_buttons.inner_widget.btn_add)

            self.text_to_speech(blocking=True,
                text="""Click this plus button to add another member. You'll have a few options. For now let's just add a blank agent."""
            )
            self.click_context_menu_item(chat_buttons.inner_widget.btn_add, item_index=1)

            dialog_window = QApplication.activeWindow()
            dialog_tree = dialog_window.tree_widget
            click_tree_item_cell(dialog_tree, 'Empty agent', 0, double=True)
            # click_widget(active_window)
            self.click_workflow_coords(chat_workflow_settings, 230, 60, double=True)
            self.text_to_speech(blocking=True,
                text="""Drop it on the workflow!"""
            )

            members_in_view = chat_workflow_settings.members_in_view
            members = list(members_in_view.values())

            self.text_to_speech(blocking=False,
                text="""An important thing to know is the order of response flows from left to right, so in this workflow, after you send a message, this member will always respond first, followed by this member."""
            )
            self.sleep(4)
            click_widget(members[0])
            self.sleep(2)
            click_widget(members[1])
            self.sleep(2)
            click_widget(members[2])
            self.sleep(2)

            self.text_to_speech(blocking=False,
                text="""Unless, an input is placed from this member to this one, in this case, because the input of this one flows into this, this member responds first."""
            )
            try:
                click_widget(members[2].output_point)
                click_widget(members[1].input_point)
                self.sleep(7)
            except Exception as e:
                print(f'Error clicking members[2].output_point or members[1].input_point: {e}')
                raise e

            click_widget(list(chat_workflow_settings.inputs_in_view.values())[0])
            click_widget(chat_workflow_settings.workflow_buttons.inner_widget.btn_delete)

            delete_dialog = QApplication.activeWindow()
            if delete_dialog:
                # Choose QMessageBox.Yes (delete_dialog is a QMessageBox)
                yes_button = delete_dialog.buttons()[0]  # First button is typically "Yes"
                click_widget(yes_button)

            # click_widget(chat_buttons.inner_widget.btn_member_list)
            # self.text_to_speech(blocking=True,
            #     text="""Click on the members button here to show the list of members, in the order they will respond."""
            # )
            # click_widget(chat_buttons.inner_widget.btn_member_list)

            members_in_view = chat_workflow_settings.members_in_view
            members = list(members_in_view.values())

            hover_widget(members[0])
            self.text_to_speech(blocking=True,
                text="""You should almost always have a user member at the beginning, this represents you. There can be multiple user instances, so you can add your input at any point within a workflow."""
            )

            self.text_to_speech(blocking=True,
                text="""Let's go over the context window of each agent"""
            )

            click_widget(members[1])
            self.text_to_speech(blocking=True,
                text="""If the agent has no predefined inputs, then it can see all other member messages, even members placed AFTER it from previous turns."""
            )
            hover_widget(members[2])
            self.text_to_speech(blocking=False,
                text="""But if an agent has inputs set like this one, then it'll only see messages from the agents flowing into it."""
            )
            click_widget(members[1].output_point)
            click_widget(members[2].input_point)
            self.sleep(4)

            click_widget(list(chat_workflow_settings.inputs_in_view.values())[0])
            self.text_to_speech(blocking=True,
                text="""Clicking on an input will show it's settings, here you can map information between responses, structured outputs and parameters"""
            )

            inputs_json_widget = chat_workflow_settings.member_config_widget.config_widget.widgets[0].widgets[1]
            click_tree_item_cell(inputs_json_widget.tree, 0, 'Target', only_hover=True)
            self.text_to_speech(blocking=True,
                text="""By default, there's one mapping, from the source member's output (in this case an LLM response) to the target member's message input."""
            )
            # click_widget(chat_workflow_settings.member_config_widget)
            self.text_to_speech(blocking=True,
                text="""Message inputs can only be sent to Agents. They allow custom user messages with multi turn functionality."""
            )

        if demo_segments['Workflows 2']:
            self.set_segment('Workflows 2')

            self.text_to_speech(blocking=True,
                text="""Lets add an empty text block."""
            )

            self.toggle_chat_settings(True)
            page_chat = self.main.main_pages.get('chat')
            chat_workflow_settings = page_chat.workflow_settings
            chat_buttons = chat_workflow_settings.workflow_buttons
            btn_add = chat_buttons.inner_widget.btn_add
            click_widget(btn_add)
            self.click_context_menu_item(btn_add, item_index=11)
            self.sleep(1)

            dialog_window = QApplication.activeWindow()
            dialog_tree = dialog_window.tree_widget
            click_tree_item_cell(dialog_tree, 'Empty text block', 0, double=True)

            self.click_workflow_coords(chat_workflow_settings, 330, 110, double=True)
            members = list(chat_workflow_settings.members_in_view.values())

            click_widget(members[2].output_point)
            click_widget(members[3].input_point)
            click_widget(list(chat_workflow_settings.inputs_in_view.values())[1])

            self.text_to_speech(blocking=True,
                text="""Not every member type supports the message attribute, if we add an input to this text block, then we see a dashed line instead. This indicates there is no information transmitted between the members, but before the target member can run, the source member must finish executing."""
            )
            self.text_to_speech(blocking=True,
                text="""These attributes can transmit other data like structured output values and member parameters."""
            )
            self.text_to_speech(blocking=True,
                text="""We'll go over these soon, but first let's make a simple mixture of agents workflow to get a feel for how to use this practically."""
            )
            self.text_to_speech(blocking=True,
                text="""Let's add two agent members, one will be Gpt-4 O and the other Sonnet 3.5. Both of these should only see the user's message, so add a single input from the user to both agents."""
            )
            self.text_to_speech(blocking=True,
                text="""Since they don't depend on each other, they can run concurrently. To do this align them vertically."""
            )
            self.text_to_speech(blocking=True,
                text="""Set their models, and we also need to go into the group tab and set hide bubbles to true, and set the output placeholder to something unique. Remember to do this for both."""
            )
            self.text_to_speech(blocking=True,
                text="""We need another Agent here to use for the final response, place it down and set its model. In the system message, we can use a prompt to combine the outputs of the previous agents, using their output placeholders, enclosed in curly braces."""
            )
            self.text_to_speech(blocking=True,
                text="""Let's try chatting with this workflow. Those asynchronous agents should be working behind the scenes and the final agent should respond with a combined output."""
            )
            self.text_to_speech(blocking=True,
                text="""You can toggle the hidden bubbles by clicking this toggle icon here in the workflow settings."""
            )
            self.text_to_speech(blocking=True,
                text="""Branching chat works for multi member workflows too, giving you a practical way to use and refine your finished workflow."""
            )
            self.text_to_speech(blocking=True,
                text="""Let's save this workflow as an agent, so we can use it later."""
            )
            self.text_to_speech(blocking=True,
                text="""Now you can find it in the agents page, and start a new chat with it."""
            )
            # self.text_to_speech(blocking=True,
            #     text="""Drop it on the workflow!"""
            # )

        if demo_segments['Tools']:
            self.set_segment('Tools')
            self.text_to_speech(blocking=True,
                text="""Let's go over tool-calling. This gives your agents access to external functions and capabilities."""
            )
            self.text_to_speech(blocking=False,
                text="""Head over to the Tools page by clicking here"""
            )
            page_tools = self.goto_page('tools')
            self.sleep(1.5)
            self.text_to_speech(blocking=True,
                text="""The list of tools here can be added to any agent."""
            )
            tool_name = self.first_item_name(page_tools.tree)
            if tool_name:
                click_tree_item_cell(page_tools.tree, tool_name, 0)
            self.text_to_speech(blocking=True,
                text="""By default, a tool is just a code block. But it can be an entire workflow."""
            )
            self.text_to_speech(blocking=True,
                text="""Pages and widgets can also expose their own methods as tools, they're listed here too. This lets agents drive the application itself."""
            )

        if demo_segments['Projects']:
            self.set_segment('Projects')
            self.text_to_speech(blocking=False,
                text="""Let's take a look at the Projects page. Projects let you organize your work into separate workspaces, each with their own files, chats, and block mappings."""
            )
            page_projects = self.goto_page('projects')
            self.sleep(2)

            self.text_to_speech(blocking=False,
                text="""You'll notice there's already an Application project here. This is a special project that points to the actual running source code of Agent Pilot itself."""
            )
            click_tree_item_cell(page_projects.tree, 'Application', 'name')
            self.sleep(2)

            self.text_to_speech(blocking=True,
                text="""When an agent edits the Application project, Agent Pilot hot-reloads every module it changed as soon as the agent finishes its turn. No restart needed. We'll see this in action shortly."""
            )

            self.text_to_speech(blocking=True,
                text="""Let's create a new project to see how it works."""
            )
            self.add_tree_item(page_projects, 'My Demo Project')

            # The config widget is rebuilt for each project type, so re-fetch it
            project_widget = page_projects.config_widget
            project_fields = project_widget.widgets[0]
            hover_widget(project_fields.working_dir_wgt)
            self.text_to_speech(blocking=True,
                text="""At the top you can set the project's working directory using this file picker. The file tree below shows all the files in that directory, and you can preview any file by clicking it."""
            )
            hover_widget(project_fields._PROJECT_TYPE_wgt)
            self.text_to_speech(blocking=True,
                text="""This button sets the project type. A general project, an application, or a website, which adds a live preview tab. Project types are modules, so you can add your own."""
            )

            project_bottom_tabs = project_widget.widgets[2]

            self.text_to_speech(blocking=False,
                text="""Down here we have tabs for Chat, Skills, Blocks, Plans and Block Maps. Let's look at the Chat tab first."""
            )
            project_chats = self.goto_page('Chat', project_bottom_tabs)
            self.sleep(1)
            click_widget(project_chats.tree_buttons.inner_widget.btn_add)
            self.sleep(1)
            hover_widget(project_chats.config_widget.input_widget.message_text)
            self.text_to_speech(blocking=True,
                text="""Each project has its own chats, separate from the main chat. They use your default project agent, Claude Code, which works directly inside the project's directory. The tree even groups chats by the files they edited."""
            )

            self.text_to_speech(blocking=False,
                text="""Skills, Blocks and Plans can also be scoped to a project, so each workspace has its own instructions and reusable content."""
            )
            self.goto_page('Skills', project_bottom_tabs)
            self.sleep(1.5)
            self.goto_page('Plans', project_bottom_tabs)
            self.sleep(2)

            self.text_to_speech(blocking=False,
                text="""Now let's check out Block Maps."""
            )
            self.goto_page('Blocks', project_bottom_tabs)
            block_maps = project_bottom_tabs.block_maps
            self.sleep(1)

            self.text_to_speech(blocking=True,
                text="""Block Maps let you map blocks to file paths within your project. Each row links a block from your collection to a specific file. When you click the Bake button, the content of each block is written to its mapped file on disk. This is a powerful way to keep your project files in sync with your block collection."""
            )
            bake_btn = block_maps.widgets[0].tree_buttons.inner_widget.btn_bake
            hover_widget(bake_btn)
            self.sleep(3)

        if demo_segments['Live Coding']:
            self.set_segment('Live Coding')
            demo_page_name = 'Notes'
            main_pages = self.main.main_pages

            self.text_to_speech(blocking=True,
                text="""Agent Pilot can rewrite itself while it's running. Let's vibe-code a brand new page."""
            )
            self.goto_page('chat')
            self.text_to_speech(blocking=False,
                text="""Hover over the sidebar to reveal this plus button, then click it to add a page."""
            )
            click_widget(main_pages.settings_sidebar.new_page_btn)
            if self.wait_for_modal():
                type_text(demo_page_name)
                pyautogui.press('enter')
            self.sleep(2.5)

            popup = self.main.module_popup
            self.text_to_speech(blocking=True,
                text="""The new page opens with the page editor beside it. This is the same Application project we just saw, with a coding agent that knows which page is currently open."""
            )
            popup_chats = popup.project_widget.widgets[2].pages['Chat']
            click_widget(popup_chats.tree_buttons.inner_widget.btn_add)
            self.sleep(1)

            self.text_to_speech(blocking=False,
                text="""Just describe what you want."""
            )
            self.send_message(
                'Make this a notes page: a title field and a large '
                'multi-line text field for the note.',
                chat_widget=popup_chats.config_widget,
                timeout=600,
            )
            self.dismiss_modals()  # "Restart required" prompt, if any
            self.sleep(2)
            self.text_to_speech(blocking=True,
                text="""As soon as the agent finishes, the page reloads with the new code, while the app keeps running."""
            )
            self.sleep(2)

            # The reload may have rebuilt the popup and the sidebar
            click_widget(self.main.module_popup.btn_close)
            self.sleep(1)

            self.text_to_speech(blocking=False,
                text="""You can open the page editor on any page from this menu, or by right-clicking a page. Right-click also lets you delete a page."""
            )
            hover_widget(self.main.history_menu_btn)
            self.sleep(1.5)
            page_btn = main_pages.settings_sidebar.page_buttons.get(demo_page_name)
            if page_btn:
                self.right_click_widget(page_btn)
                self.sleep(1)
                if self.click_menu_action('Delete', 'Disable') == 'Delete':
                    self.confirm_yes()
            self.sleep(1.5)

        if demo_segments['Tasks']:
            self.set_segment('Tasks')
            self.text_to_speech(blocking=False,
                text="""Next up, tasks. Head to the Tasks page."""
            )
            page_tasks = self.goto_page('tasks')
            self.sleep(1)
            self.text_to_speech(blocking=True,
                text="""At the top is a calendar and a timeline of the selected day. Below is the list of every task, with its status and when it runs."""
            )

            calendar_fields = page_tasks.widgets[0].widgets[1]
            self.text_to_speech(blocking=False,
                text="""Click this plus button to schedule a task on the selected day."""
            )
            click_widget(calendar_fields.add_btn)
            dialog = self.wait_for_modal()
            if dialog:
                type_text('Morning briefing')
                self.text_to_speech(blocking=False,
                    text="""Give it a name, a time, and how often it repeats. Let's make this one daily."""
                )
                click_widget(dialog.recurrence_combo)
                self.sleep(0.5)
                pyautogui.press('down')
                pyautogui.press('enter')
                self.sleep(1)
                ok_button = _run_on_main(
                    lambda: dialog.buttons.button(QDialogButtonBox.Ok)
                )
                click_widget(ok_button)
            self.sleep(1.5)

            scheduled_tasks = page_tasks.widgets[1]
            self.text_to_speech(blocking=True,
                text="""It shows up on the timeline and in the task list. You can drag it along the timeline to move it, or drag its bottom edge to change how long it runs."""
            )
            click_tree_item_cell(scheduled_tasks.tree, 'Morning briefing', 0)
            self.sleep(1)

            self.text_to_speech(blocking=False,
                text="""Describe what the task should do. Every task is a full workflow, by default it uses your default task agent."""
            )
            click_widget(scheduled_tasks.config_widget.description.task_wgt)
            type_text("Summarise today's calendar and the top tech headlines.")
            self.sleep(1)
            hover_widget(scheduled_tasks.config_widget.chat.input_widget.send_button)
            self.text_to_speech(blocking=True,
                text="""When it's due, the scheduler runs it in the background, or click run to start it now. Every run is saved as a chat you can look back on."""
            )

            self.text_to_speech(blocking=False,
                text="""Tasks without a schedule work as a to-do list. Add one with this plus button."""
            )
            self.add_tree_item(scheduled_tasks, 'Book dentist appointment')
            click_tree_item_cell(scheduled_tasks.tree, 'Book dentist appointment', 2, only_hover=True)
            self.text_to_speech(blocking=True,
                text="""Each task has a status: to do, running, review, done or failed. Agents update it as they work using the built-in task tools, so you can simply ask an agent to add, list or tick off your to-dos."""
            )
            click_tree_item_cell(scheduled_tasks.tree, 'Book dentist appointment', 3, only_hover=True)
            self.text_to_speech(blocking=True,
                text="""You can also type a schedule in plain English in the When column, like every weekday at 9 AM, and it's turned into a recurring schedule."""
            )

            self.text_to_speech(blocking=False,
                text="""For bigger, open-ended work there are Goals."""
            )
            page_goals = self.goto_page('goals')
            self.sleep(1)
            self.add_tree_item(page_goals, 'Launch the landing page')
            goal_widget = page_goals.config_widget
            click_widget(goal_widget.fields.description_wgt)
            type_text('Build and deploy a landing page for my project.')
            hover_widget(goal_widget.fields.status_wgt)
            self.text_to_speech(blocking=True,
                text="""A goal has a description, a working directory and a status to track its progress."""
            )
            hover_widget(goal_widget.run_button)
            self.text_to_speech(blocking=True,
                text="""Click Run goal and Claude Code works towards it in the chat below. You can also start a goal from any Claude Code chat by typing slash goal."""
            )

            self.text_to_speech(blocking=False,
                text="""Scheduling is handled by a background daemon, which you can find on the Daemons page."""
            )
            page_daemons = self.goto_page('daemons')
            self.sleep(1)
            click_tree_item_cell(page_daemons.tree, 'tasks', 0)
            self.text_to_speech(blocking=True,
                text="""From here you can start, stop or restart any daemon, including the task scheduler and the telephony webhook."""
            )

        if demo_segments['Telephony']:
            self.set_segment('Telephony')
            self.text_to_speech(blocking=True,
                text="""Agent Pilot can also make and take real phone calls, using a live voice agent."""
            )
            self.text_to_speech(blocking=False,
                text="""Telephony is set up in the settings."""
            )
            page_telephony = self.goto_page('telephony')
            self.sleep(1)
            hover_widget(page_telephony.provider_wgt)
            self.text_to_speech(blocking=True,
                text="""Pick a provider, Telnyx or Twilio, and these buttons set up the account for you."""
            )
            hover_widget(page_telephony.set_up_twilio_wgt)
            self.sleep(1)
            hover_widget(page_telephony.from_number_wgt)
            self.text_to_speech(blocking=True,
                text="""Enter your phone number here."""
            )
            hover_widget(page_telephony.answer_agent_wgt)
            self.text_to_speech(blocking=True,
                text="""Then choose which agent answers incoming calls. Any agent with a live agent member can hold a real-time voice conversation."""
            )
            hover_widget(page_telephony.auto_accept_after_wgt)
            self.text_to_speech(blocking=True,
                text="""When someone calls, a popup lets you answer or reject it, or the agent can pick up automatically after a few seconds."""
            )
            self.text_to_speech(blocking=True,
                text="""A webhook daemon runs in the background and opens a secure tunnel, so there's no server to configure."""
            )

            self.text_to_speech(blocking=False,
                text="""To call someone, head to the Contacts page and add a contact."""
            )
            page_contacts = self.goto_page('contacts')
            self.sleep(1)
            self.add_tree_item(page_contacts, 'Alex')
            contact_settings = page_contacts.config_widget.member_config_widget.config_widget
            click_widget(contact_settings.phone_number_wgt)
            type_text('+447700900123')
            self.sleep(1)

            contact_buttons = page_contacts.tree_buttons.inner_widget
            hover_widget(contact_buttons.btn_call_options)
            self.text_to_speech(blocking=True,
                text="""Call options set which number to call from, and which agent makes the call."""
            )
            hover_widget(contact_buttons.btn_call)
            self.text_to_speech(blocking=True,
                text="""Then hit call. The agent dials out, and the whole conversation is transcribed into a chat you can read back later."""
            )

        time.sleep(2)
        self.main.test_running = False
