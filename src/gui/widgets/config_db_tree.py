import json
import os
import sqlite3
import sys
import yaml

from PySide6.QtWidgets import *
from PySide6.QtGui import Qt, QCursor
from typing_extensions import override

from utils.filesystem import get_application_path, get_all_baked_items
from utils.helpers import display_message_box, merge_config_into_workflow_config, convert_to_safe_case, display_message
from utils.helpers import BaseManager, set_module_type

from gui import system
from gui.util import save_table_config
from gui.widgets.config_tree import ConfigTree


def str_presenter(dumper, data):
    """Custom representer for multiline strings in YAML."""
    if isinstance(data, str) and '\n' in data:
        # Use literal style (|) for multiline strings
        # YAML will automatically use |- when there are no trailing newlines
        # and | when there are trailing newlines to preserve
        # remove trailing spaces on each line
        data = '\n'.join([line.rstrip() for line in data.split('\n')])
        return dumper.represent_scalar('tag:yaml.org,2002:str', data, style='|')
    return dumper.represent_scalar('tag:yaml.org,2002:str', data)


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
            'text': 'Versionable',
            'key': 'w_versionable',
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

        self.init_select = kwargs.get('init_select', True)
        self.items_pinnable = kwargs.get('items_pinnable', True)
        self.items_bakeable = kwargs.get('items_bakeable', True)

        self.schema_overrides = {}
        # define_table(self.table_name)
        self.current_version = None  # todo, should be here?

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

    def after_init(self):
        from plugins.workflows.widgets.workflow_settings import WorkflowSettings
        if isinstance(self.config_widget, WorkflowSettings):
            default_item_icon = getattr(self, 'default_item_icon', '')
            self.config_widget.header_widget.widgets[0].schema[0]['default'] = default_item_icon
            self.config_widget.header_widget.build_schema()

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
        
        # # if callable(self.extra_data):
        # #     extra_data = self.extra_data()
        # #     data.extend(extra_data)
        # if hasattr(self, 'extra_data'):
        #     extra_data = self.extra_data()
        #     data.extend(extra_data)

        self.tree.load(
            data=data,
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
        )
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
        self.current_version = None

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

    def on_folder_toggled(self, item):
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
        if not self.show_tree_buttons:
            return

        search_query = self.tree_buttons.search_box.text().lower()
        if not self.tree_buttons.search_box.isVisible():
            search_query = ''

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

    def add_item(self):
        add_opts = self.add_item_options
        if not add_opts:
            return

        dlg_title = add_opts['title']
        dlg_prompt = add_opts['prompt']

        text, ok = QInputDialog.getText(self, dlg_title, dlg_prompt)

        if not ok:
            return

        from gui.util import find_ancestor_tree_item_id

        kwargs = {}
        if self.table_name == 'models':  # todo automatic relations
            api_id = find_ancestor_tree_item_id(self.parent)
            kwargs['api_id'] = api_id
        kind = self.filter_widget.get_kind() if hasattr(self, 'filter_widget') else self.kind
        if callable(kind):
            kind = kind()
        if kind:
            kwargs['kind'] = kind
        # elif self.table_name == 'workspace_concepts':
        #     workspace_id = find_ancestor_tree_item_id(self)  #  self.parent.parent.parent.get_selected_item_id()
        #     kwargs['workspace_id'] = workspace_id

        self.manager.add(name=text, **kwargs)
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

            folder_parent = item.parent() if item else None
            folder_parent_id = folder_parent.text(1) if folder_parent else None

            # Unpack all items from folder to parent folder (or root)
            self.db_connector.execute(f"""
                UPDATE `{self.table_name}`
                SET folder_id = {'NULL' if not folder_parent_id else folder_parent_id}
                WHERE folder_id = ?
            """, (folder_id,))
            # Unpack all folders from folder to parent folder (or root)
            self.db_connector.execute(f"""
                UPDATE `folders`
                SET parent_id = {'NULL' if not folder_parent_id else folder_parent_id}
                WHERE parent_id = ?
            """, (folder_id,))

            self.db_connector.execute(f"""
                DELETE FROM folders
                WHERE id = ?
            """, (folder_id,))

            self.on_edited()
            self.load()

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

            if has_parent_id_col:
                parent_id_of_deleting_item = self.db_connector.get_scalar(f"SELECT parent_id FROM {self.table_name} WHERE id = ?", (item_id,))
                if has_children:
                    self.db_connector.execute(f"""
                        UPDATE `{self.table_name}`
                        SET parent_id = ?
                        WHERE parent_id = ?
                    """, (parent_id_of_deleting_item, item_id,))

            self.manager.delete(item_id)
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
            text, ok = QInputDialog.getText(self, dlg_title, dlg_prompt, text=current_name)
            if not ok:
                return

            try:
                self.db_connector.execute(f"UPDATE `folders` SET `name` = ? WHERE id = ?", (text, folder_id))
            except sqlite3.IntegrityError as e:
                display_message(
                    message=f"Error renaming folder, name already exists",
                    icon=QMessageBox.Warning,
                )
                return
            # self.reload_current_row()
            self.load()

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
            text, ok = QInputDialog.getText(self, dlg_title, dlg_prompt, text=current_name)
            if not ok:
                return

            item_id = self.get_selected_item_id()
            if not item_id:
                return
            try:
                self.db_connector.execute(f"UPDATE `{self.table_name}` SET `name` = ? WHERE id = ?", (text, item_id,))
                if self.table_name in ['agents', 'blocks', 'tools', 'tasks', 'entities']:  # todo
                    self.db_connector.execute(f"UPDATE `{self.table_name}` SET `config` = json_set(config, '$.name', ?) WHERE id = ?", (text, item_id,))
                # self.reload_current_row()

                is_baked = self.is_tree_item_baked()
                auto_bake = system.manager.config.get('system.auto_bake', False)
                if auto_bake and is_baked:
                    self.bake_item(force=True)

                # if is_baked and old_name != text and hasattr(self, 'get_module_file_path'):  # todo dedupe
                #     old_file_path = self.get_module_file_path(item_id, module_name=old_name)
                #     os.remove(old_file_path)
                    
                self.load()

            except sqlite3.IntegrityError as e:
                display_message(
                    message=f"Error renaming item, name already exists",
                    icon=QMessageBox.Warning,
                )
                return

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

    def add_folder(self, name=None, parent_folder=None):
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
            name, ok = QInputDialog.getText(self, dlg_title, dlg_prompt)
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

            text, ok = QInputDialog.getText(self, dlg_title, dlg_prompt)
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
        menu = QMenu(self)

        btn_rename = menu.addAction('Rename')
        btn_duplicate = menu.addAction('Duplicate')
        btn_delete = menu.addAction('Delete')

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

        # add separator
        if self.items_pinnable:
            menu.addSeparator()
            is_pinned = self.is_tree_item_pinned()
            btn_pin = menu.addAction('Pin' if not is_pinned else 'Unpin')
            btn_pin.triggered.connect(self.pin_item)

        is_exe = getattr(sys, 'frozen', False)
        if not is_exe:
            item = self.tree.currentItem()
            if item:
                # tag = item.data(0, Qt.UserRole)
                # if tag != 'folder':
                menu.addSeparator()
                is_baked = self.is_tree_item_baked()
                if is_baked:
                    auto_bake = system.manager.config.get('system.auto_bake', False)
                    if not auto_bake:
                        btn_bake = menu.addAction('Bake')
                        btn_bake.triggered.connect(self.bake_item)
                        
                    btn_unbake = menu.addAction('Unbake')
                    btn_unbake.triggered.connect(self.unbake_item)
                else:
                    btn_bake = menu.addAction('Bake')
                    btn_bake.triggered.connect(self.bake_item)

        btn_rename.triggered.connect(self.rename_item)
        btn_duplicate.triggered.connect(self.duplicate_item)
        btn_delete.triggered.connect(self.delete_item)

        self.on_context_menu(menu)
        menu.exec_(QCursor.pos())

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

        item_tuple = self.db_connector.get_results(f"""
            SELECT
                uuid,
                name
            FROM `{self.table_name}`
            WHERE id = ?
        """, (item_id,), return_type='tuple')

        if not item_tuple:
            return

        uuid, name = item_tuple[:2]

        app_path = get_application_path()
        baked_dir_path = os.path.join(app_path, 'src', 'utils', 'baked', self.table_name)
        os.makedirs(baked_dir_path, exist_ok=True)

        short_uuid = f'_{uuid[:4]}'
        safe_filename = f"{convert_to_safe_case(name) + short_uuid}.yaml"
        safe_filepath = os.path.join(baked_dir_path, safe_filename)

        if os.path.exists(safe_filepath):
            os.remove(safe_filepath)

        self.db_connector.execute(f"UPDATE `{self.table_name}` SET baked = 0 WHERE id = ?", (item_id,))
        self.load()
        # self.load()

    def bake_item(self, force=False):
        if not self.items_bakeable:
            return

        # check if running from source code or executable
        is_exe = getattr(sys, 'frozen', False)
        if is_exe:
            if not force:
                display_message(
                    message='Baking is not supported from binaries.',
                    icon=QMessageBox.Information,
                )
            return

        table_name = self.table_name
        bake_columns = ['uuid', 'name', 'config', 'parent_id']
        item = self.tree.currentItem()
        if not item:
            return
        tag = item.data(0, Qt.UserRole)
        if tag == 'folder':
            table_name = 'folders'
            item_id = self.get_selected_folder_id()
            bake_columns += ['type']
        else:
            item_id = self.get_selected_item_id()

        if not item_id:
            return
        
        non_existing_columns = [
            col for col in bake_columns 
            if self.db_connector.get_scalar(f"SELECT COUNT(*) FROM pragma_table_info('{table_name}') WHERE name = ?", (col,)) == 0
        ]
        # table_has_uuid_col = self.db_connector.get_scalar(f"SELECT COUNT(*) FROM pragma_table_info('{table_name}') WHERE name = 'uuid'") > 0
        if 'uuid' in non_existing_columns:
            display_message(
                message=f"Table `{table_name}` does not have a 'uuid' column. Cannot bake.",
                icon=QMessageBox.Warning,
            )
            return
        
        bake_columns = [col for col in bake_columns if col not in non_existing_columns]

        item_tuple = self.db_connector.get_results(f"""
            SELECT
                {', '.join(bake_columns)}
            FROM `{table_name}`
            WHERE id = ?
        """, (item_id,), return_type='tuple')

        if not item_tuple:
            return

        uuid, name, config = item_tuple[:3]

        app_path = get_application_path()
        baked_dir_path = os.path.join(app_path, 'src', 'utils', 'baked', table_name)
        os.makedirs(baked_dir_path, exist_ok=True)

        short_uuid = f'_{uuid[:4]}'
        safe_filename = f"{convert_to_safe_case(name) + short_uuid}.yaml"
        safe_filepath = os.path.join(baked_dir_path, safe_filename)

        existing_baked = get_all_baked_items(table_name)
        if uuid in [baked_json['uuid'] for baked_json in existing_baked.values()]:
            if not force:
                dr = display_message_box(
                    icon=QMessageBox.Question,
                    title="Overwrite item",
                    text=f"Item with UUID {uuid} already exists in baked items. Overwrite?",
                    buttons=QMessageBox.Yes | QMessageBox.No,
                )
                if dr != QMessageBox.Yes:
                    return
                    
            existing_path = next((path for path, baked_json in existing_baked.items() if baked_json['uuid'] == uuid), None)
            # rename the existing file to new filename
            os.rename(existing_path, safe_filepath)

        wrapped_config = {
            col_name: item_tuple[i] for i, col_name in enumerate(bake_columns)
        }
        wrapped_config['config'] = json.loads(config)

        parent_id = wrapped_config.pop('parent_id', None)
        if parent_id:
            parent_uuid = self.db_connector.get_scalar(
                f"SELECT uuid FROM `{table_name}` WHERE id = ?", (parent_id,))
            if parent_uuid:
                wrapped_config['parent_uuid'] = parent_uuid

        folder_id = self.db_connector.get_scalar(f"SELECT folder_id FROM `{table_name}` WHERE id = ?", (item_id,))
        if folder_id:
            folder_path = self.get_folder_path_from_id(folder_id)
            wrapped_config['folder_path'] = folder_path

        try:
            # Write the config dictionary to the YAML file with pretty printing
            # Create a custom SafeDumper class with our string representer
            class CustomDumper(yaml.SafeDumper):
                pass
            
            # Add our custom string representer to handle multiline strings properly
            CustomDumper.add_representer(str, str_presenter)
            
            with open(safe_filepath, 'w', encoding='utf-8') as f:
                yaml.dump(wrapped_config, f, 
                         Dumper=CustomDumper,
                         default_flow_style=False, 
                         allow_unicode=True, 
                         sort_keys=False,
                         width=1000,
                         line_break='\n')

            if not force:
                display_message(
                    message=f"Successfully baked item to:\n{safe_filepath}",
                    icon=QMessageBox.Information,
                )
            
            is_baked = self.db_connector.get_scalar(f"SELECT baked FROM `{table_name}` WHERE id = ?", (item_id,)) == 1
            if not is_baked:
                self.db_connector.execute(f"UPDATE `{table_name}` SET baked = 1 WHERE id = ?", (item_id,))
                self.load()

        except Exception as e:
            display_message(
                message=f"Failed to write file.\nError: {e}",
                icon=QMessageBox.Critical,
            )

    def show_history_context_menu(self):
        if not self.versionable:
            return

        id = self.get_selected_item_id()
        if not id:
            return

        metadata = self.db_connector.get_scalar(f"""
            SELECT metadata
            FROM `{self.table_name}`
            WHERE id = ?
        """, (id,))
        if not metadata:
            return

        metadata = json.loads(metadata)
        current_version = metadata.get('current_version', None)
        versions = metadata.get('versions', {})

        menu = QMenu(self)
        for key, value in versions.items():
            action = menu.addAction(key)
            action.setCheckable(True)
            action.setChecked(key == current_version)
            action.triggered.connect(lambda: self.load_version(key))
        # show_history = menu.addAction('Last week')
        # show_history = menu.addAction('Yesterday 17:42')
        sep = menu.addSeparator()
        # show_history = menu.addAction('Newwww')
        # sep = menu.addSeparator()
        # show_history = menu.addAction('Delete version')
        show_history = menu.addAction('Save as new version')
        # show_history.triggered.connect(self.show_history)
        menu.exec_(QCursor.pos())

    def load_version(self, version_config):
        pass

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

    def is_tree_item_baked(self):
        # todo temp
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
        else:
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