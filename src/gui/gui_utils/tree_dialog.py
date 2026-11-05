import json

from PySide6.QtGui import Qt
from PySide6.QtWidgets import QAbstractItemView, QDialog, QSizePolicy, QVBoxLayout

from gui.gui_utils.base_tree_widget import BaseTreeWidget
from plugins.workflows.utils.workflows import merge_config_into_workflow_config
from utils import sql


class TreeDialog(QDialog):
    def __init__(self, parent, *args, **kwargs):
        super().__init__(parent=parent)
        self.parent = parent
        self.setWindowFlags(
            Qt.Window
            | Qt.WindowTitleHint
            | Qt.WindowSystemMenuHint
            | Qt.WindowCloseButtonHint
            | Qt.WindowStaysOnTopHint
        )

        self.setWindowTitle(kwargs.get('title', ''))
        self.list_type = kwargs.get('list_type', '')
        if self.list_type in ('agent', 'tool', 'module'):
            self.list_type = self.list_type.upper()
        self.callback = kwargs.get('callback', None)
        multiselect = kwargs.get('multiselect', False)
        show_blank = kwargs.get('show_blank', False)

        layout = QVBoxLayout(self)
        self.tree_widget = BaseTreeWidget(self)
        self.tree_widget.setDragDropMode(QAbstractItemView.NoDragDrop)
        self.tree_widget.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        layout.addWidget(self.tree_widget)

        # todo refactor
        if self.list_type == 'AGENT':  # or self.list_type == 'CONTACT':
            def_avatar = ':/resources/icon-agent-solid.png'  # if self.list_type == 'AGENT' else ':/resources/icon-user.png'
            col_name_list = ['name', 'id', 'config']
            empty_member_label = 'Empty agent'  # if self.list_type == 'AGENT' else 'You'
            folder_key = 'agents'  # if self.list_type == 'AGENT' else 'users'
            query = f"""
                SELECT
                    name,
                    uuid,
                    config,
                    folder_id
                FROM (
                    SELECT
                        e.id,
                        e.name,
                        e.uuid,
                        e.config,
                        e.folder_id
                    FROM entities e
                    WHERE kind = '{self.list_type}'
                )
                ORDER BY id DESC"""
        elif self.list_type == 'live_agent':
            def_avatar = ':/resources/icon-mic-member.png'
            col_name_list = ['name', 'id', 'config']
            empty_member_label = 'Empty live agent'
            folder_key = 'agents'
            # saved agents that are, or contain, a live agent member
            query = """
                SELECT name, uuid, config, folder_id
                FROM entities e
                WHERE kind = 'AGENT'
                    AND (json_extract(e.config, '$._TYPE') = 'live_agent'
                        OR EXISTS (
                            SELECT 1 FROM json_each(json_extract(e.config, '$.members')) m
                            WHERE json_extract(m.value, '$.config._TYPE') = 'live_agent'))
                ORDER BY id DESC"""
        elif self.list_type == 'TOOL':
            def_avatar = ':/resources/icon-tool.png'
            col_name_list = ['name', 'id', 'config']
            empty_member_label = None
            folder_key = 'tools'
            query = """
                SELECT
                    name,
                    uuid as id,
                    '{}' as config,
                    folder_id
                FROM tools
                ORDER BY name"""

        elif self.list_type == 'MODULE':
            def_avatar = ':/resources/icon-jigsaw-solid.png'
            col_name_list = ['name', 'id', 'config']
            empty_member_label = None
            folder_key = 'modules'
            query = """
                SELECT
                    name,
                    uuid as id,
                    '{}' as config,
                    folder_id
                FROM modules
                ORDER BY name"""

        # elif self.list_type == 'prompt', 'code']:
        #     def_avatar = ':/resources/icon-blocks.png'
        #     col_name_list = ['block', 'id', 'config']
        #     empty_member_label = None
        #     folder_key = 'blocks'
        #     query = f"""
        #         SELECT
        #             name,
        #             uuid,
        #             COALESCE(json_extract(config, '$.members[0].config'), config) as config,
        #             folder_id
        #         FROM blocks
        #         WHERE (json_array_length(json_extract(config, '$.members')) = 1
        #             OR json_type(json_extract(config, '$.members')) IS NULL)
        #         ORDER BY name"""

        elif self.list_type == 'text':
            def_avatar = ':/resources/icon-blocks.png'
            col_name_list = ['block', 'id', 'config']
            empty_member_label = 'Empty text block'
            folder_key = 'blocks'
            query = f"""
                SELECT
                    name,
                    uuid,
                    COALESCE(json_extract(config, '$.members[0].config'), config) as config,
                    folder_id
                FROM blocks
                WHERE (json_array_length(json_extract(config, '$.members')) = 1
                    OR json_type(json_extract(config, '$.members')) IS NULL)
                    AND COALESCE(json_extract(config, '$._TYPE'), 'text') = 'text'
                ORDER BY name"""

        elif self.list_type == 'prompt':
            def_avatar = ':/resources/icon-brain.png'
            col_name_list = ['block', 'id', 'config']
            empty_member_label = 'Empty prompt block'
            folder_key = 'blocks'
            # extract members[0] of workflow `block_type` when `members` is not null
            query = f"""
                SELECT
                    name,
                    uuid,
                    COALESCE(json_extract(config, '$.members[0].config'), config) as config,
                    folder_id
                FROM blocks
                WHERE (json_array_length(json_extract(config, '$.members')) = 1
                    OR json_type(json_extract(config, '$.members')) IS NULL)
                    AND COALESCE(json_extract(config, '$._TYPE'), 'text') = 'prompt'
                ORDER BY name"""

        elif self.list_type == 'code':
            def_avatar = ':/resources/icon-code.png'
            col_name_list = ['block', 'id', 'config']
            empty_member_label = 'Empty code block'
            folder_key = 'blocks'
            query = f"""
                SELECT
                    name,
                    uuid,
                    COALESCE(json_extract(config, '$.members[0].config'), config) as config,
                    folder_id
                FROM blocks
                WHERE (json_array_length(json_extract(config, '$.members')) = 1
                    OR json_type(json_extract(config, '$.members')) IS NULL)
                    AND COALESCE(json_extract(config, '$._TYPE'), 'text') = 'code'
                ORDER BY name"""
        else:
            raise NotImplementedError(f'List type {self.list_type} not implemented')

        column_schema = [
            {
                'text': 'Name',
                'key': 'name',
                'type': str,
                'stretch': True,
                'image_key': 'config' if self.list_type == 'agent' else None,
            },
            {
                'text': 'id',
                'key': 'id',
                'type': int,
                'visible': False,
            },
            {
                'text': 'config',
                'type': str,
                'visible': False,
            },
        ]
        self.tree_widget.build_columns_from_schema(column_schema)
        self.tree_widget.setHeaderHidden(True)

        if self.list_type in ('AGENT', 'live_agent'):
            tbl_name = 'entities'
        elif self.list_type in ['text', 'prompt', 'code']:
            tbl_name = 'blocks'
        elif self.list_type == 'TOOL':
            tbl_name = 'tools'
        else:
            tbl_name = None

        # todo clean
        data = sql.get_results(query)
        data = [
            (
                row[0],
                row[1],
                json.dumps(
                    merge_config_into_workflow_config(
                        json.loads(row[2]),
                        entity_id=row[1] if tbl_name is not None else None,
                        entity_table=tbl_name
                    )
                ) if self.list_type in ['AGENT', 'live_agent', 'TOOL', 'text', 'prompt', 'code'] else row[2],
                row[3],
            )
            for row in data
        ]
        if empty_member_label is not None and show_blank:
            if self.list_type == 'workflow':
                pass
            empty_config = {}
            if self.list_type in ['text', 'prompt', 'code']:
                empty_config = {
                    "_TYPE": self.list_type.lower(),
                    "name": self.list_type.replace('_', ' ').title()
                }
            # elif self.list_type == 'agent':
            #     empty_config = {}
            else:
                empty_config = {
                    "_TYPE": self.list_type.lower(),
                    "name": self.list_type.replace('_', ' ').title()
                }

            data.insert(0, (empty_member_label, '', json.dumps(empty_config), None))

        group_by_kind = self.list_type == 'TOOL'
        if group_by_kind:
            from gui import system
            data = [row + ('',) for row in data] + [
                (tool['name'], tool['id'], '{}', None, tool['folder'])
                for tool in system.manager.tools.get_method_tools()
            ]

        self.tree_widget.load(
            data=data,
            folder_key=folder_key,
            schema=column_schema,
            readonly=True,
            default_item_icon=def_avatar,
            group_by_kind=group_by_kind,
        )

        if self.callback:
            self.tree_widget.itemDoubleClicked.connect(self.itemSelected)

    class TreeWidget(BaseTreeWidget):
        def __init__(self, *args, **kwargs):
            super().__init__(*args, **kwargs)

        def load(self, data, **kwargs):
            super().load(data, **kwargs)

    def open(self):
        self.exec()

    def itemSelected(self, item):
        is_folder = item.data(0, Qt.UserRole) in ('folder', 'kind_folder')
        if is_folder and self.list_type != 'TOOL':
            return
        self.close()
        self.callback(item)  # , linked_id=)

    def keyPressEvent(self, event):
        super().keyPressEvent(event)
        if event.key() != Qt.Key_Return:
            return
        item = self.tree_widget.currentItem()
        self.itemSelected(item)
