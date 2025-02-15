import json
import os

from PySide6.QtWidgets import *
from PySide6.QtCore import QRunnable, Slot, QFileInfo
from PySide6.QtGui import Qt, QIcon, QPixmap

from src.gui.bubbles import MessageCollection
from src.members.workflow import WorkflowSettings
from src.utils.helpers import path_to_pixmap, display_message_box, block_signals, get_avatar_paths_from_config, \
    merge_config_into_workflow_config, apply_alpha_to_hex, convert_model_json_to_obj, params_to_schema
from src.utils import sql

from src.members.workflow import Workflow
from src.gui.widgets import IconButton
from src.gui.config import CHBoxLayout, CVBoxLayout, ConfigFields, save_table_config


class Page_Chat(QWidget):
    def __init__(self, parent):
        super().__init__(parent=parent)

        self.main = parent
        self.icon_path = ':/resources/icon-chat.png'
        self.workspace_window = None
        self.workflow = None

        self.layout = CVBoxLayout(self)

        self.top_bar = self.Top_Bar(self)
        self.workflow_params_input = self.WorkflowParamsInput(self)

        self.layout.addWidget(self.top_bar)
        self.layout.addWidget(self.workflow_params_input)

        self.page_splitter = QSplitter(Qt.Vertical)
        self.page_splitter.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.page_splitter.setChildrenCollapsible(False)

        self.layout.addWidget(self.page_splitter)

        self.workflow = Workflow(main=self.main, get_latest=True, chat_page=self)
        self.workflow_settings = self.ChatWorkflowSettings(self)
        self.workflow_settings.hide()
        self.page_splitter.addWidget(self.workflow_settings)
        self.workflow.workflow_settings = self.workflow_settings

        self.message_collection = MessageCollection(self)

        self.page_splitter.addWidget(self.message_collection)
        self.page_splitter.setSizes([350, 1000])

        self.attachment_bar = self.AttachmentBar(self)
        self.layout.addWidget(self.attachment_bar)

    def load(self, also_config=True):
        if sql.get_scalar("SELECT COUNT(*) FROM contexts WHERE id = ?", (self.workflow.context_id,)) == 0:
            self.workflow = Workflow(main=self.main, get_latest=True, chat_page=self)  # todo dirty fix for when the context is deleted but the page is still open

        self.workflow.load()
        if also_config:
            self.workflow_settings.load_config(self.workflow.config)
            self.workflow_settings.load()

        self.workflow.message_history.load()
        self.message_collection.load()

        self.workflow_params_input.load()

    def get_selected_item_id(self):  # hack
        return self.workflow.context_id

    def update_config(self):
        self.save_config()

    def save_config(self):
        item_id = self.get_selected_item_id()
        config = self.workflow_settings.get_config()

        save_table_config(
            ref_widget=self,
            table_name='contexts',
            item_id=item_id,
            value=config,
        )
        self.workflow.load_config(config)
        self.workflow_settings.load_config(config)
        self.workflow.load()
        self.workflow_params_input.load()
        self.message_collection.load()

    class ChatWorkflowSettings(WorkflowSettings):
        def __init__(self, parent):
            super().__init__(parent=parent)

    class Top_Bar(QWidget):
        def __init__(self, parent):
            super().__init__(parent)

            self.parent = parent
            self.setMouseTracking(True)

            self.settings_layout = CVBoxLayout(self)

            self.input_container = QWidget()
            self.input_container.setFixedHeight(44)
            self.topbar_layout = CHBoxLayout(self.input_container)
            self.topbar_layout.setContentsMargins(6, 0, 0, 0)

            self.settings_layout.addWidget(self.input_container)

            self.profile_pic_label = QLabel(self)
            self.profile_pic_label.setFixedSize(44, 44)
            # self.profile_pic_label.enterEvent = lambda event: self.parent.main.show_side_bubbles()
            # self.profile_pic_label.leaveEvent = lambda event: self.parent.main.hide_side_bubbles()

            self.topbar_layout.addWidget(self.profile_pic_label)
            # connect profile label click to method 'open'
            self.profile_pic_label.mousePressEvent = self.agent_name_clicked

            self.agent_name_label = QLabel(self)

            self.lbl_font = self.agent_name_label.font()
            self.lbl_font.setPointSize(15)
            self.agent_name_label.setFont(self.lbl_font)
            self.agent_name_label.mousePressEvent = self.agent_name_clicked
            self.agent_name_label.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)

            self.topbar_layout.addWidget(self.agent_name_label)

            self.title_label = QLineEdit(self)
            self.small_font = self.title_label.font()
            self.small_font.setPointSize(10)
            self.title_label.setFont(self.small_font)

            from src.system.base import manager
            text_color = manager.config.dict.get('display.text_color', '#c4c4c4')
            self.title_label.setStyleSheet(f"QLineEdit {{ color: {apply_alpha_to_hex(text_color, 0.90)}; background-color: transparent; }}"
                                           f"QLineEdit:hover {{ color: {text_color}; }}")
            self.title_label.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
            self.title_label.textChanged.connect(self.title_edited)

            self.topbar_layout.addWidget(self.title_label)

            self.button_container = QWidget()
            self.button_layout = QHBoxLayout(self.button_container)
            self.button_layout.setSpacing(5)

            # Create buttons
            self.btn_prev_context = IconButton(parent=self, icon_path=':/resources/icon-left-arrow.png')
            self.btn_next_context = IconButton(parent=self, icon_path=':/resources/icon-right-arrow.png')

            self.btn_prev_context.clicked.connect(self.previous_context)
            self.btn_next_context.clicked.connect(self.next_context)

            self.btn_info = QPushButton()
            self.btn_info.setText('i')
            self.btn_info.setFixedSize(25, 25)
            self.btn_info.clicked.connect(self.showContextInfo)

            self.button_layout.addWidget(self.btn_prev_context)
            self.button_layout.addWidget(self.btn_next_context)
            self.button_layout.addWidget(self.btn_info)

            # Add the container to the top bar layout
            self.topbar_layout.addWidget(self.button_container)

            self.button_container.hide()

        def load(self):
            self.agent_name_label.setText(self.parent.workflow.chat_name)
            with block_signals(self.title_label):
                self.title_label.setText(self.parent.workflow.chat_title)
                self.title_label.setCursorPosition(0)

            member_paths = get_avatar_paths_from_config(self.parent.workflow.config)
            member_pixmap = path_to_pixmap(member_paths, diameter=35)
            self.profile_pic_label.setPixmap(member_pixmap)

        def title_edited(self, text):
            sql.execute(f"""
                UPDATE contexts
                SET name = ?
                WHERE id = ?
            """, (text, self.parent.workflow.context_id,))
            self.parent.workflow.chat_title = text

        def showContextInfo(self):
            context_id = self.parent.workflow.context_id
            leaf_id = self.parent.workflow.leaf_id
            branches = self.parent.workflow.message_history.branches

            display_message_box(
                icon=QMessageBox.Warning,
                text=f"Context ID: {context_id}\nLeaf ID: {leaf_id}\nBranches: {branches}",
                title="Context Info",
                buttons=QMessageBox.Ok,
            )

        def next_context(self):
            next_context_id = sql.get_scalar("""
                SELECT
                    id
                FROM contexts
                WHERE parent_id IS NULL
                    AND kind = 'CHAT'
                    AND id > ?
                ORDER BY
                    id
                LIMIT 1;""", (self.parent.workflow.context_id,))

            if next_context_id:
                self.parent.goto_context(next_context_id)
                self.btn_prev_context.setEnabled(True)
            else:
                self.btn_next_context.setEnabled(False)

        def previous_context(self):
            prev_context_id = sql.get_scalar("""
                SELECT
                    id
                FROM contexts
                WHERE parent_id IS NULL
                    AND kind = 'CHAT'
                    AND id < ?
                ORDER BY
                    id DESC
                LIMIT 1;""", (self.parent.workflow.context_id,))
            if prev_context_id:
                self.parent.goto_context(prev_context_id)
                self.btn_next_context.setEnabled(True)
            else:
                self.btn_prev_context.setEnabled(False)

        def enterEvent(self, event):
            self.button_container.show()

        def leaveEvent(self, event):
            self.button_container.hide()

        def agent_name_clicked(self, event):
            if not self.parent.workflow_settings.isVisible():
                self.parent.workflow_settings.show()
                self.parent.workflow_settings.load()
            else:
                self.parent.workflow_settings.hide()

    class WorkflowParamsInput(ConfigFields):
        def __init__(self, parent):
            super().__init__(parent, add_stretch_to_end=False)
            # self.load()

        def load(self):
            workflow_params = self.parent.workflow.config.get('params', [])
            param_schema = params_to_schema(workflow_params)
            if param_schema != self.schema:
                self.schema = param_schema
                self.build_schema()

            # with block_signals(self):
            self.clear_fields()
            # update size
            self.updateGeometry()
            super().load()

        def save_config(self):
            params_config = self.get_config()
            self.parent.workflow.params = params_config


    class AttachmentBar(QWidget):
        def __init__(self, parent):
            super().__init__(parent)
            self.parent = parent
            self.layout = CVBoxLayout(self)

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
                    thumbnail_pixmap = QPixmap(filepath).scaled(16, 16, Qt.KeepAspectRatio)
                    self.icon_label.setPixmap(thumbnail_pixmap)

                else:
                    # show file icon
                    icon_provider = QFileIconProvider()
                    icon = icon_provider.icon(QFileInfo(filepath))
                    self.icon_label.setPixmap(icon.pixmap(16, 16))

                self.layout.addWidget(self.icon_label)
                self.layout.addWidget(self.text_label)

                remove_button = IconButton(parent=self, icon_path=':/resources/close.png')
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

    def on_send_message(self):
        if self.workflow.responding:
            self.workflow.behaviour.stop()
        else:
            self.ensure_visible()
            next_expected_member = self.workflow.next_expected_member()
            if not next_expected_member:
                return

            next_expected_member_type = next_expected_member.config.get('_TYPE', 'agent')
            as_member_id = next_expected_member.member_id

            if next_expected_member_type == 'user':
                text = self.main.message_text.toPlainText()
                self.message_collection.send_message(text, clear_input=True, as_member_id=as_member_id)
            else:
                self.message_collection.run_workflow(from_member_id=next_expected_member.member_id)

    def ensure_visible(self):
        # make sure chat page button is shown
        stacked_widget = self.main.main_menu.content
        index = stacked_widget.indexOf(self)
        current_index = stacked_widget.currentIndex()
        if index != current_index:
            self.main.main_menu.settings_sidebar.page_buttons['Chat'].click()
            self.main.main_menu.settings_sidebar.page_buttons['Chat'].setChecked(True)

    def try_generate_title(self):
        current_title = self.workflow.chat_title
        if current_title != '':
            return

        system_config = self.main.system.config.dict
        auto_title = system_config.get('system.auto_title', True)

        if not auto_title:
            return
        if not self.workflow.message_history.count(incl_roles=('user',)) == 1:
            return

        title_runnable = self.AutoTitleRunnable(self)
        self.main.threadpool.start(title_runnable)

    class AutoTitleRunnable(QRunnable):
        def __init__(self, parent):
            super().__init__()
            self.page_chat = parent

        def run(self):
            from src.system.base import manager
            user_msg = self.page_chat.workflow.message_history.last(incl_roles=('user',))

            conf = self.page_chat.main.system.config.dict
            model_name = conf.get('system.auto_title_model', 'mistral/mistral-large-latest')
            model_obj = convert_model_json_to_obj(model_name)

            prompt = conf.get('system.auto_title_prompt',
                              'Generate a brief and concise title for a chat that begins with the following message:\n\n{user_msg}')
            prompt = prompt.format(user_msg=user_msg['content'])  # todo

            try:
                title = manager.providers.get_scalar(prompt, single_line=True, model_obj=model_obj)
                title = title.replace('\n', ' ').strip("'").strip('"')
                self.page_chat.main.title_update_signal.emit(title)
            except Exception as e:
                e_str = f'Auto title response error, check the model in System settings:\n\n{str(e)}'
                self.page_chat.main.error_occurred.emit(e_str)

    @Slot(str)
    def on_title_update(self, title):
        with block_signals(self.top_bar.title_label):
            self.top_bar.title_label.setText(title)
            self.top_bar.title_label.setCursorPosition(0)
        self.top_bar.title_edited(title)

    def new_context(self, copy_context_id: int = None, entity_id: int = None, entity_table: str = None):
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

        elif entity_id is not None:
            # kinds = {
            #     'entities': 'CHAT',  # todo rename to agents
            #     'blocks': 'BLOCK',
            #     'tools': 'TOOL',
            # }
            config = json.loads(
                sql.get_scalar(f"SELECT config FROM {entity_table} WHERE id = ?",
                               (entity_id,))
            )
            entity_type = config.get('_TYPE', 'agent')  # !! #
            if entity_type == 'workflow':
                sql.execute(f"""
                    INSERT INTO contexts (
                        kind,
                        config
                    )
                    SELECT
                        'CHAT',
                        config
                    FROM {entity_table}
                    WHERE id = ?""", (entity_id,))
            else:
                wf_config = merge_config_into_workflow_config(config, entity_id=entity_id)
                sql.execute("""
                    INSERT INTO contexts
                        (kind, config)
                    VALUES ('CHAT', ?)""", (json.dumps(wf_config),))
        else:
            raise NotImplementedError()

        context_id = sql.get_scalar("SELECT MAX(id) FROM contexts WHERE kind = 'CHAT'")

        user_members = self.workflow.get_members(incl_types=('user',))
        user_member_id = user_members[0].member_id if user_members else '1'

        member_id, preload_msgs = self.get_preload_messages(config)
        for msg_dict in preload_msgs:
            role, content, typ = msg_dict.values()
            m_id = user_member_id if role == 'user' else member_id
            if typ == 'Welcome':
                role = 'welcome'
            sql.execute("""
                INSERT INTO contexts_messages
                    (context_id, member_id, role, msg, embedding_id, log)
                VALUES
                    (?, ?, ?, ?, ?, ?)""",
                (context_id, m_id, role, content, None, ''))

        context_id = sql.get_scalar("SELECT MAX(id) FROM contexts WHERE kind = 'CHAT'")
        self.goto_context(context_id)

    def get_preload_messages(self, config):
        member_type = config.get('_TYPE', 'agent')  # !! #
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

    def goto_context(self, context_id=None):
        from src.members.workflow import Workflow
        self.workflow = Workflow(main=self.main, context_id=context_id, chat_page=self)
        self.load()
