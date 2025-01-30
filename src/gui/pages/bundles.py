
from src.gui.config import ConfigDBTree, ConfigJoined, ConfigJsonDBTree


class Page_Bundle_Settings(ConfigDBTree):
    def __init__(self, parent):
        super().__init__(
            parent=parent,
            table_name='bundles',
            query="""
                SELECT
                    name,
                    id,
                    folder_id
                FROM bundles
                ORDER BY pinned DESC, ordr, name""",
            schema=[
                {
                    'text': 'Modules',
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
            add_item_options={'title': 'Add bundle', 'prompt': 'Enter a name for the bundle:'},
            del_item_options={'title': 'Delete bundle', 'prompt': 'Are you sure you want to delete this bundle?'},
            folder_key='bundles',
            readonly=False,
            layout_type='vertical',
            tree_header_hidden=True,
            config_widget=self.Bundle_Config_Widget(parent=self),
            searchable=True,
            default_item_icon=':/resources/icon-jigsaw-solid.png',
        )
        self.icon_path = ":/resources/icon-jigsaw.png"
        self.try_add_breadcrumb_widget(root_title='Bundles')
        self.splitter.setSizes([400, 1000])

    class Bundle_Config_Widget(ConfigJoined):
        def __init__(self, parent):
            super().__init__(parent=parent, layout_type='horizontal')
            self.widgets = [
                self.Bundle_Blocks(parent=self),
                self.Bundle_Entities(parent=self),
                self.Bundle_Tools(parent=self),
                self.Bundle_Modules(parent=self),
                # self.Module_Config_Fields(parent=self),
            ]

        class Bundle_Blocks(ConfigJsonDBTree):
            def __init__(self, parent):
                super().__init__(
                    parent=parent,
                    add_item_options={'title': 'NA', 'prompt': 'NA'},
                    del_item_options={'title': 'NA', 'prompt': 'NA'},
                    # tree_header_hidden=True,
                    table_name='blocks',
                    key_field='id',
                    item_icon_path=':/resources/icon-block.png',
                    show_fields=[
                        'name',
                        'id',  # ID ALWAYS LAST
                    ],
                    readonly=True
                )
                self.conf_namespace = 'blocks'
                self.schema = [
                    {
                        'text': 'Blocks',
                        'type': str,
                        'width': 175,
                        'default': '',
                    },
                    {
                        'text': 'id',
                        'visible': False,
                        'default': '',
                    },
                ]

        class Bundle_Entities(ConfigJsonDBTree):
            def __init__(self, parent):
                super().__init__(
                    parent=parent,
                    add_item_options={'title': 'NA', 'prompt': 'NA'},
                    del_item_options={'title': 'NA', 'prompt': 'NA'},
                    # tree_header_hidden=True,
                    table_name='entities',
                    key_field='id',
                    item_icon_path=':/resources/icon-agent-solid.png',
                    show_fields=[
                        'name',
                        'id',  # ID ALWAYS LAST
                    ],
                    readonly=True
                )
                self.conf_namespace = 'agents'
                self.schema = [
                    {
                        'text': 'Agents',
                        'type': str,
                        'width': 175,
                        'default': '',
                    },
                    {
                        'text': 'id',
                        'visible': False,
                        'default': '',
                    },
                ]

        class Bundle_Modules(ConfigJsonDBTree):
            def __init__(self, parent):
                super().__init__(
                    parent=parent,
                    add_item_options={'title': 'NA', 'prompt': 'NA'},
                    del_item_options={'title': 'NA', 'prompt': 'NA'},
                    # tree_header_hidden=True,
                    table_name='modules',
                    key_field='id',
                    item_icon_path=':/resources/icon-jigsaw-solid.png',
                    show_fields=[
                        'name',
                        'id',  # ID ALWAYS LAST
                    ],
                    readonly=True
                )
                self.conf_namespace = 'modules'
                self.schema = [
                    {
                        'text': 'Modules',
                        'type': str,
                        'width': 175,
                        'default': '',
                    },
                    {
                        'text': 'id',
                        'visible': False,
                        'default': '',
                    },
                ]

        class Bundle_Tools(ConfigJsonDBTree):
            def __init__(self, parent):
                super().__init__(
                    parent=parent,
                    add_item_options={'title': 'NA', 'prompt': 'NA'},
                    del_item_options={'title': 'NA', 'prompt': 'NA'},
                    # tree_header_hidden=True,
                    table_name='tools',
                    key_field='uuid',
                    item_icon_path=':/resources/icon-tool-small.png',
                    show_fields=[
                        'name',
                        'uuid',  # ID ALWAYS LAST
                    ],
                    readonly=True
                )
                self.conf_namespace = 'tools'
                self.schema = [
                    {
                        'text': 'Tools',
                        'type': str,
                        'width': 175,
                        'default': '',
                    },
                    {
                        'text': 'id',
                        'visible': False,
                        'default': '',
                    },
                ]

        # class Module_Config_Fields(ConfigFields):
        #     def __init__(self, parent):
        #         super().__init__(parent=parent)
        #         self.schema = [
        #             {
        #                 'text': 'Load on startup',
        #                 'type': bool,
        #                 'default': True,
        #                 'row_key': 0,
        #             },
        #             {
        #                 'text': 'Data',
        #                 'type': str,
        #                 'default': '',
        #                 'num_lines': 2,
        #                 'stretch_x': True,
        #                 'stretch_y': True,
        #                 'highlighter': 'PythonHighlighter',
        #                 'gen_block_folder_name': 'Generate page',
        #                 'label_position': None,
        #             },
        #         ]
