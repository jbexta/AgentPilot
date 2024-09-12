from PySide6.QtWidgets import QHBoxLayout, QPushButton, QVBoxLayout, QMessageBox

import src.system.base
from src.gui.config import ConfigFields, ConfigTabs, ConfigDBTree, ConfigWidget, ModelComboBox
from src.gui.widgets import IconButton
from src.system.plugins import get_plugin_class
from src.utils.helpers import display_messagebox
from src.utils.reset import reset_models


class Page_Models_Settings(ConfigDBTree):
    def __init__(self, parent):
        super().__init__(
            parent=parent,
            db_table='apis',
            propagate=False,
            query="""
                SELECT
                    name,
                    id,
                    provider_plugin,
                    client_key,
                    api_key
                FROM apis
                ORDER BY name""",
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
            add_item_prompt=('Add API', 'Enter a name for the API:'),
            del_item_prompt=('Delete API', 'Are you sure you want to delete this API?'),
            readonly=False,
            layout_type=QVBoxLayout,
            config_widget=self.Models_Tab_Widget(parent=self),
            tree_height=300,
            # tree_width=500,
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
        res = display_messagebox(
            icon=QMessageBox.Question,
            text="This will reset your APIs and models to the latest version.\nAll model parameters will be reset\nAPI keys will be preserved\nAre you sure you want to continue?",
            title="Reset APIs and models",
            buttons=QMessageBox.Yes | QMessageBox.No,
        )

        if res != QMessageBox.Yes:
            return

        reset_models()
        self.on_edited()
        self.load()

        display_messagebox(
            icon=QMessageBox.Information,
            title="Synced models",
            text="Models synced successfully",
        )

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
            provider_class = get_plugin_class('Provider', provider_name)  # , dict(parent=self))
            if not provider_class:
                if provider_name:
                    display_messagebox(
                        icon=QMessageBox.Warning,
                        text=f"Provider plugin '{provider_name}' not found",
                        title="Error",
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

            for typ in ['Chat', 'Voice']:
                self.pages[typ].pages['Models'].folder_key = getattr(self.provider, 'folder_key', None)

                type_model_params_class = getattr(self.provider, f'{typ}ModelParameters', None)
                if type_model_params_class:
                    self.pages[typ].pages['Models'].config_widget.pages['Parameters'].schema = type_model_params_class \
                        (None).schema
                    self.pages[typ].pages['Models'].config_widget.pages['Parameters'].build_schema()

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
                self.pages = {
                    'Models': self.Tab_Chat_Models(parent=self),
                    'Config': self.Tab_Chat_Config(parent=self),
                }

            class Tab_Chat_Models(ConfigDBTree):
                def __init__(self, parent):
                    super().__init__(
                        parent=parent,
                        db_table='models',
                        kind='CHAT',
                        query="""
                            SELECT
                                name,
                                id,
                                folder_id
                            FROM models
                            WHERE api_id = ?
                                AND kind = ?
                            ORDER BY name""",
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
                        add_item_prompt=('Add Model', 'Enter a name for the model:'),
                        del_item_prompt=('Delete Model', 'Are you sure you want to delete this model?'),
                        layout_type=QHBoxLayout,
                        readonly=False,
                        config_widget=self.Chat_Model_Params_Tabs(parent=self),
                        tree_header_hidden=True,
                        tree_width=150,
                        propagate=False,
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

                def on_item_selected(self):
                    super().on_item_selected()
                    self.config_widget.content.setCurrentIndex(0)

                class Chat_Model_Params_Tabs(ConfigTabs):
                    def __init__(self, parent):
                        super().__init__(parent=parent, hide_tab_bar=True)

                        self.pages = {
                            'Parameters': self.Chat_Config_Parameters_Widget(parent=self),
                            'Finetune': self.Chat_Config_Finetune_Widget(parent=self),
                        }

                    class Chat_Config_Parameters_Widget(ConfigFields):
                        def __init__(self, parent):
                            super().__init__(parent=parent)
                            self.parent = parent
                            self.schema = []

                    class Chat_Config_Finetune_Widget(ConfigWidget):
                        def __init__(self, parent):
                            super().__init__(parent=parent)
                            self.parent = parent
                            self.propagate = False

                            self.layout = QVBoxLayout(self)
                            self.btn_cancel_finetune = QPushButton('Cancel')
                            self.btn_cancel_finetune.setFixedWidth(150)
                            self.btn_proceed_finetune = QPushButton('Finetune')
                            self.btn_proceed_finetune.setFixedWidth(150)
                            h_layout = QHBoxLayout()
                            h_layout.addWidget(self.btn_cancel_finetune)
                            h_layout.addStretch(1)
                            h_layout.addWidget(self.btn_proceed_finetune)

                            self.layout.addStretch(1)
                            self.layout.addLayout(h_layout)
                            self.btn_cancel_finetune.clicked.connect(self.cancel_finetune)

                        def cancel_finetune(self):
                            # switch to parameters tab
                            self.parent.content.setCurrentIndex(0)

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
                        db_table='models',
                        kind='VOICE',
                        query="""
                            SELECT
                                name,
                                id,
                                folder_id
                            FROM models
                            WHERE api_id = ?
                                AND kind = ?
                            ORDER BY name""",
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
                        add_item_prompt=('Add Model', 'Enter a name for the model:'),
                        del_item_prompt=('Delete Model', 'Are you sure you want to delete this model?'),
                        layout_type=QHBoxLayout,
                        readonly=False,
                        config_widget=self.Voice_Model_Params_Tabs(parent=self),
                        tree_header_hidden=True,
                        tree_width=150,
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