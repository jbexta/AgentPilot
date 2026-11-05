import json
import os

from PySide6.QtWidgets import *
from PySide6.QtCore import QFileInfo, QSize, Signal
from PySide6.QtGui import QFont, QTextCursor, Qt, QIcon, QPixmap
import qasync
from typing_extensions import override

from gui import system
from gui.widgets.config_widget import ConfigWidget
from utils.helpers import display_message, block_signals, \
    convert_model_json_to_obj, params_to_schema, \
    convert_to_safe_case
from plugins.workflows.utils.workflows import merge_config_into_workflow_config, save_linked_config, \
    clear_context_messages, get_bubble_display_state, is_instant_runnable
from utils.media import IMAGE_EXTS
from utils import sql

from plugins.workflows.members.workflow import Workflow
from plugins.workflows.utils.runs import get_run_manager
from gui.gui_utils.helpers import colorize_pixmap, find_main, save_table_config, find_ancestor_tree_widget, \
    bake_table_item, get_member_settings_class, set_style_property
from gui.gui_utils.icon_button import IconButton
from gui.gui_utils.layouts import CHBoxLayout, CVBoxLayout
from gui.gui_utils.toggle_icon_button import ToggleIconButton

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
        self.bubble_state = None
        self.message_collection = MessageCollection(self)
        self.restore_scroll_pos = 0  # pin to bottom
        self.user_has_run = False  # gates instant run until the user runs once
        self.member_bar = self.MemberChatBar(self)
        self.chat_panel = QWidget()
        chat_panel_layout = CVBoxLayout(self.chat_panel)
        chat_panel_layout.addWidget(self.member_bar)
        chat_panel_layout.addWidget(self.message_collection, 1)
        chat_panel_layout.addStretch()
        self.attachment_bar = self.AttachmentBar(self)
        self.input_widget = self.ChatInputWidget(self)

        workflow_editable = kwargs.get('workflow_editable', True)
        collapsible = kwargs.get('collapsible', False)
        # When False, the workflow graph editor is kept out of the visible
        # layout (but still instantiated below, so all config/save plumbing
        # that reads workflow_settings keeps working). Used by the Plans
        # page, where the workflow is a fixed single Claude Code member and
        # the user edits a markdown document rather than the graph.
        self.show_workflow = kwargs.get('show_workflow', True)
        self.show_member_bar = True

        # if self.show_settings and not self.workflow_settings:
        if not self.workflow_settings:
            self.workflow_settings = WorkflowSettings(
                parent=self,
                workflow_editable=workflow_editable,
                collapsible=collapsible,
            )

        if not self.show_workflow:
            self.layout.addWidget(self.chat_panel, 1)
        elif workflow_editable:
            self.page_splitter = QSplitter(Qt.Vertical)
            self.page_splitter.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
            self.page_splitter.setChildrenCollapsible(False)

            self.page_splitter.addWidget(self.workflow_settings)
            self.page_splitter.addWidget(self.chat_panel)
            self.page_splitter.setSizes([350, 1000])
        
            self.layout.addWidget(self.page_splitter, 1)
        else:
            self.layout.addWidget(self.workflow_settings)
            self.layout.addWidget(self.chat_panel, 1)

        self.layout.addWidget(self.attachment_bar)
        self.layout.addSpacing(3)
        self.layout.addWidget(self.input_widget)
        get_run_manager().changed.connect(self.refresh_run_state)

    def refresh_run_state(self):
        if self.workflow is not None:
            self.input_widget.send_button.update_icon(get_run_manager().is_running(self.workflow.context_id))
    
    def get_config(self):
        return self.workflow_settings.get_config()

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

        self.member_bar.load()
        self.message_collection.load()
        self.bubble_state = get_bubble_display_state(
            self.workflow_settings.get_config())
        self.input_widget.load()

        get_run_manager().attach(self)

        self.resize_for_context()

    def update_config(self):
        self.save_config()

    @staticmethod
    def rebake_linked_entity(linked_id):
        """Baked entities are restored from their YAML at startup, so keep it current."""
        if not system.manager.config.get('system.auto_bake', False):
            return
        table, entity_uuid = linked_id.split('.', 1)
        row = sql.get_results(f"SELECT id, baked FROM `{table}` WHERE uuid = ?", (entity_uuid,), return_type='tuple')
        if row and row[1] == 1:
            bake_table_item(table, row[0])

    def save_config(self):
        if not self.workflow_settings:
            return
        config = self.workflow_settings.get_config()

        # from core.actions import base as undo_history
        # from core.actions.save_chat_entity import SaveChatEntityAction
        # with undo_history.capture() as saves:
        # Sync back to linked source entity
        linked_id = self.workflow_settings.linked_id
        if linked_id:
            save_linked_config(linked_id, config)
            self.rebake_linked_entity(linked_id)

        if self.workflow.context_id is not None:
            save_table_config(
                ref_widget=self,
                table_name='contexts',
                item_id=self.workflow.context_id,  # item_id,
                value=json.dumps(config),
            )
        if hasattr(self.parent, 'save_config'):
            self.parent.save_config()
        # if saves:
        #     undo_history.record(SaveChatEntityAction(saves=saves))
        self.workflow.load_config(config)
        self.workflow_settings.load_config(config)
        self.workflow.load()
        # self.workflow_settings.load()
        self.member_bar.load()
        self.input_widget.load()
        bubble_state = get_bubble_display_state(config)
        if bubble_state != self.bubble_state:
            self.bubble_state = bubble_state
            scroll_bar = self.message_collection.scroll_area.verticalScrollBar()
            self.restore_scroll_pos = scroll_bar.maximum() - scroll_bar.value()
            self.message_collection.load()

        # Only rerun on edit once the user has run this context themselves
        if self.input_widget.instant_run_button.isChecked() and self.user_has_run:
            self.instant_run()

    @qasync.asyncSlot()
    async def instant_run(self):
        if get_run_manager().is_running(self.workflow.context_id):
            return
        if self.workflow.context_id is not None:
            clear_context_messages(self.workflow.context_id)
            self.workflow.message_history.load()
        # Keep showing the previous output until the rerun's is complete
        scroll_bar = self.message_collection.scroll_area.verticalScrollBar()
        from_bottom = scroll_bar.maximum() - scroll_bar.value()
        self.message_collection.setUpdatesEnabled(False)
        try:
            await self.run_workflow_async()
        finally:
            self.restore_scroll_pos = from_bottom
            self.message_collection.load()
            self.message_collection.setUpdatesEnabled(True)

    @qasync.asyncSlot()
    async def on_send_message(self, restore_scroll_pos=None):
        if restore_scroll_pos:
            self.restore_scroll_pos = restore_scroll_pos
            print('restore_scroll_pos: ', restore_scroll_pos)

        runs = get_run_manager()
        if runs.is_running(self.workflow.context_id):
            runs.stop(self.workflow.context_id)
        else:
            if self.workflow.context_id is not None:
                runs.register_display(self.workflow.context_id, self)
            # self.ensure_visible()
            next_expected_member = self.workflow.next_expected_member()
            if not next_expected_member:
                return
            self.user_has_run = True

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
                # self.maybe_link_goal(text)  # Goals disabled
                await self.workflow.send_message(text, clear_input=True, as_member_id=as_member_id)
            else:
                await self.run_workflow_async(from_member_id=next_expected_member.member_id)
        
            if getattr(self, 'restore_scroll_pos', None):
                try:
                    scroll_bar = self.message_collection.scroll_area.verticalScrollBar()
                    scroll_bar.setValue(scroll_bar.maximum() - self.restore_scroll_pos)
                except Exception as e:
                    print('error restoring scroll poss: ', e)

            self.resize_for_context()

    @qasync.asyncSlot(bool)
    async def on_mic_toggled(self, checked):
        """Start/stop voice capture on the next-expected User member."""
        if not self.workflow:
            return
        next_member = self.workflow.next_expected_member()
        if not next_member or next_member.config.get('_TYPE', 'agent') != 'user':
            return
        try:
            if checked:
                await next_member.start_capture()
            else:
                await next_member.stop_capture()
        except Exception as e:
            if 'AP_DEV_MODE' in os.environ:
                raise e
            display_message(message=str(e), icon=QMessageBox.Critical)

    def maybe_link_goal(self, text):
        """If ``text`` is a ``/goal <name>`` command in a Claude Code chat,
        link this chat's context to a goal so it appears on the Goals page.

        The text is left untouched so it still passes through to the Claude
        Code SDK, which honours ``/goal`` natively.
        """
        stripped = (text or '').strip()
        if not (stripped == '/goal' or stripped.startswith('/goal ')):
            return
        has_claude_code = any(
            member.config.get('_TYPE') == 'claude_code'
            for member in self.workflow.members.values()
        )
        if not has_claude_code:
            return
        name = stripped[len('/goal'):].strip()
        from plugins.workflows.pages._goals import link_context_to_goal
        link_context_to_goal(self.workflow.context_id, name)

    def refresh_member_bar(self):
        self.member_bar.load()
        self.resize_for_context()

    def resize_for_context(self):
        """Below the workflow editor, show the messages only once there are
        some, leaving just the input below an empty chat. (Elsewhere an
        empty message area is blank already, and holds the layout.)"""
        if not hasattr(self, 'page_splitter'):
            return
        has_bubbles = len(self.message_collection.chat_bubbles) > 0
        self.message_collection.setVisible(has_bubbles)
        self.chat_panel.setVisible(
            has_bubbles or not self.member_bar.isHidden())
        if has_bubbles:
            self.page_splitter.setSizes([500, 500])

    async def run_workflow_async(self, from_member_id=None, feed_back=False):
        workflow = self.workflow
        runs = get_run_manager()
        self.input_widget.send_button.update_icon(is_generating=True)
        try:
            await runs.start(workflow, from_member_id, feed_back=feed_back)

        except Exception as e:
            if 'AP_DEV_MODE' in os.environ:
                raise e  # re-raise the exception for debugging
            display_message(
                message=str(e),
                icon=QMessageBox.Critical,
            )
        finally:
            # End the turn on whichever widget displays this context now; the
            # user may have switched this widget to another context mid-run.
            # If the context is still running (this call was a duplicate
            # no-op), leave the UI in its responding state.
            widget = runs.get_display(workflow.context_id)
            if (widget and not runs.is_running(workflow.context_id)
                    and getattr(widget.workflow, 'context_id', None) == workflow.context_id):
                widget.end_turn()
                await widget.try_generate_title()

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
        """Open an unsaved context, its row is created when first needed."""
        if kind:
            self.kind = kind

        if copy_context_id:
            config = sql.get_scalar("SELECT config FROM contexts WHERE id = ?", (copy_context_id,), load_json=True)
        elif entity_id is not None:
            config = json.loads(
                sql.get_scalar(f"SELECT config FROM `{entity_table}` WHERE uuid = ?",
                            (entity_id,))
            )
            config = merge_config_into_workflow_config(config, entity_id=entity_id, entity_table=entity_table)
        config = merge_config_into_workflow_config(config or {})

        self.goto_context(config=config)

    def goto_context(self, context_id=None, config=None):
        from plugins.workflows.members.workflow import Workflow
        if getattr(self, 'workflow', None) is not None:
            self.workflow.close()  # tear down any open live voice session
        self.workflow = Workflow(main=self.main, context_id=context_id, config=config, kind=self.kind, chat_widget=self)
        if context_id is not None:
            self.kind = sql.get_scalar('SELECT kind FROM contexts WHERE id = ?', (context_id,))  # todo temp
        self.input_widget.instant_run_button.auto_checked = None
        self.user_has_run = False
        self.restore_scroll_pos = 0  # pin to bottom
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

        conf = system.manager.config
        model_name = conf.get('system.auto_title_model')

        if not model_name:
            return
        if not self.workflow.message_history.count(incl_roles=('user',)) == 1:
            return

        user_msg = self.workflow.message_history.last(incl_roles=('user',))

        model_obj = convert_model_json_to_obj(model_name)

        prompt = conf.get('system.auto_title_prompt',
                            'Generate a brief and concise title for a chat that begins with the following message:\n\n{user_msg}')
        prompt = prompt.format(user_msg=user_msg['content'])

        try:
            response = await system.manager.models.run_model(model_obj=model_obj, messages=[{'role': 'user', 'content': prompt}], stream=False)
            title = response.choices[0]['message']['content']

            # title = system.manager.providers.get_scalar(prompt, single_line=True, model_obj=model_obj)
            title = title.replace('\n', ' ').strip("'").strip('"')
            
            header = self.workflow_settings.header_widget
            if hasattr(header, 'context_bar'):
                title_label = header.context_bar.title_label
                with block_signals(title_label):
                    title_label.setText(title)
                    title_label.setCursorPosition(0)
                header.context_bar.title_edited(title)

            tree_widget = find_ancestor_tree_widget(self)
            if tree_widget:
                item = tree_widget.tree.currentItem()
                if item:
                    item.setText(0, title)
            
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
            self.mic_button = self.MicButton(self)
            self.toggle_project_button = self.ToggleProjectButton(self)

            v_layout = CVBoxLayout()
            self.workflow_params_input = self.WorkflowParamsInput(self)
            v_layout.addWidget(self.workflow_params_input)
            v_layout.addWidget(self.message_text)
            self.layout.addLayout(v_layout)

            v_layout_2 = CVBoxLayout()
            v_layout_2.addStretch()
            v_layout_2.addWidget(self.send_button)
            self.layout.addLayout(v_layout_2)

            v_layout_mic = CVBoxLayout()
            v_layout_mic.addStretch()
            v_layout_mic.addWidget(self.mic_button)
            self.layout.addLayout(v_layout_mic)

            v_layout_project = CVBoxLayout()
            v_layout_project.addStretch()
            v_layout_project.addWidget(self.toggle_project_button)
            self.layout.addLayout(v_layout_project)

            v_layout_3 = CVBoxLayout()
            v_layout_3.addStretch()
            v_layout_3.addWidget(self.instant_run_button)
            self.layout.addLayout(v_layout_3)

            # Connect signals
            self.send_button.clicked.connect(self.parent.on_send_message, Qt.QueuedConnection)
            self.message_text.enterPressed.connect(self.parent.on_send_message, Qt.QueuedConnection)
            self.mic_button.toggled.connect(self.parent.on_mic_toggled, Qt.QueuedConnection)

        def load(self):
            self.workflow_params_input.load()
            self.instant_run_button.auto_enable(
                self.parent.workflow_settings.get_config())
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
            self.send_button.update_icon(is_generating=False)

        def set_user_mode(self):
            """Show message text with send button (joined style)"""
            self.message_text.show()
            self.send_button.set_style_mode(joined=True)
            self.mic_button.show()

        def set_non_user_mode(self):
            """Hide message text, show only send button (standalone style)"""
            self.message_text.hide()
            self.mic_button.hide()

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
                self.auto_checked = None

            def auto_enable(self, workflow_config):
                """Only offered for workflows that are cheap to rerun, where
                it starts checked; manual toggles are kept until that
                changes."""
                cheap = is_instant_runnable(workflow_config)
                self.setVisible(cheap)
                if cheap != self.auto_checked:
                    self.auto_checked = cheap
                    self.setChecked(cheap)

        class MicButton(ToggleIconButton):
            def __init__(self, parent):
                super().__init__(
                    parent=parent,
                    icon_path=':/resources/icon-mic.png',
                    icon_path_checked=':/resources/icon-mic.png',
                    tooltip='Voice input: toggle to speak instead of typing',
                    tooltip_checked='Listening… toggle to stop',
                    color_when_checked='#6aa84f',
                    icon_size_percent=0.6,
                )
                self.setMaximumWidth(25)

        class ToggleProjectButton(ToggleIconButton):
            def __init__(self, parent):
                super().__init__(
                    parent=parent,
                    icon_path=':/resources/icon-expand.png',
                    tooltip='Hide the project',
                    tooltip_checked='Show the project',
                    icon_size_percent=0.68,
                )
                self.setMaximumWidth(25)
                self.hide()

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
                # Match the standalone SendButton height so the two controls
                # sit at the same size when empty.
                self.min_height = 30
                self.setMinimumHeight(self.min_height)

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
                self.document().documentLayout().documentSizeChanged.connect(
                    lambda _: self.on_resize())

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
                    return  # We handle the event, no need to pass it to the base class

                if key == Qt.Key.Key_Enter or key == Qt.Key.Key_Return:
                    if mod != Qt.KeyboardModifier.ShiftModifier:
                        if self.toPlainText().strip() == '':
                            return

                        workflow = self.parent.parent.workflow
                        if not get_run_manager().is_running(workflow.context_id):
                            self.enterPressed.emit()
                            return

                super().keyPressEvent(event)

            def sizeHint(self):
                content_height = max(
                    self.min_height,
                    min(700, self.document().size().height()),
                )
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
                # with no message or parameter inputs, the button just runs
                inputs = self.parent  # params input is built after this button
                is_run = not is_generating and hasattr(inputs, 'workflow_params_input') \
                    and inputs.message_text.isHidden() and inputs.workflow_params_input.isHidden()
                self.setText('Run' if is_run else '')
                if is_run:
                    self.setIcon(QIcon())
                    return
                if is_generating:
                    icon_iden = 'stop'
                elif self._next_member_is_live():
                    icon_iden = 'mic'  # running the member starts the live conversation
                else:
                    icon_iden = 'send'
                pixmap = colorize_pixmap(QPixmap(f":/resources/icon-{icon_iden}.png"))
                self.setIconPixmap(pixmap)

            def _next_member_is_live(self):
                workflow = getattr(self.parent.parent, 'workflow', None)
                member = workflow.next_expected_member() if workflow else None
                return member is not None and member.config.get('_TYPE', 'agent') == 'live_agent'

            def set_style_mode(self, joined=True):
                """Set stylesheet based on whether button is joined with message text or standalone"""
                set_style_property(self, 'joined', joined)
                if not joined:
                    self.setFixedHeight(50)

    class MemberChatBar(ConfigFields):
        """Edits the fields of the chat's member named by its settings
        class `chat_bar_keys`, taken from its `chat_bar_page` schema."""
        def __init__(self, parent):
            super().__init__(parent=parent, flow_rows=True)
            self.propagate_config = False
            self.conf_namespace = 'chat'
            self.member = None
            self.settings_class = None
            self.hide()

        def resizeEvent(self, event):
            super().resizeEvent(event)
            # splitters size by minimum height, which ignores wrapped rows
            self.setMinimumHeight(self.heightForWidth(self.width()))

        def find_member(self):
            workflow_settings = self.parent.workflow_settings
            if not workflow_settings.can_simplify_view():
                return None
            members = [
                m for m in workflow_settings.members_in_view.values()
                if m.member_type != 'user'
            ]
            return members[0] if len(members) == 1 else None

        def workflow_editor_visible(self):
            chattable = self.parent
            return chattable.show_workflow \
                and not chattable.workflow_settings.splitter.isHidden()

        @override
        def load(self):
            if not self.parent.show_member_bar or self.workflow_editor_visible():
                self.member = None
                self.hide()
                return
            self.member = self.find_member()
            settings_class = None
            if self.member:
                settings_class = get_member_settings_class(
                    self.member.member_type)
            page_class = getattr(settings_class, 'chat_bar_page', None)
            if page_class is None:
                self.member = None
                self.hide()
                return

            if settings_class is not self.settings_class:
                self.settings_class = settings_class
                self.schema = [
                    dict(param_dict, row_key=0)
                    for param_dict in page_class.schema
                    if self.param_key(param_dict)
                    in settings_class.chat_bar_keys
                ]
                self.build_schema()

            self.load_config(self.member.member_config)
            super().load()
            self.show()

        @staticmethod
        def param_key(param_dict):
            return convert_to_safe_case(
                param_dict.get('key', param_dict['text'].lower()))

        def save_config(self):
            member = self.member
            for param_dict in self.schema:
                member.member_config.pop(
                    f'{self.conf_namespace}.{self.param_key(param_dict)}',
                    None)
            member.member_config.update(self.config)
            if member.linked_id:
                save_linked_config(member.linked_id, member.member_config)

            workflow_settings = self.parent.workflow_settings
            workflow_settings.update_config()

            member_config_widget = workflow_settings.member_config_widget
            shown_id = getattr(member_config_widget.config_widget,
                               'member_id', None)
            if shown_id == member.id:
                member_config_widget.display_member(member=member)

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
