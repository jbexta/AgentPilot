import json
import os
import sqlite3
import sys

from PySide6.QtWidgets import *
from PySide6.QtGui import Qt, QCursor
from typing_extensions import override

from utils.filesystem import get_all_baked_items
from utils.helpers import display_message_box, convert_to_safe_case, display_message, get_text
from plugins.workflows.utils.workflows import merge_config_into_workflow_config
from utils.helpers import BaseManager, set_module_type, llm_tool, format_llm_tools

from gui import system
from gui.gui_utils.helpers import save_table_config, bake_table_item
from gui.gui_utils.custom_menu import CustomMenu
from gui.widgets.config_tree import ConfigTree


@set_module_type('Widgets')
class ConfigDBTree(ConfigTree):
    """
    A widget that displays a tree of items from the db, with buttons to add and delete items.
    Can contain a config widget shown either to the right of the tree or below it,
    representing the config for each item in the tree.
    """  # unchecked
    param_schema = [
        {
            'text': 'Table name',
            'key': 'w_table_name',
            'type': str,
            'stretch_x': True,
            'default': '',
        },
        {
            'text': 'Query',
            'key': 'w_query',
            'type': str,
            'label_position': 'top',
            'stretch_x': True,
            'num_lines': 3,
            'default': '',
        },
        {
            'text': 'Folder key',
            'key': 'w_folder_key',
            'type': str,
            'default': '',
        },
        {
            'text': 'Layout type',
            'key': 'w_layout_type',
            'type': ('Vertical', 'Horizontal',),
            'default': 'vertical',
        },
        {
            'text': 'Readonly',
            'key': 'w_readonly',
            'type': bool,
            'default': False,
        },
        {
            'text': 'Searchable',
            'key': 'w_searchable',
            'type': bool,
            'default': False,
        },
        {
            'text': 'Default item icon',
            'key': 'w_default_item_icon',
            'type': str,
            'default': '',
        },
        {
            'text': 'Items pinnable',
            'key': 'w_items_pinnable',
            'type': bool,
            'default': True,
        },
        {
            'text': 'Tree header hidden',
            'key': 'w_tree_header_hidden',
            'type': bool,
            'default': False,
        },
        {
            'text': 'Tree header resizable',
            'key': 'w_tree_header_resizable',
            'type': bool,
            'default': True,
        },
        {
            'text': 'Show tree buttons',
            'key': 'w_show_tree_buttons',
            'type': bool,
            'default': True,
        },
        # {
        #     'text': 'Add item options',
        #     'type': list,
        #     'default': [],
        # },
        # {
        #     'text': 'Delete item options',
        #     'type': list,
        #     'default': [],
        # },
    ],
    def __init__(self, parent, **kwargs):
        super().__init__(parent=parent, **kwargs)
        self.default_schema = self.schema.copy()
        # self.kind_folders = kwargs.get('kind_folders', None)
        self.manager = kwargs.get('manager', None)
        self.table_name = kwargs.get('table_name', None)
        # self.load_columns = kwargs.get('load_columns', [])
        self.kind = kwargs.get('kind', None)
        self.query = kwargs.get('query', None)
        self.query_params = kwargs.get('query_params', {})
        self.propagate_config = False
        
        # Initialize connector # todo dedupe
        from core.connectors.sqlite import SqliteConnector
        self.db_connector = kwargs.get('db_connector', SqliteConnector())
        # self.connector_kwargs = kwargs.get('connector_kwargs', {})
        # if connector_param is None:
        #     connector_param = 'SqliteConnector'
        # if isinstance(connector_param, str):
        #     from gui import system as system
        #     connector_class = system.get_module_class(module_type='Connectors', module_name=connector_param)
        #     if connector_class:
        #         self.db_connector = connector_class(**self.connector_kwargs)
        #     else:
        #         raise ValueError(f"Connector '{connector_param}' not found")
        # else:

        # self.extra_data = kwargs.get('extra_data', None)
        # # # self.db_config_field = kwargs.get('db_config_field', 'config')
        # # # self.config_buttons = kwargs.get('config_buttons', None)
        # # # self.user_editable = True
        if self.manager and isinstance(self.manager, str):  # todo clean
            self.manager = getattr(system.manager, self.manager)
            if self.manager is None:
                raise ValueError(f"Manager {self.manager} not found")

            self.table_name = self.table_name or getattr(self.manager, 'table_name')
            self.kind = self.kind or getattr(self.manager, 'default_fields', {}).get('kind', None)
            self.query = self.query or getattr(self.manager, 'query', None)
            self.query_params = self.query_params or getattr(self.manager, 'query_params', None)
            # self.load_columns = self.load_columns or getattr(self.manager, 'load_columns', None)
            self.folder_key = self.folder_key or getattr(self.manager, 'folder_key', None)
            self.add_item_options = self.add_item_options or getattr(self.manager, 'add_item_options', None)
            self.del_item_options = self.del_item_options or getattr(self.manager, 'del_item_options', None)
            # self.query = getattr(self.manager, 'query', self.query)  # .get('query', self.query)
        else:
            # create a manager automatically
            self.manager = BaseManager(
                system.manager,
                db_connector=self.db_connector,
                # connector_kwargs=self.connector_kwargs,
                table_name=self.table_name,
                query=self.query,
                query_params=self.query_params,
                # load_columns=self.load_columns,
                folder_key=self.folder_key,
                kind=self.kind,
                add_item_options=self.add_item_options,
                del_item_options=self.del_item_options,
                store_data=False,
            )
        self._editing_manager = False
        self.manager.signals.changed.connect(self.on_manager_changed)

        self.init_select = kwargs.get('init_select', True)
        self.items_pinnable = kwargs.get('items_pinnable', True)
        self.items_bakeable = kwargs.get('items_bakeable', True)

        self.notify_unread = kwargs.get('notify_unread', False)
        if self.notify_unread:
            from plugins.workflows.utils.runs import get_run_manager
            get_run_manager().changed.connect(self.refresh_notify_badges)

        self.schema_overrides = {}
        # define_table(self.table_name)

        # if self.show_tree_buttons:
        #     self.tree_buttons.btn_add.clicked.connect(self.add_item)
        #     self.tree_buttons.btn_del.clicked.connect(self.delete_item)
        #     if hasattr(self.tree_buttons, 'btn_new_folder'):
        #         self.tree_buttons.btn_new_folder.clicked.connect(self.add_folder_btn_clicked)
        #     # if hasattr(self.tree_buttons, 'btn_run'):
        #     #     self.tree_buttons.btn_run.clicked.connect(self.run_btn_clicked)
        #     if not self.add_item_options:
        #         self.tree_buttons.btn_add.hide()
        #     if not self.del_item_options:
        #         self.tree_buttons.btn_del.hide()

        # self.after_init()

    def refresh_notify_badges(self):
        from plugins.workflows.utils.runs import get_run_manager
        self.tree._notify_ids = self.get_notify_ids(get_run_manager().attention_keys())
        self.tree.viewport().update()

    def get_notify_ids(self, unread_context_ids) -> set:
        """Map unread context ids to this tree's row ids. Rows in `contexts` map
        directly; other tables map through contexts linked to their uuid."""
        from utils import sql
        if not unread_context_ids:
            return set()
        if self.table_name == 'contexts':
            return set(unread_context_ids)
        placeholders = ','.join('?' * len(unread_context_ids))
        rows = sql.get_results(f"""
            SELECT DISTINCT t.id
            FROM `{self.table_name}` t
            JOIN contexts c ON instr(c.config, '{self.table_name}.' || t.uuid) > 0
            WHERE c.id IN ({placeholders})""", tuple(unread_context_ids), return_type='list')
        return set(rows)

    def after_init(self):
        from plugins.workflows.widgets.workflow_settings import WorkflowSettings
        if isinstance(self.config_widget, WorkflowSettings):
            default_item_icon = getattr(self, 'default_item_icon', '')
            self.config_widget.header_widget.widgets[0].schema[0]['default'] = default_item_icon
            self.config_widget.header_widget.build_schema()

    def on_manager_changed(self):
        if self._editing_manager:
            return
        self.load(silent_select_id=self.get_selected_item_id())

    @override
    def load(self, select_id=None, select_folder_id=None, silent_select_id=None, append=False):  # todo clean selects
        """
        Loads the QTreeWidget with folders and agents from the database.
        """
        if not self.query:
            return

        if hasattr(self, 'load_count'):
            if not append:
                self.load_count = 0
            limit = 100
            offset = self.load_count * limit
            if not self.query_params:
                self.query_params = {}
            self.query_params.update({'limit': limit, 'offset': offset})

        kind = self.filter_widget.get_kind() if hasattr(self, 'filter_widget') else self.kind
        if callable(kind):
            kind = kind()
        if kind:
            if not self.query_params:
                self.query_params = {}
            self.query_params['kind'] = kind

        if ':search' in self.query:
            if not self.query_params:
                self.query_params = {}
            self.query_params['search'] = self.get_search_text()

        prev_selected_id = self.get_selected_item_id()
        group_folders = False
        # if self.show_tree_buttons:
        #     if hasattr(self.tree_buttons, 'btn_group_folders'):
        #         group_folders = self.tree_buttons.btn_group_folders.isChecked()

        # # query = self.query if not self.filterable else self.query.replace('{{kind}}', self.filter_widget.get_kind())
        data = self.db_connector.get_results(query=self.query, params=self.query_params)
        
        # Get baked IDs for styling
        baked_ids = []
        is_exe = getattr(sys, 'frozen', False)
        if not is_exe:
            try:
                baked_ids = self.db_connector.get_results(
                    f"SELECT id FROM `{self.table_name}` WHERE baked = 1", 
                    return_type='list'
                )
            except Exception:
                # Table might not have a baked column, ignore silently
                pass
        
        if hasattr(self, 'extra_data'):
            data.extend(self.extra_data())

        self.tree.load(
            data=list(data),  # tree.load consumes the list
            append=append,
            select_id=select_id,
            select_folder_id=select_folder_id,
            silent_select_id=silent_select_id,
            folder_key=self.folder_key,
            # kind_folders=self.kind_folders,
            init_select=self.init_select,
            readonly=self.readonly,
            schema=self.schema,
            group_folders=group_folders,
            default_item_icon=self.default_item_icon,
            baked_ids=baked_ids,
            support_item_nesting=self.support_item_nesting,
            group_by_kind=self.group_by_kind,
            kind_folder_key=self.kind_folder_key,
        )
        if ':search' not in self.query and self.get_search_text():
            self.filter_rows()

        selected_id = self.get_selected_item_id()
        if (not append and select_id is None and silent_select_id is None
                and selected_id is not None
                and str(selected_id) == str(prev_selected_id)):
            self.on_item_selected()

        if len(data) == 0:
            return

        if hasattr(self, 'load_count'):
            self.load_count += 1

    def reload_current_row(self):
        data = self.db_connector.get_results(query=self.query, params=self.query_params)
        self.tree.reload_selected_item(data=data, schema=self.schema)

    @override
    def update_config(self):
        """Overrides to stop propagation to the parent."""
        self.save_config()
    
    def update_name(self):
        item_id = self.tree.get_selected_item_id()
        config = self.config_widget.get_config()
        name = config.get('name')
        if name is None:
            return
        folder_id = self.db_connector.get_scalar(f"SELECT folder_id FROM `{self.table_name}` WHERE id = ?", (item_id,))

        existing_names = self.db_connector.get_results(  # where name like  f'{name}%' and id != {item_id}
            f"SELECT name FROM `{self.table_name}` WHERE folder_id = ? AND name LIKE ? AND id != ?",
            (folder_id, f'{name}%', item_id,), return_type='list'
        )
        # append _n until name not in existing_names
        row_name = name
        n = 0
        while row_name in existing_names:
            n += 1
            row_name = f"{name}_{n}"

        self.db_connector.execute(f"""
            UPDATE `{self.table_name}`
            SET name = ?
            WHERE id = ?
        """, (row_name, item_id))

    @override
    def save_config(self):
        """
        Saves the config to the database using the tree selected ID.
        """
        # print('SAVE_CONFIG CALLED')
        # print(f'SAVE_CONFIG: id={self.tree.get_selected_item_id()}, name={self.config_widget.get_config().get("name", "??")}')
        # # item_id = self.get_selected_item_id()
        # # config = self.get_config()
        item_id = self.tree.get_selected_item_id()
        config = self.config_widget.get_config()
        name = config.get('name')
        if name is None:
            name = self.db_connector.get_scalar(
                f"SELECT name FROM `{self.table_name}` WHERE id = ?", (item_id,)
            )

        old_name = self.db_connector.get_scalar(f"SELECT name FROM {self.table_name} WHERE id = ?", (item_id,))
        # is_baked = is_baked == 1
        is_baked = False
        baked_in_table = self.db_connector.get_scalar(f"SELECT COUNT(*) FROM pragma_table_info('{self.table_name}') WHERE `name` = 'baked'") > 0
        if baked_in_table:
            is_baked = self.db_connector.get_scalar(f"SELECT baked FROM {self.table_name} WHERE id = ?", (item_id,)) == 1

        if hasattr(self, 'update_name'):
            self.update_name()

        save_table_config(
            ref_widget=self,
            table_name=self.table_name,
            item_id=item_id,
            value=json.dumps(config),
        )

        auto_bake = system.manager.config.get('system.auto_bake', False)
        if auto_bake and is_baked:
            self.bake_item(force=True)

        if is_baked and old_name != name:  # todo dedupe
            from gui.pages.modules import get_module_abs_path
            old_file_path = get_module_abs_path(item_id, module_name=old_name)
            if old_file_path:
                os.remove(old_file_path)
        
        if hasattr(self, 'after_save_config'):  # todo clean
            self.after_save_config(config=config)

        # # Notify open workflows that a linked entity changed
        # uuid_val = self.db_connector.get_scalar(
        #     f"SELECT uuid FROM `{self.table_name}` WHERE id = ?",
        #     (item_id,)
        # )
        # if uuid_val:
        #     from utils.helpers import notify_linked_config_changed
        #     notify_linked_config_changed(
        #         f"{self.table_name}.{uuid_val}"
        #     )

        self.reload_current_row()

    def on_edited(self):
        if self.manager is not None:
            self.manager.load()
        self.reload_current_row()

    def on_item_selected(self):
        # return

        item_id = self.get_selected_item_id()
        folder_id = self.get_selected_folder_id()
        # if hasattr(self.tree_buttons, 'btn_run'):
        #     self.tree_buttons.btn_run.setVisible(item_id is not None)
        # if hasattr(self.tree_buttons, 'btn_chat'):
        #     self.tree_buttons.btn_chat.setVisible(item_id is not None)
        # if hasattr(self.tree_buttons, 'btn_versions'):
        #     self.tree_buttons.btn_versions.setVisible(item_id is not None)

        if item_id and self.config_widget:
            self.toggle_config_widget(config_type='item')

            self.config_widget.maybe_rebuild_schema(self.schema_overrides, item_id)

            json_config = self.db_connector.get_scalar(f"""
                SELECT
                    `config`
                FROM `{self.table_name}`
                WHERE id = ?
            """, (item_id,), load_json=True)

            # try:
            #     json_metadata = json.loads(sql.get_scalar(f"""
            #         SELECT
            #             `metadata`
            #         FROM `{self.table_name}`
            #         WHERE id = ?
            #     """, (item_id,)))
            #     self.current_version = json_metadata.get('current_version', None)
            # except Exception as e:
            #     pass

            # if ((self.table_name == 'entities' or self.table_name == 'blocks' or self.table_name == 'tools')
            #         and json_config.get('_TYPE', 'agent') != 'workflow'):
            if getattr(self.manager, 'config_is_workflow', False) and json_config.get('_TYPE', 'agent') != 'workflow':
                # entity_uuid = self.db_connector.get_scalar(
                #     f"SELECT uuid FROM `{self.table_name}` WHERE id = ?", (item_id,)
                # )
                json_config = merge_config_into_workflow_config(json_config, entity_table=self.table_name)  # , entity_id=entity_uuid
            self.config_widget.load_config(json_config)
            self.config_widget.load()

        elif folder_id and self.folder_config_widget:
            self.toggle_config_widget(config_type='folder')

            json_config = self.db_connector.get_scalar(f"""
                SELECT
                    `config`
                FROM `folders`
                WHERE id = ?
            """, (folder_id,), load_json=True)

            self.folder_config_widget.load_config(json_config)
            self.folder_config_widget.load()
        else:
            self.toggle_config_widget(None)

        self.defer_update_page_map()

    def on_folder_toggled(self, item):
        if item.data(0, Qt.UserRole) != 'folder':
            return
        folder_id = int(item.text(1))  # self.get_selected_folder_id()
        if not folder_id:
            return

        expanded = 1 if item.isExpanded() else 0
        self.db_connector.execute("""
            UPDATE folders
            SET expanded = ?
            WHERE id = ?
        """, (expanded, folder_id,))

    def filter_rows(self):
        search_query = self.get_search_text().lower()

        def filter_item(item, search_query):
            # Initially set the item as not matched
            matched = False
            # Check if the item's text matches the query
            for c in range(item.columnCount()):
                item_col_text = item.text(c).lower()
                if search_query in item_col_text:
                    matched = True
                    break

            # Recursively check children of the item
            child_count = item.childCount()
            for i in range(child_count):
                child_item = item.child(i)
                if filter_item(child_item, search_query):
                    matched = True

            # Hide or show item based on match
            item.setHidden(not matched)

            return matched

        # Ensure the search query is correctly applied
        if search_query == '':
            # show all items
            for i in range(self.tree.topLevelItemCount()):
                item = self.tree.topLevelItem(i)
                item.setHidden(False)

                # Show all nested items
                def show_all_children(item):
                    for i in range(item.childCount()):
                        child = item.child(i)
                        child.setHidden(False)
                        show_all_children(child)

                show_all_children(item)
            return

        # Start filtering from the top level items
        for i in range(self.tree.topLevelItemCount()):
            item = self.tree.topLevelItem(i)
            filter_item(item, search_query)

    def get_selected_item_id(self):
        return self.tree.get_selected_item_id()

    @llm_tool(
        name='select_item',
        description='Select an item in the tree and open its config',
        params={'item_id': 'Id of the item to select'},
    )
    def select_item(self, item_id: int):
        self.select_tree_row(item_id, is_folder=False)

    def select_tree_row(self, row_id, is_folder):
        it = QTreeWidgetItemIterator(self.tree)
        while it.value():
            row = it.value()
            if (row.data(0, Qt.UserRole) == 'folder') == is_folder and row.text(1) == str(row_id):
                self.tree.setCurrentItem(row)
                self.tree.scrollToItem(row)
                return
            it += 1
        raise ValueError(f"{'Folder' if is_folder else 'Item'} {row_id} is not in the tree")

    def agent_tools(self, refs):
        manager_tools = [
            tool for tool in system.manager.tools.get_manager_tools()
            if getattr(system.manager, tool['manager']) is self.manager
        ]
        parts = [super().agent_tools(refs), format_llm_tools(self.manager, refs, manager_tools)]
        return '\n'.join(p for p in parts if p)

    def agent_item_suffix(self, item):
        tag = item.data(0, Qt.UserRole)
        if tag == 'kind_folder':
            return f' [kind={item.data(1, Qt.UserRole)}]'
        if tag == 'folder':
            return f' [F#{item.text(1)}]'
        return f' [#{item.text(1)}]'

    def get_selected_folder_id(self):
        return self.tree.get_selected_folder_id()

    def on_cell_edited(self, item):
        item_id = int(item.text(1))
        col_indx = self.tree.currentColumn()
        field_schema = self.schema[col_indx]
        is_config_field = field_schema.get('is_config_field', False)

        if is_config_field:
            self.update_config()
            change_callback = field_schema.get('change_callback', None)
            if change_callback:
                change_callback()
            # reload_on_change = field_schema.get('reload_on_change', False)
        else:
            col_key = convert_to_safe_case(field_schema.get('key', field_schema['text']))
            new_value = item.text(col_indx)
            if not col_key:
                return

            try:
                is_locked = self.db_connector.get_scalar(f"SELECT locked FROM {self.table_name} WHERE id = ?", (item_id,)) == 1
                if is_locked:
                    display_message(
                        message='Item is locked',
                        icon=QMessageBox.Information,
                    )
                    return
            except Exception:
                pass  # locked column doesn't exist  todo

            try:
                self.db_connector.execute(f"""
                    UPDATE `{self.table_name}`
                    SET `{col_key}` = ?
                    WHERE id = ?
                """, (new_value, item_id,))
            except Exception as e:
                display_message(
                    message=f"Error updating item:\n{str(e)}",
                    icon=QMessageBox.Warning,
                )
                self.load()
                return

        self.on_edited()
        self.tree.update_tooltips()

    def get_new_item_values(self):
        add_opts = self.add_item_options
        if not add_opts:
            return None

        dlg_title = add_opts['title']
        dlg_prompt = add_opts['prompt']

        name, ok = get_text(self, dlg_title, dlg_prompt)

        if not ok:
            return None
        return {'name': name}

    def add_item(self, *, parent_id=None):
        values = self.get_new_item_values()
        if values is None:
            return

        from gui.gui_utils.helpers import find_ancestor_tree_item_id

        kwargs = {}
        if self.table_name == 'models':  # todo automatic relations
            api_id = find_ancestor_tree_item_id(self.parent)
            kwargs['api_id'] = api_id
        kind = self.filter_widget.get_kind() if hasattr(self, 'filter_widget') else self.kind
        if callable(kind):
            kind = kind()
        if kind:
            kwargs['kind'] = kind
        if parent_id is not None:
            kwargs['parent_id'] = parent_id
            has_kind_col = self.db_connector.get_scalar(f"SELECT COUNT(*) FROM pragma_table_info('{self.table_name}') WHERE name = 'kind'") > 0
            if has_kind_col:
                kwargs['kind'] = self.db_connector.get_scalar(f"SELECT kind FROM `{self.table_name}` WHERE id = ?", (parent_id,))
        # elif self.table_name == 'workspace_concepts':
        #     workspace_id = find_ancestor_tree_item_id(self)  #  self.parent.parent.parent.get_selected_item_id()
        #     kwargs['workspace_id'] = workspace_id

        self._editing_manager = True
        try:
            self.manager.add(**values, **kwargs)
        finally:
            self._editing_manager = False
        last_insert_id = self.db_connector.get_scalar("SELECT seq FROM sqlite_sequence WHERE name=?", (self.table_name,))
        self.load(select_id=last_insert_id)

    def delete_item(self):
        item = self.tree.currentItem()
        if not item:
            return
        tag = item.data(0, Qt.UserRole)
        if tag == 'folder':
            folder_id = int(item.text(1))
            is_locked = self.db_connector.get_scalar(f"""SELECT locked FROM folders WHERE id = ?""", (folder_id,)) or False
            if is_locked == 1:
                display_message(
                    message='Folder is locked',
                    icon=QMessageBox.Information,
                )
                return

            retval = display_message_box(
                icon=QMessageBox.Warning,
                title="Delete folder",
                text="Are you sure you want to delete this folder? It's contents will be extracted.",
                buttons=QMessageBox.Yes | QMessageBox.No,
            )
            if retval != QMessageBox.Yes:
                return

            self.remove_folder(folder_id)

        else:
            item_id = self.get_selected_item_id()
            if not item_id:
                return

            locked_col_cnt = self.db_connector.get_scalar(f"SELECT COUNT(*) FROM pragma_table_info('{self.table_name}') WHERE `name` = 'locked'")
            if locked_col_cnt != 0:
                is_locked = self.db_connector.get_scalar(f"SELECT locked FROM {self.table_name} WHERE id = ?", (item_id,)) == 1
                if is_locked:
                    display_message(
                        message='Item is locked',
                        icon=QMessageBox.Information,
                    )
                    return

            del_opts = self.del_item_options
            if not del_opts:
                print(f'No del_item_options for {self.table_name}')
                return
            
            has_parent_id_col = self.db_connector.get_scalar(f"SELECT COUNT(*) FROM pragma_table_info('{self.table_name}') WHERE name = 'parent_id'") > 0
            # if has_parent_id_col:
            #     has_children = self.db_connector.get_scalar(f"SELECT COUNT(*) FROM {self.table_name} WHERE parent_id = ?", (item_id,)) > 0
            #     if has_children:
            #         retval = display_message_box(
            #             icon=QMessageBox.Question,
            #             title='Delete item',
            #             text='Are you sure you want to delete this item? Its contents will be moved to the parent folder.',
            #             buttons=QMessageBox.Yes | QMessageBox.No,
            #             # custom_buttons=[("Delete contents", QMessageBox.ActionRole)],
            #         )
            # else:
            dlg_title = del_opts['title']
            dlg_prompt = del_opts['prompt']

            if has_parent_id_col:
                has_children = self.db_connector.get_scalar(f"SELECT COUNT(*) FROM {self.table_name} WHERE parent_id = ?", (item_id,)) > 0
                if has_children:
                    dlg_prompt += '\nThis item has children, they will be moved to the parent folder.'

            retval = display_message_box(
                icon=QMessageBox.Warning,
                title=dlg_title,
                text=dlg_prompt,
                buttons=QMessageBox.Yes | QMessageBox.No,
            )

            if retval != QMessageBox.Yes:
                return

            self.remove_item(item_id)

    def remove_item(self, item_id: int):
        locked_col_cnt = self.db_connector.get_scalar(f"SELECT COUNT(*) FROM pragma_table_info('{self.table_name}') WHERE `name` = 'locked'")
        if locked_col_cnt != 0 and self.db_connector.get_scalar(f"SELECT locked FROM {self.table_name} WHERE id = ?", (item_id,)) == 1:
            raise ValueError('Item is locked')

        self._editing_manager = True
        try:
            self.manager.delete(item_id)
        finally:
            self._editing_manager = False
        self.load()

    def rename_item(self):
        item = self.tree.currentItem()
        if not item:
            return
        tag = item.data(0, Qt.UserRole)
        if tag == 'folder':
            folder_id = int(item.text(1))
            is_locked = self.db_connector.get_scalar(f"""SELECT locked FROM folders WHERE id = ?""", (folder_id,)) or False
            if is_locked == 1:
                display_message(
                    message='Folder is locked',
                    icon=QMessageBox.Information,
                )
                return

            current_name = item.text(0)
            dlg_title, dlg_prompt = ('Rename folder', 'Enter a new name for the folder')
            text, ok = get_text(self, dlg_title, dlg_prompt, text=current_name)
            if not ok:
                return

            try:
                self.set_folder_name(folder_id, text)
            except sqlite3.IntegrityError as e:
                display_message(
                    message=f"Error renaming folder, name already exists",
                    icon=QMessageBox.Warning,
                )
                return

        else:
            item_id = self.get_selected_item_id()
            try:
                is_locked = self.db_connector.get_scalar(f"SELECT locked FROM {self.table_name} WHERE id = ?", (item_id,)) or False
                if is_locked == 1:
                    display_message(
                        message='Item is locked',
                        icon=QMessageBox.Information,
                    )
                    return
            except sqlite3.OperationalError:
                pass

            current_name = item.text(0)
            dlg_title, dlg_prompt = ('Rename item', 'Enter a new name for the item')
            text, ok = get_text(self, dlg_title, dlg_prompt, text=current_name)
            if not ok:
                return

            item_id = self.get_selected_item_id()
            if not item_id:
                return
            try:
                self.set_item_name(item_id, text)

                # if is_baked and old_name != text and hasattr(self, 'get_module_file_path'):  # todo dedupe
                #     old_file_path = self.get_module_file_path(item_id, module_name=old_name)
                #     os.remove(old_file_path)

            except sqlite3.IntegrityError as e:
                display_message(
                    message=f"Error renaming item, name already exists",
                    icon=QMessageBox.Warning,
                )
                return

    @llm_tool(
        name='rename_item',
        description='Rename an item',
        params={
            'item_id': 'Id of the item to rename',
            'name': 'New name of the item',
        },
    )
    def set_item_name(self, item_id: int, name: str):
        try:
            is_locked = self.db_connector.get_scalar(f"SELECT locked FROM {self.table_name} WHERE id = ?", (item_id,)) == 1
        except sqlite3.OperationalError:
            is_locked = False
        if is_locked:
            raise ValueError('Item is locked')

        self.db_connector.execute(f"UPDATE `{self.table_name}` SET `name` = ? WHERE id = ?", (name, item_id,))
        if self.table_name in ['agents', 'blocks', 'tools', 'entities']:  # todo
            self.db_connector.execute(f"UPDATE `{self.table_name}` SET `config` = json_set(config, '$.name', ?) WHERE id = ?", (name, item_id,))

        auto_bake = system.manager.config.get('system.auto_bake', False)
        if auto_bake and self.is_tree_item_baked(item_id):
            self.bake_item(force=True, item_id=item_id)

        self.load()
        if self.get_selected_item_id() == item_id:
            self.on_item_selected()

    @llm_tool(
        description='Move an item into a folder, under another item, or to the top of a kind group',
        params={
            'item_id': 'Id of the item to move',
            'folder_id': 'Id of the folder to move it into, empty for top level',
            'parent_item': 'Id of the item to nest it under, ignores folder_id',
            'kind': 'Kind group to move it into, ignores folder_id and parent_item',
        },
    )
    def move_item(self, item_id: int, folder_id: int = None, parent_item: int = None, kind: str = None):
        if kind is not None:
            self.tree.move_to_kind_group('item', item_id, kind)
        elif parent_item is not None:
            if not self.support_item_nesting:
                raise ValueError('This tree does not support nesting items')
            self.tree.update_item_parent(item_id, parent_item)
        else:
            self.tree.update_item_folder(item_id, folder_id)

        auto_bake = system.manager.config.get('system.auto_bake', False)
        if auto_bake and self.is_tree_item_baked(item_id):
            self.bake_item(force=True, item_id=item_id)

    def pin_item(self):
        is_pinned = self.is_tree_item_pinned()
        item = self.tree.currentItem()
        if not item:
            return
        tag = item.data(0, Qt.UserRole)
        if tag == 'folder':
            self.db_connector.execute(f"UPDATE folders SET pinned = ? WHERE id = ?", (not is_pinned, int(item.text(1))))
        else:
            self.db_connector.execute(f"UPDATE `{self.table_name}` SET pinned = ? WHERE id = ?", (not is_pinned, self.get_selected_item_id()))

        self.load()

    # def run_btn_clicked(self):
    #     main = find_main_widget(self)
    #     if main.page_chat.workflow.responding:
    #         return
    #     item_id = self.get_selected_item_id()
    #     if not item_id:
    #         return
    #     main.page_chat.new_context(entity_id=item_id, entity_table=self.table_name)
    #     main.page_chat.ensure_visible()

    # def add_folder_btn_clicked(self):
    #     self.add_folder()
    #     self.load()

    @llm_tool(
        description='Add a folder, returns its id',
        params={
            'name': 'Name of the new folder',
            'parent_folder': 'Id of the folder to add it under',
        },
    )
    def add_folder(self, name: str = None, parent_folder: int = None):
        if self.folder_key is None:
            raise ValueError('Folder key not set')

        if parent_folder is None:
            item = self.tree.currentItem()
            parent_item = item.parent() if item else None
            parent_id = int(parent_item.text(1)) if parent_item else None
        else:
            parent_id = parent_folder

        if name is None:
            dlg_title, dlg_prompt = ('New folder', 'Enter the name of the new folder')
            name, ok = get_text(self, dlg_title, dlg_prompt)
            if not ok:
                return

        kind = self.filter_widget.get_kind() if hasattr(self, 'filter_widget') else self.kind
        if callable(kind):
            kind = kind()
        folder_key = self.folder_key.get(kind) if isinstance(self.folder_key, dict) else self.folder_key
        if callable(folder_key):  # todo dedupe
            folder_key = folder_key()
        
        # check if name already exists
        ex_ids = self.db_connector.get_results(f"""
            SELECT id
            FROM folders 
            WHERE name = ? 
                AND parent_id {'is' if not parent_id else '='} ?
                AND type = ?""",
            (name, parent_id, folder_key),
            return_type='list'
        )
        if len(ex_ids) > 0:
            return ex_ids[0]

        self.db_connector.execute(f"INSERT INTO `folders` (`name`, `parent_id`, `type`) VALUES (?, ?, ?)",
                    (name, parent_id, folder_key))
        ins_id = self.db_connector.get_scalar("SELECT MAX(id) FROM folders")

        self.on_edited()
        self.load()

        return ins_id

    @llm_tool(
        description='Move a folder under another folder, or to the top of a kind group',
        params={
            'folder_id': 'Id of the folder to move',
            'parent_folder': 'Id of the new parent folder, empty for top level',
            'kind': 'Kind group to move it into, ignores parent_folder',
        },
    )
    def move_folder(self, folder_id: int, parent_folder: int = None, kind: str = None):
        if self.db_connector.get_scalar("SELECT locked FROM folders WHERE id = ?", (folder_id,)) == 1:
            raise ValueError('Folder is locked')
        if kind is not None:
            self.tree.move_to_kind_group('folder', folder_id, kind)
        else:
            self.tree.update_folder_parent(folder_id, parent_folder)

    @llm_tool(
        name='select_folder',
        description='Select a folder in the tree',
        params={'folder_id': 'Id of the folder to select'},
    )
    def select_folder(self, folder_id: int):
        self.select_tree_row(folder_id, is_folder=True)

    @llm_tool(
        name='rename_folder',
        description='Rename a folder',
        params={
            'folder_id': 'Id of the folder to rename',
            'name': 'New name of the folder',
        },
    )
    def set_folder_name(self, folder_id: int, name: str):
        if self.db_connector.get_scalar("SELECT locked FROM folders WHERE id = ?", (folder_id,)) == 1:
            raise ValueError('Folder is locked')
        self.db_connector.execute("UPDATE `folders` SET `name` = ? WHERE id = ?", (name, folder_id))
        self.load()

    @llm_tool(
        name='delete_folder',
        description='Delete a folder, its contents are moved to its parent folder',
        params={'folder_id': 'Id of the folder to delete'},
        confirm=True,
    )
    def remove_folder(self, folder_id: int):
        if self.db_connector.get_scalar("SELECT locked FROM folders WHERE id = ?", (folder_id,)) == 1:
            raise ValueError('Folder is locked')

        folder_parent_id = self.db_connector.get_scalar("SELECT parent_id FROM folders WHERE id = ?", (folder_id,))
        self.db_connector.execute(f"UPDATE `{self.table_name}` SET folder_id = ? WHERE folder_id = ?", (folder_parent_id, folder_id))
        self.db_connector.execute("UPDATE `folders` SET parent_id = ? WHERE parent_id = ?", (folder_parent_id, folder_id))
        self.db_connector.execute("DELETE FROM folders WHERE id = ?", (folder_id,))

        self.on_edited()
        self.load()

    def get_folder_path_from_id(self, folder_id):
        """
        Get a path of folder names separated by '/' from a folder ID.
        Returns the full hierarchical path from root to the specified folder.
        """
        if not folder_id:
            return ""
        
        path_parts = []
        current_id = folder_id
        
        while current_id:
            folder_data = self.db_connector.get_scalar(
                "SELECT name, parent_id FROM folders WHERE id = ?", 
                (current_id,), 
                return_type='tuple'
            )
            if not folder_data:
                break
                
            name, parent_id = folder_data
            path_parts.insert(0, name)  # Insert at beginning to build path from root
            current_id = parent_id
            
        return '/'.join(path_parts)

    def duplicate_item(self):
        item = self.tree.currentItem()
        if not item:
            return
        tag = item.data(0, Qt.UserRole)
        if tag == 'folder':
            display_message(
                message='Folders cannot be duplicated yet',
                icon=QMessageBox.Information,
            )
            return

        else:
            id = self.get_selected_item_id()
            if not id:
                return

            config = self.db_connector.get_scalar(f"""
                SELECT
                    `config`
                FROM `{self.table_name}`
                WHERE id = ?
            """, (id,))
            if not config:
                return

            add_opts = self.add_item_options
            if not add_opts:
                return
            dlg_title = add_opts['title']
            dlg_prompt = add_opts['prompt']

            text, ok = get_text(self, dlg_title, dlg_prompt)
            if not ok:
                return

            if self.table_name == 'entities':
                self.db_connector.execute(f"""
                    INSERT INTO `entities` (`name`, `kind`, `config`)
                    VALUES (?, ?, ?)
                """, (text, self.kind, config))
            else:
                self.db_connector.execute(f"""
                    INSERT INTO `{self.table_name}` (`name`, `config`)
                    VALUES (?, ?)
                """, (text, config,))
            self.on_edited()
            self.load()

    def show_context_menu(self):
        context_menu = self.Tree_Context_Menu(self)
        menu = context_menu._create_menu_recursive(title='', schema=context_menu.schema, parent=self)
        self.on_context_menu(menu)
        menu.exec_(QCursor.pos())
        menu.deleteLater()
        context_menu.deleteLater()

    class Tree_Context_Menu(CustomMenu):
        def __init__(self, parent):
            super().__init__(parent)

            def is_item_selected():
                item = parent.tree.currentItem()
                return item is not None and isinstance(item.data(0, Qt.UserRole), dict)

            def is_bakeable():
                is_exe = getattr(sys, 'frozen', False)
                return not is_exe and parent.items_bakeable and parent.tree.currentItem() is not None

            self.schema = [
                {
                    'text': 'Add sub-item',
                    'target': lambda: parent.add_item(parent_id=parent.get_selected_item_id()),
                    'visibility_predicate': lambda: parent.support_item_nesting and is_item_selected(),
                },
                {
                    'text': 'Rename',
                    'target': parent.rename_item,
                },
                {
                    'text': 'Duplicate',
                    'target': parent.duplicate_item,
                },
                {
                    'text': 'Delete',
                    'target': parent.delete_item,
                },
                {'type': 'separator'},
                {
                    'text': 'Pin',
                    'target': parent.pin_item,
                    'visibility_predicate': lambda: parent.items_pinnable and not parent.is_tree_item_pinned(),
                },
                {
                    'text': 'Unpin',
                    'target': parent.pin_item,
                    'visibility_predicate': lambda: parent.items_pinnable and parent.is_tree_item_pinned(),
                },
                {'type': 'separator'},
                {
                    'text': 'Bake',
                    'target': parent.bake_item,
                    'visibility_predicate': lambda: is_bakeable() and not (
                        parent.is_tree_item_baked() and system.manager.config.get('system.auto_bake', False)
                    ),
                },
                {
                    'text': 'Unbake',
                    'target': parent.unbake_item,
                    'visibility_predicate': lambda: is_bakeable() and parent.is_tree_item_baked(),
                },
            ]

        # if self.__class__.__name__ == 'Page_Models_Settings':
        #     # Add a providers submenu
        #     menu.addSeparator()
        #     providers_menu = QMenu('Provider', menu)
        #     menu.addMenu(providers_menu)

        #     # Get the current model's provider
        #     api_id = self.get_selected_item_id()
        #     current_provider = None
        #     if api_id:
        #         current_provider = self.db_connector.get_scalar("SELECT provider_plugin FROM apis WHERE id = ?", (api_id,))

        #     # Add providers from the plugins system
        #     provider_plugins = system.manager.providers

        #     for provider_name in list(provider_plugins.keys()):
        #         provider_action = providers_menu.addAction(provider_name)
        #         provider_action.setCheckable(True)
        #         provider_action.setChecked(provider_name == current_provider)

        #         # When clicked, update the model's provider
        #         def make_provider_setter(p_name):
        #             def set_provider():
        #                 if api_id:
        #                     self.db_connector.execute("UPDATE apis SET provider_plugin = ? WHERE id = ?",
        #                                (p_name, api_id))
        #                     self.on_edited()
        #                     self.load()  # Reload config
        #             return set_provider

        #         provider_action.triggered.connect(make_provider_setter(provider_name))

    def on_context_menu(self, menu):
        """Hook for subclasses to add items to the context menu."""
        pass

    def unbake_item(self):
        item = self.tree.currentItem()
        if not item:
            return
        tag = item.data(0, Qt.UserRole)
        if tag == 'folder':
            return
        item_id = self.get_selected_item_id()
        if not item_id:
            return

        uuid = self.db_connector.get_scalar(
            f"SELECT uuid FROM `{self.table_name}` WHERE id = ?", (item_id,)
        )
        if not uuid:
            return

        for path, baked_item in get_all_baked_items(self.table_name).items():
            if baked_item.get('uuid') == uuid:
                os.remove(path)

        self.db_connector.execute(f"UPDATE `{self.table_name}` SET baked = 0 WHERE id = ?", (item_id,))
        self.load()
        # self.load()

    def bake_item(self, force=False, item_id=None):
        if not self.items_bakeable:
            return

        if getattr(sys, 'frozen', False):
            if not force:
                display_message(
                    message='Baking is not supported from binaries.',
                    icon=QMessageBox.Information,
                )
            return

        table_name = self.table_name
        if item_id is None:
            item = self.tree.currentItem()
            if not item:
                return
            if item.data(0, Qt.UserRole) == 'folder':
                table_name = 'folders'
                item_id = self.get_selected_folder_id()
            else:
                item_id = self.get_selected_item_id()
        if not item_id:
            return

        uuid_col_exists = self.db_connector.get_scalar(
            f"SELECT COUNT(*) FROM pragma_table_info('{table_name}') WHERE name = 'uuid'"
        ) > 0
        if not uuid_col_exists:
            display_message(
                message=f"Table `{table_name}` does not have a 'uuid' column. Cannot bake.",
                icon=QMessageBox.Warning,
            )
            return

        if not force:
            uuid = self.db_connector.get_scalar(
                f"SELECT uuid FROM `{table_name}` WHERE id = ?", (item_id,)
            )
            existing_baked = get_all_baked_items(table_name)
            if uuid in [b.get('uuid') for b in existing_baked.values()]:
                dr = display_message_box(
                    icon=QMessageBox.Question,
                    title="Overwrite item",
                    text=f"Item with UUID {uuid} already exists in baked items. Overwrite?",
                    buttons=QMessageBox.Yes | QMessageBox.No,
                )
                if dr != QMessageBox.Yes:
                    return

        try:
            target = bake_table_item(table_name, item_id)
            if target is None:
                return
            if not force:
                display_message(
                    message=f"Successfully baked item to:\n{target}",
                    icon=QMessageBox.Information,
                )
                self.load()

        except Exception as e:
            display_message(
                message=f"Failed to write file.\nError: {e}",
                icon=QMessageBox.Critical,
            )

    def is_tree_item_pinned(self):
        # todo temp
        item = self.tree.currentItem()
        if not item:
            return None
        tag = item.data(0, Qt.UserRole)
        if tag == 'folder':
            folder_id = int(item.text(1))
            is_pinned = self.db_connector.get_scalar(f"""
                SELECT pinned
                FROM folders
                WHERE id = ?
                """, (folder_id,)) == 1
            return is_pinned

        else:
            item_id = self.get_selected_item_id()
            if not item_id:
                return False
            is_pinned = self.db_connector.get_scalar(f"""
                SELECT pinned
                FROM `{self.table_name}`
                WHERE id = ?
                """, (item_id,)) == 1
            return is_pinned

    def is_tree_item_baked(self, item_id=None):
        # todo temp
        if item_id is None:
            item = self.tree.currentItem()
            if not item:
                return None
            tag = item.data(0, Qt.UserRole)
            if tag == 'folder':
                return False
                # raise NotImplementedError("")
                # folder_id = int(item.text(1))
                # is_baked = self.db_connector.get_scalar(f"""
                #     SELECT baked
                #     FROM folders
                #     WHERE id = ?
                #     """, (folder_id,)) == 1
                # return is_pinned
            item_id = self.get_selected_item_id()
            if not item_id:
                return False
        table_has_baked_col = self.db_connector.get_scalar(f"SELECT COUNT(*) FROM pragma_table_info('{self.table_name}') WHERE name = 'baked'") > 0
        if not table_has_baked_col:
            return False
        is_baked = self.db_connector.get_scalar(f"""
            SELECT baked
            FROM `{self.table_name}`
            WHERE id = ?
            """, (item_id,)) == 1
        return is_baked

    def check_infinite_load(self):
        if self.tree.signalsBlocked():
            return  # mid tree.load, e.g. `clear()` resetting the scrollbar
        if self.tree.verticalScrollBar().value() == self.tree.verticalScrollBar().maximum():
            self.load(append=True)
    
    # def toggle_chat(self):
    #     if not self.has_chat:
    #         return
    #     chat_widget = self.config_widget.widgets[1]
    #     is_checked = self.tree_buttons.btn_chat.isChecked()
    #     if is_checked and not chat_widget.isVisible():
    #         chat_widget.show()
    #     elif not is_checked and chat_widget.isVisible():
    #         chat_widget.hide()