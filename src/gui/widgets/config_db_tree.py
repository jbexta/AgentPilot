import json
from sqlite3 import IntegrityError

from PySide6.QtWidgets import *
from PySide6.QtGui import Qt, QCursor
from typing_extensions import override

from src.utils.helpers import block_pin_mode, display_message_box, \
    merge_config_into_workflow_config, convert_to_safe_case, \
    display_message, get_module_type_folder_id

from src.gui.util import find_main_widget, save_table_config
from src.utils import sql

from src.gui.widgets.config_tree import ConfigTree


class ConfigDBTree(ConfigTree):
    """
    A widget that displays a tree of items from the db, with buttons to add and delete items.
    Can contain a config widget shown either to the right of the tree or below it,
    representing the config for each item in the tree.
    """
    def __init__(self, parent, **kwargs):
        super().__init__(parent=parent, **kwargs)
        self.default_schema = self.schema.copy()
        self.kind = kwargs.get('kind', None)
        # self.kind_folders = kwargs.get('kind_folders', None)
        self.query = kwargs.get('query', None)
        self.query_params = kwargs.get('query_params', ())
        self.table_name = kwargs.get('table_name', None)
        self.propagate = False
        # self.db_config_field = kwargs.get('db_config_field', 'config')
        # self.config_buttons = kwargs.get('config_buttons', None)
        # self.user_editable = True

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
        if not self.query:
            return

        if hasattr(self, 'load_count'):
            if not append:
                self.load_count = 0
            limit = 100
            offset = self.load_count * limit
            self.query_params = (limit, offset,)

        group_folders = False
        if self.show_tree_buttons:
            if hasattr(self.tree_buttons, 'btn_group_folders'):
                group_folders = self.tree_buttons.btn_group_folders.isChecked()

        query = self.query if not self.filterable else self.query.replace('{{kind}}', self.filter_widget.get_kind())
        data = sql.get_results(query=query, params=self.query_params)
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

    def on_item_selected(self):
        self.current_version = None

        item_id = self.get_selected_item_id()
        if hasattr(self.tree_buttons, 'btn_run'):
            self.tree_buttons.btn_run.setVisible(item_id is not None)
        if hasattr(self.tree_buttons, 'btn_versions'):
            self.tree_buttons.btn_versions.setVisible(item_id is not None)

        if isinstance(item_id, str):
            item_id = None  # todo clean
        if not item_id:
            self.toggle_config_widget(False)
            return

        self.toggle_config_widget(True)

        if self.config_widget:
            self.config_widget.maybe_rebuild_schema(self.schema_overrides, item_id)

            json_config = json.loads(sql.get_scalar(f"""
                SELECT
                    `config`
                FROM `{self.table_name}`
                WHERE id = ?
            """, (item_id,)))

            try:
                json_metadata = json.loads(sql.get_scalar(f"""
                    SELECT
                        `metadata`
                    FROM `{self.table_name}`
                    WHERE id = ?
                """, (item_id,)))
                self.current_version = json_metadata.get('current_version', None)
            except Exception as e:
                pass

            if ((self.table_name == 'entities' or self.table_name == 'blocks' or self.table_name == 'tools')
                    and json_config.get('_TYPE', 'agent') != 'workflow'):
                json_config = merge_config_into_workflow_config(json_config)
            self.config_widget.load_config(json_config)
            self.config_widget.load()

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

    def toggle_config_widget(self, enabled):
        widget = self.config_widget
        if widget:
            widget.setEnabled(enabled)
            widget.setVisible(enabled)

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

        if hasattr(self, 'on_edited'):
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
                return False

        try:
            from src.gui.util import find_ancestor_tree_item_id
            if self.table_name == 'entities':
                from src.system import manager
                manager.agents.add(name=text, kind='AGENT', config=json.dumps({'info.name': text}))

            elif self.table_name == 'tools':
                from src.system import manager
                manager.tools.add(name=text)

            elif self.table_name == 'apis':
                from src.system import manager
                manager.apis.add(name=text, provider_plugin='litellm')

            elif self.table_name == 'blocks':
                from src.system import manager
                manager.blocks.add(name=text)

            elif self.table_name == 'models':  # todo automatic relations
                # kind = self.get_kind() if hasattr(self, 'get_kind') else ''
                api_id = find_ancestor_tree_item_id(self)  #  self.parent.parent.parent.get_selected_item_id()
                sql.execute(f"INSERT INTO `models` (`api_id`, `kind`, `name`) VALUES (?, ?, ?)",
                            (api_id, self.kind, text,))

            # elif self.table_name == 'workspace_concepts':
            #     # kind = self.get_kind() if hasattr(self, 'get_kind') else ''
            #     workspace_id = find_ancestor_tree_item_id(self)  #  self.parent.parent.parent.get_selected_item_id()
            #     sql.execute(f"INSERT INTO `workspace_concepts` (`workspace_id`, `name`) VALUES (?, ?)",
            #                 (workspace_id, text,))

            else:
                if self.kind:
                    sql.execute(f"INSERT INTO `{self.table_name}` (`name`, `kind`) VALUES (?, ?)", (text, self.kind,))
                else:
                    sql.execute(f"INSERT INTO `{self.table_name}` (`name`) VALUES (?)", (text,))

            last_insert_id = sql.get_scalar("SELECT seq FROM sqlite_sequence WHERE name=?", (self.table_name,))
            self.load(select_id=last_insert_id)

            if hasattr(self, 'on_edited'):
                self.on_edited()
                if self.table_name == 'modules':
                    main = find_main_widget(self)
                    main.main_menu.build_custom_pages()
                    main.page_settings.build_schema()
                    main.main_menu.settings_sidebar.toggle_page_pin(text, True)
            return True

        except IntegrityError:
            display_message(self,
                message='Item already exists',
                icon=QMessageBox.Warning,
            )
            return False

    def delete_item(self):
        main = find_main_widget(self)
        item = self.tree.currentItem()
        if not item:
            return None
        tag = item.data(0, Qt.UserRole)
        if tag == 'folder':
            folder_id = int(item.text(1))
            is_locked = sql.get_scalar(f"""SELECT locked FROM folders WHERE id = ?""", (folder_id,)) or False
            if is_locked == 1:
                display_message(self,
                    message='Folder is locked',
                    icon=QMessageBox.Information,
                )
                return False

            retval = display_message_box(
                icon=QMessageBox.Warning,
                title="Delete folder",
                text="Are you sure you want to delete this folder? It's contents will be extracted.",
                buttons=QMessageBox.Yes | QMessageBox.No,
            )
            if retval != QMessageBox.Yes:
                return False

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

            if hasattr(self, 'on_edited'):
                self.on_edited()
            self.load()
            return True
        else:
            item_id = self.get_selected_item_id()
            if not item_id:
                return False

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
                return False

            try:
                if self.table_name == 'contexts':
                    context_id = item_id
                    all_context_ids = sql.get_results("""
                        WITH RECURSIVE context_tree AS (
                            SELECT id FROM contexts WHERE id = ?
                            UNION ALL
                            SELECT c.id
                            FROM contexts c
                            JOIN context_tree ct ON c.parent_id = ct.id
                        )
                        SELECT id FROM context_tree;""", (context_id,), return_type='list')
                    if all_context_ids:
                        all_context_ids = tuple(all_context_ids)
                        sql.execute(f"DELETE FROM contexts_messages WHERE context_id IN ({','.join('?' * len(all_context_ids))});", all_context_ids)
                        sql.execute(f"DELETE FROM contexts WHERE id IN ({','.join('?' * len(all_context_ids))});", all_context_ids)

                elif self.table_name == 'apis':
                    api_id = item_id
                    sql.execute("DELETE FROM models WHERE api_id = ?;", (api_id,))
                elif self.table_name == 'modules':
                    from src.system import manager
                    manager.modules.unload_module(item_id)
                    pages_folder_id = get_module_type_folder_id(module_type='Pages')
                    page_name = sql.get_scalar("SELECT name FROM modules WHERE id = ? and folder_id = ?",
                                               (pages_folder_id,))
                    if page_name:
                        main.main_menu.settings_sidebar.toggle_page_pin(page_name, False)

                sql.execute(f"DELETE FROM `{self.table_name}` WHERE `id` = ?", (item_id,))

                if hasattr(self, 'on_edited'):
                    self.on_edited()
                    if self.table_name == 'modules':
                        main.main_menu.build_custom_pages()
                        main.page_settings.build_schema()
                self.load()
                return True

            except Exception as e:
                display_message(self,
                    message=f'Item could not be deleted:\n' + str(e),
                    icon=QMessageBox.Warning,
                )
                return False

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

        if hasattr(self, 'on_edited'):
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

        if hasattr(self, 'on_edited'):
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
            if hasattr(self, 'on_edited'):
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
                            if hasattr(self, 'on_edited'):
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

        btn_rename.triggered.connect(self.rename_item)
        btn_duplicate.triggered.connect(self.duplicate_item)
        btn_delete.triggered.connect(self.delete_item)

        menu.exec_(QCursor.pos())

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