import json

from PySide6.QtGui import Qt
from PySide6.QtWidgets import QAbstractItemView, QCheckBox, QDialog, QTabWidget, QVBoxLayout

from gui.gui_utils.base_tree_widget import BaseTreeWidget
from plugins.workflows.utils.workflows import merge_config_into_workflow_config
from utils import sql


class LibraryDialog(QDialog):
    """Dialog with tabs for browsing Agents, Blocks, and Tools."""

    def __init__(self, parent, callback, kind=None, allow_references=False):
        super().__init__(parent=parent)
        self.callback = callback
        self.setWindowTitle('Library')
        self.setWindowFlags(
            Qt.Window
            | Qt.WindowTitleHint
            | Qt.WindowSystemMenuHint
            | Qt.WindowCloseButtonHint
            | Qt.WindowStaysOnTopHint
        )
        self.resize(400, 500)

        layout = QVBoxLayout(self)
        self.tabs = QTabWidget(self)
        layout.addWidget(self.tabs)

        column_schema = [
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
                'text': 'config',
                'type': str,
                'visible': False,
            },
            {
                'text': 'table',
                'key': 'table',
                'type': str,
                'visible': False,
            },
        ]

        tab_defs = [
            (
                'Agent',
                """SELECT name, uuid, config, folder_id
                   FROM entities
                   WHERE kind = 'AGENT'
                   ORDER BY id DESC""",
                'agents',
                ':/resources/icon-agent-solid.png',
                'entities',
                {},
            ),
            (
                'Block',
                """SELECT name, uuid,
                       COALESCE(
                           json_extract(config, '$.members[0].config'),
                           config
                       ) as config,
                       folder_id,
                       (SELECT p.uuid FROM blocks p
                        WHERE p.id = blocks.parent_id) as parent_uuid,
                       kind
                   FROM blocks
                   WHERE (json_array_length(
                              json_extract(config, '$.members')
                          ) = 1
                       OR json_type(
                              json_extract(config, '$.members')
                          ) IS NULL)
                   ORDER BY kind, name""",
                'blocks',
                ':/resources/icon-blocks.png',
                'blocks',
                {
                    'group_by_kind': True,
                    'kind_folder_key': lambda kind: f'{kind.lower()}:block',
                    'support_item_nesting': True,
                },
            ),
            (
                'Tool',
                """SELECT name, uuid as id, '{}' as config,
                       folder_id
                   FROM tools
                   ORDER BY name""",
                'tools',
                ':/resources/icon-tool.png',
                'tools',
                {},
            ),
        ]

        for label, query, folder_key, icon, tbl_name, load_kwargs in tab_defs:
            tree = BaseTreeWidget(self)
            tree.setDragDropMode(QAbstractItemView.NoDragDrop)
            tree.build_columns_from_schema(column_schema)
            tree.setHeaderHidden(True)

            data = sql.get_results(query)
            data = [
                (
                    row[0],
                    row[1],
                    json.dumps(
                        merge_config_into_workflow_config(
                            json.loads(row[2]),
                            entity_id=row[1],
                            entity_table=tbl_name,
                        )
                    ),
                    tbl_name,
                    *row[3:],
                )
                for row in data
            ]
            if load_kwargs.get('support_item_nesting'):
                uuids = {row[1] for row in data}
                data = [
                    row[:-2]
                    + (row[-2] if row[-2] in uuids else None, row[-1])
                    for row in data
                ]

            tree.load(
                data=data,
                folder_key=folder_key,
                schema=column_schema,
                readonly=True,
                default_item_icon=icon,
                **load_kwargs,
            )
            tree.itemDoubleClicked.connect(self.item_selected)
            self.tabs.addTab(tree, label)

        self.link_checkbox = QCheckBox('Link as reference', self)
        self.link_checkbox.setVisible(allow_references)
        layout.addWidget(self.link_checkbox)

        kind_tab_map = {'conversation': 0, 'blocks': 1, 'tool': 2}
        if kind in kind_tab_map:
            self.tabs.setCurrentIndex(kind_tab_map[kind])

    def item_selected(self, item):
        if item.data(0, Qt.UserRole) in ('folder', 'kind_folder'):
            return
        self.close()
        self.callback(item, link=self.link_checkbox.isChecked())

    def open(self):
        self.exec()
