import inspect
import textwrap

from PySide6.QtGui import QIcon, QPixmap

from gui import system
from gui.gui_utils.helpers import colorize_pixmap
from gui.widgets.config_db_tree import ConfigDBTree
from gui.widgets.config_fields import ConfigFields
from plugins.workflows.widgets.chat_widget import ChattableWorkflowWidget


class Page_Tool_Settings(ConfigDBTree):
    display_name = 'Tools'
    icon_path = ":/resources/icon-tool.png"
    page_type = 'any'  # either 'settings', 'main', or 'any' ('any' means it can be pinned between main and settings)

    def __init__(self, parent):
        super().__init__(
            parent=parent,
            manager='tools',
            query="""
                SELECT
                    name,
                    id,
                    uuid,
                    -- COALESCE(json_extract(config, '$.environment'), 'Local'),
                    folder_id,
                    '' AS kind
                FROM tools
                ORDER BY pinned DESC, ordr, name COLLATE NOCASE""",
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
                {
                    'text': 'uuid',
                    'key': 'uuid',
                    'type': str,
                    'visible': False,
                },
                # {
                #     'text': 'Type',
                #     'key': 'type',
                #     'type': ('Function', 'computer_20241022',),  # , 'Prompt based',),
                #     'is_config_field': True,
                #     'width': 175,
                # },
            ],
            add_item_options={'title': 'Add Tool', 'prompt': 'Enter a name for the tool:'},
            del_item_options={'title': 'Delete Tool', 'prompt': 'Are you sure you want to delete this tool?'},
            readonly=False,
            layout_type='horizontal',
            folder_key='tools',
            group_by_kind=True,
            config_widget=self.Tool_Config_Widget(parent=self),
            folder_config_widget=self.Folder_Config_Widget(parent=self),
            tree_header_resizable=True,
            searchable=True,
            default_item_icon=':/resources/icon-tool-small.png',
            has_chat=True,
            notify_unread=True,
        )
        self.splitter.setSizes([400, 1000])
        self.method_widget = self.Method_Tool_Widget(parent=self)
        self.method_widget.build_schema()
        self.method_widget.hide()
        self.config_layout.addWidget(self.method_widget)

    def load(self, *args, **kwargs):
        super().load(*args, **kwargs)
        icon = QIcon(colorize_pixmap(QPixmap(':/resources/icon-workspace.png')))
        for item_id, item in self.tree.items_mapping.items():
            if str(item_id).startswith('method:'):
                item.setIcon(0, icon)

    def extra_data(self):
        # append `@llm_tool` decorated widget/page methods, grouped by their module kind
        return [
            (tool['name'], tool['id'], '', None, tool['folder'])
            for tool in system.manager.tools.get_method_tools()
        ]

    def _is_method_tool_selected(self):
        item_id = self.tree.get_selected_item_id()
        return isinstance(item_id, str) and item_id.startswith('method:')

    def on_item_selected(self):
        if self._is_method_tool_selected():
            self.toggle_config_widget(None)
            self.load_method_tool()
            return
        self.method_widget.hide()
        super().on_item_selected()

    def load_method_tool(self):
        item_id = self.tree.get_selected_item_id()
        tool = next((t for t in system.manager.tools.get_method_tools()
                     if t['id'] == item_id), None)
        if not tool:
            return
        self.method_widget.load_config({
            'description': tool['description'],
            'code': textwrap.dedent(inspect.getsource(tool['fn'])),
        })
        self.method_widget.load()
        self.method_widget.show()

    def on_cell_edited(self, item):
        if str(item.text(1)).startswith('method:'):
            return
        super().on_cell_edited(item)

    def delete_item(self):
        if self._is_method_tool_selected():
            return
        super().delete_item()

    def on_edited(self):
        system.manager.tools.load()

    class Method_Tool_Widget(ConfigFields):
        def __init__(self, parent):
            super().__init__(
                parent=parent,
                schema=[
                    {
                        'text': 'Description',
                        'type': str,
                        'default': '',
                        'num_lines': 2,
                        'stretch_x': True,
                        'readonly': True,
                        'label_position': 'top',
                    },
                    {
                        'text': 'Code',
                        'type': str,
                        'default': '',
                        'num_lines': 2,
                        'stretch_x': True,
                        'stretch_y': True,
                        'highlighter': 'python',
                        'fold_mode': 'python',
                        'monospaced': True,
                        'readonly': True,
                        'label_position': None,
                    },
                ],
            )

    class Tool_Config_Widget(ChattableWorkflowWidget):
        def __init__(self, parent):
            super().__init__(
                parent=parent,
                kind='TOOL',
            )