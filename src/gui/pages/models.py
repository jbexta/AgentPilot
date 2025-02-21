
from src.gui.config import ConfigFields, ConfigTabs, ConfigDBTree, ModelComboBox
from src.gui.widgets import IconButton, find_main_widget
from src.system.plugins import get_plugin_class
from src.utils.helpers import display_message_box, display_message
from src.utils.reset import reset_models

from PySide6.QtWidgets import QMessageBox


class Page_Models_Settings(ConfigDBTree):
    def __init__(self, parent):
        super().__init__(
            parent=parent,
            table_name='apis',
            query="""
                SELECT
                    name,
                    id,
                    provider_plugin,
                    client_key,
                    api_key
                FROM apis
                ORDER BY pinned DESC, name""",
            schema=[
                {
                    'text': 'Provider',
                    'key': 'name',
                    'type': str,
                    'width': 150,
                },
                {
                    'text': 'id',
                    'key': 'id',
                    'type': int,
                    'visible': False,
                },
                {
                    'text': 'Provider',
                    'key': 'provider_plugin',
                    'type': str,
                    'width': 100,
                    'visible': False,
                },
                {
                    'text': 'Client Key',
                    'key': 'client_key',
                    'type': str,
                    'width': 100,
                },
                {
                    'text': 'API Key',
                    'type': str,
                    'encrypt': True,
                    'stretch': True,
                },
            ],
            add_item_options={'title': 'Add API', 'prompt': 'Enter a name for the API:'},
            del_item_options={'title': 'Delete API', 'prompt': 'Are you sure you want to delete this API?'},
            readonly=False,
            layout_type='vertical',
            config_widget=self.Models_Tab_Widget(parent=self),
        )

    def after_init(self):
        btn_sync_models = IconButton(
            parent=self.tree_buttons,
            icon_path=':/resources/icon-refresh.png',
            tooltip='Sync models',
            size=18,
        )
        btn_sync_models.clicked.connect(self.sync_models)
        self.tree_buttons.add_button(btn_sync_models, 'btn_sync_models')

    def sync_models(self):
        res = display_message_box(
            icon=QMessageBox.Question,
            text="This will reset your APIs and models to the latest version.\nThis might be up to date and you may need to add your models manually\nAll model parameters will be reset\nAPI keys will be preserved\nAre you sure you want to continue?",
            title="Reset APIs and models",
            buttons=QMessageBox.Yes | QMessageBox.No,
        )

        if res != QMessageBox.Yes:
            return

        reset_models()
        self.on_edited()
        self.load()

        display_message(self, 'Models synced successfully', 'Success')

    def on_edited(self):
        from src.system.base import manager
        manager.apis.load()
        manager.providers.load()
        for model_combobox in self.parent.main.findChildren(ModelComboBox):
            model_combobox.load()

    class Models_Tab_Widget(ConfigTabs):
        def __init__(self, parent):
            super().__init__(parent=parent)
            self.provider = None
            self.pages = {
                'Chat': self.Tab_Chat(parent=self),
                'Voice': self.Tab_Voice(parent=self),
                'Speech': self.Tab_Voice(parent=self),
                'Image': self.Tab_Voice(parent=self),
                'Embedding': self.Tab_Voice(parent=self),
            }

        def load_config(self, json_config=None):
            """Called when parent tree item is selected"""
            super().load_config(json_config)

            # refresh tabs
            provider_name = self.parent.tree.get_column_value(2)
            provider_class = get_plugin_class('Provider', provider_name)
            if not provider_class:
                if provider_name:
                    display_message(
                        self,
                        f"Provider plugin '{provider_name}' not found",
                        icon=QMessageBox.Warning,
                    )
                return

            api_id = self.parent.get_selected_item_id()
            self.provider = provider_class(
                parent=self,
                api_id=api_id,
            )
            visible_tabs = self.provider.visible_tabs

            for i, tab in enumerate(self.pages):
                self.content.tabBar().setTabVisible(i, tab in visible_tabs)

            # if api_id == 4:
            #     self.provider.visible_tabs = ['Chat', 'Speech']
            for typ in ['Chat']:  # , 'Speech', 'Voice']:
                self.pages[typ].pages['Models'].folder_key = getattr(self.provider, 'folder_key', None)

                type_model_params_class = getattr(self.provider, f'{typ}ModelParameters', None)
                if type_model_params_class: #!51!#
                    self.pages[typ].pages['Models'].schema_overrides = getattr(self.provider, 'schema_overrides', {})
                    self.pages[typ].pages['Models'].config_widget.set_schema(type_model_params_class(None).schema)

                type_config_class = getattr(self.provider, f'{typ}Config', None)
                self.pages[typ].content.tabBar().setTabVisible(1, (type_config_class is not None))
                if type_config_class:
                    self.pages[typ].pages['Config'].schema = type_config_class(None).schema
                    self.pages[typ].pages['Config'].build_schema()

                # refresh sync button
                sync_func_name = f'sync_{typ.lower()}'
                sync_btn_visible = hasattr(self.provider, sync_func_name)
                sync_btn_widget = self.pages[typ].pages['Models'].tree_buttons.btn_sync
                sync_btn_widget.setVisible(sync_btn_visible)
                try:
                    sync_btn_widget.clicked.disconnect()
                except RuntimeError:
                    pass  # no connection exists

                if sync_btn_visible:
                    sync_btn_widget.clicked.connect(getattr(self.provider, sync_func_name))

            first_vis_index = next((i for i in range(len(self.pages)) if self.content.tabBar().isTabVisible(i)), 0)
            self.content.setCurrentIndex(first_vis_index)

        class Tab_Chat(ConfigTabs):
            def __init__(self, parent):
                super().__init__(parent=parent)
                self.type_model_params_class = None
                self.pages = {
                    'Models': self.Tab_Chat_Models(parent=self),
                    'Config': self.Tab_Chat_Config(parent=self),
                }

            class Tab_Chat_Models(ConfigDBTree):
                def __init__(self, parent):
                    super().__init__(
                        parent=parent,
                        table_name='models',
                        kind='CHAT',
                        query="""
                            SELECT
                                name,
                                id,
                                folder_id
                            FROM models
                            WHERE api_id = ?
                                AND kind = ?
                            ORDER BY pinned DESC, name""",
                        query_params=(
                            lambda: parent.parent.parent.get_selected_item_id(),
                            lambda: self.kind,
                        ),
                        schema=[
                            {
                                'text': 'Name',
                                'key': 'name',
                                'type': str,
                                'stretch': True,
                            },
                            {
                                'text': 'id',
                                'key': 'id',
                                'type': int,
                                'visible': False,
                            },
                        ],
                        add_item_options={'title': 'Add Model', 'prompt': 'Enter a name for the model:'},
                        del_item_options={'title': 'Delete Model', 'prompt': 'Are you sure you want to delete this model?'},
                        layout_type='horizontal',
                        readonly=False,
                        config_widget=self.Chat_Model_Params_Tabs(parent=self),
                        tree_header_hidden=True,
                    )

                    # add sync button
                    btn_sync = IconButton(
                        parent=self.tree_buttons,
                        icon_path=':/resources/icon-refresh.png',
                        tooltip='Sync models',
                        size=18,
                    )
                    self.tree_buttons.add_button(btn_sync, 'btn_sync')

                def on_edited(self):
                    # # bubble upwards towards root until we find `reload_models` method
                    parent = self.parent
                    while parent:
                        if hasattr(parent, 'on_edited'):
                            parent.on_edited()
                            return
                        parent = getattr(parent, 'parent', None)

                class Chat_Model_Params_Tabs(ConfigFields):
                    def __init__(self, parent):
                        super().__init__(parent=parent)
                        self.parent = parent
                        self.schema = []

            class Tab_Chat_Config(ConfigFields):
                def __init__(self, parent):
                    super().__init__(parent=parent)
                    self.label_width = 125
                    self.schema = []

        class Tab_Voice(ConfigTabs):
            def __init__(self, parent):
                super().__init__(parent=parent)

                self.pages = {
                    'Models': self.Tab_Voice_Models(parent=self),
                    'Config': self.Tab_Voice_Config(parent=self),
                }

            class Tab_Voice_Models(ConfigDBTree):
                def __init__(self, parent):
                    super().__init__(
                        parent=parent,
                        table_name='models',
                        kind='VOICE',
                        query="""
                            SELECT
                                name,
                                id,
                                folder_id
                            FROM models
                            WHERE api_id = ?
                                AND kind = ?
                            ORDER BY pinned DESC, name""",
                        query_params=(
                            lambda: parent.parent.parent.get_selected_item_id(),
                            lambda: self.kind,
                        ),
                        schema=[
                            {
                                'text': 'Name',
                                'key': 'name',
                                'type': str,
                                'stretch': True,
                            },
                            {
                                'text': 'id',
                                'key': 'id',
                                'type': int,
                                'visible': False,
                            },
                        ],
                        add_item_options={'title': 'Add Model', 'prompt': 'Enter a name for the model:'},
                        del_item_options={'title': 'Delete Model', 'prompt': 'Are you sure you want to delete this model?'},
                        layout_type='horizontal',
                        readonly=False,
                        config_widget=self.Voice_Model_Params_Tabs(parent=self),
                        tree_header_hidden=True,
                    )

                    # add sync button
                    btn_sync = IconButton(
                        parent=self.tree_buttons,
                        icon_path=':/resources/icon-refresh.png',
                        tooltip='Sync models',
                        size=18,
                    )
                    self.tree_buttons.add_button(btn_sync, 'btn_sync')

                def on_edited(self):
                    # # bubble upwards towards root until we find `reload_models` method
                    parent = self.parent
                    while parent:
                        if hasattr(parent, 'on_edited'):
                            parent.on_edited()
                            return
                        parent = getattr(parent, 'parent', None)

                class Voice_Model_Params_Tabs(ConfigTabs):
                    def __init__(self, parent):
                        super().__init__(parent=parent, hide_tab_bar=True)

                        self.pages = {
                            'Parameters': self.Voice_Config_Parameters_Widget(parent=self),
                            # 'Finetune': self.Chat_Config_Finetune_Widget(parent=self),
                        }

                    class Voice_Config_Parameters_Widget(ConfigFields):
                        def __init__(self, parent):
                            super().__init__(parent=parent)
                            self.parent = parent
                            self.schema = []

            class Tab_Voice_Config(ConfigFields):
                def __init__(self, parent):
                    super().__init__(parent=parent)
                    self.label_width = 125
                    self.schema = []