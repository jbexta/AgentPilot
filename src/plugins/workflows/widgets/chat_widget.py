import json
import os

from PySide6.QtWidgets import *
from PySide6.QtCore import QFileInfo, QSize, Signal
from PySide6.QtGui import QFont, QTextCursor, Qt, QIcon, QPixmap
import qasync
from typing_extensions import override

from gui import system
from gui.widgets.config_widget import ConfigWidget
from utils.helpers import IMAGE_EXTS, display_message, block_signals, \
    merge_config_into_workflow_config, apply_alpha_to_hex, convert_model_json_to_obj, params_to_schema, \
    save_linked_config
from utils import sql

from plugins.workflows.members.workflow import Workflow
from gui.util import IconButton, CHBoxLayout, CVBoxLayout, ToggleIconButton, colorize_pixmap, find_main, save_table_config

from gui.widgets.config_fields import ConfigFields
from plugins.workflows.widgets.workflow_settings import WorkflowSettings
from plugins.workflows.widgets.message_collection import MessageCollection


class ChattableWorkflowWidget(ConfigWidget):
    def __init__(self, parent, **kwargs):
        super().__init__(parent=parent)
        self.parent = parent
        self.main = find_main()
        self.workflow = kwargs.get('workflow', None)
        self.kind = kwargs.get('kind', 'CHAT')

        self.layout = CVBoxLayout(self)

        self.workflow_settings = kwargs.get('workflow_settings', None)
        self.message_collection = MessageCollection(self)
        self.attachment_bar = self.AttachmentBar(self)
        self.input_widget = self.ChatInputWidget(self)

        workflow_editable = kwargs.get('workflow_editable', True)
        collapsible = kwargs.get('collapsible', False)

        # if self.show_settings and not self.workflow_settings:
        if not self.workflow_settings:
            self.workflow_settings = WorkflowSettings(
                parent=self,
                workflow_editable=workflow_editable,
                collapsible=collapsible,
            )

        if workflow_editable:
            self.page_splitter = QSplitter(Qt.Vertical)
            self.page_splitter.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
            self.page_splitter.setChildrenCollapsible(False)

            self.page_splitter.addWidget(self.workflow_settings)
            self.page_splitter.addWidget(self.message_collection)
            self.page_splitter.setSizes([350, 1000])
        
            self.layout.addWidget(self.page_splitter, 1)
        else:
            self.layout.addWidget(self.workflow_settings)
            self.layout.addWidget(self.message_collection, 1)

        self.layout.addWidget(self.attachment_bar)
        self.layout.addSpacing(3)
        self.layout.addWidget(self.input_widget)
    
    def get_config(self):
        return self.workflow_settings.get_config()
    
    def update_config(self):
        if hasattr(self.parent, 'update_config'):
            self.parent.update_config()

    def load_config(self, json_config=None):
        self.new_context(config=json_config)

    def load(self):
        if not self.workflow:
            self.workflow = Workflow(
                main=self.main,
                kind=self.kind,
                get_latest=True,
                chat_widget=self,
            )

        self.workflow.load()
        self.workflow.message_history.load()

        if self.workflow_settings:
            self.workflow_settings.load_config(self.workflow.config)
            self.workflow_settings.load()

        self.message_collection.load()
        self.input_widget.load()

        self.resize_for_context()

    def update_config(self):
        self.save_config()

    def save_config(self):
        if not self.workflow_settings:
            return
        config = self.workflow_settings.get_config()

        # Sync back to linked source entity
        linked_id = self.workflow_settings.linked_id
        if linked_id:
            save_linked_config(linked_id, config)

        save_table_config(
            ref_widget=self,
            table_name='contexts',
            item_id=self.workflow.context_id,  # item_id,
            value=json.dumps(config),
        )
        if hasattr(self.parent, 'save_config'):
            self.parent.save_config()
        self.workflow.load_config(config)
        self.workflow_settings.load_config(config)
        self.workflow.load()
        # self.workflow_settings.load()
        self.input_widget.load()
        self.message_collection.load()

    @qasync.asyncSlot()
    async def on_send_message(self, restore_scroll_pos=None):
        if restore_scroll_pos:
            self.restore_scroll_pos = restore_scroll_pos
            print('restore_scroll_pos: ', restore_scroll_pos)

        if self.workflow.responding:
            self.workflow.behaviour.stop()
        else:
            # self.ensure_visible()
            next_expected_member = self.workflow.next_expected_member()
            if not next_expected_member:
                return

            next_expected_member_type = next_expected_member.config.get('_TYPE', 'agent')
            as_member_id = next_expected_member.member_id

            if next_expected_member_type == 'user':  # todo clean  # !memberdiff! #
                # attachments = [filepath for filepath in self.attachment_bar.attachments]
                image_attachments = [
                    attachment for attachment in self.attachment_bar.attachments 
                    if any(attachment.filename.lower().endswith(ext) for ext in IMAGE_EXTS)
                ]
                for attachment in image_attachments:  # todo other media types
                    image_filepath = attachment.filepath
                    if os.path.exists(image_filepath):
                        self.workflow.save_message('image', json.dumps({"filepath": image_filepath}), member_id=as_member_id)
                        self.attachment_bar.remove_attachment(attachment)

                text = self.input_widget.message_text.toPlainText()
                await self.workflow.send_message(text, clear_input=True, as_member_id=as_member_id)
            else:
                await self.run_workflow_async(from_member_id=next_expected_member.member_id)
        
            if getattr(self, 'restore_scroll_pos', None):
                try:
                    self.message_collection.scroll_area.verticalScrollBar().setValue(self.restore_scroll_pos)
                except Exception as e:
                    print('error restoring scroll poss: ', e)

            self.resize_for_context()

    def resize_for_context(self):
        has_bubbles = len(self.message_collection.chat_bubbles) > 0
        if hasattr(self, 'page_splitter'):
            if has_bubbles:
                self.page_splitter.setSizes([500, 500])
            else:
                self.page_splitter.setSizes([1000, 0])

    async def run_workflow_async(self, from_member_id=None, feed_back=False):
        self.input_widget.send_button.update_icon(is_generating=True)
        try:
            await self.workflow.behaviour.start(from_member_id, feed_back=feed_back)
            
        except Exception as e:
            if 'AP_DEV_MODE' in os.environ:
                raise e  # re-raise the exception for debugging
            display_message(
                message=str(e),
                icon=QMessageBox.Critical,
            )
        finally:
            self.end_turn()
            if self.__class__.__name__ == 'Page_Chat':
                await self.try_generate_title()

    def new_sentence(self, role, member_id, sentence):
        with self.workflow.message_history.thread_lock:
            if (role, member_id) not in self.message_collection.last_member_bubbles:
                from utils.messages import Message
                msg = Message(msg_id=-1, role=role, content=sentence, member_id=member_id)
                self.message_collection.insert_bubble(msg)
                self.message_collection.maybe_scroll_to_end()
            else:
                last_member_bubble = self.message_collection.last_member_bubbles[(role, member_id)]
                last_member_bubble.bubble.append_text(sentence)

    def end_turn(self):
        self.workflow.responding = False
        self.input_widget.send_button.update_icon(is_generating=False)

        self.message_collection.refresh_waiting_bar(set_visibility=True)
        if self.workflow_settings:
            self.workflow_settings.refresh_member_highlights()

        # Update input widget based on next expected member
        self.input_widget.update_for_next_member()

    def new_chat(self):
        has_no_messages = len(self.workflow.message_history.messages) == 0
        if has_no_messages:
            return
        copy_context_id = self.workflow.context_id
        self.new_context(copy_context_id=copy_context_id)

        self.workflow_settings.header_widget.widgets[1].btn_prev_context.setEnabled(True)

    def new_context(self,
        copy_context_id: int = None,
        entity_id: str = None,
        entity_table: str = None,
        config=None,
        kind=None,
    ):
        context_id = None  # todo clean
        if kind:
            self.kind = kind

        if copy_context_id:
            config = json.loads(
                sql.get_scalar("SELECT config FROM contexts WHERE id = ?", (copy_context_id,))
            )
            sql.execute("""
                INSERT INTO contexts (
                    kind,
                    config
                )
                SELECT
                    kind,
                    config
                FROM contexts
                WHERE id = ?""", (copy_context_id,))

        else:
            if entity_id is not None:
                config = json.loads(
                    sql.get_scalar(f"SELECT config FROM `{entity_table}` WHERE uuid = ?",
                                (entity_id,))
                )
                config = merge_config_into_workflow_config(config, entity_id=entity_id, entity_table=entity_table)
            if config is None:
                config = {}
            context_id = sql.get_scalar("""
                SELECT id
                FROM contexts c
                WHERE kind = ? AND config = ?
                AND NOT EXISTS (
                    SELECT 1
                    FROM contexts_messages cm
                    WHERE cm.context_id = c.id
                )
                LIMIT 1;""", (self.kind, json.dumps(config))
            )
            if not context_id:
                sql.execute("""
                    INSERT INTO contexts
                        (kind, config)
                    VALUES (?, ?)""", (self.kind, json.dumps(config)))

        if not context_id:
            context_id = sql.get_scalar("SELECT MAX(id) FROM contexts WHERE kind = ?", (self.kind,))

        self.goto_context(context_id)

    def goto_context(self, context_id=None):
        from plugins.workflows.members.workflow import Workflow
        self.workflow = Workflow(main=self.main, context_id=context_id, chat_widget=self)
        self.kind = sql.get_scalar('SELECT kind FROM contexts WHERE id = ?', (context_id,))  # todo temp
        self.load()

    def get_preload_messages(self, config):
        member_type = config.get('_TYPE', 'agent')
        if member_type == 'workflow':
            wf_members = config.get('members', [])
            agent_members = [member_data for member_data in wf_members if member_data.get('config', {}).get('_TYPE', 'agent') == 'agent']

            if len(agent_members) == 1:
                agent_config = agent_members[0].get('config', {})
                preload_msgs = agent_config.get('chat.preload.data', [])
                member_id = agent_members[0]['id']
                return member_id, preload_msgs
            else:
                return None, []

        elif member_type == 'agent':
            preload_msgs = config.get('chat.preload.data', [])
            member_id = 2
            return member_id, preload_msgs
        else:
            return None, []

    async def try_generate_title(self):
        current_title = self.workflow.chat_title
        if current_title != '':
            return

        system_config = system.manager.config
        auto_title = system_config.get('system.auto_title', True)

        if not auto_title:
            return
        if not self.workflow.message_history.count(incl_roles=('user',)) == 1:
            return
        
        user_msg = self.workflow.message_history.last(incl_roles=('user',))

        conf = system.manager.config
        model_name = conf.get('system.auto_title_model', 'mistral/mistral-large-latest')
        model_obj = convert_model_json_to_obj(model_name)

        prompt = conf.get('system.auto_title_prompt',
                            'Generate a brief and concise title for a chat that begins with the following message:\n\n{user_msg}')
        prompt = prompt.format(user_msg=user_msg['content'])

        try:
            response = await system.manager.models.run_model(model_obj=model_obj, messages=[{'role': 'user', 'content': prompt}], stream=False)
            title = response.choices[0]['message']['content']

            # title = system.manager.providers.get_scalar(prompt, single_line=True, model_obj=model_obj)
            title = title.replace('\n', ' ').strip("'").strip('"')
            
            context_buttons = self.workflow_settings.header_widget.widgets[1]
            title_label = context_buttons.title_label
            with block_signals(title_label):
                title_label.setText(title)
                title_label.setCursorPosition(0)
            context_buttons.title_edited(title)
            
        except Exception as e:
            display_message(
                message=f'Auto title response error, check the model in System settings:\n\n{str(e)}',
                icon=QMessageBox.Critical,
            )

    class ChatInputWidget(QWidget):
        """Stores next_expected_member, if it's user, show message_text and send_button, otherwise show nothing"""
        def __init__(self, parent):
            super().__init__(parent)
            self.parent = parent
            
            self.layout = CHBoxLayout(self)

            self.message_text = self.MessageText(self)
            self.send_button = self.SendButton(self)
            self.instant_run_button = self.InstantRunButton(self)

            v_layout = CVBoxLayout()
            self.workflow_params_input = self.WorkflowParamsInput(self)
            v_layout.addWidget(self.workflow_params_input)
            v_layout.addWidget(self.message_text)
            self.layout.addLayout(v_layout)

            v_layout_2 = CVBoxLayout()
            v_layout_2.addStretch()
            v_layout_2.addWidget(self.send_button)
            self.layout.addLayout(v_layout_2)

            v_layout_3 = CVBoxLayout()
            v_layout_3.addStretch()
            v_layout_3.addWidget(self.instant_run_button)
            self.layout.addLayout(v_layout_3)

            # Connect signals
            self.send_button.clicked.connect(self.parent.on_send_message, Qt.QueuedConnection)
            self.message_text.enterPressed.connect(self.parent.on_send_message, Qt.QueuedConnection)

        def load(self):
            self.workflow_params_input.load()
            self.update_for_next_member()

        def update_for_next_member(self):
            """Update UI based on the next expected member type"""
            if not self.parent.workflow:
                self.set_non_user_mode()
                return
            next_expected_member = self.parent.workflow.next_expected_member()
            if not next_expected_member:
                # Default to user mode
                self.set_user_mode()
                return

            next_expected_member_type = next_expected_member.config.get('_TYPE', 'agent')

            if next_expected_member_type == 'user':
                self.set_user_mode()
            else:
                self.set_non_user_mode()

        def set_user_mode(self):
            """Show message text with send button (joined style)"""
            self.message_text.show()
            self.send_button.set_style_mode(joined=True)

        def set_non_user_mode(self):
            """Hide message text, show only send button (standalone style)"""
            self.message_text.hide()

            # If workflow params is visible, show send button standalone
            if self.workflow_params_input.isVisible():
                self.send_button.set_style_mode(joined=False)
        
        class InstantRunButton(ToggleIconButton):
            def __init__(self, parent):
                super().__init__(
                    parent=parent, 
                    icon_path=':/resources/icon-lightning.png', 
                    icon_path_checked=':/resources/icon-lightning-solid.png',
                    tooltip='Instantly run the workflow when modified. Use this only with text based workflows!',
                    icon_size_percent=0.6,
                )
                self.setMaximumWidth(25)

        class WorkflowParamsInput(ConfigFields):
            def __init__(self, parent):
                super().__init__(parent, add_stretch_to_end=False)

            @override
            def load(self):
                chattable = self.parent.parent
                workflow_params = chattable.workflow_settings.get_config().get('params', [])
                workflow_params = [{k.lower(): v for k, v in param.items()} for param in workflow_params]
                param_schema = params_to_schema(workflow_params)
                if param_schema != self.schema:
                    self.schema = param_schema
                    self.build_schema()

                if len(self.schema) == 0:
                    self.hide()
                    return

                self.show()
                self.clear_fields()
                self.updateGeometry()
                super().load()

            def save_config(self):
                params_config = self.get_config()
                workflow = self.parent.parent.workflow
                if workflow:
                    workflow.params = {k.lower(): v for k, v in params_config.items()}

        class MessageText(QTextEdit):
            enterPressed = Signal()

            def __init__(self, parent):
                super().__init__(parent)
                self.parent = parent
                # Set minimum height
                self.setMinimumHeight(51)
                
                self.setProperty("class", "msgbox")

                text_size = system.manager.config.get('display.text_size', 15)
                text_font = system.manager.config.get('display.text_font', '')

                self.font = QFont()
                if text_font != '':  #  and text_font != 'Default':
                    self.font.setFamily(text_font)
                self.font.setPointSize(text_size)
                self.setFont(self.font)
                self.setAcceptDrops(True)
                self.resize(self.sizeHint())

            def resizeEvent(self, e):
                super().resizeEvent(e)
                self.on_resize()

            def on_resize(self):
                self.setFixedHeight(self.sizeHint().height())
                # Trigger layout update for parent widgets
                self.updateGeometry()
                # Also update send button height to match
                if hasattr(self.parent, 'send_button'):
                    self.parent.send_button.setFixedHeight(self.sizeHint().height())

            def keyPressEvent(self, event):
                combo = event.keyCombination()
                key = combo.key()
                mod = combo.keyboardModifiers()

                # Check for Ctrl + B key combination
                if key == Qt.Key.Key_B and mod == Qt.KeyboardModifier.ControlModifier:
                    # Insert the code block where the cursor is
                    cursor = self.textCursor()
                    cursor.insertText("```\n\n```")  # Inserting with new lines between to create a space for the code
                    cursor.movePosition(QTextCursor.PreviousBlock, QTextCursor.MoveAnchor, 1)  # Move cursor inside the code block
                    self.setTextCursor(cursor)
                    self.on_resize()
                    return  # We handle the event, no need to pass it to the base class

                if key == Qt.Key.Key_Enter or key == Qt.Key.Key_Return:
                    if mod != Qt.KeyboardModifier.ShiftModifier:
                        if self.toPlainText().strip() == '':
                            return

                        if not self.parent.parent.workflow.responding:
                            self.enterPressed.emit()
                            return

                super().keyPressEvent(event)
                # Update the widget's size based on content
                self.on_resize()

            def sizeHint(self):
                content_height = min(700, self.document().size().height())
                return QSize(self.width(), content_height)

            # files = []

            # mouse hover event show mic button
            def enterEvent(self, event):
                super().enterEvent(event)

            def leaveEvent(self, event):
                # if not self.button_bar.mic_button.isChecked():
                #     self.button_bar.hide()
                super().leaveEvent(event)

        class SendButton(IconButton):
            def __init__(self, parent):
                super().__init__(parent=parent, icon_path=":/resources/icon-send.png", opacity=0.7)
                self.parent = parent
                self.setMinimumWidth(50)
                self.setMinimumHeight(35)
                self.setProperty("class", "send")
                self.update_icon(is_generating=False)

            def update_icon(self, is_generating):
                icon_iden = 'send' if not is_generating else 'stop'
                pixmap = colorize_pixmap(QPixmap(f":/resources/icon-{icon_iden}.png"))
                self.setIconPixmap(pixmap)

            def set_style_mode(self, joined=True):
                """Set stylesheet based on whether button is joined with message text or standalone"""
                text_color = system.manager.config.get('display.text_color', '#c4c4c4')
                secondary_color = system.manager.config.get('display.secondary_color', '#292629')
                hover_color = apply_alpha_to_hex(text_color, 0.05)

                if joined:
                    # Joined with message text - left side flat, right side rounded (match msgbox 12px)
                    self.setStyleSheet(f"""
                        QPushButton.send {{
                            background-color: {secondary_color};
                            border-top-right-radius: 12px;
                            border-bottom-right-radius: 12px;
                            border-top-left-radius: 0px;
                            border-bottom-left-radius: 0px;
                            color: {text_color};
                        }}
                        QPushButton.send:hover {{
                            background-color: {hover_color};
                            border-top-right-radius: 12px;
                            border-bottom-right-radius: 12px;
                            border-top-left-radius: 0px;
                            border-bottom-left-radius: 0px;
                            color: {text_color};
                        }}
                    """)
                else:
                    # Standalone - fully rounded (match msgbox 12px)
                    self.setStyleSheet(f"""
                        QPushButton.send {{
                            background-color: {secondary_color};
                            border-radius: 12px;
                            color: {text_color};
                        }}
                        QPushButton.send:hover {{
                            background-color: {hover_color};
                            border-radius: 12px;
                            color: {text_color};
                        }}
                    """)
                    self.setFixedHeight(50)

    class AttachmentBar(QWidget):
        def __init__(self, parent):
            super().__init__(parent)
            self.parent = parent
            self.layout = CVBoxLayout(self)
            # self.setMinimumHeight(2)  # acts as a spacer in chat

            self.attachments = []  # A list of filepaths
            self.hide()

        def add_attachments(self, paths):
            if not isinstance(paths, list):
                paths = [paths]

            for filepath in paths:
                attachment = self.Attachment(self, filepath)
                self.attachments.append(attachment)
                self.layout.addWidget(attachment)

            self.show()

        def remove_attachment(self, attachment):
            self.attachments.remove(attachment)
            attachment.deleteLater()

        class Attachment(QWidget):
            def __init__(self, parent, filepath):
                super().__init__(parent)
                self.parent = parent

                self.filepath = filepath
                self.filename = os.path.basename(filepath)

                self.layout = CHBoxLayout(self)

                self.icon_label = QLabel()
                self.text_label = QLabel()
                self.text_label.setText(self.filename)

                # If is any image type
                if self.filename.endswith(('.png', '.jpg', '.jpeg', '.gif', '.bmp', '.tiff', '.webp')):
                    pixmap = QPixmap(filepath)
                    if not pixmap.isNull():
                        thumbnail_pixmap = pixmap.scaled(16, 16, Qt.KeepAspectRatio)
                        self.icon_label.setPixmap(thumbnail_pixmap)

                else:
                    # show file icon
                    icon_provider = QFileIconProvider()
                    icon = icon_provider.icon(QFileInfo(filepath))
                    self.icon_label.setPixmap(icon.pixmap(16, 16))

                self.layout.addWidget(self.icon_label)
                self.layout.addWidget(self.text_label)

                remove_button = IconButton(parent=self, icon_path=':/resources/close.png', icon_size_percent=0.5)
                remove_button.clicked.connect(self.on_delete_click)

                self.layout.addWidget(remove_button)
                self.layout.addStretch(1)

            def update_widget(self):
                icon_provider = QFileIconProvider()
                icon = icon_provider.icon(QFileInfo(self.filepath))
                if icon is None or not isinstance(icon, QIcon):
                    icon = QIcon()  # Fallback to a default QIcon if no valid icon is found
                self.icon_label.setPixmap(icon.pixmap(16, 16))

            def on_delete_click(self):
                self.parent.remove_attachment(self)
