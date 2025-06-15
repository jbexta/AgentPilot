import json
import os

from PySide6.QtWidgets import *
from PySide6.QtGui import Qt, QCursor
from typing_extensions import override

from src.utils.helpers import block_pin_mode, display_message_box, \
    merge_config_into_workflow_config, convert_to_safe_case, \
    display_message, ManagerController

from src.gui.util import find_main_widget, save_table_config
from src.utils import sql

from src.gui.widgets.config_tree import ConfigTree


class ConfigDBTree(ConfigTree):
    """
    A widget that displays a tree of items from the db, with buttons to add and delete items.
    Can contain a config widget shown either to the right of the tree or below it,
    representing the config for each item in the tree.
    """
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
        self.propagate = False
        # # # self.db_config_field = kwargs.get('db_config_field', 'config')
        # # # self.config_buttons = kwargs.get('config_buttons', None)
        # # # self.user_editable = True
        from src.system import manager as system
        if self.manager and isinstance(self.manager, str):  # todo clean
            self.manager = getattr(system, self.manager)
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
            self.manager = ManagerController(
                system,
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

        self.schema_overrides = {}
        # define_table(self.table_name)
        self.current_version = None  # todo, should be here?

        if self.show_tree_buttons:
            self.tree_buttons.btn_add.clicked.connect(self.add_item)
            self.tree_buttons.btn_del.clicked.connect(self.delete_item)
            if hasattr(self.tree_buttons, 'btn_new_folder'):
                self.tree_buttons.btn_new_folder.clicked.connect(self.add_folder_btn_clicked)
            if hasattr(self.tree_buttons, 'btn_run'):
                self.tree_buttons.btn_run.clicked.connect(self.run_btn_clicked)
            if not self.add_item_options:
                self.tree_buttons.btn_add.hide()
            if not self.del_item_options:
                self.tree_buttons.btn_del.hide()

        if hasattr(self, 'after_init'):
            self.after_init()

    @override
    def load(self, select_id=None, silent_select_id=None, append=False):
        """
        Loads the QTreeWidget with folders and agents from the database.
        """
        if self.__class__.__name__ == 'Tab_Chat_Models':
            pass
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
        if kind:
            if not self.query_params:
                self.query_params = {}
            self.query_params['kind'] = kind
        # if self.kind:
        #     if not self.query_params:
        #         self.query_params = {}
        #     self.query_params['kind'] = self.kind

        group_folders = False
        if self.show_tree_buttons:
            if hasattr(self.tree_buttons, 'btn_group_folders'):
                group_folders = self.tree_buttons.btn_group_folders.isChecked()

        # query = self.query if not self.filterable else self.query.replace('{{kind}}', self.filter_widget.get_kind())
        data = sql.get_results(query=self.query, params=self.query_params)
        self.tree.load(
            data=data,
            append=append,
            select_id=select_id,
            silent_select_id=silent_select_id,
            folder_key=self.folder_key,
            # kind_folders=self.kind_folders,
            init_select=self.init_select,
            readonly=self.readonly,
            schema=self.schema,
            group_folders=group_folders,
            default_item_icon=self.default_item_icon,
        )
        if len(data) == 0:
            return

        if hasattr(self, 'load_count'):
            self.load_count += 1

    def reload_current_row(self):
        data = sql.get_results(query=self.query, params=self.query_params)
        self.tree.reload_selected_item(data=data, schema=self.schema)

    @override
    def update_config(self):
        """Overrides to stop propagation to the parent."""
        self.save_config()

    @override
    def save_config(self):
        """
        Saves the config to the database using the tree selected ID.
        """
        item_id = self.get_selected_item_id()
        config = self.get_config()

        save_table_config(
            ref_widget=self,
            table_name=self.table_name,
            item_id=item_id,
            value=json.dumps(config),
        )

    def on_edited(self):
        if self.manager is not None:
            self.manager.load()
        # from src.system import manager
        # manager.blocks.load()

    def on_item_selected(self):
        self.current_version = None

        item_id = self.get_selected_item_id()
        folder_id = self.get_selected_folder_id()
        if hasattr(self.tree_buttons, 'btn_run'):
            self.tree_buttons.btn_run.setVisible(item_id is not None)
        if hasattr(self.tree_buttons, 'btn_versions'):
            self.tree_buttons.btn_versions.setVisible(item_id is not None)

        if item_id and self.config_widget:
            item_type = 'item'
            self.toggle_config_widget(item_type)

            self.config_widget.maybe_rebuild_schema(self.schema_overrides, item_id)

            json_config = sql.get_scalar(f"""
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
                json_config = merge_config_into_workflow_config(json_config, entity_id=item_id, entity_table=self.table_name)
            self.config_widget.load_config(json_config)
            self.config_widget.load()

        elif folder_id and self.folder_config_widget:
            item_type = 'folder'
            self.toggle_config_widget(item_type)

            json_config = sql.get_scalar(f"""
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
        sql.execute("""
            UPDATE folders
            SET expanded = ?
            WHERE id = ?
        """, (expanded, folder_id,))

    def toggle_config_widget(self, config_type):
        type_map = {
            'item': self.config_widget,
            'folder': self.folder_config_widget,
        }
        for w in type_map.values():
            if w:
                w.setEnabled(False)
                w.setVisible(False)

        widget = type_map.get(config_type, None)
        if not widget:
            return

        # enabled = widget is not None and widget.isEnabled() and widget.isVisible()
        widget.setEnabled(True)
        widget.setVisible(True)
        #
        # enabled = widget is not None and widget.isEnabled() and widget.isVisible()
        #
        # widget = self.config_widget
        # if widget:
        #     widget.setEnabled(enabled)
        #     widget.setVisible(enabled)

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
                sql.execute(f"""
                    UPDATE `{self.table_name}`
                    SET `{col_key}` = ?
                    WHERE id = ?
                """, (new_value, item_id,))
            except Exception as e:
                display_message(self,
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

        with block_pin_mode():
            text, ok = QInputDialog.getText(self, dlg_title, dlg_prompt)

            if not ok:
                return

        from src.gui.util import find_ancestor_tree_item_id

        kwargs = {}
        if self.table_name == 'models':  # todo automatic relations
            api_id = find_ancestor_tree_item_id(self)
            kwargs['api_id'] = api_id
        kind = self.filter_widget.get_kind() if hasattr(self, 'filter_widget') else self.kind
        if kind:
            kwargs['kind'] = kind
        # elif self.table_name == 'workspace_concepts':
        #     workspace_id = find_ancestor_tree_item_id(self)  #  self.parent.parent.parent.get_selected_item_id()
        #     kwargs['workspace_id'] = workspace_id

        self.manager.add(name=text, **kwargs)
        last_insert_id = sql.get_scalar("SELECT seq FROM sqlite_sequence WHERE name=?", (self.table_name,))
        self.load(select_id=last_insert_id)

    def delete_item(self):
        item = self.tree.currentItem()
        if not item:
            return
        tag = item.data(0, Qt.UserRole)
        if tag == 'folder':
            folder_id = int(item.text(1))
            is_locked = sql.get_scalar(f"""SELECT locked FROM folders WHERE id = ?""", (folder_id,)) or False
            if is_locked == 1:
                display_message(self,
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
            sql.execute(f"""
                UPDATE `{self.table_name}`
                SET folder_id = {'NULL' if not folder_parent_id else folder_parent_id}
                WHERE folder_id = ?
            """, (folder_id,))
            # Unpack all folders from folder to parent folder (or root)
            sql.execute(f"""
                UPDATE `folders`
                SET parent_id = {'NULL' if not folder_parent_id else folder_parent_id}
                WHERE parent_id = ?
            """, (folder_id,))

            sql.execute(f"""
                DELETE FROM folders
                WHERE id = ?
            """, (folder_id,))

            self.on_edited()
            self.load()

        else:
            item_id = self.get_selected_item_id()
            if not item_id:
                return

            del_opts = self.del_item_options
            if not del_opts:
                return

            dlg_title = del_opts['title']
            dlg_prompt = del_opts['prompt']

            retval = display_message_box(
                icon=QMessageBox.Warning,
                title=dlg_title,
                text=dlg_prompt,
                buttons=QMessageBox.Yes | QMessageBox.No,
            )
            if retval != QMessageBox.Yes:
                return

            self.manager.delete(item_id)
            self.load()

    def rename_item(self):
        item = self.tree.currentItem()
        if not item:
            return
        tag = item.data(0, Qt.UserRole)
        if tag == 'folder':
            folder_id = int(item.text(1))
            is_locked = sql.get_scalar(f"""SELECT locked FROM folders WHERE id = ?""", (folder_id,)) or False
            if is_locked == 1:
                display_message(self,
                    message='Folder is locked',
                    icon=QMessageBox.Information,
                )
                return

            current_name = item.text(0)
            dlg_title, dlg_prompt = ('Rename folder', 'Enter a new name for the folder')
            text, ok = QInputDialog.getText(self, dlg_title, dlg_prompt, text=current_name)
            if not ok:
                return

            sql.execute(f"UPDATE `folders` SET `name` = ? WHERE id = ?", (text, folder_id))
            # self.reload_current_row()
            self.load()

        else:
            current_name = item.text(0)
            dlg_title, dlg_prompt = ('Rename item', 'Enter a new name for the item')
            text, ok = QInputDialog.getText(self, dlg_title, dlg_prompt, text=current_name)
            if not ok:
                return

            item_id = self.get_selected_item_id()
            if not item_id:
                return

            sql.execute(f"UPDATE `{self.table_name}` SET `name` = ? WHERE id = ?", (text, item_id,))
            self.reload_current_row()

        self.on_edited()

    def pin_item(self):
        is_pinned = self.is_tree_item_pinned()
        item = self.tree.currentItem()
        if not item:
            return
        tag = item.data(0, Qt.UserRole)
        if tag == 'folder':
            sql.execute(f"UPDATE folders SET pinned = ? WHERE id = ?", (not is_pinned, int(item.text(1))))
        else:
            sql.execute(f"UPDATE `{self.table_name}` SET pinned = ? WHERE id = ?", (not is_pinned, self.get_selected_item_id()))

        self.load()

    def run_btn_clicked(self):
        main = find_main_widget(self)
        if main.page_chat.workflow.responding:
            return
        item_id = self.get_selected_item_id()
        if not item_id:
            return
        main.page_chat.new_context(entity_id=item_id, entity_table=self.table_name)
        main.page_chat.ensure_visible()

    def add_folder_btn_clicked(self):
        self.add_folder()
        self.load()

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
        folder_key = self.folder_key.get(kind) if isinstance(self.folder_key, dict) else self.folder_key
        # check if name already exists
        ex_ids = sql.get_results(f"""
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

        sql.execute(f"INSERT INTO `folders` (`name`, `parent_id`, `type`) VALUES (?, ?, ?)",
                    (name, parent_id, folder_key))
        ins_id = sql.get_scalar("SELECT MAX(id) FROM folders")

        self.on_edited()

        return ins_id

    def duplicate_item(self):
        item = self.tree.currentItem()
        if not item:
            return
        tag = item.data(0, Qt.UserRole)
        if tag == 'folder':
            display_message(self,
                message='Folders cannot be duplicated yet',
                icon=QMessageBox.Information,
            )
            return

        else:
            id = self.get_selected_item_id()
            if not id:
                return

            config = sql.get_scalar(f"""
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

            with block_pin_mode():
                text, ok = QInputDialog.getText(self, dlg_title, dlg_prompt)
                if not ok:
                    return

            if self.table_name == 'entities':
                sql.execute(f"""
                    INSERT INTO `entities` (`name`, `kind`, `config`)
                    VALUES (?, ?, ?)
                """, (text, self.kind, config))
            else:
                sql.execute(f"""
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

        if self.__class__.__name__ == 'Page_Models_Settings':
            # Add a providers submenu
            menu.addSeparator()
            providers_menu = QMenu('Provider', menu)
            menu.addMenu(providers_menu)

            # Get the current model's provider
            api_id = self.get_selected_item_id()
            current_provider = None
            if api_id:
                current_provider = sql.get_scalar("SELECT provider_plugin FROM apis WHERE id = ?", (api_id,))

            # Add providers from the plugins system
            from src.system import manager
            provider_plugins = manager.modules

            for provider_name in list(provider_plugins.keys()):
                provider_action = providers_menu.addAction(provider_name)
                provider_action.setCheckable(True)
                provider_action.setChecked(provider_name == current_provider)

                # When clicked, update the model's provider
                def make_provider_setter(p_name):
                    def set_provider():
                        if api_id:
                            sql.execute("UPDATE apis SET provider_plugin = ? WHERE id = ?",
                                       (p_name, api_id))
                            self.on_edited()
                            self.load()  # Reload config
                    return set_provider

                provider_action.triggered.connect(make_provider_setter(provider_name))

        # add separator
        if self.items_pinnable:
            menu.addSeparator()
            is_pinned = self.is_tree_item_pinned()
            btn_pin = menu.addAction('Pin' if not is_pinned else 'Unpin')
            btn_pin.triggered.connect(self.pin_item)

        if 'AP_DEV_MODE' in os.environ:
            item = self.tree.currentItem()
            if item:
                tag = item.data(0, Qt.UserRole)
                if tag != 'folder':
                    menu.addSeparator()
                    btn_bake = menu.addAction('Bake')
                    btn_bake.triggered.connect(self.bake_item)

        btn_rename.triggered.connect(self.rename_item)
        btn_duplicate.triggered.connect(self.duplicate_item)
        btn_delete.triggered.connect(self.delete_item)

        menu.exec_(QCursor.pos())

    def bake_item(self):
        pass

    def show_history_context_menu(self):
        if not self.versionable:
            return

        id = self.get_selected_item_id()
        if not id:
            return

        metadata = sql.get_scalar(f"""
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
            is_pinned = sql.get_scalar(f"""
                SELECT pinned
                FROM folders
                WHERE id = ?
                """, (folder_id,)) == 1
            return is_pinned

        else:
            item_id = self.get_selected_item_id()
            if not item_id:
                return False
            is_pinned = sql.get_scalar(f"""
                SELECT pinned
                FROM `{self.table_name}`
                WHERE id = ?
                """, (item_id,)) == 1
            return is_pinned

    def check_infinite_load(self):
        if self.tree.verticalScrollBar().value() == self.tree.verticalScrollBar().maximum():
            self.load(append=True)