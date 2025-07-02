from gui.util import find_main_widget
from gui.widgets.config_db_tree import ConfigDBTree
from gui.widgets.config_fields import ConfigFields


class Page_Role_Settings(ConfigDBTree):
    display_name = 'Roles'
    page_type = 'settings'

    def __init__(self, parent):
        super().__init__(
            parent=parent,
            table_name='roles',
            query="""
                SELECT
                    name,
                    id
                FROM roles
                ORDER BY pinned DESC, name""",
            schema=[
                {
                    'text': 'Roles',
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
            add_item_options={'title': 'Add Role', 'prompt': 'Enter a name for the role:'},
            del_item_options={'title': 'Delete Role', 'prompt': 'Are you sure you want to delete this role?'},
            readonly=False,
            layout_type='horizontal',
            config_widget=self.Role_Config_Widget(parent=self),
            tree_header_hidden=True,
        )

    def on_edited(self):
        from system import manager
        manager.roles.load()
        main = find_main_widget(self)
        main.apply_stylesheet()

    class Role_Config_Widget(ConfigFields):
        def __init__(self, parent):
            super().__init__(parent=parent)
            self.label_width = 175
            self.schema = [
                {
                    'text': 'Show bubble',
                    'type': bool,
                    'default': True,
                },
                {
                    'text': 'Bubble bg color',
                    'type': 'color_picker',
                    'default': '#3b3b3b',
                },
                {
                    'text': 'Bubble text color',
                    'type': 'color_picker',
                    'default': '#c4c4c4',
                },
                {
                    'text': 'Bubble image size',
                    'type': int,
                    'minimum': 3,
                    'maximum': 100,
                    'default': 25,
                },
                {
                    'text': 'Module',
                    'type': 'module',
                    'module_type': 'Bubbles',
                    'items_have_keys': False,
                    'default': 'Default',
                    'row_key': 0,
                },
            ]
