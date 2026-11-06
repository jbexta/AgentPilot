from gui.widgets.config_json_db_tree import ConfigJsonDBTree
from utils.helpers import set_module_type


@set_module_type(module_type='Widgets')
class AgentTools(ConfigJsonDBTree):
    """The app and workflow tools selected for a coding agent, served to it
    by ``AcpAgent.app_tools``."""

    def __init__(self, parent):
        super().__init__(
            parent=parent,
            add_item_options={'title': 'NA', 'prompt': 'NA'},
            del_item_options={'title': 'NA', 'prompt': 'NA'},
            tree_header_hidden=True,
            table_name='tools',
            key_field='uuid',
            item_icon_path=':/resources/icon-tool-small.png',
            show_fields=[
                'name',
                'uuid',
            ],
            readonly=True
        )
        self.conf_namespace = 'custom_tools'
        self.schema = [
            {
                'text': 'Tool',
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
