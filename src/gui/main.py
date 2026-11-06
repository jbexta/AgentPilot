
import asyncio
import importlib
import inspect
import json
import logging
import os
import shutil
import sys
import time
from pathlib import Path

import PySide6
import qasync
from PySide6.QtWidgets import *
from PySide6.QtCore import QThreadPool
from PySide6.QtGui import QIcon, QKeySequence, QShortcut, Qt
from typing_extensions import override


from utils.sql_upgrade import upgrade_script
from utils.helpers import display_message_box, display_message, get_text, llm_tool, load_language
from utils import process, sql
from utils.filesystem import get_application_path
from utils import console_log
from plugins.workflows.utils.workflows import get_avatar_paths_from_config
from gui.style import get_stylesheet, get_palette, is_native_style
from gui.widgets.config_pages import ConfigPages
from gui.gui_utils.helpers import clear_layout, retranslate, safe_single_shot, set_selected_pages
from gui.gui_utils.custom_menu import CustomMenu
from gui.gui_utils.icon_button import IconButton
from gui.gui_utils.layouts import CVBoxLayout
from gui.gui_utils.frameless_resize_mixin import FramelessResizeMixin
from gui.gui_utils.notifications import NotificationManager

from gui import system

logger = logging.getLogger(__name__)

os.environ["QT_OPENGL"] = "software"

loop = None


class SystemManager:
    def __init__(self):
        self._main_gui = None

        from core.managers.modules import ModuleManager
        self.modules = ModuleManager(system=self)
        # Managers will be populated here
        # self.apis = APIManager
        # self.agents = AgentManager
        # ....
    
    def reload_managers(self):
        self.modules.load()
        custom_managers = self.modules.get_modules_in_folder(
            module_type='Managers',
            fetch_keys=('name', 'class',)
        )
        for name, mgr in custom_managers:
            if name in self.__dict__:
                continue
            if mgr:
                setattr(self, name, mgr(self))

    def load(self):
        self.reload_managers()

        for name, mgr in self.__dict__.items():
            if name.startswith('_') or name == 'modules':
                continue
            logger.info('Loading manager: %s', name)
            mgr.load()

    def load_manager(self, manager_name):
        mgr = getattr(self, manager_name, None)
        if mgr:
            mgr.load()

    def restart(self):
        """Quit the app and relaunch it in a fresh process."""
        from utils.process import restart_app
        restart_app()


class TOSDialog(QDialog):
    def __init__(self):
        super().__init__()

        self.setWindowTitle("Terms of Use")
        self.setWindowIcon(QIcon(':/resources/icon.png'))
        self.setMinimumSize(300, 350)
        self.resize(300, 350)

        self.setWindowFlags(
            Qt.Window
            | Qt.WindowTitleHint
            | Qt.WindowSystemMenuHint
            | Qt.WindowCloseButtonHint
            | Qt.WindowStaysOnTopHint
        )

        layout = QVBoxLayout(self)

        self.tos_label = QTextEdit("""
The material embodied in this software is provided to you "as-is" and without warranty of any kind, express, implied or otherwise, including without limitation, any warranty of fitness for a particular purpose. 
In no event shall Agent Pilot or it's creators be liable to you or anyone else for any direct, special, incidental, indirect or consequential damages of any kind, or any damages whatsoever, including but not limited to, loss of profit, loss of use, savings or revenue, or the claims of third parties, whether or not Agent Pilot creators have been advised of the possibility of such loss, however caused and on any theory of liability, arising out of or in connection with the possession, use or performance of this software.
"""
                                )
        self.tos_label.setReadOnly(True)
        self.tos_label.setFrameStyle(QFrame.NoFrame)

        layout.addWidget(self.tos_label)

        h_layout = QHBoxLayout()
        h_layout.addStretch(1)

        self.decline_button = QPushButton("Decline")
        self.decline_button.setFixedWidth(100)
        self.decline_button.clicked.connect(self.reject)
        h_layout.addWidget(self.decline_button)

        self.agree_button = QPushButton("Agree")
        self.agree_button.setFixedWidth(100)
        self.agree_button.clicked.connect(self.accept)
        h_layout.addWidget(self.agree_button)

        layout.addLayout(h_layout)


class TitleButtonBar(CustomMenu):
    def __init__(self, parent):
        super().__init__(parent=parent)
        self.icon_size = 12
        self.schema = [
            {
                'text': 'Minimize',
                'icon_path': ':/resources/icon-minimize.png',
                'target': self.minimizeApp,
            },
            {
                'text': 'Maximize',
                'icon_path': ':/resources/icon-maximize.png',
                'target': self.maximizeApp,
            },
            {
                'text': 'Close',
                'icon_path': ':/resources/close.png',
                'target': self.closeApp,
            },
        ]
        self.create_toolbar()

    def minimizeApp(self):
        self.window().showMinimized()

    def maximizeApp(self):
        if self.window().isMaximized():
            self.window().showNormal()
        else:
            self.window().showMaximized()

    def closeApp(self):
        self.window().close()


class MainPages(ConfigPages):
    _ap_llm_tool_root = True

    def __init__(self, parent):
        super().__init__(
            parent=parent,
            default_page='chat',
            right_to_left=True,
            bottom_to_top=True,
            button_kwargs=dict(
                button_type='icon',
                icon_size=50
            ),
        )
        self.parent = parent
        self.main = parent
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        from plugins.projects.utils.sync import snapshot_mtimes
        self.loaded_mtimes = snapshot_mtimes()

        self.build_schema()

    @llm_tool(
        description='View the app UI as text, with the tools of each widget',
        params={},
    )
    def view_ui(self, refs):
        return self.get_agent_visualisation(refs)

    @llm_tool(
        description='Quit the app and relaunch it in a fresh process, then '
                    'continue this chat. Only use it when you still have work '
                    'to do after the restart, e.g. testing your changes. '
                    'Otherwise just finish responding: changed modules are '
                    'reloaded, or a restart offered, when you finish.',
    )
    def restart_app(self):
        self.main.save_page_editor()
        process.restart_app()

    @llm_tool(
        description="Read the end of the app's console log (prints, logs and tracebacks)",
        params={'lines': 'Number of lines from the end to return'},
    )
    def read_console(self, lines: int = 200):
        return console_log.tail(lines)

    @llm_tool(
        name='reload_modules',
        description='Reload all modules and rebuild the GUI in place, then '
                    'continue this chat. Only use it when you still have work '
                    'to do after the reload, e.g. testing your changes. '
                    'Otherwise just finish responding: changed modules are '
                    'reloaded when you finish.',
    )
    def reload_modules_and_resume(self):
        asyncio.ensure_future(self.main.reload_and_resume())

    def get_registered_modules(self):
        return {
            inspect.getmodule(obj)
            for controller in system.manager.modules.type_controllers.values()
            for _, obj in controller.get_modules(fetch_keys=('name', 'class'))
        }

    # @llm_tool(description='Reload all modules and rebuild the GUI in place')
    def reload_modules(self):
        from gui.gui_utils.helpers import get_selected_pages
        from plugins.projects.utils.sync import (
            changed_files, is_project_module, reload_stale, snapshot_mtimes,
        )
        # from plugins.projects.utils.sync import get_modified_module_files, sync_file_to_db
        # modified_files = get_modified_module_files()
        # if not modified_files:
        #     return
        # for file_path in modified_files:
        #     sync_file_to_db(file_path)
        from utils import sql
        mtimes = snapshot_mtimes()
        deleted = self.loaded_mtimes.keys() - mtimes.keys()
        for controller in system.manager.modules.type_controllers.values():
            for name, entry in list(controller.items()):
                module = inspect.getmodule(entry[4])
                path = getattr(module, '__file__', None)
                if path and os.path.abspath(path) in deleted:
                    del controller[name]
                    sys.modules.pop(module.__name__)
                    sql.execute("DELETE FROM modules WHERE id = ?", (entry[0],))
        registered_modules = self.get_registered_modules()
        changed = changed_files(self.loaded_mtimes, mtimes)
        reload_stale(filter(is_project_module, registered_modules), changed)
        self.loaded_mtimes = mtimes
        importlib.invalidate_caches()
        system.manager.modules.load()
        selections = get_selected_pages(self)
        self.build_schema()
        if 'settings' in self.pages:
            self.pages['settings'].build_schema()
        set_selected_pages(self, selections)
        page = self.content.currentWidget()
        if page and hasattr(page, 'load'):
            page.load()

        popup = self.main.module_popup
        if popup and popup.isVisible():
            popup_selections = get_selected_pages(popup.project_widget)
            scroll_bar = popup.tasks_tree.config_widget.message_collection.scroll_area.verticalScrollBar()
            from_bottom = scroll_bar.maximum() - scroll_bar.value()
            self.main.module_popup = None
            self.main.open_page_editor()
            set_selected_pages(self.main.module_popup.project_widget, popup_selections)
            self.main.module_popup.tasks_tree.config_widget.restore_scroll_pos = from_bottom
            self.main.module_popup.setGeometry(popup.geometry())
            popup.close()

    @override
    def build_schema(self):
        from utils import sql
        pinned_pages: list = sql.get_scalar(
            "SELECT `value` FROM settings WHERE `field` = 'pinned_pages';",
            load_json=True
        )
        page_definitions = system.manager.modules.get_modules_in_folder(
            module_type='Pages',
            fetch_keys=('id', 'name', 'class',),
        )
        page_definitions = [  # filter out pages that are not main or pinned
            (module_id, module_name, page_class)
            for module_id, module_name, page_class in page_definitions
            if getattr(page_class, 'page_type', 'any') == 'main'
            or (getattr(page_class, 'page_type', 'any') == 'any' and module_name in pinned_pages)
        ]
        preferred_order = ['chat', 'contexts', 'agents', 'blocks', 'tools', 'projects', 'files', 'tasks']
        locked_below = ['settings']
        locked_above = ['chat', 'contexts', 'agents', 'blocks', 'tools', 'projects', 'files', 'tasks']
        order_column = 1
        if preferred_order:
            order_idx = {name: i for i, name in enumerate(preferred_order)}
            page_definitions.sort(key=lambda x: order_idx.get(x[order_column], len(preferred_order)))
        
        # sort so locked_below are at the bottom
        page_definitions.sort(key=lambda x: x[1] in locked_below)

        new_pages = {}
        for page_name in locked_above:
            if page_name in self.pages and page_name in [page[1] for page in page_definitions]:
                new_pages[page_name] = self.pages[page_name]
        for module_id, module_name, page_class in page_definitions:
            try:
                existing_page = self.pages.get(module_name, None)
                if existing_page and type(existing_page) is page_class:
                    new_pages[module_name] = existing_page
                    continue

                page = page_class(parent=self)
                setattr(page, 'module_id', module_id)
                if existing_page and getattr(existing_page, 'user_editing', False):
                    setattr(page, 'user_editing', True)

                if hasattr(page, 'add_breadcrumb_widget') and getattr(page, 'show_breadcrumbs', True):
                    page.add_breadcrumb_widget()

                new_pages[module_name] = page

            except Exception as e:
                from gui.gui_utils.helpers import record_page_load_error
                record_page_load_error(module_name)
                display_message(f"Error loading page '{module_name}': {e}", 'Error', QMessageBox.Warning)

        for page_name in locked_below:
            if page_name in self.pages and page_name in [page[1] for page in page_definitions]:
                new_pages[page_name] = self.pages[page_name]

        self.pages = new_pages

        super().build_schema()

        self.settings_sidebar.setFixedWidth(70)

    def add_page(self):
        dlg_title, dlg_prompt = ('New page name', 'Enter a new name for the new page')
        text, ok = get_text(self, dlg_title, dlg_prompt)
        if not ok:
            return
    
        system.manager.modules.add(name=text, module_type='Pages')
    
        self.build_schema()
        # main.page_settings.build_schema()
        self.settings_sidebar.toggle_page_pin(text, True)
        page_btn = self.settings_sidebar.page_buttons.get(text, None)
        if page_btn:
            page_btn.click()
            self.edit_page(text)


class Main(FramelessResizeMixin, QMainWindow):

    def __init__(self):
        super().__init__()

        self.init_frameless_resize(margin=10)

        self.setWindowTitle('AgentPilot')
        self.setWindowIcon(QIcon(':/resources/icon.png'))

        # self.main = self  # workaround for bubbling up

        self.threadpool = QThreadPool()

        self.central = QWidget()
        self.central.setProperty("class", "central")
        self.setCentralWidget(self.central)
        self.layout = QVBoxLayout(self.central)

        self.setMouseTracking(True)
        self.setAcceptDrops(True)

        self.title_bar = TitleButtonBar(parent=self)
        self.history_menu_btn = QPushButton('⋮', self)
        self.history_menu_btn.setFixedSize(24, 24)
        self.history_menu_btn.setFlat(True)
        self.history_menu_btn.setToolTip('Menu')
        self.history_menu_btn.clicked.connect(self.show_history_menu)
        self.module_popup = None
        system.manager = SystemManager()
        system.manager._main_gui = self

        # Initialize the notification manager
        self.notification_manager = NotificationManager(self)
        self.notification_manager.show()

        auto_trigger = None
        if os.environ.get('AP_RUN_TESTS'):
            from utils.reset import reset_application
            self._switch_to_dummy_db(filename='test_data.db')
            # bootstrap=False: managers aren't loaded yet, and reset just
            # dropped tables that bootstrap_entities would INSERT into.
            # init_app below re-creates the tables and runs bootstrap_app.
            reset_application(force=True, preserve_audio_msgs=True, reset_models_=False, reset_tos=False, bootstrap=False)
            auto_trigger = self.run_tests
        elif os.environ.get('AP_RUN_DEMO'):
            from utils.reset import reset_application
            self._switch_to_dummy_db(filename='demo_data.db')
            reset_application(force=True, preserve_audio_msgs=True, reset_models_=False, reset_tos=False, bootstrap=False)
            auto_trigger = self.run_demo

        self.init_app()

        # from core.actions import base as undo_history
        # undo_history.load()

        # self.undo_shortcut = QShortcut(QKeySequence.StandardKey.Undo, self)
        # self.undo_shortcut.setContext(Qt.ShortcutContext.ApplicationShortcut)
        # self.undo_shortcut.activated.connect(lambda: self.on_undo_shortcut(redo=False))
        # self.redo_shortcut = QShortcut(QKeySequence('Ctrl+Shift+Z'), self)
        # self.redo_shortcut.setContext(Qt.ShortcutContext.ApplicationShortcut)
        # self.redo_shortcut.activated.connect(lambda: self.on_undo_shortcut(redo=True))

        if auto_trigger is not None:
            # init_app() must run and confirm TOS accepted before running test or demo
            safe_single_shot(1500, auto_trigger)

        # Create tray icon (required for notifications)
        self.tray = QSystemTrayIcon()
        self.tray.setIcon(QIcon(':/resources/icon.png'))
        self.tray.show()

        safe_single_shot(2000, system.manager.daemons.start_all_daemons)
        safe_single_shot(0, self.resume_running_chats)

    def running_chats(self):
        """Ids of the running chats and tasks, the runs that can be resumed."""
        from utils import sql
        from plugins.workflows.utils.runs import get_run_manager
        return [
            context_id for context_id in get_run_manager().runs
            if (sql.get_scalar("SELECT kind FROM contexts WHERE id = ?", (context_id,)) or '')
            .startswith(('CHAT', 'TASK:'))
        ]

    def save_running_chats(self):
        from utils import sql
        sql.execute("DELETE FROM settings WHERE field = 'running_chats'")
        sql.execute(
            "INSERT INTO settings (field, value) VALUES ('running_chats', ?)",
            (json.dumps(self.running_chats()),),
        )

    def resume_running_chats(self):
        from utils import sql
        context_ids = sql.get_scalar(
            "SELECT value FROM settings WHERE field = 'running_chats'",
            load_json=True,
        ) or []
        sql.execute("DELETE FROM settings WHERE field = 'running_chats'")
        if not system.manager.config.get('system.resume_chats_on_startup', True):
            return
        for context_id in context_ids:
            asyncio.ensure_future(self.resume_chat(
                context_id, 'The app was restarted. Continue where you left off.',
            ))

    async def reload_and_resume(self):
        """Stop the running chats, reload all modules, then resume the chats
        on the reloaded code."""
        from plugins.workflows.utils.runs import get_run_manager
        runs = get_run_manager()
        context_ids = self.running_chats()
        for context_id in context_ids:
            runs.stop(context_id)
        while any(runs.is_running(context_id) for context_id in context_ids):
            await asyncio.sleep(0.1)
        self.main_pages.reload_modules()
        for context_id in context_ids:
            asyncio.ensure_future(self.resume_chat(
                context_id, 'Modules were reloaded. Continue where you left off.',
            ))

    async def restart_when_idle(self, context_id):
        """Restart once the chat has finished, so it isn't resumed after the
        restart."""
        from plugins.workflows.utils.runs import get_run_manager
        while get_run_manager().is_running(context_id):
            await asyncio.sleep(0.1)
        self.main_pages.restart_app()

    async def resume_chat(self, context_id, message):
        """Continue a chat's run with a message from its first member, as
        `send_message` does."""
        from utils import sql
        from plugins.workflows.members.workflow import Workflow
        from plugins.workflows.utils.runs import get_run_manager
        kind = sql.get_scalar("SELECT kind FROM contexts WHERE id = ?", (context_id,))
        if kind is None:
            return
        workflow = Workflow(main=self, context_id=context_id, kind=kind)
        member_id = next(iter(workflow.members))
        workflow.save_message('system', message, member_id=member_id)
        await get_run_manager().start(workflow, member_id)

    def save_page_editor(self):
        from utils import sql
        from gui.gui_utils.helpers import get_selected_pages
        popup = self.module_popup
        is_open = popup and popup.isVisible()
        geometry = popup.geometry().getRect() if is_open else None
        sql.execute("UPDATE settings SET value = json(?) WHERE field = 'page_editor'", (json.dumps(geometry),))
        pages = get_selected_pages(popup.project_widget) if is_open else {}
        sql.execute("DELETE FROM settings WHERE field = 'page_editor_pages'")
        sql.execute(
            "INSERT INTO settings (field, value) VALUES ('page_editor_pages', ?)",
            (json.dumps(pages),),
        )

    def closeEvent(self, event):
        # from core.actions import base as undo_history
        # undo_history.flush()
        self.save_page_editor()
        super().closeEvent(event)
        # The tray icon is a visible top-level window, so Qt doesn't consider
        # this the last window and won't quit on its own — without this the
        # process keeps running invisibly after the window is closed.
        QApplication.quit()

    async def stop_daemons(self, grace=0.5, timeout=5.0):
        """Stop all daemons and wait for them to release any open files.

        Daemons that hold file handles need to unwind before the process
        exits, otherwise the file is left unclosed and can be corrupted.
        Daemons still running after `grace` seconds (typically asleep between
        polls) are cancelled, so their cleanup runs without waiting out the
        sleep.
        """
        daemons = getattr(system.manager, 'daemons', None)
        if daemons is None or not daemons.running_daemons:
            return

        daemons.stop_all_daemons()

        async def wait(seconds):
            deadline = time.time() + seconds
            while daemons.running_daemons and time.time() < deadline:
                await asyncio.sleep(0.01)

        await wait(grace)
        daemons.cancel_all_daemons()
        await wait(timeout)

        still_running = list(daemons.running_daemons)
        if still_running:
            print(f'Daemons did not stop within {timeout}s: {still_running}')

    # def on_undo_shortcut(self, redo=False):
    #     # Text editing widgets keep their own character-level undo stack, defer to it while focused
    #     # (except our Text field widgets, whose edits are recorded in the app history instead)
    #     focused = QApplication.focusWidget()
    #     # if getattr(focused, '_ap_no_native_undo', False):
    #     #     focused = None
    #     if isinstance(focused, QLineEdit):
    #         if (focused.isRedoAvailable() if redo else focused.isUndoAvailable()):
    #             focused.redo() if redo else focused.undo()
    #             return
    #     elif isinstance(focused, (QPlainTextEdit, QTextEdit)):
    #         doc = focused.document()
    #         if (doc.isRedoAvailable() if redo else doc.isUndoAvailable()):
    #             focused.redo() if redo else focused.undo()
    #             return

    #     # Widgets with their own local undo history (e.g. studios) take precedence while focused
    #     widget = QApplication.focusWidget()
    #     while widget is not None:
    #         local_history = getattr(widget, 'undo_history', None)
    #         if local_history is not None:
    #             local_history.redo() if redo else local_history.undo()
    #             return
    #         widget = widget.parentWidget()

    #     # from core.actions import base as undo_history
    #     # undo_history.redo() if redo else undo_history.undo()

    def init_app(self):
        clear_layout(self.layout)

        self.check_db()
        self.patch_db()

        self.check_tos()

        from utils.reset import ensure_system_folders
        ensure_system_folders()

        system.manager.load()
        load_language(system.manager.config.get('system.language', 'English'))

        # Bootstrap baked content whenever we're running from source (bootstrap
        # needs the source tree to re-derive baked modules), or on a disposable
        # dummy DB (test/demo) — regardless of how the test was launched
        # (AP_RUN_TESTS env var via run_tests.sh, or the in-app Settings → Run
        # Tests button which doesn't set the env var).
        from utils import sql as _sql
        if not getattr(sys, 'frozen', False) or _sql.get_db_path().endswith(('test_data.db', 'demo_data.db')):
            from utils.reset import bootstrap_app
            bootstrap_app()

        get_stylesheet()  # init stylesheet

        self.test_running = False

        always_on_top = system.manager.config.get('system.always_on_top', True)
        current_flags = self.windowFlags()
        new_flags = current_flags
        if always_on_top:
            new_flags |= Qt.WindowStaysOnTopHint
        else:
            new_flags &= ~Qt.WindowStaysOnTopHint
        self.setWindowFlags(new_flags)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setWindowFlags(self.windowFlags() | Qt.FramelessWindowHint)

        self.main_pages = MainPages(self)

        self.layout.addWidget(self.main_pages)

        # self.side_bubbles = self.SideBubbles(self)
        # is_in_ide = 'AP_DEV_MODE' in os.environ
        # dev_mode_state = True if is_in_ide else None
        # self.main_menu.pages['Settings'].pages['System'].widgets[1].toggle_dev_mode(dev_mode_state)

        from utils import sql
        window_size = sql.get_scalar("SELECT value FROM settings WHERE `field` = 'window_size'", load_json=True)
        if not window_size:
            window_size = {}
        self.resize(window_size.get('width', 720), window_size.get('height', 900))

        # self.main_menu.settings_sidebar.btn_new_context.setFocus()
        self.apply_stylesheet()
        self.apply_margin()

        app_config = system.manager.config
        self.main_pages.pages['settings'].load_config(app_config)

        screen_geometry = QApplication.primaryScreen().availableGeometry()
        new_x = screen_geometry.x() + screen_geometry.width() - self.width()
        new_y = screen_geometry.y() + screen_geometry.height() - self.height()
        self.move(new_x, new_y)

        self.notification_manager.update_position()

        self.main_pages.build_schema()
        page_path = sql.get_scalar("SELECT value FROM settings WHERE `field` = 'page_path'", load_json=True)
        if page_path:
            set_selected_pages(self.main_pages, page_path)
        self.main_pages.load()
        retranslate(self, system.manager.config.get('system.language', 'English'))
        safe_single_shot(0, self.restore_page_editor)

    @property  # todo remove
    def page_chat(self):
        return self.main_pages.get('chat')

    def check_tos(self):
        from utils import sql
        is_accepted = sql.get_scalar("SELECT value FROM settings WHERE `field` = 'accepted_tos'")
        if is_accepted == '1':
            return

        dialog = TOSDialog()
        if dialog.exec() == QDialog.Accepted:
            sql.execute("UPDATE settings SET value = '1' WHERE `field` = 'accepted_tos'")
            return
        else:
            sys.exit(0)

    def check_db(self):
        from utils import sql
        # Check if the database is up-to-date
        try:
            upgrade_db = sql.check_database_upgrade()
            if upgrade_db:
                # ask confirmation first
                if QMessageBox.question(None, "Database outdated",
                                        "Do you want to upgrade the database to the newer version?",
                                        QMessageBox.Yes | QMessageBox.No) != QMessageBox.Yes:
                    # exit the app
                    sys.exit(0)

                db_version = upgrade_db
                upgrade_script.upgrade(current_version=db_version)

        except Exception as e:
            display_message_box(icon=QMessageBox.Critical, title="Error", text=str(e), buttons=QMessageBox.Ok)
            sys.exit(0)

    def patch_db(self):
        # claude_tool* roles -> agent_tool*, with normalised payloads
        claude_tool = "role = 'claude_tool' AND json_valid(msg)"
        name = "json_extract(msg, '$.name')"
        file_path = "json_extract(msg, '$.input.file_path')"
        sql.execute(f"""
            UPDATE contexts_messages SET msg = json_set(msg, '$.diff', json_object(
                'path', {file_path},
                'old_text', COALESCE(json_extract(msg, '$.input.old_string'), ''),
                'new_text', COALESCE(json_extract(msg, '$.input.new_string'), '')))
            WHERE {claude_tool} AND {name} = 'Edit'""")
        sql.execute(f"""
            UPDATE contexts_messages SET msg = json_set(msg, '$.diff', json_object(
                'path', {file_path},
                'old_text', '',
                'new_text', COALESCE(json_extract(msg, '$.input.content'), '')))
            WHERE {claude_tool} AND {name} = 'Write'""")
        sql.execute(f"""
            UPDATE contexts_messages SET msg = json_set(msg,
                '$.kind', CASE {name}
                    WHEN 'Edit' THEN 'edit' WHEN 'Write' THEN 'edit'
                    WHEN 'MultiEdit' THEN 'edit' WHEN 'NotebookEdit' THEN 'edit'
                    WHEN 'Read' THEN 'read'
                    WHEN 'Glob' THEN 'search' WHEN 'Grep' THEN 'search'
                    WHEN 'Bash' THEN 'execute'
                    WHEN 'WebFetch' THEN 'fetch' WHEN 'WebSearch' THEN 'fetch'
                    ELSE 'other' END,
                '$.paths', json(CASE
                    WHEN COALESCE({file_path}, json_extract(msg, '$.input.notebook_path')) IS NULL THEN '[]'
                    ELSE json_array(COALESCE({file_path}, json_extract(msg, '$.input.notebook_path'))) END))
            WHERE {claude_tool}""")
        sql.execute("UPDATE contexts_messages SET role = 'agent_tool' WHERE role = 'claude_tool'")
        sql.execute("UPDATE contexts_messages SET role = 'agent_tool_result' WHERE role = 'claude_tool_result'")
        sql.execute("""
            DELETE FROM modules
            WHERE name IN ('claude_tool', 'claude_tool_result')
              AND folder_id IN (SELECT id FROM folders WHERE type = 'modules' AND LOWER(name) = 'bubbles')""")
        sql.execute("""
            DELETE FROM modules
            WHERE name = 'claude_context'
              AND folder_id IN (SELECT id FROM folders WHERE type = 'modules' AND LOWER(name) = 'widgets')""")

        # Skills and plans belong to an agent: kinds '' -> 'Claude',
        # 'PROJECT:9' -> 'PROJECT:9:Claude', and app_skills/skills ->
        # app_skills/Claude/skills
        for table in ('skills', 'plans'):
            sql.execute(f"UPDATE {table} SET kind = 'Claude' WHERE kind = ''")
            sql.execute(f"""
                UPDATE {table} SET kind = kind || ':Claude'
                WHERE kind LIKE 'PROJECT:%' AND kind NOT LIKE 'PROJECT:%:%'""")
        skills_root = Path(get_application_path()) / 'app_skills'
        if (os.path.basename(sql.get_db_path()) == 'data.db' and (skills_root / 'skills').is_dir()
                and not (skills_root / 'Claude' / 'skills').exists()):
            (skills_root / 'Claude').mkdir(exist_ok=True)
            shutil.move(skills_root / 'skills', skills_root / 'Claude' / 'skills')
            if (skills_root / '.claude-plugin').is_dir():
                shutil.move(skills_root / '.claude-plugin', skills_root / 'Claude' / '.claude-plugin')
            manifest = skills_root / 'mirrors.json'
            if manifest.exists():
                mirrors = json.loads(manifest.read_text(encoding='utf-8'))
                manifest.write_text(json.dumps(
                    {k if '/' in k else f'Claude/{k}': v for k, v in mirrors.items()},
                    indent=2), encoding='utf-8')

    # def show_side_bubbles(self):
    #     self.side_bubbles.show()
    #     # move to top left of the main window
    #     self.side_bubbles.move(self.x() - self.side_bubbles.width(), self.y())

    # def hide_side_bubbles(self):
    #     print("hide side bubbles")
    #     self.side_bubbles.hide()

    # class SideBubbles(QWidget):
    #     def __init__(self, main):
    #         super().__init__(parent=None)
    #         self.main = main
    #         self.setWindowFlags(Qt.Popup | Qt.FramelessWindowHint)
    #         self.setAttribute(Qt.WA_TranslucentBackground)
    #         self.setFixedWidth(50)

    #         # allow mouseMoveEvent
    #         self.setMouseTracking(True)

    #         # show 3 circles 50x50 px vertically
    #         self.layout = CVBoxLayout(self)

    #         self.load()

    #     def load(self):
    #         from utils import sql
    #         recent_chats = sql.get_results("""
    #             SELECT config
    #             FROM contexts
    #             WHERE kind = 'CHAT'
    #             ORDER BY id DESC
    #             LIMIT 3
    #         """, return_type='list')

    #         for config in recent_chats:
    #             row_layout = QHBoxLayout()
    #             config = json.loads(config)
    #             member_paths = get_avatar_paths_from_config(config)
    #             # member_pixmap = path_to_pixmap(member_paths, diameter=50)
    #             label = IconButton(  #) QLabel()
    #                 parent=self,
    #                 icon_path=member_paths,  # default icon
    #                 size=50,
    #                 opacity=0.75,
    #                 icon_size_percent=0.5,
    #             )

    #             # # when label is hovered, show a 1px border
    #             # # set transparent background
    #             # label.setStyleSheet("background-color: transparent;")
    #             # # set border radius to 25px
    #             #border-radius: 25px; border: 1px solid transparent; background-color: transparent;
    #             # label.setStyleSheet("""
    #             #     background-color: transparent;
    #             #     border-radius: 25px;
    #             #     border: 1px solid transparent;
    #             #     padding: 5px;
    #             # """)
    #             # set hovered background color to #ffffff20
    #             # label.setProperty("class", "bubble")
    #             # label.setPixmap(member_pixmap)
    #             row_layout.addWidget(label)
    #             self.layout.addLayout(row_layout)

    #     def mouseMoveEvent(self, event):
    #         # If the mouse is more than 50px away from any edge of side bubbles, hide it
    #         left_distance = event.globalX() - self.x()
    #         right_distance = self.x() + self.width() - event.globalX()
    #         top_distance = event.globalY() - self.y()
    #         bottom_distance = self.y() + self.height() - event.globalY()
    #         if left_distance < -50 or right_distance < -50 or \
    #            top_distance < -50 or bottom_distance < -50:
    #             self.hide()

    def position_title_bar(self):
        x = self.width() - self.title_bar.sizeHint().width()
        self.title_bar.move(x, 0)
        self.title_bar.raise_()
        self.history_menu_btn.move(
            self.width() - self.history_menu_btn.width() - 4,
            self.title_bar.sizeHint().height())
        self.history_menu_btn.raise_()

    def show_history_menu(self):
        # from core.actions import base as undo_history
        menu = QMenu(self)
        # undo_label = undo_history.next_undo_label()
        # redo_label = undo_history.next_redo_label()
        # undo_action = menu.addAction(f'Undo ({undo_label})' if undo_label else 'Undo')
        # undo_action.setEnabled(undo_label is not None)
        # undo_action.triggered.connect(undo_history.undo)
        # redo_action = menu.addAction(f'Redo ({redo_label})' if redo_label else 'Redo')
        # redo_action.setEnabled(redo_label is not None)
        # redo_action.triggered.connect(undo_history.redo)
        # menu.addSeparator()
        edit_action = menu.addAction('Edit')
        edit_action.triggered.connect(self.open_page_editor)
        menu.exec(self.history_menu_btn.mapToGlobal(self.history_menu_btn.rect().bottomLeft()))

    def open_page_editor(self):
        from gui.pages.modules import PageEditor
        self.module_popup = self.module_popup or PageEditor(self)
        self.module_popup.load()
        self.module_popup.show()

    def restore_page_editor(self):
        from utils import sql
        geometry = sql.get_scalar("SELECT value FROM settings WHERE `field` = 'page_editor'", load_json=True)
        if geometry:
            self.open_page_editor()
            self.module_popup.setGeometry(*geometry)
            pages = sql.get_scalar("SELECT value FROM settings WHERE `field` = 'page_editor_pages'", load_json=True)
            if pages:
                set_selected_pages(self.module_popup.project_widget, pages)

    def apply_stylesheet(self):
        old_text_color = getattr(self, '_cached_text_color', None)
        new_stylesheet = get_stylesheet()
        if getattr(self, '_cached_stylesheet', None) != new_stylesheet:
            self._cached_stylesheet = new_stylesheet
            QApplication.setOverrideCursor(Qt.WaitCursor)
            app = QApplication.instance()
            app.setPalette(get_palette() if is_native_style() else app.style().standardPalette())
            app.setStyleSheet(new_stylesheet)
            QApplication.restoreOverrideCursor()
        from gui.style import TEXT_COLOR as new_text_color
        self._cached_text_color = new_text_color
        text_color_changed = old_text_color != new_text_color

        if text_color_changed:
            # pixmaps
            for child in self.findChildren(IconButton):
                child.setIconPixmap()
            # trees
            for child in self.findChildren(QTreeWidget):
                if hasattr(child, 'apply_stylesheet'):
                    child.apply_stylesheet()
            # charts
            try:
                from plugins.finance.widgets.chart_widget import ChartWidget
            except ImportError:
                ChartWidget = None
            if ChartWidget is not None:
                options = PySide6.QtCore.Qt.FindChildOptions.FindChildrenRecursively
                for child in self.findChildren(ChartWidget, options=options):
                    child.apply_stylesheet()

        text_color = system.manager.config.get('display.text_color', '#c4c4c4')
        # if self.page_chat:
        #     self.page_chat.top_bar.title_label.setStyleSheet(f"QLineEdit {{ color: {apply_alpha_to_hex(text_color, 0.90)}; background-color: transparent; }}"
        #                                        f"QLineEdit:hover {{ color: {text_color}; }}")

    def apply_margin(self):
        margin = system.manager.config.get('display.window_margin', 6)
        self.layout.setContentsMargins(margin, margin, margin, margin)

    def toggle_always_on_top(self):
        always_on_top = system.manager.config.get('system.always_on_top', True)

        current_flags = self.windowFlags()
        new_flags = current_flags

        # Set or unset the always-on-top flag depending on the setting
        if always_on_top:
            new_flags |= Qt.WindowStaysOnTopHint
        else:
            new_flags &= ~Qt.WindowStaysOnTopHint

        # Hide the window before applying new flags
        self.hide()
        self.setWindowFlags(new_flags)

        # Ensuring window borders and transparency
        self.setAttribute(Qt.WA_TranslucentBackground)  # Maintain transparency
        self.setWindowFlags(self.windowFlags() | Qt.FramelessWindowHint)  # Keep it frameless
        self.show()

    def mouseReleaseEvent(self, event):
        if self._resizing:
            # save window state to database
            window_size = {
                'width': self.width(),
                'height': self.height(),
            }
            from utils import sql
            sql.execute("""
                UPDATE settings
                SET value = json(?)
                WHERE field = 'window_size'""", (json.dumps(window_size),))
        super().mouseReleaseEvent(event)

    def keyPressEvent(self, event):
        if event.key() == Qt.Key_Escape:
            self.test_running = False
        super().keyPressEvent(event)

    def _move_window(self, global_pos):
        super()._move_window(global_pos)
        self.notification_manager.update_position()

    def _switch_to_dummy_db(self, filename='demo_data.db'):
        f"""Copy the active DB to `filename` and point sql at the copy."""
        import shutil
        from utils import sql

        current_db = sql.get_db_path()
        if current_db.endswith(filename):
            return

        self._real_db_path = current_db
        self._dummy_db_path = os.path.join(
            os.path.dirname(current_db), filename
        )
        shutil.copyfile(current_db, self._dummy_db_path)
        sql.set_db_filepath(self._dummy_db_path)

    def run_demo(self):
        """Switch to a disposable demo DB, reinitialize, and run the demo."""
        from utils import sql
        from utils.reset import reset_application

        already_in_demo = sql.get_db_path().endswith('demo_data.db')
        if not already_in_demo:
            self._switch_to_dummy_db(filename='demo_data.db')
            reset_application(force=True, preserve_audio_msgs=True, reset_models_=False, reset_tos=False, bootstrap=False)
            system.manager.daemons.stop_all_daemons()
            self.init_app()

        from gui.demo import DemoRunnable, DemoOverlay
        existing_overlay = getattr(self, '_demo_overlay', None)
        if existing_overlay is not None:
            existing_overlay.close()
        self._demo_overlay = DemoOverlay(
            self, on_stop=self.stop_demo,
            on_finished=self._restore_after_dummy_run,
        )
        self._demo_overlay.show()
        self._demo_runnable = DemoRunnable(self, overlay=self._demo_overlay)
        self.threadpool.start(self._demo_runnable)

    def stop_demo(self):
        """Signal the running demo to cancel."""
        if hasattr(self, '_demo_runnable'):
            self._demo_runnable.cancel()

    def run_tests(self):
        """Switch to a disposable test DB, reinitialize, and run the test suite."""
        from utils import sql
        from utils.reset import reset_application

        already_in_test = sql.get_db_path().endswith('test_data.db')
        if not already_in_test:
            self._switch_to_dummy_db(filename='test_data.db')
            # bootstrap=False: in the in-app "Run Tests" path, reset just
            # dropped tables (skills, etc.); bootstrap_app's INSERTs would
            # fail. init_app re-creates the tables and runs bootstrap_app.
            reset_application(force=True, preserve_audio_msgs=True, reset_models_=False, reset_tos=False, bootstrap=False)
            system.manager.daemons.stop_all_daemons()
            self.init_app()

        self._last_test_failures = 0
        self.test_running = True

        # Optional page filter via `--pages page1 page2 ...`. When given, only
        # those pages are tested and all other module types are skipped.
        only_pages = None
        if '--pages' in sys.argv:
            idx = sys.argv.index('--pages')
            only_pages = [a for a in sys.argv[idx + 1:] if not a.startswith('-')]

        from gui.demo import DemoOverlay, cancel_run
        from gui.tests import TestRunnable
        self._test_overlay = DemoOverlay(
            self, on_stop=cancel_run,
            on_finished=self._restore_after_dummy_run,
            title='AgentPilot Tests',
        )
        self._test_overlay.show()
        self._test_runnable = TestRunnable(
            self, overlay=self._test_overlay, only_pages=only_pages
        )
        self.threadpool.start(self._test_runnable)

    def _restore_after_dummy_run(self):
        """Restore the user's real DB after a test or demo run."""
        from utils import sql

        if os.environ.get('AP_RUN_TESTS'):
            import threading
            exit_code = 0 if getattr(self, '_last_test_failures', 0) == 0 else 1
            # A modal left open by a failed test must not keep the app up.
            for getter in (QApplication.activePopupWidget, QApplication.activeModalWidget):
                while (widget := getter()) is not None:
                    widget.close()
                    if getter() is widget:
                        break
            # Last resort if shutdown hangs (stuck task or thread).
            watchdog = threading.Timer(30, os._exit, args=(exit_code,))
            watchdog.daemon = True
            watchdog.start()
            QApplication.instance().exit(exit_code)
            return

        if os.environ.get('AP_RUN_DEMO'):
            QApplication.instance().exit(0)
            return

        sql.set_db_filepath(self._real_db_path)
        self.test_running = False
        self.init_app()
        safe_single_shot(
            2000, system.manager.daemons.start_all_daemons
        )

        try:
            os.remove(self._dummy_db_path)
        except OSError:
            pass

    def resizeEvent(self, event):
        self.notification_manager.update_position()
        self.position_title_bar()
        super().resizeEvent(event)

    def dragEnterEvent(self, event):
        # Check if the event contains file paths to accept it
        if event.mimeData().hasUrls():
            event.acceptProposedAction()

    def dragMoveEvent(self, event):
        # Check if the event contains file paths to accept it
        if event.mimeData().hasUrls():
            event.acceptProposedAction()

    def dropEvent(self, event):
        # Get the list of URLs from the event
        urls = event.mimeData().urls()

        # Extract local paths from the URLs
        paths = [url.toLocalFile() for url in urls]
        self.page_chat.attachment_bar.add_attachments(paths=paths)
        event.acceptProposedAction()


def launch():
    try:
        import faulthandler
        faulthandler.enable()  # print a native stack trace to stderr on hard crashes
        
        # QApplication.setAttribute(Qt.AA_ShareOpenGLContexts)
        # _webengine_flags = (
        #     '--use-gl=angle --use-angle=swiftshader '
        #     '--enable-unsafe-swiftshader --ignore-gpu-blocklist '
        #     '--enable-webgl '
        #     '--disable-gpu-compositing'
        # )
        # existing_flags = os.environ.get('QTWEBENGINE_CHROMIUM_FLAGS', '')
        # if '--enable-unsafe-swiftshader' not in existing_flags:
        #     os.environ['QTWEBENGINE_CHROMIUM_FLAGS'] = (
        #         f'{existing_flags} {_webengine_flags}'.strip()
        #     )
        # os.environ.setdefault('QSG_RHI_BACKEND', 'opengl')
        
        app = QApplication(sys.argv)
        app.setAttribute(Qt.AA_EnableHighDpiScaling)
        app.setStyle("Fusion")

        # Test runs use their own test_data.db, so they can run alongside the app.
        if not os.environ.get('AP_RUN_TESTS') and process.find_other_instances():
            msg = QMessageBox(
                QMessageBox.Warning,
                'Already running',
                'Another instance of the app is already running.',
                QMessageBox.Ok,
            )
            kill_button = msg.addButton('Kill all', QMessageBox.DestructiveRole)
            msg.setWindowFlags(msg.windowFlags() | Qt.WindowStaysOnTopHint)
            msg.exec()
            if msg.clickedButton() is not kill_button:
                return
            if not process.kill_other_instances():
                display_message_box(
                    icon=QMessageBox.Critical,
                    title='Already running',
                    text='Could not stop the other instance.',
                )
                return

        # from core.actions import base as undo_history
        # app.aboutToQuit.connect(undo_history.flush)

        global loop
        loop = qasync.QEventLoop(app)
        asyncio.set_event_loop(loop)

        window = Main()
        window.show()

        with loop:
            loop.run_forever()
            window.save_running_chats()
            loop.run_until_complete(window.stop_daemons())
            if process._restarting:
                process._spawn()
            # Closing the loop waits on every executor thread (e.g. a
            # `to_thread` call that never returns), so bound the shutdown.
            import threading
            exit_code = 1 if getattr(window, '_last_test_failures', 0) else 0
            watchdog = threading.Timer(10, os._exit, args=(exit_code,))
            watchdog.daemon = True
            watchdog.start()
            pending = asyncio.all_tasks(loop)
            for task in pending:
                task.cancel()
            app.aboutToQuit.disconnect()
            if pending:
                _, stuck = loop.run_until_complete(asyncio.wait(pending, timeout=5))
                for task in stuck:
                    logger.warning('Task ignored shutdown: %r', task)
                if stuck:
                    os._exit(1)

        if os.environ.get('AP_RUN_TESTS'):
            sys.exit(1 if getattr(window, '_last_test_failures', 0) else 0)

    except Exception as e:
        if 'AP_DEV_MODE' in os.environ:
            # When debugging in IDE, re-raise
            raise e
        display_message_box(
            icon=QMessageBox.Critical,
            title='Error',
            text=str(e)
        )
