"""Todo Page Module.

Provides a todo list page for managing tasks with priorities,
due dates, and completion status.
"""

from gui.widgets.config_db_tree import ConfigDBTree
from gui.widgets.config_fields import ConfigFields
from gui.widgets.config_joined import ConfigJoined
from utils.helpers import set_module_type
from utils.sql import define_table

define_table('todo')


@set_module_type('Pages')
class Page_Todo(ConfigDBTree):
    display_name = 'Todo!'
    icon_path = ':/resources/icon-todo.png'
    page_type = 'main'

    def __init__(self, parent):
        super().__init__(
            parent=parent,
            table_name='todo',
            query="""
                SELECT
                    name,
                    id,
                    COALESCE(json_extract(config, '$.done'), 0),
                    COALESCE(json_extract(config, '$.priority'), 'Normal'),
                    folder_id
                FROM todo
                ORDER BY
                    COALESCE(json_extract(config, '$.done'), 0) ASC,
                    pinned DESC,
                    CASE COALESCE(json_extract(config, '$.priority'), 'Normal')
                        WHEN 'High' THEN 0
                        WHEN 'Normal' THEN 1
                        WHEN 'Low' THEN 2
                    END,
                    ordr,
                    name COLLATE NOCASE
            """,
            schema=[
                {
                    'text': 'Task',
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
                    'text': 'Done',
                    'key': 'done',
                    'type': bool,
                    'is_config_field': True,
                    'width': 40,
                },
                {
                    'text': 'Priority',
                    'key': 'priority',
                    'type': ('High', 'Normal', 'Low'),
                    'is_config_field': True,
                    'width': 80,
                },
            ],
            add_item_options={
                'title': 'Add Task',
                'prompt': 'Enter a task name:',
            },
            del_item_options={
                'title': 'Delete Task',
                'prompt': 'Are you sure you want to delete this task?',
            },
            folder_key='todo',
            readonly=False,
            layout_type='vertical',
            tree_header_hidden=False,
            config_widget=self.Todo_Config_Widget(parent=self),
            searchable=True,
        )

    class Todo_Config_Widget(ConfigJoined):
        def __init__(self, parent):
            super().__init__(parent=parent)
            self.widgets = [
                self.Todo_Config_Fields(parent=self),
            ]

        class Todo_Config_Fields(ConfigFields):
            def __init__(self, parent):
                super().__init__(parent=parent)
                self.schema = [
                    {
                        'text': 'Done',
                        'type': bool,
                        'default': False,
                        'row_key': 0,
                    },
                    {
                        'text': 'Priority',
                        'type': ('High', 'Normal', 'Low'),
                        'default': 'Normal',
                        'row_key': 0,
                    },
                    {
                        'text': 'Due date',
                        'type': str,
                        'default': '',
                        'row_key': 0,
                        'placeholder_text': 'YYYY-MM-DD',
                        'width': 120,
                    },
                    {
                        'text': 'Notes',
                        'type': str,
                        'default': '',
                        'num_lines': 8,
                        'stretch_x': True,
                        'stretch_y': True,
                        'placeholder_text': 'Notes...',
                        'label_position': None,
                        'wrap_text': True,
                    },
                ]
