
import json
from urllib.parse import quote

from PySide6 import QtWidgets
from PySide6.QtWidgets import *
from PySide6.QtCore import QSize, QTimer, QMargins, QRect, QUrl
from PySide6.QtGui import QPixmap, QIcon, QTextCursor, QTextOption, Qt, QDesktopServices

from src.plugins.openinterpreter.src import interpreter
from src.utils.helpers import path_to_pixmap, display_messagebox, get_avatar_paths_from_config, \
    get_member_name_from_config, apply_alpha_to_hex, split_lang_and_code
from src.gui.widgets import colorize_pixmap, IconButton
from src.utils import sql

import mistune

from src.gui.config import CHBoxLayout, CVBoxLayout


class MessageContainer(QWidget):
    # Container widget for the profile picture and bubble
    def __init__(self, parent, message):
        super().__init__(parent=parent)
        self.parent = parent
        self.setProperty("class", "message-container")

        self.member_id = message.member_id
        member = parent.workflow.members.get(self.member_id, None)
        self.member_config = getattr(member, 'config') if member else {}

        self.layout = CHBoxLayout(self)  # Avatar / bubble_v_layout / button_v_layout
        self.bubble = self.create_bubble(message)

        config = self.parent.main.system.config.dict

        context_is_multi_member = self.parent.workflow.count_members() > 1
        show_avatar_when = config.get('display.show_bubble_avatar', 'In Group')
        show_name_when = config.get('display.show_bubble_name', 'In Group')
        show_avatar = (show_avatar_when == 'In Group' and context_is_multi_member) or show_avatar_when == 'Always'
        show_name = (show_name_when == 'In Group' and context_is_multi_member) or show_name_when == 'Always'

        if show_avatar:
            agent_avatar_path = get_avatar_paths_from_config(member.config)
            diameter = parent.workflow.main.system.roles.to_dict().get(message.role, {}).get(
                'display.bubble_image_size', 20)
            diameter = int(diameter) if diameter else 0
            circular_pixmap = path_to_pixmap(agent_avatar_path, diameter=diameter)
            if not self.member_config:
                circular_pixmap = colorize_pixmap(circular_pixmap)

            self.profile_pic_label = QLabel(self)
            self.profile_pic_label.setPixmap(circular_pixmap)
            self.profile_pic_label.setFixedSize(30, 30)
            self.profile_pic_label.mousePressEvent = self.view_log

            image_container = QWidget(self)
            image_container_layout = CVBoxLayout(image_container)
            image_container_layout.addWidget(self.profile_pic_label)
            image_container_layout.addStretch(1)

            self.layout.addSpacing(6)
            self.layout.addWidget(image_container)

        bubble_v_layout = CVBoxLayout()  # Name, bubble
        bubble_v_layout.setContentsMargins(0, 5, 0, 0)
        bubble_v_layout.setSpacing(5)

        bubble_h_layout = CHBoxLayout()

        if self.member_config and show_name:
            member_type = self.member_config.get('_TYPE', 'agent')
            if member_type == 'agent':
                member_name = self.member_config.get('info.name', 'Assistant')
            elif member_type == 'user':
                member_name = self.member_config.get('info.name', 'You')
            else:
                raise NotImplementedError()

            self.member_name_label = QLabel(member_name)
            self.member_name_label.setProperty("class", "bubble-name-label")
            bubble_v_layout.addWidget(self.member_name_label)

        bubble_h_layout.addWidget(self.bubble)
        bubble_v_layout.addLayout(bubble_h_layout)
        self.layout.addLayout(bubble_v_layout)

        self.branch_msg_id = message.id

        if getattr(self.bubble, 'has_branches', False):
            branch_layout = CHBoxLayout()
            # branch_layout.setContentsMargins(1, 0, 0, 0)
            branch_layout.setSpacing(1)
            self.branch_msg_id = next(iter(self.bubble.branch_entry.keys()))
            branch_count = len(self.bubble.branch_entry[self.branch_msg_id])
            percent_codes = [int((i + 1) * 100 / (branch_count + 1)) for i in reversed(range(branch_count))]
            # hex_alpha_codes = [f'#{int((code / 100) * 255):02X}' for code in percent_codes]

            for _ in self.bubble.branch_entry[self.branch_msg_id]:
                if not percent_codes:
                    break

                bg_bubble = QWidget()
                bg_bubble.setProperty("class", "bubble-bg")
                user_config = self.parent.main.system.roles.get_role_config('user')
                user_bubble_bg_color = user_config.get('bubble_bg_color')
                user_bubble_bg_color = apply_alpha_to_hex(user_bubble_bg_color, percent_codes.pop(0)/100)

                bg_bubble.setStyleSheet(f"background-color: {user_bubble_bg_color}; border-top-left-radius: 2px; "
                                        "border-bottom-left-radius: 2px; border-top-right-radius: 6px; "
                                        "border-bottom-right-radius: 6px;")
                bg_bubble.setFixedWidth(8)
                branch_layout.addWidget(bg_bubble)

            branch_layout.addStretch(1)
            bubble_h_layout.addLayout(branch_layout)

        button_v_layout = CVBoxLayout()
        button_v_layout.setContentsMargins(0, 0, 0, 3)
        button_v_layout.addStretch()

        is_runnable = message.role in ('code', 'tool')
        if is_runnable:
            self.btn_rerun = self.RerunButton(self)
            self.btn_countdown = self.CountdownButton(self)
            button_v_layout.addWidget(self.btn_rerun)
            button_v_layout.addWidget(self.btn_countdown)
            self.btn_rerun.hide()
            self.btn_countdown.hide()
        elif message.role == 'user':
            self.btn_resend = self.ResendButton(self)
            button_v_layout.addWidget(self.btn_resend)
            self.btn_resend.hide()

        self.layout.addLayout(button_v_layout)
        self.layout.addStretch(1)

        self.log_windows = []

    def create_bubble(self, message):
        page_chat = self.parent

        params = {
            'msg_id': message.id,
            'text': message.content,
            'viewport': page_chat,
            'role': message.role,
            'parent': self,
            'member_id': message.member_id,
        }
        bubble = MessageBubble(**params)

        return bubble

    def view_log(self, _):
        msg_id = self.bubble.msg_id
        log = sql.get_scalar("SELECT log FROM contexts_messages WHERE id = ?;", (msg_id,))
        if not log or log == '':
            return

        json_obj = json.loads(log)
        # Convert JSON data to a pretty string
        pretty_json = json.dumps(json_obj, indent=4)

        # Create new window
        log_window = QMainWindow()
        log_window.setWindowTitle('Message Input')

        # Create QTextEdit widget to show JSON data
        text_edit = QTextEdit()

        # Set JSON data to the text edit
        text_edit.setText(pretty_json)

        # Set QTextEdit as the central widget of the window
        log_window.setCentralWidget(text_edit)

        # Show the new window
        log_window.show()
        self.log_windows.append(log_window)

    def enterEvent(self, event):
        self.check_and_toggle_buttons()
        # self.reset_countdown()
        super().enterEvent(event)

    def leaveEvent(self, event):
        self.check_and_toggle_buttons()
        # self.reset_countdown()
        super().leaveEvent(event)

    def check_and_toggle_buttons(self):
        is_under_mouse = self.underMouse()
        if hasattr(self, 'btn_resend'):
            self.btn_resend.setVisible(is_under_mouse)
        if hasattr(self, 'btn_rerun'):
            self.btn_rerun.setVisible(is_under_mouse)

    def start_new_branch(self):
        branch_msg_id = self.branch_msg_id
        editing_msg_id = self.bubble.msg_id

        # Deactivate all other branches
        self.parent.workflow.deactivate_all_branches_with_msg(editing_msg_id)

        # Delete all messages from editing bubble onwards
        self.parent.delete_messages_since(editing_msg_id)

        # Create a new leaf context
        sql.execute(
            "INSERT INTO contexts (parent_id, branch_msg_id) SELECT context_id, id FROM contexts_messages WHERE id = ?",
            (branch_msg_id,))
        new_leaf_id = sql.get_scalar('SELECT MAX(id) FROM contexts')
        self.parent.workflow.leaf_id = new_leaf_id

    class ResendButton(IconButton):
        def __init__(self, parent):
            super().__init__(parent=parent,
                             icon_path=':/resources/icon-send.png',
                             size=26)
            self.msg_container = parent
            # self.icon_path = icon_path
            self.setProperty("class", "resend")
            self.clicked.connect(self.resend_msg)
            self.setFixedSize(32, 24)

        def resend_msg(self):
            msg_to_send = self.msg_container.bubble.toPlainText()
            if msg_to_send == '':
                return

            self.msg_container.start_new_branch()

            # Finally send the message like normal
            editing_member_id = self.msg_container.member_id
            self.msg_container.parent.send_message(msg_to_send, clear_input=False, as_member_id=editing_member_id)

        # def check_and_toggle(self):
        #     if self.parent.bubble.toPlainText() != self.parent.bubble.original_text:
        #         self.show()
        #     else:
        #         self.hide()

    class RerunButton(IconButton):
        def __init__(self, parent):
            super().__init__(parent=parent,
                             icon_path=':/resources/icon-run-solid.png',
                             size=26,
                             colorize=False)
            self.msg_container = parent
            # self.icon_path = icon_path
            self.setProperty("class", "resend")
            self.clicked.connect(self.rerun_msg)
            self.setFixedSize(32, 24)

        def rerun_msg(self):
            bubble = self.msg_container.bubble
            member_id = self.msg_container.member_id
            if bubble.role == 'code':
                workflow = self.parent.parent.workflow
                lang, code = split_lang_and_code(self.msg_container.bubble.text)
                code = bubble.toPlainText()

                last_msg = self.msg_container.parent.workflow.message_history.messages[-1]
                is_last_msg = last_msg.id == self.msg_container.bubble.msg_id
                if not is_last_msg:
                    self.msg_container.start_new_branch()
                    workflow.save_message(bubble.role, code, member_id)

                oi_res = interpreter.computer.run(lang, code)
                output = next(r for r in oi_res if r['format'] == 'output').get('content', '')
                self.msg_container.parent.send_message(output, role='output', as_member_id=member_id, clear_input=False)

            else:
                pass

        #     branch_msg_id = self.msg_container.branch_msg_id
        #     editing_msg_id = self.msg_container.bubble.msg_id
        #
        #     # Deactivate all other branches
        #     self.msg_container.parent.workflow.deactivate_all_branches_with_msg(editing_msg_id)
        #
        #     msg_to_send = self.msg_container.bubble.toPlainText()
        #
        #     # Delete all messages from editing bubble onwards
        #     self.msg_container.parent.delete_messages_since(editing_msg_id)
        #
        #     # Create a new leaf context
        #     sql.execute(
        #         "INSERT INTO contexts (parent_id, branch_msg_id) SELECT context_id, id FROM contexts_messages WHERE id = ?",
        #         (branch_msg_id,))
        #     new_leaf_id = sql.get_scalar('SELECT MAX(id) FROM contexts')
        #     self.msg_container.parent.workflow.leaf_id = new_leaf_id
        #
        #     # Finally send the message like normal
        #     self.msg_container.parent.send_message(msg_to_send, clear_input=False)
        #
        # # def check_and_toggle(self):
        # #     if self.parent.bubble.toPlainText() != self.parent.bubble.original_text:
        # #         self.show()
        # #     else:
        # #         self.hide()

    class CountdownButton(QPushButton):
        def __init__(self, parent):
            super().__init__(parent=parent)
            self.parent = parent
            self.countdown = 5
            self.countdown_stopped = False
            self.setText(str(parent.member_config.get('actions.code_auto_run_seconds', 5)))  # )
            self.setIcon(QIcon())  # Initially, set an empty icon
            self.setStyleSheet("color: white; background-color: transparent;")
            self.setFixedHeight(22)
            self.setFixedWidth(22)
            self.clicked.connect(self.countdown_stop_btn_clicked)

        def countdown_stop_btn_clicked(self):
            self.countdown_stopped = True
            self.hide()

        def start_timer(self):
            self.countdown = int(self.parent.member_config.get('actions.code_auto_run_seconds', 5))  #
            # self.countdown_button.move(self.btn_rerun.x() - 20, self.btn_rerun.y() + 4)

            self.timer = QTimer(self)
            self.timer.timeout.connect(self.update_countdown)
            self.timer.start(1000)  # Start countdown timer with 1-second interval

        def enterEvent(self, event):
            icon = QIcon(QPixmap(":/resources/close.png"))
            self.setIcon(icon)
            self.setText("")  # Clear the text when displaying the icon
            self.reset_countdown()
            super().enterEvent(event)

        def leaveEvent(self, event):
            self.setIcon(QIcon())  # Clear the icon
            self.setText(str(self.parent().countdown))
            self.reset_countdown()
            super().leaveEvent(event)

        def update_countdown(self):
            if self.countdown > 0:
                self.countdown -= 1
                self.setText(f"{self.countdown}")
            else:
                self.timer.stop()
                self.hide()
                if hasattr(self, 'countdown_stopped'):
                    self.countdown_stopped = True

                self.parent.btn_resend.click()

        def reset_countdown(self):
            countdown_stopped = getattr(self, 'countdown_stopped', True)
            if countdown_stopped: return
            self.timer.stop()
            self.countdown = int(
                self.parent.member_config.get('actions.code_auto_run_seconds', 5))  # 5  # Reset countdown to 5 seconds
            self.setText(f"{self.countdown}")

            if not self.underMouse():
                self.timer.start()  # Restart the timer

        def on_clicked(self):
            self.countdown_stopped = True
            self.hide()


class MessageBubble(QTextEdit):
    def __init__(self, msg_id, text, viewport, role, parent, member_id=None):
        super().__init__(parent=parent)
        self.main = parent.parent.main

        if role not in ('user', 'code'):
            self.setReadOnly(True)
        self.installEventFilter(self)

        self.setSizePolicy(
            QtWidgets.QSizePolicy.Expanding,
            QtWidgets.QSizePolicy.Expanding
        )
        self.parent = parent
        self.msg_id = msg_id
        self.member_id = member_id

        self.agent_config = parent.member_config if parent.member_config else {}  # todo - remove?
        self.role = role
        self.setProperty("class", "bubble")
        self.setProperty("class", role)
        self._viewport = viewport
        self.margin = QMargins(6, 0, 6, 0)
        self.text = ''
        self.original_text = text
        self.enable_markdown = self.agent_config.get('chat.display_markdown', True)
        self.setWordWrapMode(QTextOption.WordWrap)
        self.append_text(text)
        self.textChanged.connect(self.on_text_edited)

        branches = self.parent.parent.workflow.message_history.branches
        self.branch_entry = {k: v for k, v in branches.items() if self.msg_id == k or self.msg_id in v}
        self.has_branches = len(self.branch_entry) > 0

        if self.has_branches:
            self.branch_buttons = self.BubbleBranchButtons(self.branch_entry, parent=self)
            self.branch_buttons.hide()

    def enterEvent(self, event):
        super().enterEvent(event)
        if self.has_branches:
            self.branch_buttons.reposition()
            self.branch_buttons.show()

    def leaveEvent(self, event):
        super().leaveEvent(event)
        if self.has_branches:
            self.branch_buttons.hide()

    def on_text_edited(self):
        self.update_size()

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            cursor = self.cursorForPosition(event.pos())
            if cursor.charFormat().isAnchor():
                link = cursor.charFormat().anchorHref()
                QDesktopServices.openUrl(QUrl(link))
                return
        super().mousePressEvent(event)

    def setMarkdownText(self, text):
        system_config = self.parent.parent.main.system.config.dict
        font = system_config.get('display.text_font', '')
        size = system_config.get('display.text_size', 15)

        cursor = self.textCursor()  # Get the current QTextCursor
        cursor_position = cursor.position()  # Save the current cursor position
        anchor_position = cursor.anchor()  # Save the anchor position for selection

        user_config = self.main.system.roles.get_role_config('user')
        assistant_config = self.main.system.roles.get_role_config('assistant')
        code_config = self.main.system.roles.get_role_config('code')

        # color = role_config.get('bubble_text_color', '#d1d1d1')
        if getattr(self, 'role', '') == 'user':
            color = user_config.get('bubble_text_color', '#d1d1d1')
        else:
            color = assistant_config.get('bubble_text_color', '#b2bbcf')

        code_color = '#919191' if self.role != 'code' else code_config.get('bubble_text_color', '#919191')  # todo dirty
        css_background = f"code {{ color: {code_color}; }}"
        css_font = f"body {{ color: {color}; font-family: {font}; font-size: {size}px; white-space: pre-wrap; }}"
        css = f"{css_background}\n{css_font}"

        if self.enable_markdown:  # and not self.edit_markdown:
            text = mistune.markdown(text)
            text = text.replace('\n</code>', '</code>')
        else:
            text = text.replace('\n', '<br>')
            text = text.replace('\t', '&nbsp;&nbsp;&nbsp;&nbsp;')

        html = f"<style>{css}</style><body>{text}</body>"

        # Set HTML to QTextEdit
        self.setHtml(html)

        # Restore the cursor position and selection
        new_cursor = QTextCursor(self.document())  # New cursor from the updated document
        new_cursor.setPosition(anchor_position)  # Set the start of the selection
        new_cursor.setPosition(cursor_position, QTextCursor.KeepAnchor)  # Set the end of the selection
        self.setTextCursor(new_cursor)  # Apply the new cursor with the restored position and selection

    def calculate_button_position(self):
        button_width = 32
        button_height = 32
        button_x = self.width() - button_width
        button_y = self.height() - button_height
        return QRect(button_x, button_y, button_width, button_height)

    def append_text(self, text):
        cursor = self.textCursor()

        start = cursor.selectionStart()
        end = cursor.selectionEnd()

        self.text += text
        self.original_text = self.text
        self.setMarkdownText(self.text)
        self.update_size()

        cursor.setPosition(start, cursor.MoveAnchor)
        cursor.setPosition(end, cursor.KeepAnchor)

        self.setTextCursor(cursor)

    def sizeHint(self):
        lr = self.margin.left() + self.margin.right()
        tb = self.margin.top() + self.margin.bottom()
        doc = self.document().clone()
        doc.setTextWidth((self._viewport.width() - lr) * 0.8)
        width = min(int(doc.idealWidth()), 520)
        return QSize(width + lr, int(doc.size().height() + tb))

    def update_size(self):
        self.setFixedSize(self.sizeHint())
        # if hasattr(self.parent, 'bg_bubble'):
        #     self.parent.bg_bubble.setFixedSize(8, self.parent.bubble.size().height() - 2)
        self.updateGeometry()
        self.parent.updateGeometry()

    def minimumSizeHint(self):
        return self.sizeHint()

    def contextMenuEvent(self, e):
        # add all default items
        menu = self.createStandardContextMenu()

        menu.addSeparator()
        delete_action = menu.addAction("Delete message")
        delete_action.triggered.connect(self.delete_message)

        search_action = menu.addAction("Search the web")
        search_action.triggered.connect(self.search_web)

        # show context menu
        menu.exec_(e.globalPos())

    def search_web(self):
        msg_content = quote(self.toPlainText())
        QDesktopServices.openUrl(QUrl(f"https://www.google.com/search?q={msg_content}"))

    def delete_message(self):
        if self.msg_id == -1:
            display_messagebox(
                icon=QMessageBox.Warning,
                title="Cannot delete",
                text="Please wait for response to finish before deleting",
                buttons=QMessageBox.Ok
            )
            return

        if getattr(self, 'has_branches', False):
            display_messagebox(
                icon=QMessageBox.Warning,
                title="Cannot delete",
                text="This message has branches, deleting is not implemented yet",
                buttons=QMessageBox.Ok
            )
            return

        retval = display_messagebox(
            icon=QMessageBox.Question,
            title="Delete message",
            text="Are you sure you want to delete this message?",
            buttons=QMessageBox.Yes | QMessageBox.No
        )
        if retval != QMessageBox.Yes:
            return

        sql.execute("DELETE FROM contexts_messages WHERE id = ?;", (self.msg_id,))
        page_chat = self.parent.parent
        page_chat.load()

    class BubbleBranchButtons(QWidget):
        def __init__(self, branch_entry, parent):
            super().__init__(parent=parent)
            self.parent = parent
            message_bubble = self.parent
            message_container = message_bubble.parent
            self.bubble_id = message_bubble.msg_id
            self.page_chat = message_container.parent

            self.btn_back = QPushButton("🠈", self)
            self.btn_next = QPushButton("🠊", self)
            self.btn_back.setFixedSize(30, 12)
            self.btn_next.setFixedSize(30, 12)
            self.btn_next.setProperty("class", "branch-buttons")
            self.btn_back.setProperty("class", "branch-buttons")

            self.reposition()

            self.branch_entry = branch_entry
            branch_root_msg_id = next(iter(branch_entry))
            self.child_branches = self.branch_entry[branch_root_msg_id]

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
            if self.bubble_id in self.branch_entry:
                return
            else:
                self.page_chat.workflow.deactivate_all_branches_with_msg(self.bubble_id)
                current_index = self.child_branches.index(self.bubble_id)
                if current_index == 0:
                    self.reload_following_bubbles()
                    return
                next_msg_id = self.child_branches[current_index - 1]
                self.page_chat.workflow.activate_branch_with_msg(next_msg_id)

            self.reload_following_bubbles()

        def next(self):
            if self.bubble_id in self.branch_entry:
                activate_msg_id = self.child_branches[0]
                self.page_chat.workflow.activate_branch_with_msg(activate_msg_id)
            else:
                current_index = self.child_branches.index(self.bubble_id)
                if current_index == len(self.child_branches) - 1:
                    return
                self.page_chat.workflow.deactivate_all_branches_with_msg(self.bubble_id)
                next_msg_id = self.child_branches[current_index + 1]
                self.page_chat.workflow.activate_branch_with_msg(next_msg_id)

            self.reload_following_bubbles()

        def reload_following_bubbles(self):
            self.page_chat.delete_messages_since(self.bubble_id)
            self.page_chat.workflow.message_history.load()
            self.page_chat.refresh()

        def update_buttons(self):
            pass


# class MessageBubbleUser(MessageBubbleBase):
#     def __init__(self, *args, **kwargs):
#         super().__init__(*args, **kwargs)
#         # branches = self.parent.parent.workflow.message_history.branches
#         # self.branch_entry = {k: v for k, v in branches.items() if self.msg_id == k or self.msg_id in v}
#         # self.has_branches = len(self.branch_entry) > 0
#         #
#         # if self.has_branches:
#         #     self.branch_buttons = self.BubbleBranchButtons(self.branch_entry, parent=self)
#     #     #     self.branch_buttons.hide()
#     #
#     # def mousePressEvent(self, event):
#     #     super().mousePressEvent(event)
#     #
#     # def enterEvent(self, event):
#     #     super().enterEvent(event)
#     #     if self.has_branches:
#     #         self.branch_buttons.reposition()
#     #         self.branch_buttons.show()
#     #
#     # def leaveEvent(self, event):
#     #     super().leaveEvent(event)
#     #     if self.has_branches:
#     #         self.branch_buttons.hide()
#     #
#     # def keyPressEvent(self, event):
#     #     super().keyPressEvent(event)
#     #     self.parent.btn_resend.check_and_toggle()
#
#     # def toggle_markdown_edit(self, state):
#     #     if self.edit_markdown == state:
#     #         return
#     #     self.edit_markdown = state
#     #
#     #     if not self.edit_markdown:  # When toggled off
#     #         current_text = self.toPlainText()
#     #         if current_text != self.original_text:
#     #             self.editing_text = current_text
#     #             self.setMarkdownText(current_text)
#     #         else:
#     #             use_text = self.editing_text if self.editing_text else self.original_text
#     #             self.setMarkdownText(use_text)
#     #     else:  # When toggled on
#     #         use_text = self.editing_text if self.editing_text else self.original_text
#     #         self.setMarkdownText(use_text)
#     #
#     #     self.update_size()
#
#     class BubbleBranchButtons(QWidget):
#         def __init__(self, branch_entry, parent):
#             super().__init__(parent=parent)
#             self.parent = parent
#             message_bubble = self.parent
#             message_container = message_bubble.parent
#             self.bubble_id = message_bubble.msg_id
#             self.page_chat = message_container.parent
#
#             self.btn_back = QPushButton("🠈", self)
#             self.btn_next = QPushButton("🠊", self)
#             self.btn_back.setFixedSize(30, 12)
#             self.btn_next.setFixedSize(30, 12)
#             self.btn_next.setProperty("class", "branch-buttons")
#             self.btn_back.setProperty("class", "branch-buttons")
#
#             self.reposition()
#
#             self.branch_entry = branch_entry
#             branch_root_msg_id = next(iter(branch_entry))
#             self.child_branches = self.branch_entry[branch_root_msg_id]
#
#             if self.parent.msg_id == branch_root_msg_id:
#                 self.btn_back.hide()
#                 self.btn_back.setEnabled(False)
#             else:
#                 indx = branch_entry[branch_root_msg_id].index(self.parent.msg_id)
#                 if indx == len(branch_entry[branch_root_msg_id]) - 1:
#                     self.btn_next.hide()
#                     self.btn_next.setEnabled(False)
#
#             self.btn_back.clicked.connect(self.back)
#             self.btn_next.clicked.connect(self.next)
#
#         def reposition(self):
#             bubble_width = self.parent.size().width()
#
#             available_width = bubble_width - 8
#             half_av_width = available_width / 2
#
#             self.btn_back.setFixedWidth(half_av_width)
#             self.btn_next.setFixedWidth(half_av_width)
#
#             self.btn_back.move(4, 0)
#             self.btn_next.move(half_av_width + 4, 0)
#
#         def back(self):
#             if self.bubble_id in self.branch_entry:
#                 return
#             else:
#                 self.page_chat.workflow.deactivate_all_branches_with_msg(self.bubble_id)
#                 current_index = self.child_branches.index(self.bubble_id)
#                 if current_index == 0:
#                     self.reload_following_bubbles()
#                     return
#                 next_msg_id = self.child_branches[current_index - 1]
#                 self.page_chat.workflow.activate_branch_with_msg(next_msg_id)
#
#             self.reload_following_bubbles()
#
#         def next(self):
#             if self.bubble_id in self.branch_entry:
#                 activate_msg_id = self.child_branches[0]
#                 self.page_chat.workflow.activate_branch_with_msg(activate_msg_id)
#             else:
#                 current_index = self.child_branches.index(self.bubble_id)
#                 if current_index == len(self.child_branches) - 1:
#                     return
#                 self.page_chat.workflow.deactivate_all_branches_with_msg(self.bubble_id)
#                 next_msg_id = self.child_branches[current_index + 1]
#                 self.page_chat.workflow.activate_branch_with_msg(next_msg_id)
#
#             self.reload_following_bubbles()
#
#         def reload_following_bubbles(self):
#             self.page_chat.delete_messages_since(self.bubble_id)
#             self.page_chat.workflow.message_history.load()
#             self.page_chat.refresh()
#
#         def update_buttons(self):
#             pass


# class MessageBubbleCode(MessageBubbleBase):
#     def __init__(self, *args, **kwargs):
#         super().__init__(*args, **kwargs)
#         self.lang, self.code = self.split_lang_and_code(kwargs.get('text', ''))
#         self.original_text = self.code
#         # self.append_text(self.code)
#         self.setToolTip(f'{self.lang} code')
#         self.parent.btn_countdown.show()
#         # self.tag = lang
#         # self.btn_rerun = self.BubbleButton_Rerun_Code(self)
#         # self.btn_rerun.setGeometry(self.calculate_button_position())
#         # self.btn_rerun.hide()
#
#     def split_lang_and_code(self, text):
#         if text.startswith('```') and text.endswith('```'):
#             lang, code = text[3:-3].split('\n', 1)
#             # code = code.rstrip('\n')
#             return lang, code
#         return None, text
#     # def update_countdown(self):
#     #     if self.countdown > 0:
#     #         self.countdown -= 1
#     #         self.countdown_button.setText(f"{self.countdown}")
#     #     else:
#     #         self.timer.stop()
#     #         self.countdown_button.hide()
#     #         if hasattr(self, 'countdown_stopped'):
#     #             self.countdown_stopped = True
#     #
#     #         self.btn_rerun.click()
#     #
#     # def reset_countdown(self):
#     #     countdown_stopped = getattr(self, 'countdown_stopped', True)
#     #     if countdown_stopped: return
#     #     self.timer.stop()
#     #     self.countdown = int(
#     #         self.agent_config.get('actions.code_auto_run_seconds', 5))  # 5  # Reset countdown to 5 seconds
#     #     self.countdown_button.setText(f"{self.countdown}")
#     #
#     #     if not self.underMouse():
#     #         self.timer.start()  # Restart the timer
#
#     # def check_and_toggle_rerun_button(self):
#     #     if self.underMouse():
#     #         self.btn_rerun.show()
#     #     else:
#     #         self.btn_rerun.hide()
#
#     def run_bubble_code(self):
#         # raise NotImplementedError()
#         from interpreter import interpreter
#         output_list = interpreter.computer.run(self.lang, self.code)
#         output = output_list[0].get('content', '')
#         self.parent.parent.send_message(output, role='output')
#         pass
#         # member_id = self.member_id
#         # member = self.parent.parent.context.members[member_id]
#         # agent = member.agent
#         # agent_object = getattr(agent, 'agent_object', None)
#         #
#         # if agent_object:
#         #     run_code_func = getattr(agent_object, 'run_code', None)
#         # else:
#         #     agent_object = Interpreter()
#         #     run_code_func = agent_object.run_code
#         #
#         # output = run_code_func(self.lang, self.code)
#         #
#         # last_msg = self.parent.parent.context.message_history.last(incl_roles=('user', 'assistant', 'code'))
#         # if last_msg['id'] == self.msg_id:
#         #     self.parent.parent.send_message(output, role='output')
#
#     class BubbleButton_Rerun_Code(QPushButton):
#         def __init__(self, parent):
#             super().__init__(parent=parent)
#             self.bubble = parent
#             self.setProperty("class", "rerun")
#             self.clicked.connect(self.rerun_code)
#
#             icon = QIcon(QPixmap(":/resources/icon-run.png"))
#             self.setIcon(icon)
#
#         def rerun_code(self):
#             self.bubble.run_bubble_code()
#             # stop timer
#             self.bubble.timer.stop()
#             self.bubble.countdown_button.hide()
#             self.bubble.countdown_stopped = True
#
#         # def enterEvent(self, event):
#         #     icon = QIcon(QPixmap(":/resources/close.png"))
#         #     self.setIcon(icon)
#         #     self.setText("")  # Clear the text when displaying the icon
#         #     super().enterEvent(event)
#
#         # def leaveEvent(self, event):
#         #     self.setIcon(QIcon())  # Clear the icon
#         #     self.setText(str(self.parent().countdown))  # Reset the text to the current countdown value
#         #     super().leaveEvent(event)
#
#
# class MessageBubbleTool(MessageBubbleBase):
#     def __init__(self, *args, **kwargs):
#         super().__init__(*args, **kwargs)
#         # self.original_text = self.code
#         # self.append_text(self.code)
#         self.setToolTip(f'{self.lang} code')
#         # self.tag = lang
#         self.btn_rerun = self.BubbleButton_Rerun_Code(self)
#         self.btn_rerun.setGeometry(self.calculate_button_position())
#         self.btn_rerun.hide()
#
#     def start_timer(self):
#         self.countdown_stopped = False
#         self.countdown = int(self.agent_config.get('actions.code_auto_run_seconds', 5))  #
#         self.countdown_button = self.CountdownButton(self)
#         self.countdown_button.move(self.btn_rerun.x() - 20, self.btn_rerun.y() + 4)
#
#         self.countdown_button.clicked.connect(self.countdown_stop_btn_clicked)
#
#         self.timer = QTimer(self)
#         self.timer.timeout.connect(self.update_countdown)
#         self.timer.start(1000)  # Start countdown timer with 1-second interval
#
#     def countdown_stop_btn_clicked(self):
#         self.countdown_stopped = True
#         self.countdown_button.hide()
#
#     def split_lang_and_code(self, text):
#         if text.startswith('```') and text.endswith('```'):
#             lang, code = text[3:-3].split('\n', 1)
#             # code = code.rstrip('\n')
#             return lang, code
#         return None, text
#
#     def enterEvent(self, event):
#         self.check_and_toggle_rerun_button()
#         self.reset_countdown()
#         super().enterEvent(event)
#
#     def leaveEvent(self, event):
#         self.check_and_toggle_rerun_button()
#         self.reset_countdown()
#         super().leaveEvent(event)
#
#     def update_countdown(self):
#         if self.countdown > 0:
#             self.countdown -= 1
#             self.countdown_button.setText(f"{self.countdown}")
#         else:
#             self.timer.stop()
#             self.countdown_button.hide()
#             if hasattr(self, 'countdown_stopped'):
#                 self.countdown_stopped = True
#
#             self.btn_rerun.click()
#
#     def reset_countdown(self):
#         countdown_stopped = getattr(self, 'countdown_stopped', True)
#         if countdown_stopped: return
#         self.timer.stop()
#         self.countdown = int(
#             self.agent_config.get('actions.code_auto_run_seconds', 5))  # 5  # Reset countdown to 5 seconds
#         self.countdown_button.setText(f"{self.countdown}")
#
#         if not self.underMouse():
#             self.timer.start()  # Restart the timer
#
#     def check_and_toggle_rerun_button(self):
#         if self.underMouse():
#             self.btn_rerun.show()
#         else:
#             self.btn_rerun.hide()
#
#     def run_bubble_code(self):
#         # raise NotImplementedError()
#         from interpreter import interpreter
#         output_list = interpreter.computer.run(self.lang, self.code)
#         output = output_list[0].get('content', '')
#         self.parent.parent.send_message(output, role='output')
#         pass
#         # member_id = self.member_id
#         # member = self.parent.parent.context.members[member_id]
#         # agent = member.agent
#         # agent_object = getattr(agent, 'agent_object', None)
#         #
#         # if agent_object:
#         #     run_code_func = getattr(agent_object, 'run_code', None)
#         # else:
#         #     agent_object = Interpreter()
#         #     run_code_func = agent_object.run_code
#         #
#         # output = run_code_func(self.lang, self.code)
#         #
#         # last_msg = self.parent.parent.context.message_history.last(incl_roles=('user', 'assistant', 'code'))
#         # if last_msg['id'] == self.msg_id:
#         #     self.parent.parent.send_message(output, role='output')
#
#     class BubbleButton_Rerun_Code(QPushButton):
#         def __init__(self, parent):
#             super().__init__(parent=parent)
#             self.bubble = parent
#             self.setProperty("class", "rerun")
#             self.clicked.connect(self.rerun_code)
#
#             icon = QIcon(QPixmap(":/resources/icon-run.png"))
#             self.setIcon(icon)
#
#         def rerun_code(self):
#             self.bubble.run_bubble_code()
#             # stop timer
#             self.bubble.timer.stop()
#             self.bubble.countdown_button.hide()
#             self.bubble.countdown_stopped = True
#
#     # class CountdownButton(QPushButton):
#     #     def __init__(self, parent):
#     #         super().__init__(parent=parent)
#     #         self.setText(str(parent.agent_config.get('actions.code_auto_run_seconds', 5)))  # )
#     #         self.setIcon(QIcon())  # Initially, set an empty icon
#     #         self.setStyleSheet("color: white; background-color: transparent;")
#     #         self.setFixedHeight(22)
#     #         self.setFixedWidth(22)
#     #
#     #     def enterEvent(self, event):
#     #         icon = QIcon(QPixmap(":/resources/close.png"))
#     #         self.setIcon(icon)
#     #         self.setText("")  # Clear the text when displaying the icon
#     #         super().enterEvent(event)
#     #
#     #     def leaveEvent(self, event):
#     #         self.setIcon(QIcon())  # Clear the icon
#     #         self.setText(str(self.parent().countdown))  # Reset the text to the current countdown value
#     #         super().leaveEvent(event)