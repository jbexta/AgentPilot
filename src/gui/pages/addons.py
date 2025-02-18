import json

from PySide6.QtWidgets import QFileDialog, QMessageBox
from aiohttp.client_reqrep import json_re

from src.gui.config import ConfigDBTree, ConfigJoined, ConfigJsonDBTree
from src.gui.widgets import IconButton, find_main_widget
from src.utils import sql
from src.utils.helpers import block_pin_mode, display_message, display_message_box, get_metadata


class Page_Addon_Settings(ConfigDBTree):
    def __init__(self, parent):
        super().__init__(
            parent=parent,
            table_name='addons',
            query="""
                SELECT
                    name,
                    id,
                    folder_id
                FROM addons
                ORDER BY pinned DESC, ordr, name""",
            schema=[
                {
                    'text': 'Modules',
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
            add_item_options={'title': 'New addon', 'prompt': 'Enter a name for the addon:'},
            del_item_options={'title': 'Delete addon', 'prompt': 'Are you sure you want to delete this addon?'},
            folder_key='addons',
            readonly=False,
            layout_type='vertical',
            tree_header_hidden=True,
            config_widget=self.Addon_Config_Widget(parent=self),
            searchable=True,
            default_item_icon=':/resources/icon-jigsaw-solid.png',
        )
        self.icon_path = ":/resources/icon-jigsaw.png"
        self.try_add_breadcrumb_widget(root_title='Addons')
        self.splitter.setSizes([400, 1000])

    def after_init(self):
        btn_save_as = IconButton(
            parent=self.tree_buttons,
            icon_path=':/resources/icon-save.png',
            tooltip='Save As',
            size=19,
        )
        btn_save_as.clicked.connect(self.save_as)
        self.tree_buttons.add_button(btn_save_as, 'btn_save_as')

        btn_import = IconButton(
            parent=self.tree_buttons,
            icon_path=':/resources/icon-import.png',
            tooltip='Import',
            size=19,
        )
        btn_import.clicked.connect(self.import_addon)
        self.tree_buttons.add_button(btn_import, 'btn_import')

        btn_nuke = IconButton(
            parent=self.tree_buttons,
            icon_path=':/resources/icon-nuke.png',
            tooltip='Delete this addon and all containing items',
            size=19,
        )
        btn_nuke.clicked.connect(self.nuke_addon)
        self.tree_buttons.add_button(btn_nuke, 'btn_nuke')

    def save_as(self):
        # browse file location
        with block_pin_mode():
            fd = QFileDialog()
            fd.setStyleSheet("QFileDialog { color: black; }")
            fd.setAcceptMode(QFileDialog.AcceptSave)
            fd.setDefaultSuffix('agp')
            filename, _ = fd.getSaveFileName(None, "Save As", "", "Add-on Files (*.agp)")

        if not filename:
            return

        if not filename.endswith('.agp'):
            filename += '.agp'

        # get selected item
        addon_id = self.get_selected_item_id()
        if not addon_id:
            return

        # get bundle data
        addon_uuid, addon_name, addon_config = sql.get_scalar(f"SELECT uuid, name, config FROM addons WHERE id = ?", (addon_id,), return_type='tuple')
        addon_data = json.loads(addon_config)

        block_uuids = addon_data.get('blocks.data', [])
        agent_uuids = addon_data.get('agents.data', [])
        module_uuids = addon_data.get('modules.data', [])
        tool_uuids = addon_data.get('tools.data', [])

        from src.utils.sql_upgrade import upgrade_script
        current_version = list(upgrade_script.versions.keys())[-1]

        file = {
            'name': addon_name,
            'uuid': addon_uuid,
            'version': current_version,
            'config': {
                'blocks': self.get_table_data('blocks', block_uuids),
                'entities': self.get_table_data('entities', agent_uuids),
                'modules': self.get_table_data('modules', module_uuids),
                'tools': self.get_table_data('tools', tool_uuids),
            }
        }
        # remove config entries if value is empty
        file['config'] = {k: v for k, v in file['config'].items() if v}

        with open(filename, 'w') as f:
            f.write(json.dumps(file, indent=4))

    def get_table_data(self, table_name, uuids):
        data = []
        for uuid in uuids:  # todo bug
            name, folder_id, config = sql.get_scalar(f"SELECT name, folder_id, config FROM {table_name} WHERE uuid = ?", (uuid,), return_type='tuple')
            system_folder_name = sql.get_scalar(f"SELECT name FROM folders WHERE id = ? AND locked = 1", (folder_id,))
            data.append({
                'name': name,
                'uuid': uuid,
                'folder': system_folder_name,
                'config': json.loads(config),
            })
        return data

    def import_addon(self):
        with block_pin_mode():
            fd = QFileDialog()
            fd.setStyleSheet("QFileDialog { color: black; }")  # Modify text color

            # filter to .agp files
            filename, _ = fd.getOpenFileName(None, "Choose Add-on", "", "Add-on Files (*.agp)")

        if filename:
            # try:
            #     self.verify_addon(filename)
            # except Exception as e:
            #     display_message(self, message='Invalid Add-on', icon=QMessageBox.Warning)

            try:
                self.install_addon(filename)
            except Exception as e:
                display_message(self, message=f'Error installing Add-on: {str(e)}', icon=QMessageBox.Warning)

        from src.system.base import manager
        manager.load()
        self.load()
        main = find_main_widget(self)
        main.main_menu.build_custom_pages()
        main.page_settings.build_schema()

    def install_addon(self, filename):
        file_text = open(filename, 'r').read()
        json_data = json.loads(file_text)

        name = json_data['name']
        uuid = json_data['uuid']
        config = json_data['config']
        version = json_data['version']

        uuid_exists = sql.get_scalar(f"SELECT uuid FROM addons WHERE uuid = '{uuid}'")
        if uuid_exists:
            display_message(self, message='Add-on already installed')
            return

        # extract to tables
        table_keys = ['blocks', 'entities', 'modules', 'tools']

        any_uuids_exist = False
        for table_name in table_keys:
            table_data = config.get(table_name, [])
            item_uuids = [item['uuid'] for item in table_data]
            uuids_that_exist = self.uuids_that_exist(table_name, item_uuids)
            if uuids_that_exist:
                any_uuids_exist = True

        if any_uuids_exist:
            retval = display_message_box(
                icon=QMessageBox.Warning,
                title='Name conflict',
                text='Some items in the Add-on already exist in the database, these will be overwritten. Do you want to continue?',
                buttons=QMessageBox.Yes | QMessageBox.No
            )
            if retval != QMessageBox.Yes:
                return

        for table_key in table_keys:
            table_data = config.get(table_key, [])
            self.extract_table(table_data, table_key)

        task_config = {}
        for table_key in table_keys:
            task_config[f'{table_key}.data'] = [item['uuid'] for item in json_data['config'].get(table_key, [])]

        sql.execute(f"""
            INSERT INTO addons (name, uuid, config)
            VALUES (?, ?, ?)
        """, (name, uuid, json.dumps(task_config)))

    def extract_table(self, table_data, table_key):
        new_entries = []
        update_entries = []
        table_existing_uuids = sql.get_results(f"SELECT uuid FROM {table_key}", return_type='list')
        for item in table_data:
            name = item['name']
            uuid = item['uuid']
            config = json.dumps(item['config'])
            system_folder_name = item.get('folder', None)
            system_folder_id = None
            if system_folder_name:
                system_folder_id = sql.get_scalar(f"SELECT id FROM folders WHERE name = ? AND locked = 1",
                                                (system_folder_name,))
            if uuid in table_existing_uuids:
                update_entries.append((name, uuid, system_folder_id, config))
            else:
                new_entries.append((name, uuid, system_folder_id, config))

        if new_entries:
            insert_query = f"""
                INSERT INTO {table_key} (name, uuid, folder_id, config)
                VALUES """ + ', '.join(['(?, ?, ?, ?)'] * len(new_entries))
            params = [param for entry in new_entries for param in entry]
            sql.execute(insert_query, params)

        if update_entries:
            for entry in update_entries:
                sql.execute(f"""
                    UPDATE {table_key}
                    SET config = ?, folder_id = ?, name = ?
                    WHERE uuid = ?
                """, (entry[3], entry[2], entry[0], entry[1],))

        if table_key == 'modules':
            uuid_configs = {item['uuid']: item['config'] for item in table_data}
            uuid_metadatas = {uuid: get_metadata(config) for uuid, config in uuid_configs.items()}
            for uuid, metadata in uuid_metadatas.items():
                sql.execute(f"""
                    UPDATE modules
                    SET metadata = ?
                    WHERE uuid = ?
                """, (json.dumps(metadata), uuid))

    def uuids_that_exist(self, table_name, item_uuids):
        return sql.get_results(
            f"""SELECT uuid FROM {table_name} WHERE uuid IN ("{'", "'.join(item_uuids)}")""",
            return_type='list'
        )

    def nuke_addon(self):
        addon_id = self.get_selected_item_id()
        if not addon_id:
            return

        addon_uuid = sql.get_scalar(f"SELECT uuid FROM addons WHERE id = ?", (addon_id,))

        retval = display_message_box(
            icon=QMessageBox.Warning,
            title='Nuke Add-on',
            text='Are you sure you want to delete this Add-on and all containing items?',
            buttons=QMessageBox.Yes | QMessageBox.No
        )
        if retval != QMessageBox.Yes:
            return

        addon_data = sql.get_scalar(f"SELECT config FROM addons WHERE id = ?", (addon_id,))
        addon_data = json.loads(addon_data)
        block_uuids = addon_data.get('blocks.data', [])
        agent_uuids = addon_data.get('agents.data', [])
        module_uuids = addon_data.get('modules.data', [])
        tool_uuids = addon_data.get('tools.data', [])

        for table_name, uuids in zip(['blocks', 'entities', 'modules', 'tools'], [block_uuids, agent_uuids, module_uuids, tool_uuids]):
            sql.execute(f""" DELETE FROM {table_name} WHERE uuid IN ("{'", "'.join(uuids)}") """)

        sql.execute(f""" DELETE FROM addons WHERE id = ? """, (addon_id,))

        from src.system.base import manager
        manager.load()
        self.load()
        main = find_main_widget(self)
        main.main_menu.build_custom_pages()
        main.page_settings.build_schema()

    class Addon_Config_Widget(ConfigJoined):
        def __init__(self, parent):
            super().__init__(parent=parent, layout_type='horizontal')
            self.widgets = [
                self.Addon_Blocks(parent=self),
                self.Addon_Entities(parent=self),
                self.Addon_Tools(parent=self),
                self.Addon_Modules(parent=self),
                # self.Module_Config_Fields(parent=self),
            ]

        class Addon_Blocks(ConfigJsonDBTree):
            def __init__(self, parent):
                super().__init__(
                    parent=parent,
                    add_item_options={'title': 'NA', 'prompt': 'NA'},
                    del_item_options={'title': 'NA', 'prompt': 'NA'},
                    # tree_header_hidden=True,
                    table_name='blocks',
                    key_field='uuid',
                    item_icon_path=':/resources/icon-block.png',
                    show_fields=[
                        'name',
                        'uuid',  # ID ALWAYS LAST
                    ],
                    readonly=True,
                )
                self.conf_namespace = 'blocks'
                self.schema = [
                    {
                        'text': 'Blocks',
                        'key': 'name',
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

        class Addon_Entities(ConfigJsonDBTree):
            def __init__(self, parent):
                super().__init__(
                    parent=parent,
                    add_item_options={'title': 'NA', 'prompt': 'NA'},
                    del_item_options={'title': 'NA', 'prompt': 'NA'},
                    # tree_header_hidden=True,
                    table_name='entities',
                    key_field='uuid',
                    item_icon_path=':/resources/icon-agent-solid.png',
                    show_fields=[
                        'name',
                        'uuid',  # ID ALWAYS LAST
                    ],
                    readonly=True
                )
                self.conf_namespace = 'agents'
                self.schema = [
                    {
                        'text': 'Agents',
                        'key': 'name',
                        # 'image_key': 'config',
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

        class Addon_Modules(ConfigJsonDBTree):
            def __init__(self, parent):
                super().__init__(
                    parent=parent,
                    add_item_options={'title': 'NA', 'prompt': 'NA'},
                    del_item_options={'title': 'NA', 'prompt': 'NA'},
                    # tree_header_hidden=True,
                    table_name='modules',
                    key_field='uuid',
                    item_icon_path=':/resources/icon-jigsaw-solid.png',
                    show_fields=[
                        'name',
                        'uuid',  # ID ALWAYS LAST
                    ],
                    readonly=True
                )
                self.conf_namespace = 'modules'
                self.schema = [
                    {
                        'text': 'Modules',
                        'key': 'name',
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

        class Addon_Tools(ConfigJsonDBTree):
            def __init__(self, parent):
                super().__init__(
                    parent=parent,
                    add_item_options={'title': 'NA', 'prompt': 'NA'},
                    del_item_options={'title': 'NA', 'prompt': 'NA'},
                    # tree_header_hidden=True,
                    table_name='tools',
                    key_field='uuid',
                    item_icon_path=':/resources/icon-tool-small.png',
                    show_fields=[
                        'name',
                        'uuid',  # ID ALWAYS LAST
                    ],
                    readonly=True
                )
                self.conf_namespace = 'tools'
                self.schema = [
                    {
                        'text': 'Tools',
                        'key': 'name',
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

        # class Module_Config_Fields(ConfigFields):
        #     def __init__(self, parent):
        #         super().__init__(parent=parent)
        #         self.schema = [
        #             {
        #                 'text': 'Load on startup',
        #                 'type': bool,
        #                 'default': True,
        #                 'row_key': 0,
        #             },
        #             {
        #                 'text': 'Data',
        #                 'type': str,
        #                 'default': '',
        #                 'num_lines': 2,
        #                 'stretch_x': True,
        #                 'stretch_y': True,
        #                 'highlighter': 'PythonHighlighter',
        #                 'gen_block_folder_name': 'Generate page',
        #                 'label_position': None,
        #             },
        #         ]
