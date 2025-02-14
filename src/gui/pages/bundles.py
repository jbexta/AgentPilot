import json

from PySide6.QtWidgets import QFileDialog, QMessageBox
from aiohttp.client_reqrep import json_re

from src.gui.config import ConfigDBTree, ConfigJoined, ConfigJsonDBTree
from src.gui.widgets import IconButton
from src.utils import sql
from src.utils.helpers import block_pin_mode, display_message, display_message_box


class Page_Bundle_Settings(ConfigDBTree):
    def __init__(self, parent):
        super().__init__(
            parent=parent,
            table_name='bundles',
            query="""
                SELECT
                    name,
                    id,
                    folder_id
                FROM bundles
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
            add_item_options={'title': 'New bundle', 'prompt': 'Enter a name for the bundle:'},
            del_item_options={'title': 'Delete bundle', 'prompt': 'Are you sure you want to delete this bundle?'},
            folder_key='bundles',
            readonly=False,
            layout_type='vertical',
            tree_header_hidden=True,
            config_widget=self.Bundle_Config_Widget(parent=self),
            searchable=True,
            default_item_icon=':/resources/icon-jigsaw-solid.png',
        )
        self.icon_path = ":/resources/icon-jigsaw.png"
        self.try_add_breadcrumb_widget(root_title='Bundles')
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

    def save_as(self):
        # browse file location
        with block_pin_mode():
            fd = QFileDialog()
            fd.setStyleSheet("QFileDialog { color: black; }")
            filename, _ = fd.getSaveFileName(None, "Save As", "", "Add-on Files (*.agp)")

        if not filename:
            return

        # get selected item
        bundle_id = self.get_selected_item_id()
        if not bundle_id:
            return

        # get bundle data
        bundle_uuid, bundle_name, bundle_config = sql.get_scalar(f"SELECT uuid, name, config FROM bundles WHERE id = ?", (bundle_id,), return_type='tuple')
        bundle_data = json.loads(bundle_config)

        block_uuids = bundle_data.get('blocks.data', [])
        agent_uuids = bundle_data.get('agents.data', [])
        module_uuids = bundle_data.get('modules.data', [])
        tool_uuids = bundle_data.get('tools.data', [])

        from src.utils.sql_upgrade import upgrade_script
        current_version = list(upgrade_script.versions.keys())[-1]

        file = {
            'name': bundle_name,
            'uuid': bundle_uuid,
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

        # blocks_data = self.get_table_data('blocks', block_uuids)
        # if len(blocks_data) > 0:
        #     file['config']['blocks'] = blocks_data

        with open(filename, 'w') as f:
            f.write(json.dumps(file, indent=4))

    def get_table_data(self, table_name, uuids):
        data = []
        for uuid in uuids:  # todo bug
            name, config = sql.get_scalar(f"SELECT name, config FROM {table_name} WHERE uuid = ?", (uuid,), return_type='tuple')
            data.append({
                'name': name,
                'uuid': uuid,
                'config': json.loads(config),
            })
        return data

    def add_itemm(self):
        with block_pin_mode():
            fd = QFileDialog()
            fd.setStyleSheet("QFileDialog { color: black; }")  # Modify text color

            # filter to .agp files
            filename, _ = fd.getOpenFileName(None, "Choose Add-on", "", "Add-on Files (*.agp)")

        if filename:
            try:
                self.verify_addon(filename)
            except Exception as e:
                display_message(self, message='Invalid Add-on', icon=QMessageBox.Warning)

            try:
                self.install_addon(filename)
            except Exception as e:
                display_message(self, message='Error installing Add-on', icon=QMessageBox.Warning)

    def install_addon(self, filename):
        file_text = open(filename, 'r').read()
        json_data = json.loads(file_text)

        name = json_data['name']
        uuid = json_data['uuid']
        config = json_data['config']
        version = json_data['version']

        uuid_exists = sql.get_scalar(f"SELECT uuid FROM bundles WHERE uuid = '{uuid}'")
        if uuid_exists:
            display_message(self, message='Add-on already installed')
            return

        # extract to tables
        table_keys = ['blocks', 'entities', 'modules', 'tools']

        any_names_exist = False
        for table_name in table_keys:
            table_data = config.get(table_name, [])
            item_names = [item['name'] for item in table_data]
            names_that_exist = self.names_that_exist(table_name, item_names)
            if names_that_exist:
                any_names_exist = True

        if any_names_exist:
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

        sql.execute(f"""
            INSERT INTO bundles (name, uuid, config)
            VALUES (?, ?, ?)
        """, (name, uuid, file_text))

    def extract_table(self, table_data, table_key):
        new_entries = []
        update_entries = []
        table_existing_names = sql.get_scalar(f"SELECT name FROM {table_key}", return_type='list')
        for item in table_data:
            name = item['name']
            uuid = item['uuid']
            config = item['config']
            if name in table_existing_names:
                update_entries.append((name, uuid, config))
            else:
                new_entries.append((name, uuid, config))

        if new_entries:
            insert_query = f"""
                INSERT INTO {table_key} (name, uuid, config)
                VALUES """ + ', '.join(['(?, ?, ?)'] * len(new_entries))
            params = [param for entry in new_entries for param in entry]
            sql.execute(insert_query, params)

        if update_entries:
            for entry in update_entries:
                sql.execute(f"""
                    UPDATE {table_key}
                    SET config = ?, uuid = ?
                    WHERE name = ?
                """, (entry[2], entry[1], entry[0]))

    def names_that_exist(self, table_name, item_names):
        return sql.get_scalar(
            f"SELECT name FROM {table_name} WHERE name IN ({', '.join(item_names)})",
            return_type='list'
        )


    class Bundle_Config_Widget(ConfigJoined):
        def __init__(self, parent):
            super().__init__(parent=parent, layout_type='horizontal')
            self.widgets = [
                self.Bundle_Blocks(parent=self),
                self.Bundle_Entities(parent=self),
                self.Bundle_Tools(parent=self),
                self.Bundle_Modules(parent=self),
                # self.Module_Config_Fields(parent=self),
            ]

        class Bundle_Blocks(ConfigJsonDBTree):
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

        class Bundle_Entities(ConfigJsonDBTree):
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

        class Bundle_Modules(ConfigJsonDBTree):
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

        class Bundle_Tools(ConfigJsonDBTree):
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
