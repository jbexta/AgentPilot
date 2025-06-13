#
# from .user_bubble import UserBubble
# from .assistant_bubble import AssistantBubble
# from .code_bubble import CodeBubble
# from .tool_bubble import ToolBubble
# from .result_bubble import ResultBubble
# from .image_bubble import ImageBubble
# from .audio_bubble import AudioBubble
import math
# from .base import *


import platform

from PySide6 import QtWidgets
from PySide6.QtWidgets import *
from PySide6.QtCore import QSize, QUrl
from PySide6.QtGui import QTextCursor, QTextOption, Qt, QDesktopServices

from src.gui.util import IconButton, find_main_widget, find_workflow_widget
from src.utils.helpers import display_message, display_message_box
from src.utils import sql

import mistune
from urllib.parse import quote


class MessageBubble(QTextEdit):
    def __init__(self, parent, message, **kwargs):
        super().__init__(parent=parent)
        self.main = parent.parent.main
        self.parent = parent
        self.msg_id: int = None
        self.member_id: str = None
        print(f"MessageBubble: {message.id} {message.member_id} {message.role}")
        self.setContentsMargins(5, 0, 0, 0)

        self.role: str = None
        self.log = None

        self.text = ''
        self.code_blocks = []

        self.setSizePolicy(
            QtWidgets.QSizePolicy.Expanding,
            QtWidgets.QSizePolicy.Expanding
            # QtWidgets.QSizePolicy.Preferred
        )
        self.setWordWrapMode(QTextOption.WordWrap)
        # self.height = 0  # todo clean
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

        from src.system import manager
        role_config = manager.roles.get(self.role, {})
        bg_color = role_config.get('bubble_bg_color', '#252427')
        text_color = role_config.get('bubble_text_color', '#999999')
        self.setStyleSheet(f"background-color: {bg_color}; color: {text_color};")

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

        from src.system import manager
        font = manager.config.get('display.text_font', '')
        size = manager.config.get('display.text_size', 15)

        cursor = self.textCursor()  # Get the current QTextCursor
        cursor_position = cursor.position()  # Save the current cursor position
        anchor_position = cursor.anchor()  # Save the anchor position for selection

        role_config = manager.roles.get(self.role, {})

        bubble_text_color = role_config.get('bubble_text_color', '#d1d1d1')

        if self.enable_markdown and not self.is_edit_mode:
            text = mistune.markdown(display_text if display_text else text)
            code_color = '#919191' if self.role != 'code' else bubble_text_color
            css_background = f"code {{ color: {code_color}; }}"
            css_font = f"body {{ color: {bubble_text_color}; font-family: {font}; font-size: {size}px; white-space: pre-wrap; }}"
            # css_headings = f"h1 { font-size: {size * 1.2}px; margin: 0.5em 0; } h2 { font-size: 1em; margin: 0.4em 0; } h3, h4, h5, h6 { font-size: 1em; margin: 0.3em 0; }"
            # css_headings = "h1, h2, h3, h4, h5, h6 { font-size: 0.5em; margin: 0.3em 0; }"
            css = f"{css_background}\n{css_font}"  # \n{css_headings}"
            html = f"<style>{css}</style><body>{text}</body>"
            self.setHtml(html)
        else:
            self.setPlainText(text)

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
        # Clone the document to avoid altering the state of the real one.
        doc = self.document().clone()
        margins = self.contentsMargins()

        # --- Step 1: Determine the maximum available width for the bubble's text.
        main = find_main_widget(self)
        max_text_width = 400  # A sensible default width.

        if main and hasattr(main, 'main_pages'):
            try:
                # This calculation can be fragile during UI setup.
                # We subtract a bit more to account for layout spacing, scrollbars, etc.
                available_width = main.width() - main.main_pages.settings_sidebar.width() - 60
                if available_width > 0:
                    max_text_width = available_width
            except AttributeError:
                # This can happen if widgets aren't fully initialized.
                pass

        # --- Step 2: Calculate the text's "ideal" unwrapped width.
        # Set text width to -1 to tell the layout to calculate the size without any wrapping.
        doc.setTextWidth(-1)
        ideal_content_width = doc.idealWidth() # + 6

        # --- Step 3: Determine the actual width the bubble should use.
        # It should be as wide as its content, but no wider than the maximum allowed.
        final_text_width = min(ideal_content_width, max_text_width)

        # --- Step 4: Calculate the required height based on that final width.
        # Now we set the final width to allow the layout to calculate wrapping and height.
        doc.setTextWidth(final_text_width)
        text_height = doc.size().height()

        # --- Step 5: Return the total size, including the widget's margins.
        hint_width = final_text_width + margins.left() + margins.right()
        hint_height = text_height + margins.top() + margins.bottom()

        return QSize(hint_width, hint_height)

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

    def contextMenuEvent(self, event):
        # add all default items
        menu = self.createStandardContextMenu()

        menu.addSeparator()
        # delete_action = menu.addAction("Add message after")
        # delete_action.triggered.connect(self.add_msg_after)

        delete_action = menu.addAction("Delete message")
        delete_action.triggered.connect(self.delete_message)

        search_action = menu.addAction("Search the web")
        search_action.triggered.connect(self.search_web)

        over_code_block = self.get_code_block_under_cursor(event.pos())
        if over_code_block:
            menu.addSeparator()

            lang, code, start_line_number, end_line_number = over_code_block
            copy_code_action = menu.addAction("Copy code block")
            copy_code_action.triggered.connect(lambda: QApplication.clipboard().setText(code))

        if self.log:
            menu.addSeparator()
            view_log_action = menu.addAction("View log")
            view_log_action.triggered.connect(self.view_log)

            if 'member_id' in self.log and find_workflow_widget(self):
                view_member_action = menu.addAction("Goto member")
                view_member_action.triggered.connect(self.goto_member)

        #     edit_action = menu.addAction("Edit message")
        #     edit_action.triggered.connect(self.edit_message)

        # show context menu
        menu.exec_(event.globalPos())

    def view_log(self):
        self.parent.view_log(None)

    def goto_member(self):
        full_member_id = self.log.get('member_id')
        workflow_settings = find_workflow_widget(self)
        workflow_settings.goto_member(full_member_id)
        main = find_main_widget(self)
        page_chat = main.main_pages.get('chat')
        if page_chat:
            if not page_chat.workflow_settings.isVisible():
                page_chat.top_bar.agent_name_clicked(None)

    def search_web(self):
        search_text = self.textCursor().selectedText()
        if search_text == '':
            search_text = self.toPlainText()
        formatted_text = quote(search_text)
        QDesktopServices.openUrl(QUrl(f"https://www.google.com/search?q={formatted_text}"))

    def delete_message(self):
        if self.msg_id == -1:
            display_message(self,
                message="Please wait for response to finish before deleting",
                icon=QMessageBox.Warning,
            )
            return

        if getattr(self, 'has_branches', False):
            display_message(self,
                message="This message has branches, deleting is not implemented yet",
                icon=QMessageBox.Warning,
            )
            return

        retval = display_message_box(
            icon=QMessageBox.Question,
            title="Delete message",
            text="Are you sure you want to delete this message?",
            buttons=QMessageBox.Yes | QMessageBox.No
        )
        if retval != QMessageBox.Yes:
            return

        sql.execute("DELETE FROM contexts_messages WHERE id = ?;", (self.msg_id,))
        self.main.main_pages.load_page('chat')

    class BubbleBranchButtons(QWidget):
        def __init__(self, branch_entry, parent):
            super().__init__(parent=parent)
            self.parent = parent
            self.main = parent.main
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
            page_chat = self.main.main_pages.get('chat')
            if self.bubble_id in self.branch_entry:
                return
            else:
                page_chat.workflow.deactivate_all_branches_with_msg(self.bubble_id)
                current_index = self.child_branches.index(self.bubble_id)
                if current_index == 0:
                    self.reload_following_bubbles()
                    return
                next_msg_id = self.child_branches[current_index - 1]
                page_chat.workflow.activate_branch_with_msg(next_msg_id)

            self.reload_following_bubbles()

        def next(self):
            page_chat = self.main.main_pages.get('chat')
            if self.bubble_id in self.branch_entry:
                activate_msg_id = self.child_branches[0]
                page_chat.workflow.activate_branch_with_msg(activate_msg_id)
            else:
                current_index = self.child_branches.index(self.bubble_id)
                if current_index == len(self.child_branches) - 1:
                    return
                page_chat.workflow.deactivate_all_branches_with_msg(self.bubble_id)
                next_msg_id = self.child_branches[current_index + 1]
                page_chat.workflow.activate_branch_with_msg(next_msg_id)

            self.reload_following_bubbles()

        def reload_following_bubbles(self):
            page_chat = self.main.main_pages.get('chat')
            page_chat.message_collection.remove_messages_since(self.bubble_id)
            page_chat.workflow.message_history.load()
            page_chat.message_collection.refresh()

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
