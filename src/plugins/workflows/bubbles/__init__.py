
"""Message Bubbles GUI Module.

This module provides the core message role components for the chat interface.
Message roles define how different types of messages (user, assistant, code, tool,
etc.) are displayed and interact within conversations.

Key Components:
- MessageBubble: Base class for all message role display components
- MessageButton: Interactive button component for message actions
- BubbleBranchButtons: Branch navigation controls for message histories

The roles module enables extensible message display by providing a framework
for creating specialized message roles that can handle different content types
and interaction patterns within the chat interface.
"""  # unchecked

import platform

from PySide6 import QtWidgets
from PySide6.QtWidgets import *
from PySide6.QtCore import QSize, QTimer, QUrl
from PySide6.QtGui import QTextCursor, QTextOption, Qt, QDesktopServices

from gui import system as gui_system
from gui.util import IconButton, find_chat_widget
from utils.helpers import apply_alpha_to_hex
from utils import sql

import mistune


def get_bubble_attr(role, attr, default=None):
    """Look up a styling attribute for a role via its bubble module class.

    Replaces the old ``system.manager.roles.get(role, {}).get(attr, default)``
    pattern. The role name is the bubble module filename — this reads the
    attribute from the class discovered by the modules controller.
    """
    modules = gui_system.manager.modules.get_modules_in_folder(
        'Bubbles', fetch_keys=('name', 'class'),
    )
    cls = next(
        (c for n, c in modules if n.lower() == role.lower()),
        MessageBubble,
    )
    return getattr(cls, attr, default)


class MessageBubble(QTextEdit):
    bubble_bg_color = '#00000000'
    bubble_bg_opacity = 1.0
    bubble_text_color = '#ffd1d1d1'
    bubble_image_size = 25
    show_bubble = True

    def __init__(self, parent, message, **kwargs):
        super().__init__(parent=parent)
        self.parent = parent
        self.msg_id: int = None
        self.member_id: str = None
        print(f"MessageBubble: {message.id} {message.member_id} {message.role}")
        self.setContentsMargins(5, 0, 0, 0)

        # Per-instance style overrides via kwargs (default to class attrs).
        self.bubble_bg_color = kwargs.get('bubble_bg_color', self.bubble_bg_color)
        self.bubble_text_color = kwargs.get('bubble_text_color', self.bubble_text_color)
        self.bubble_bg_opacity = kwargs.get('bubble_bg_opacity', self.bubble_bg_opacity)
        if self.bubble_bg_opacity != 1.0:
            self.bubble_bg_color = apply_alpha_to_hex(
                self.bubble_bg_color, self.bubble_bg_opacity)

        self.role: str = None
        self.log = None

        self.text = ''
        self.code_blocks = []

        self.setSizePolicy(
            QtWidgets.QSizePolicy.Expanding,
            QtWidgets.QSizePolicy.Preferred
        )
        self.setWordWrapMode(QTextOption.WordWrap)
        self.setContextMenuPolicy(Qt.NoContextMenu)
        self.collapsed = False

        self.enable_markdown: bool = True

        self.readonly = kwargs.get('readonly', True)
        self.is_edit_mode = False

        self.textChanged.connect(self.on_text_edited)

        self.installEventFilter(self)

        self.workflow = self.parent.parent.workflow
        self.branch_entry = {}
        self.has_branches = False

        self.autorun_button = kwargs.get('autorun_button', None)
        self.autorun_secs = kwargs.get('autorun_secs', 5)

        # self.context_menu = self.BubbleContextMenu(parent=self)
        # ignore context menu, let message container handle it
        # self.createStandardContextMenu = lambda: None
        # self.contextMenuEvent = lambda event: None

        self.set_message(message)

    def set_message(self, message):
        self.msg_id = message.id
        self.member_id = message.member_id

        self.role = message.role
        self.log = message.log
        self.text = ''
        self.code_blocks = []

        self.enable_markdown = self.parent.member_config.get('chat.display_markdown', True)
        if self.readonly:  # role not in ('user', 'code'):
            self.setReadOnly(True)

        branches = self.workflow.message_history.branches
        self.branch_entry = {k: v for k, v in branches.items() if self.msg_id == k or self.msg_id in v}
        self.has_branches = len(self.branch_entry) > 0

        if self.has_branches:
            self.branch_buttons = self.BubbleBranchButtons(self.branch_entry, parent=self)
            self.branch_buttons.hide()

        # role_config = system.manager.roles.get(self.role, {})
        # bg_color = role_config.get('bubble_bg_color', '#252427')
        # text_color = role_config.get('bubble_text_color', '#999999')
        self.setStyleSheet(
            f"background-color: {self.bubble_bg_color}; "
            f"color: {self.bubble_text_color};"
        )

    def extract_code_blocks(self, text):
        """Extracts code blocks, their first and last line number, and their language from a block of text"""
        import re

        # Regular expression to match code blocks, with or without language
        code_block_re = re.compile(r'```(?P<lang>\w+)?\n?(?P<code>.*?)```', re.DOTALL)

        # Find all code blocks in the text
        matches = list(code_block_re.finditer(text))

        # Initialize an empty list to hold the results
        code_blocks_with_line_numbers = []

        for match in matches:
            start_pos = match.start()  # Starting position of the code block
            end_pos = match.end()  # Ending position of the code block
            lang = match.group('lang')  # Language of the code block
            code = match.group('code')  # Code block content

            # Calculate the line number of the start and end of the code block
            start_line_number = text[:start_pos].count('\n') + 1
            end_line_number = text[:end_pos].count('\n')

            # Append the (language, code, start line number, end line number) tuple to the result list
            code_blocks_with_line_numbers.append((lang if lang else None, code, start_line_number, end_line_number))

        return code_blocks_with_line_numbers

    def on_text_edited(self):
        self.updateGeometry()
        self.parent.check_and_toggle_buttons()
        # self.parent.check_and_toggle_collapse_button()

    def get_code_block_under_cursor(self, cursor_pos):
        if not self.code_blocks:
            return None
        cursor = self.cursorForPosition(cursor_pos)
        line_number = cursor.blockNumber() + 1
        for lang, code, start_line_number, end_line_number in self.code_blocks:
            if start_line_number <= line_number < end_line_number:
                return lang, code, start_line_number, end_line_number
            line_number += 2
        return None

    def enterEvent(self, event):
        super().enterEvent(event)
        if self.has_branches:
            self.branch_buttons.reposition()
            self.branch_buttons.show()

    def leaveEvent(self, event):
        super().leaveEvent(event)
        if self.has_branches:
            self.branch_buttons.hide()

    def focusOutEvent(self, event):
        self.toggle_edit_mode(False)
        super().focusOutEvent(event)

    # BLOCK SCROLL WHEN COLLAPSED
    def wheelEvent(self, event):
        if self.collapsed:
            event.ignore()
            return
        super().wheelEvent(event)

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            # collapse_button = getattr(self.parent, 'collapse_button')
            if self.collapsed:
                self.parent.toggle_collapse()
                # collapse_button.click()

            can_edit = not self.isReadOnly()
            if can_edit:
                self.toggle_edit_mode(True)

            cursor = self.cursorForPosition(event.pos())
            if cursor.charFormat().isAnchor():
                link = cursor.charFormat().anchorHref()
                QDesktopServices.openUrl(QUrl(link))
                return

        super().mousePressEvent(event)

    def toggle_edit_mode(self, state):
        if self.is_edit_mode == state:
            return
        should_reset_text = self.is_edit_mode != state
        self.is_edit_mode = state
        if not self.is_edit_mode:  # Save the text
            self.text = self.toPlainText()
        if should_reset_text:
            self.setMarkdownText(self.text)
        if self.collapsed:
            self.parent.toggle_collapse()

    def setMarkdownText(self, text, display_text=None):
        self.text = text
        cursor = self.textCursor()

        start = cursor.selectionStart()
        end = cursor.selectionEnd()

        font = gui_system.manager.config.get('display.text_font', '')
        size = gui_system.manager.config.get('display.text_size', 15)

        cursor = self.textCursor()  # Get the current QTextCursor
        cursor_position = cursor.position()  # Save the current cursor position
        anchor_position = cursor.anchor()  # Save the anchor position for selection

        # role_config = system.manager.roles.get(self.role, {})
        # bubble_text_color = role_config.get('bubble_text_color', '#d1d1d1')
        bubble_text_color = self.bubble_text_color
        link_color = gui_system.manager.config.get('display.link_color', '#438BB9')
        hover_link_color = apply_alpha_to_hex(link_color, 0.7)

        if self.enable_markdown and not self.is_edit_mode:
            text = mistune.markdown(display_text if display_text else text)
            code_color = '#919191' if self.role != 'code' else bubble_text_color
            css_background = f"code {{ color: {code_color}; }}"
            css_font = f"body {{ color: {bubble_text_color}; font-family: {font}; font-size: {size}px; white-space: pre-wrap; }}"
            css_links = f"""
            a {{
                color: {link_color};
                text-decoration: underline;
            }}
            a:hover {{
                color: {hover_link_color};
                text-decoration: underline;
            }}
            """
            # css_headings = f"h1 { font-size: {size * 1.2}px; margin: 0.5em 0; } h2 { font-size: 1em; margin: 0.4em 0; } h3, h4, h5, h6 { font-size: 1em; margin: 0.3em 0; }"
            # css_headings = "h1, h2, h3, h4, h5, h6 { font-size: 0.5em; margin: 0.3em 0; }"
            css = f"{css_background}\n{css_font}\n{css_links}"  # \n{css_headings}"
            html = f"<style>{css}</style><body>{text}</body>"
            self.setHtml(html)
        else:
            from PySide6.QtGui import QFont, QTextDocument
            # Create new document to fully clear HTML formatting
            doc = QTextDocument()
            doc.setPlainText(text)
            font_obj = QFont(font, size - 1)
            doc.setDefaultFont(font_obj)
            self.setDocument(doc)
            # Restore colors through stylesheet
            # bg_color = role_config.get('bubble_bg_color', '#252427')
            self.setStyleSheet(
                f"background-color: {self.bubble_bg_color}; "
                f"color: {bubble_text_color};"
            )

        # Restore the cursor position and selection
        new_cursor = QTextCursor(self.document())  # New cursor from the updated document
        new_cursor.setPosition(anchor_position)  # Set the start of the selection
        new_cursor.setPosition(cursor_position, QTextCursor.KeepAnchor)  # Set the end of the selection
        self.setTextCursor(new_cursor)  # Apply the new cursor with the restored position and selection

        # cursor.setPosition(start, cursor.MoveAnchor)
        # cursor.setPosition(end, cursor.KeepAnchor)
        # self.setTextCursor(cursor)
        self.code_blocks = self.extract_code_blocks(text)
        # self.update_size()

    # def calculate_button_position(self):
    #     button_width = 32
    #     button_height = 32
    #     button_x = self.width() - button_width
    #     button_y = self.height() - button_height
    #     return QRect(button_x, button_y, button_width, button_height)

    def append_text(self, text):
        # cursor = self.textCursor()
        #
        # start = cursor.selectionStart()
        # end = cursor.selectionEnd()

        self.text += text
        # self.original_text = self.text
        self.setMarkdownText(self.text)
        # self.update_size()
        #
        # cursor.setPosition(start, cursor.MoveAnchor)
        # cursor.setPosition(end, cursor.KeepAnchor)
        #
        # self.setTextCursor(cursor)
        # self.code_blocks = self.extract_code_blocks(text)

    # def sizeHint(self) -> QSize:
    #     # Get the document and its layout
    #     doc = self.document()
    #     layout = doc.documentLayout()
    #
    #     if not layout:
    #         return super().sizeHint()  # Fallback if no layout
    #
    #     # Determine the width to use for height calculation.
    #     # Option 1: Use current width if available and reasonable.
    #     current_width = self.viewport().width()  # viewport().width() is for the content area
    #
    #     # Option 2: If you know the approximate width from the parent layout (MessageContainer)
    #     # This can be complex to get accurately before the layout is fully resolved.
    #     # For now, let's assume current_width is a decent estimate or will be set by the layout.
    #
    #     # If current_width is 0 or very small (e.g., before first layout pass),
    #     # sizeHint might be inaccurate. However, heightForWidth should correct this later.
    #     # For sizeHint itself, we want to provide the best possible estimate.
    #
    #     # Let's ensure the document's textWidth is set for accurate height calculation
    #     # This helps the documentLayout().documentSize() be correct.
    #     if current_width > 0:
    #         doc.setTextWidth(current_width)
    #     else:
    #         # If no width, use a reasonable default or calculate based on parent.
    #         # For simplicity here, we might fall back or use a default.
    #         # Fallback to a large text width to get minimum lines, or a typical chat bubble width.
    #         # This part is tricky because sizeHint itself influences the width.
    #         # Let's assume the Expanding width policy will handle the actual width,
    #         # and heightForWidth is more critical.
    #         # For sizeHint's height, we rely on the document's current textWidth setting.
    #         # If it's -1 (default for unset), height will be for unwrapped text.
    #         pass  # Let current doc.textWidth() be used by documentSize()
    #
    #     doc_size = layout.documentSize()
    #     height = int(doc_size.height()) + self.contentsMargins().top() + self.contentsMargins().bottom()
    #
    #     # For width in sizeHint:
    #     # With Expanding horizontal policy, the hint width is less critical but shouldn't be 0.
    #     # It can be idealWidth or a sensible minimum.
    #     width = int(doc_size.width()) + self.contentsMargins().left() + self.contentsMargins().right()
    #
    #     # Ensure a minimum reasonable size if content is very small or calculation is off
    #     min_height = 20  # Or compute based on font size for one line
    #     height = max(height, min_height)
    #
    #     return QSize(width, height)
    # def sizeHint(self):
    #     doc = self.document().clone()
    #     main = find_main_widget(self)
    #     if not hasattr(main, 'page_chat'):
    #         return QSize(0, 0)
    #     page_chat = main.page_chat
    #     sidebar = main.main_menu.settings_sidebar
    #     doc.setTextWidth(page_chat.width() - sidebar.width())
    #     lr = self.contentsMargins().left() + self.contentsMargins().right() + 6
    #     doc_width = doc.idealWidth() + lr
    #     doc_height = doc.size().height() # + self.contentsMargins().top() + self.contentsMargins().bottom()
    #     return QSize(doc_width, doc_height)
    # In src.gui.bubble.__init__.py, inside the MessageBubble class

    # import math  # Make sure to import math at the top of the file

    # ... inside the MessageBubble class ...


    def sizeHint(self):
        import math
        # Clone the document to avoid altering the state of the real one.
        doc = self.document().clone()
        margins = self.contentsMargins()

        # Chrome that eats into the viewport width: frame on both sides, the
        # QTextEdit's internal document margin, and a small safety buffer so
        # sub-pixel rounding in idealWidth() doesn't cause the last glyph to wrap.
        frame = self.frameWidth() * 2
        doc_margin = int(doc.documentMargin() * 2)
        chrome = frame + doc_margin + 2

        # --- Step 1: Determine the maximum available width for the bubble's text.
        chat_widget = find_chat_widget(self)
        # main = find_main_widget(self)
        max_text_width = 400  # A sensible default width.

        # Horizontal overhead next to the bubble inside its MessageContainer:
        # avatar column (~25 when shown), action-button column (~64 for two
        # buttons + spacing), branch-indicator strip, and layout padding. We
        # subtract a flat estimate so the resulting hint_width — which adds
        # margins and chrome back on — still fits inside chat_widget.width()
        # without triggering a horizontal scrollbar.
        other_columns = 110

        if chat_widget:  #  and hasattr(main, 'main_pages'):
            try:
                # This calculation can be fragile during UI setup.
                # We subtract a bit more to account for layout spacing, scrollbars, etc.
                available_width = (
                    chat_widget.width()
                    - chrome
                    - margins.left()
                    - margins.right()
                    - other_columns
                )  # - main.main_pages.settings_sidebar.width() - 60
                if available_width > 0:
                    max_text_width = available_width
            except AttributeError:
                # This can happen if widgets aren't fully initialized.
                pass

        # --- Step 2: Calculate the text's "ideal" unwrapped width.
        # Set text width to -1 to tell the layout to calculate the size without any wrapping.
        doc.setTextWidth(-1)
        ideal_content_width = math.ceil(doc.idealWidth()) # + 6

        # --- Step 3: Determine the actual width the bubble should use.
        # It should be as wide as its content, but no wider than the maximum allowed.
        final_text_width = min(ideal_content_width, max_text_width)

        # --- Step 4: Calculate the required height based on that final width.
        # Now we set the final width to allow the layout to calculate wrapping and height.
        doc.setTextWidth(final_text_width)
        text_height = doc.size().height()

        # --- Step 5: Return the total size, including the widget's margins and chrome.
        hint_width = final_text_width + margins.left() + margins.right() + chrome
        hint_height = text_height + margins.top() + margins.bottom() + frame

        return QSize(hint_width, hint_height)

    def minimumSizeHint(self):
        # QTextEdit's default minimumSizeHint inherits from QAbstractScrollArea
        # and is several lines tall, which leaves a fat empty bubble for short
        # messages. Defer to sizeHint so the bubble can shrink to its content.
        return self.sizeHint()

    # # def sizeHint(self):
    # #     doc = self.document().clone()
    # #     main = find_main_widget(self)
    # #     page_chat_width = main.width() - main.main_pages.settings_sidebar.width()  # workaround
    # #     max_text_width = page_chat_width - 30  # Leave some space for margins and buttons
    # #     # lr = self.contentsMargins().left() + self.contentsMargins().right() + 9
    # #     text_width = min(doc.idealWidth(), max_text_width)
    # #     doc.setTextWidth(text_width)
    # #     # doc_width = min(doc.idealWidth() + lr, page_chat_width - 30)  # Ensure it doesn't exceed the page width
    # #     # doc_height = doc.size().height() - self.contentsMargins().top() - self.contentsMargins().bottom()
    # #
    # #     # print(f'doc_height: {doc_height}')
    # #     return QSize(text_width, doc.size().height())
    # #
    # #     # doc = self.document().clone()
    # #     # main = find_main_widget(self)
    # #     # page_chat_width = main.width() - main.main_pages.settings_sidebar.width()  # workaround
    # #     # doc.setTextWidth(page_chat_width - 30)
    # #     # lr = self.contentsMargins().left() + self.contentsMargins().right() + 9
    # #     # doc_width = max(doc.idealWidth() - lr, 10)
    # #     # doc_height = doc.size().height() - self.contentsMargins().top() - self.contentsMargins().bottom()
    # #     #
    # #     # print(f'doc_height: {doc_height}')
    # #     # return QSize(doc_width, doc_height)
    # # # #
    # # # # def minimumSizeHint(self):
    # # # #     return QSize(0, self.sizeHint().height())


    # def contextMenuEvent(self, event):
    #     # add all default items
    #     menu = self.createStandardContextMenu()

    #     menu.addSeparator()
    #     # delete_action = menu.addAction("Add message after")
    #     # delete_action.triggered.connect(self.add_msg_after)

    #     delete_action = menu.addAction("Delete message")
    #     delete_action.triggered.connect(self.delete_message)

    #     search_action = menu.addAction("Search the web")
    #     search_action.triggered.connect(self.search_web)

    #     over_code_block = self.get_code_block_under_cursor(event.pos())
    #     if over_code_block:
    #         menu.addSeparator()

    #         lang, code, start_line_number, end_line_number = over_code_block
    #         copy_code_action = menu.addAction("Copy code block")
    #         copy_code_action.triggered.connect(lambda: QApplication.clipboard().setText(code))

    #     if self.log:
    #         menu.addSeparator()
    #         view_log_action = menu.addAction("View log")
    #         view_log_action.triggered.connect(self.view_log)

    #         if 'member_id' in self.log and find_workflow_widget(self):
    #             view_member_action = menu.addAction("Goto member")
    #             view_member_action.triggered.connect(self.goto_member)

    #     #     edit_action = menu.addAction("Edit message")
    #     #     edit_action.triggered.connect(self.edit_message)

    #     # show context menu
    #     menu.exec_(event.globalPos())

    class BubbleBranchButtons(QWidget):
        def __init__(self, branch_entry, parent):
            super().__init__(parent=parent)
            self.parent = parent

            message_bubble = self.parent
            self.bubble_id = message_bubble.msg_id

            self.btn_back = QPushButton("🠈" if not platform.system() == 'Darwin' else "<", self)
            self.btn_next = QPushButton("🠊" if not platform.system() == 'Darwin' else ">", self)
            self.btn_back.setFixedSize(30, 12)
            self.btn_next.setFixedSize(30, 12)
            self.btn_next.setProperty("class", "branch-buttons")
            self.btn_back.setProperty("class", "branch-buttons")

            self.reposition()

            self.branch_entry = branch_entry
            branch_root_msg_id = next(iter(branch_entry))
            self.child_branches = branch_entry[branch_root_msg_id]

            if self.parent.msg_id == branch_root_msg_id:
                self.btn_back.hide()
                self.btn_back.setEnabled(False)
            else:
                indx = branch_entry[branch_root_msg_id].index(self.parent.msg_id)
                if indx == len(branch_entry[branch_root_msg_id]) - 1:
                    self.btn_next.hide()
                    self.btn_next.setEnabled(False)

            self.btn_back.clicked.connect(self.back)
            self.btn_next.clicked.connect(self.next)

        def reposition(self):
            bubble_width = self.parent.size().width()

            available_width = bubble_width - 8
            half_av_width = available_width / 2

            self.btn_back.setFixedWidth(half_av_width)
            self.btn_next.setFixedWidth(half_av_width)

            self.btn_back.move(4, 0)
            self.btn_next.move(half_av_width + 4, 0)

        def back(self):
            chat_widget = find_chat_widget(self)

            if self.bubble_id in self.branch_entry:
                return
            else:
                chat_widget.workflow.deactivate_all_branches_with_msg(self.bubble_id)
                current_index = self.child_branches.index(self.bubble_id)
                if current_index == 0:
                    self.reload_following_bubbles()
                    return
                next_msg_id = self.child_branches[current_index - 1]
                chat_widget.workflow.activate_branch_with_msg(next_msg_id)

            self.reload_following_bubbles()

        def next(self):
            chat_widget = find_chat_widget(self)

            if self.bubble_id in self.branch_entry:
                activate_msg_id = self.child_branches[0]
                chat_widget.workflow.activate_branch_with_msg(activate_msg_id)
            else:
                current_index = self.child_branches.index(self.bubble_id)
                if current_index == len(self.child_branches) - 1:
                    return
                chat_widget.workflow.deactivate_all_branches_with_msg(self.bubble_id)
                next_msg_id = self.child_branches[current_index + 1]
                chat_widget.workflow.activate_branch_with_msg(next_msg_id)

            self.reload_following_bubbles()

        def reload_following_bubbles(self):
            from PySide6.QtCore import QPointF
            from PySide6.QtGui import QCursor, QEnterEvent
            click_pos = QCursor.pos()

            chat_widget = find_chat_widget(self)
            chat_widget.message_collection.remove_messages_since(self.bubble_id)
            chat_widget.workflow.message_history.load()
            chat_widget.message_collection.refresh()

            # The rebuild destroyed this bubble and recreated it under the
            # cursor — Qt won't send an enterEvent because the pointer never
            # moved. Deferring one event-loop tick lets Qt finish the pending
            # layout pass on the new bubbles; after that, walk the freshly
            # laid-out chat_bubbles, find the MessageBubble containing the
            # click position, and synthesize an enter on it so its hover
            # handler shows the branch buttons.
            def _refire_enter():
                for cont in chat_widget.message_collection.chat_bubbles:
                    bubble = cont.bubble
                    if not isinstance(bubble, MessageBubble):
                        continue
                    local = bubble.mapFromGlobal(click_pos)
                    if bubble.rect().contains(local):
                        QApplication.sendEvent(
                            bubble,
                            QEnterEvent(
                                QPointF(local),
                                QPointF(local),
                                QPointF(click_pos),
                            ),
                        )
                        return
            QTimer.singleShot(0, _refire_enter)

        def update_buttons(self):
            pass


class MessageButton(IconButton):
    def __init__(self, parent, **kwargs):
        super().__init__(parent=parent, **kwargs)
        self.msg_container = parent
        self.setFixedSize(32, 24)
        self.hide()
        if hasattr(self, 'on_clicked'):
            self.pressed.connect(self.on_clicked)  # CANT USE CLICKED
