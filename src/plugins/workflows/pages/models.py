from PySide6.QtWidgets import QMessageBox

from gui import system
from gui.fields.model import ModelComboBox
from gui.widgets.config_db_tree import ConfigDBTree
from gui.widgets.config_fields import ConfigFields
from gui.widgets.config_joined import ConfigJoined
from gui.widgets.config_tabs import ConfigTabs
from gui.widgets.multi_preview import MultiPreview
from gui.util import clear_layout, find_ancestor_tree_item_id, find_main
from plugins.workflows.widgets.generate_widget import GenerateWidget
from utils.helpers import block_signals
from utils import sql
from utils.helpers import display_message_box, display_message
from utils.reset import reset_models


class Page_Models_Settings(ConfigDBTree):
    display_name = 'Models'
    page_type = 'settings'  # either 'settings', 'main', or 'any' ('any' means it can be pinned between main and settings)

    def __init__(self, parent):
        super().__init__(
            parent=parent,
            table_name='apis',
            query="""
                SELECT
                    name,
                    id,
                    client_key,
                    api_key
                FROM apis
                ORDER BY 
                    pinned DESC, 
                    api_key != '' DESC, 
                    name""",
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
            config_widget=self.Kinds_Tab_Widget(parent=self),
            extra_tree_buttons=[
                {
                    'text': 'Sync models',
                    'icon_path': ':/resources/icon-refresh.png',
                    'target': self.sync_models,
                },
            ],
        )

    def sync_models(self):
        res = display_message_box(
            icon=QMessageBox.Question,
            text="This will reset your APIs and models to the latest known models.\nAll model parameters will be reset\nAPI keys will be preserved\nAre you sure you want to continue?",
            title="Reset APIs and models",
            buttons=QMessageBox.Yes | QMessageBox.No,
        )

        if res != QMessageBox.Yes:
            return

        reset_models()
        
        self.on_edited()
        self.load()

        display_message('Models synced successfully', 'Success')

    def on_edited(self):
        system.manager.apis.load()
        system.manager.providers.load()
        main = find_main()
        for model_combobox in main.findChildren(ModelComboBox):
            model_combobox.load()
    
    class Kinds_Tab_Widget(ConfigTabs):
        def __init__(self, parent):
            super().__init__(parent=parent)
            self.provider = None
            self.pages = {
                'Chat': self.Tab_Kind(parent=self, kind='CHAT'),
                'Video': self.Tab_Kind(parent=self, kind='VIDEO'),
                'Image': self.Tab_Kind(parent=self, kind='IMAGE'),
                'Audio': self.Tab_Kind(parent=self, kind='AUDIO'),
                'Text': self.Tab_Kind(parent=self, kind='TEXT'),
                '3D': self.Tab_Kind(parent=self, kind='3D'),
            }

        def load_config(self, json_config=None):
            super().load_config(json_config)

            api_id = find_ancestor_tree_item_id(self)
            kinds_in_api = sql.get_results("""
                SELECT DISTINCT kind
                FROM models
				WHERE api_id = ?""", 
                (api_id,), return_type='list'
            )

            with block_signals(self.content, recurse_children=False):
                while self.content.count() > 0:
                    self.content.removeTab(0)

                for tab_name, tab_widget in self.pages.items():
                    is_visible = tab_name.upper() in kinds_in_api
                    if is_visible:
                        self.content.addTab(tab_widget, tab_name)

                if self.content.count() > 0:
                    self.content.setCurrentIndex(0)

        class Tab_Kind(ConfigTabs):
            def __init__(self, parent, kind):
                super().__init__(parent=parent)
                self.kind = kind
                self.pages = {
                    'Models': self.Tab_Kind_Models(parent=self),
                    'Config': self.Tab_Kind_Config(parent=self),
                }
            
            class Tab_Kind_Models(ConfigDBTree):
                def __init__(self, parent):
                    super().__init__(
                        parent=parent,
                        table_name='models',
                        kind=parent.kind,
                        query="""
                            SELECT
                                name,
                                id
                            FROM models
                            WHERE api_id = :api_id
                                AND kind = :kind
                            ORDER BY pinned DESC, name COLLATE NOCASE""",
                        query_params={
                            'api_id': lambda: find_ancestor_tree_item_id(self.parent),
                        },
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
                        config_widget=self.Kind_Model_Config(parent=self),
                        tree_header_hidden=True,
                    )

                def update_name(self):
                    pass

                def on_edited(self):
                    parent = self.parent
                    while parent:
                        if hasattr(parent, 'on_edited'):
                            parent.on_edited()
                            return
                        parent = getattr(parent, 'parent', None)

                def on_item_selected(self):
                    model_id = self.get_selected_item_id()
                    if not model_id:
                        clear_layout(self.config_widget.model_params.layout)
                        return

                    # todo clean & dedupe
                    model_metadata = sql.get_scalar("""
                        SELECT metadata
                        FROM models
                        WHERE id = ?
                    """, (model_id,), load_json=True)

                    model_input_schema = model_metadata.get('input_schema', [])

                    self.config_widget.model_params.schema = model_input_schema
                    self.config_widget.model_params.build_schema()
                    super().on_item_selected()

                class Kind_Model_Config(ConfigJoined):
                    def __init__(self, parent):
                        super().__init__(parent=parent)
                        self.model_params = self.Kind_Model_Params(parent=self)
                        self.multi_preview = MultiPreview(parent=self)
                        self.widgets = [
                            self.Kind_Model_Header(parent=self),
                            self.model_params,
                            self.GenerateFields(parent=self),
                            self.multi_preview,
                        ]

                    class Kind_Model_Header(ConfigFields):
                        def __init__(self, parent):
                            super().__init__(parent=parent)  # , add_stretch_to_end=False)
                            self.schema = [
                                {
                                    'text': 'Model name',
                                    'key': '_model_name',
                                    'type': str,
                                },
                            ]

                    class GenerateFields(GenerateWidget):
                        def get_current_model(self):
                            config_joined = self.parent
                            header = config_joined.widgets[0]
                            model_name = header._model_name_wgt.get_value()
                            if not model_name:
                                return None

                            kind = self._get_kind()
                            provider_plugin = self._get_provider_plugin()
                            model_params = config_joined.model_params.get_config()

                            return {
                                'model_name': model_name,
                                'kind': kind,
                                'provider': provider_plugin,
                                'model_params': model_params,
                            }

                        def _get_kind(self):
                            widget = self.parent
                            while widget is not None:
                                if hasattr(widget, 'kind'):
                                    return widget.kind
                                widget = getattr(widget, 'parent', None)
                            return None

                        def _get_provider_plugin(self):
                            model_id = self._get_model_id()
                            if not model_id:
                                return None
                            return sql.get_scalar("""
                                SELECT provider_plugin
                                FROM models
                                WHERE id = ?
                            """, (model_id,))

                        def _get_model_id(self):
                            widget = self.parent
                            while widget is not None:
                                if hasattr(widget, 'get_selected_item_id'):
                                    return widget.get_selected_item_id()
                                widget = getattr(widget, 'parent', None)
                            return None

                    class Kind_Model_Params(ConfigFields):
                        def __init__(self, parent):
                            super().__init__(
                                parent=parent,
                                auto_label_width=True,
                            )
                            self.schema = []

            class Tab_Kind_Config(ConfigFields):
                def __init__(self, parent):
                    super().__init__(
                        parent=parent,
                        auto_label_width=True
                    )
                    # self.provider_name = None
                    self.schema = []
