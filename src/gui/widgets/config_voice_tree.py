from typing_extensions import override

from src.gui.widgets.config_db_tree import ConfigDBTree
from src.utils import sql


class ConfigVoiceTree(ConfigDBTree):
    """At the top left is an api provider combobox, below that is the tree of voices."""
    def __init__(self, parent, **kwargs):
        super().__init__(
            parent=parent,
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
            tree_header_hidden=True,
            readonly=True,
        )

    def after_init(self):
        # take the tree from the layout
        # tree_layout = self.tree_layout
        self.tree_layout.setSpacing(5)
        tree = self.tree_layout.itemAt(0).widget()

        # add the api provider combobox
        from src.gui.util import APIComboBox
        self.api_provider = APIComboBox(with_model_kind='VOICE')
        self.api_provider.currentIndexChanged.connect(self.load)

        # add spacing
        self.tree_layout.insertWidget(0, self.api_provider)

        # add the tree back to the layout
        self.tree_layout.addWidget(tree)

    @override
    def load(self, select_id=None, append=False):
        """
        Loads the QTreeWidget with folders and agents from the database.
        """
        api_id = self.api_provider.currentData()
        api_voices = sql.get_results(query="""
            SELECT
                name,
                id
            FROM models
            WHERE api_id = ?
                AND kind = 'VOICE'
            ORDER BY name
        """, params=(api_id,))

        self.tree.load(
            data=api_voices,
            append=append,
            folder_key=None,
            # folder_key=self.folder_key,
            init_select=False,
            readonly=True,
            schema=self.schema,
        )

    def on_cell_edited(self, item):
        pass

    def add_item(self):
        pass

    def delete_item(self):
        pass

    def rename_item(self):
        pass

    def show_context_menu(self):
        pass