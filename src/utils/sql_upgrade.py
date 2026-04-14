import json
import os
import shutil

from utils import sql
from packaging import version

from utils.reset import ensure_system_folders
from utils.sql import ensure_column_in_tables


class SQLUpgrade:
    def __init__(self):
        self.versions = {
            '0.0.8': None,
            '0.1.0': self.v0_1_0,
            '0.2.0': self.v0_2_0,
            '0.3.0': self.v0_3_0,
            '0.4.0': self.v0_4_0,
            '0.5.0': self.v0_5_0,
            '0.6.0': self.v0_6_0,
        }

    def upgrade(self, current_version):
        # make a copy of the current data.db
        db_path = sql.get_db_path()
        copy_to_path = db_path + '.copy'
        if os.path.isfile(copy_to_path):
            os.remove(copy_to_path)
        shutil.copyfile(db_path, copy_to_path)

        # run the upgrade scripts
        with sql.write_to_copy():
            for ver, run_script in self.versions.items():
                ver = version.parse(ver)
                if current_version < ver:
                    run_script()
                    current_version = ver

        # rename the original with .old
        old_filepath = db_path
        while os.path.isfile(old_filepath):
            old_filepath += '.old'
        os.rename(db_path, old_filepath)

        # rename the copy to the original
        os.rename(copy_to_path, db_path)

    def v0_6_0(self):
        # for all workflow configs (`contexts`, `entities`, `blocks`, `tools`)
        # recursively patch the config dict
        # if '_TYPE' is 'block', then replace '_TYPE' with f"{block_type}_block"
        wf_tables = ['contexts', 'entities', 'blocks', 'tools', 'tasks']
        for table in wf_tables:
            table_exists = sql.get_scalar(f"SELECT COUNT(*) FROM sqlite_master WHERE type='table' AND name='{table}'") > 0
            if not table_exists:
                continue
            rows = sql.get_results(f"SELECT id, name, config FROM {table}")
            for row_id, name, config in rows:
                config = json.loads(config)
                new_config = self.patch_config_dict_recursive_0_6_0(config)
                if 'name' not in new_config:
                    new_config['name'] = name
                sql.execute(f"""
                    UPDATE {table}
                    SET config = ?
                    WHERE id = ?""", (json.dumps(new_config), row_id))
        
        # for `settings` table, modify the `pinned_pages` field (json list), set all to lower case
        pinned_pages = sql.get_scalar("SELECT value FROM settings WHERE field = 'pinned_pages'", load_json=True)
        pinned_pages = [page.lower() for page in pinned_pages] + ['modules']
        sql.execute("UPDATE settings SET value = ? WHERE field = 'pinned_pages'", (json.dumps(pinned_pages),))

        ensure_column_in_tables(
            tables=[
                'modules',
            ],
            column_name='baked',
            column_type='INTEGER',
            default_value="0",
            not_null=True,
        )
        ensure_column_in_tables(
            tables=[
                'folders',
            ],
            column_name='uuid',
            column_type='TEXT',
            default_value="""(
                lower(hex(randomblob(4))) || '-' ||
                lower(hex(randomblob(2))) || '-' ||
                '4' || substr(lower(hex(randomblob(2))), 2) || '-' ||
                substr('89ab', abs(random()) % 4 + 1, 1) || substr(lower(hex(randomblob(2))), 2) || '-' ||
                lower(hex(randomblob(6)))
            )""",
            not_null=True,
        )
        # ensure_column_in_tables(
        #     tables=[
        #         'modules',
        #     ],
        #     column_name='kind',
        #     column_type='TEXT',
        #     default_value="NULL",
        #     # not_null=True,
        # )
        # # modules = [
        # #     "Managers",
        # #     "Pages",
        # #     "Widgets",
        # #     "Fields",
        # #     "Members",
        # #     "Bubbles",
        # #     "Providers",
        # #     "Toolkits",
        # #     "Widgets",
        # # ],
        # module_folders = sql.get_results("SELECT id, name FROM folders WHERE type = 'modules'",
        #                                  return_type='dict')
        # for module_folder_id, module_folder_name in module_folders.items():
        #     sql.execute("""
        #         UPDATE modules
        #         SET kind = ?
        #         WHERE folder_id = ?
        #     """, (module_folder_name.upper()[:-1], module_folder_id))
        # sql.execute("DELETE FROM folders WHERE type = 'modules'")

        # Roles table is deprecated in 0.6.0 — bubble styling now lives on bubble
        # module classes. The tool_approval bubble defines its own colours via
        # ToolApprovalBubble.bubble_bg_color / bubble_text_color in
        # src/plugins/claude_code/bubbles/tool_approval.py.
        #
        # tool_approval_exists = sql.get_scalar(
        #     "SELECT COUNT(*) FROM roles WHERE LOWER(name) = 'tool_approval'"
        # ) > 0
        # if not tool_approval_exists:
        #     ta_config = json.dumps({
        #         "display.bubble_bg_color": "#2d2a1e",
        #         "display.bubble_text_color": "#d4a844",
        #         "display.bubble_image_size": "0",
        #     })
        #     sql.execute(
        #         "INSERT INTO roles (name, config) VALUES ('tool_approval', ?)",
        #         (ta_config,),
        #     )

        sql.execute("""
            CREATE TABLE IF NOT EXISTS "skills" (
                "id"        INTEGER,
                "name"      TEXT NOT NULL,
                "kind"      TEXT NOT NULL DEFAULT 'USER',
                "config"    TEXT NOT NULL DEFAULT '{}',
                "folder_id" INTEGER DEFAULT NULL,
                "ordr"      INTEGER DEFAULT 0,
                "pinned"    INTEGER DEFAULT 0,
                "metadata"  TEXT DEFAULT '{}',
                "uuid"      TEXT DEFAULT (
                    lower(hex(randomblob(4))) || '-' ||
                    lower(hex(randomblob(2))) || '-' ||
                    '4' || substr(lower(hex(randomblob(2))), 2) || '-' ||
                    substr('89ab', abs(random()) % 4 + 1, 1) || substr(lower(hex(randomblob(2))), 2) || '-' ||
                    lower(hex(randomblob(6)))
                ) UNIQUE,
                "baked"     INTEGER NOT NULL DEFAULT 0,
                "parent_id" INTEGER DEFAULT NULL,
                PRIMARY KEY("id" AUTOINCREMENT)
            )
        """)

        # app config
        sql.execute("""
            UPDATE settings SET value = '0.6.0' WHERE field = 'app_version'""")

        sql.execute("""VACUUM""")

    def patch_config_dict_recursive_0_6_0(self, config):
        # recursively patch the config dict
        # if '_TYPE' is 'block', then replace '_TYPE' with f"{block_type}_block"
        config_type = config.get('_TYPE', 'agent')
        if config_type == 'block':
            block_type = config.get('_TYPE_PLUGIN', 'Text')
            config['_TYPE'] = block_type.lower()
        elif config_type == 'model':
            model_type = config.get('_TYPE_PLUGIN', 'Voice')
            config['_TYPE'] = f"{model_type.lower()}_model"
        elif config_type == 'workflow':
            members = config.get('members', [])
            for member in members:
                member['config'] = self.patch_config_dict_recursive_0_6_0(member.get('config', {}))
            config['members'] = members
            config['name'] = 'Workflow'

        config.pop('_TYPE_PLUGIN', None)

        if 'info.name' in config:
            config['name'] = config.pop('info.name')
        if 'info.avatar_path' in config:
            config['avatar_path'] = config.pop('info.avatar_path')

        return config

    def v0_5_0(self):
        sql.execute("""
            UPDATE tools
            SET config = json_insert(config, '$.extras.description', json_extract(config, '$.description'))
            WHERE json_extract(config, '$.description') IS NOT NULL
        """)
        sql.execute("""
            UPDATE tools
            SET config = json_remove(config, '$.description')
            WHERE json_extract(config, '$.description') IS NOT NULL
        """)

        sql.execute("""
            CREATE TABLE "addons" (
                "id"	INTEGER,
                "name"	TEXT NOT NULL,
                "kind"	TEXT NOT NULL DEFAULT '',
                "config"	TEXT NOT NULL DEFAULT '{}',
                "metadata"	TEXT NOT NULL DEFAULT '{}',
                "folder_id"	INTEGER DEFAULT NULL,
                "ordr"	INTEGER DEFAULT 0,
                "pinned"	INTEGER DEFAULT 0,
                PRIMARY KEY("id")
            )
        """)

        ensure_column_in_tables(
            tables=[
                'blocks',
                'addons',
                'contexts',
                'entities',
                'modules',
                'tools',
            ],
            column_name='metadata',
            column_type='TEXT',
            default_value="{}",
        )

        uuid_tables = [
            'blocks',
            'addons',
            'contexts',
            'entities',
            'modules',
            'tools',
        ]
        ensure_column_in_tables(
            tables=uuid_tables,
            force_tables=['tools'],
            column_name='uuid',
            column_type='TEXT',
            default_value="""(
                lower(hex(randomblob(4))) || '-' ||
                lower(hex(randomblob(2))) || '-' ||
                '4' || substr(lower(hex(randomblob(2))), 2) || '-' ||
                substr('89ab', abs(random()) % 4 + 1, 1) || substr(lower(hex(randomblob(2))), 2) || '-' ||
                lower(hex(randomblob(6)))
            )""",
            unique=True,
        )

        # # uuid must be in format  f0784945-a77f-4097-b071-5e0c1dbbc4fd
        # for table in uuid_tables:
        #     sql.execute(f"""
        #         UPDATE {table}
        #         SET uuid = lower(hex(randomblob(4))) || '-' || lower(hex(randomblob(2))) || '-' || '4' || lower(hex(randomblob(2))) || '-' || substr('89ab', abs(random()) % 4 + 1, 1) || lower(hex(randomblob(2))) || '-' || lower(hex(randomblob(6)))
        #         WHERE uuid IS NULL
        #     """)

        item_uuids = {
            'blocks': {
                'machine-name': "67a2fead-bdee-48fe8-8472c-1b8e9253bf24",
                'machine-os': "b09a11ac-8148-44c3f-8b81b-3512859ee60c",
                'known-personality': "57805110-3410-4fdd5-a4e71-3f4ab9b35148",
                "claude-prompt-enhancer": "3d200d26-3e36-44328-97cc8-2a9376252167",
            },
        }
        for table, uuids in item_uuids.items():
            for name, uuid in uuids.items():
                sql.execute(f"""
                    UPDATE {table}
                    SET uuid = ?
                    WHERE name = ?
                """, (uuid, name))

        # "display.pinned_pages": json.dumps(['Blocks', 'Tools']),
        sql.execute("""
            INSERT INTO settings (`field`, `value`) VALUES
	            ('pinned_pages', json_array('Blocks', 'Tools'))
	    """)

        # remove display.pinned_pages from app_config
        sql.execute("""
            UPDATE settings
            SET value = json_remove(value, '$."display.pinned_pages"')
            WHERE field = 'app_config'
        """)
        sql.execute("DROP TABLE IF EXISTS `tasks`")

        # rename `sandboxes` table to `environments`
        sql.execute("ALTER TABLE sandboxes RENAME TO environments")

        sql.execute("""UPDATE folders SET type = 'environments' WHERE type = 'sandboxes'""")

        # change `blocks` and `entities` table `name` column to not UNIQUE
        rename_name_col_in_tables = ['blocks', 'entities']
        for table_name in rename_name_col_in_tables:
            create_stmt = sql.get_scalar(f"SELECT sql FROM sqlite_master WHERE type='table' AND name='{table_name}'")
            create_stmt = create_stmt.replace('"name"	TEXT NOT NULL UNIQUE', '"name"	TEXT NOT NULL')
            create_stmt = create_stmt.replace(f'CREATE TABLE "{table_name}"', f'CREATE TABLE "{table_name}_new"')
            sql.execute(create_stmt)
            sql.execute(f"INSERT INTO {table_name}_new SELECT * FROM {table_name}")
            sql.execute(f"DROP TABLE {table_name}")
            sql.execute(f"ALTER TABLE {table_name}_new RENAME TO {table_name}")

        # app config
        sql.execute("""
            UPDATE settings SET value = '0.5.0' WHERE field = 'app_version'""")

        sql.execute("""VACUUM""")

    def v0_4_0(self):
        sql.execute("DELETE FROM models WHERE api_id NOT IN (SELECT id FROM apis)")

        sql.execute("UPDATE apis SET provider_plugin = 'litellm' WHERE provider_plugin = '' OR provider_plugin IS NULL")

        sql.execute("""
        CREATE TABLE "folders_new" (
            "id"	INTEGER,
            "name"	TEXT NOT NULL,
            "parent_id"	INTEGER,
            "type"	TEXT,
            "config"	TEXT NOT NULL DEFAULT '{}',
            "locked"	INTEGER NOT NULL DEFAULT 0,
            "expanded"	INTEGER NOT NULL DEFAULT 1,
            "ordr"	INTEGER DEFAULT 0,
            PRIMARY KEY("id")
        )
        """)
        sql.execute("""
        INSERT INTO folders_new (id, name, parent_id, type, config, locked, expanded, ordr)
        SELECT id, name, parent_id, type, config, 
            CASE WHEN ordr = 5 THEN 1 ELSE 0 END, 
            1, 
            0
        FROM folders
        """)
        sql.execute("DROP TABLE folders")
        sql.execute("ALTER TABLE folders_new RENAME TO folders")

        # create table if not exists
        sql.execute("""
            CREATE TABLE IF NOT EXISTS `workspaces` (
                "id"  INTEGER,
                "name"    TEXT,
                "config"  TEXT DEFAULT '{}',
                "folder_id"	INTEGER DEFAULT NULL,
                PRIMARY KEY("id" AUTOINCREMENT)
            )""")

        # if logs table has 3 columns
        col_count = sql.get_scalar("SELECT COUNT(*) FROM pragma_table_info('logs');")
        if col_count == 3:
            sql.execute("""
                CREATE TABLE logs_new (
                    "id"  INTEGER,
                    "name"    TEXT,
                    "config"  TEXT DEFAULT '{}',
                    "folder_id"	INTEGER DEFAULT NULL,
                    PRIMARY KEY("id" AUTOINCREMENT)
                )""")
            sql.execute("""
                INSERT INTO logs_new (id, name, config, folder_id)
                SELECT id, log_type, message, NULL
                FROM logs
                """)
            sql.execute("DROP TABLE logs")
            sql.execute("ALTER TABLE logs_new RENAME TO logs")

        sql.execute("""
            CREATE TABLE IF NOT EXISTS pypi_packages (
                "name"	TEXT,
                "folder_id"	INTEGER DEFAULT NULL,
                PRIMARY KEY("name")
            )""")

        # if type of sqlite column `contexts_messages`.`member_id` is INTEGER
        member_id_col_type = sql.get_scalar("SELECT type FROM pragma_table_info('contexts_messages') WHERE `name` = 'member_id'")
        if member_id_col_type == 'INTEGER':
            sql.execute("ALTER TABLE contexts_messages RENAME TO contexts_messages_old")
            sql.execute("""
            CREATE TABLE "contexts_messages" (
                "id"	INTEGER,
                "unix"	INTEGER NOT NULL DEFAULT (CAST(strftime('%s', 'now') AS TYPE_NAME)),
                "context_id"	INTEGER,
                "member_id"	TEXT NOT NULL,
                "role"	TEXT,
                "msg"	TEXT,
                "embedding_id"	INTEGER,
                "log"	TEXT NOT NULL DEFAULT '',
                "alt_turn"	INTEGER NOT NULL DEFAULT 0,
                "del"	INTEGER NOT NULL DEFAULT 0,
                PRIMARY KEY("id" AUTOINCREMENT)
            )""")
            sql.execute("""
                INSERT INTO contexts_messages (id, unix, context_id, member_id, role, msg, embedding_id, log, alt_turn, del)
                SELECT id, unix, context_id, CAST(member_id AS TEXT), role, msg, embedding_id, log, alt_turn, del
                FROM contexts_messages_old
            """)
            sql.execute("DROP TABLE contexts_messages_old")

        # if models table has schema_plugin
        schema_plugin_col_cnt = sql.get_scalar("SELECT COUNT(*) FROM pragma_table_info('models') WHERE `name` = 'schema_plugin'")
        has_schema_plugin_column = (schema_plugin_col_cnt == '1')
        if has_schema_plugin_column:
            # removes `schema_plugin` column
            sql.execute("""
                CREATE TABLE "models_new" (
                    "id"	INTEGER,
                    "api_id"	INTEGER NOT NULL DEFAULT 0,
                    "name"	TEXT NOT NULL DEFAULT '',
                    "kind"	TEXT NOT NULL DEFAULT 'CHAT',
                    "config"	TEXT NOT NULL DEFAULT '{}',
                    "folder_id"	INTEGER DEFAULT NULL, 
                    PRIMARY KEY("id" AUTOINCREMENT)
                )""")
            sql.execute("""
                INSERT INTO models_new (id, api_id, name, kind, config, folder_id)
                SELECT id, api_id, name, kind, config, folder_id
                FROM models
            """)
            sql.execute("DROP TABLE models")
            sql.execute("ALTER TABLE models_new RENAME TO models")

        # if contexts table has 'kind' column
        kind_col_cnt = sql.get_scalar("SELECT COUNT(*) FROM pragma_table_info('contexts') WHERE `name` = 'kind'")
        has_kind_column = (kind_col_cnt == '1')
        if not has_kind_column:
            sql.execute("""
                CREATE TABLE "contexts_new" (
                        "id"	INTEGER,
                        "parent_id"	INTEGER,
                        "branch_msg_id"	INTEGER DEFAULT NULL,
                        "name"	TEXT NOT NULL DEFAULT '',
                        "kind"	TEXT NOT NULL DEFAULT 'CHAT',
                        "active"	INTEGER NOT NULL DEFAULT 1,
                        "folder_id"	INTEGER DEFAULT NULL,
                        "ordr"	INTEGER DEFAULT 0,
                        "config"	TEXT NOT NULL DEFAULT '{}',
                        PRIMARY KEY("id" AUTOINCREMENT)
                    )
            """)
            sql.execute("""
                INSERT INTO contexts_new (id, parent_id, branch_msg_id, name, kind, active, folder_id, ordr, config)
                SELECT id, parent_id, branch_msg_id, name, 'CHAT', active, folder_id, ordr, config
                FROM contexts
            """)
            sql.execute("DROP TABLE contexts")
            sql.execute("ALTER TABLE contexts_new RENAME TO contexts")

        # some blocks might have same name, go through and rename them so they're unique, add 1 to each name
        sql.execute("""
            UPDATE blocks
            SET name = name || '-' || (
                SELECT uuid
                FROM (
                    SELECT
                        id,
                        name,
                        hex(randomblob(16)) AS uuid
                    FROM
                        blocks
                    WHERE
                        LOWER(name) IN (
                            SELECT LOWER(name)
                            FROM blocks
                            GROUP BY LOWER(name)
                            HAVING COUNT(*) > 1
                        )
                ) AS DuplicateBlocks
                WHERE DuplicateBlocks.id = blocks.id
            )
            WHERE id IN (
                SELECT id
                FROM blocks
                WHERE LOWER(name) IN (
                    SELECT LOWER(name)
                    FROM blocks
                    GROUP BY LOWER(name)
                    HAVING COUNT(*) > 1
                )
            );
        """)

        # add kind field to `blocks` table
        sql.execute("""
            CREATE TABLE IF NOT EXISTS `blocks_new` (
                "id"	INTEGER,
                "name"	TEXT NOT NULL UNIQUE,
                "kind"    TEXT NOT NULL DEFAULT 'USER',
                "config"	TEXT NOT NULL DEFAULT '{}',
                "folder_id"	INTEGER DEFAULT NULL,
                "ordr"	INTEGER DEFAULT 0,
                PRIMARY KEY("id" AUTOINCREMENT)
            )
        """)

        sql.execute("""
            INSERT INTO blocks_new (id, name, kind, config, folder_id, ordr)
            SELECT id, name, 'USER', config, folder_id, ordr
            FROM blocks
        """)
        sql.execute("DROP TABLE blocks")
        sql.execute("ALTER TABLE blocks_new RENAME TO blocks")

        instructions_exist = sql.get_scalar("SELECT COUNT(*) FROM roles WHERE LOWER(name) = 'instructions'") > 0
        if not instructions_exist:
            config = json.dumps({"bubble_bg_color": "#003b3b3b", "bubble_text_color": "#ff818365"})
            sql.execute("""
                INSERT INTO roles (name, config)
                VALUES ('instructions', ?)
            """, (config,))
        audio_config = json.dumps({"show_bubble": False})
        sql.execute("""
            INSERT INTO roles (name, config)
            VALUES ('audio', ?)
        """, (audio_config,))

        # insert into folders
        ensure_system_folders()

        # Update blocks config
        sql.execute("""
            UPDATE blocks
            SET config = json_insert(config, '$._TYPE', 'block')
            WHERE json_extract(config, '$._TYPE') IS NULL;""")

        # update tools configs
        tool_configs = sql.get_results("SELECT id, config FROM tools", return_type='dict')
        tool_configs = {tool_id: json.loads(config) for tool_id, config in tool_configs.items()}

        for tool_id, config in tool_configs.items():
            new_config = {
                "_TYPE": "workflow",
                "description": config.get('description', ''),
                "environment": config.get('environment', ''),
                "config": {
                    "filter_role": "result",
                },
                "inputs": [],
                "members": [
                    {
                        "config": {
                            "_TYPE": "block",
                            "block_type": "Code",
                            "data": config.get('code.data', ''),
                        },
                        "id": "1",
                        "loc_x": 70,
                        "loc_y": 55
                    }
                ],
                "params": json.loads(config.get('parameters.data', '[]')),
            }
            sql.execute("""
                UPDATE tools
                SET config = ?
                WHERE id = ?""", (json.dumps(new_config), tool_id))

        # remove metaprompt folder and item
        folder_id = sql.get_scalar("SELECT id FROM folders WHERE name = 'Metaprompts'")
        sql.execute("""
            UPDATE blocks 
            SET folder_id = NULL
            WHERE folder_id = ?""", (folder_id,))
        sql.execute("""
            UPDATE folders
            SET parent_id = NULL
            WHERE parent_id = ?""", (folder_id,))
        sql.execute("""
            DELETE FROM folders WHERE id = ?""", (folder_id,))
        sql.execute("""
            UPDATE blocks 
            SET name = 'Claude prompt generator (DELETE ME)'
            WHERE name = 'Claude prompt generator'""")

        # ensure all tables have `ordr` column - prep for sortable items
        orderable_tables = ['blocks', 'contexts', 'entities', 'folders', 'models', 'tools']
        for table in orderable_tables:
            ordr_column_cnt = sql.get_scalar(f"SELECT count(*) FROM pragma_table_info('{table}') WHERE name = 'ordr'")
            if ordr_column_cnt == 0:
                sql.execute(f"ALTER TABLE {table} ADD COLUMN ordr INTEGER DEFAULT 0")

        # set  `settings`.`app_config`  json value `system.dev_mode` to false
        sql.execute("""
            UPDATE settings
            SET value = json_set(value, '$."system.dev_mode"', json('false'))
            WHERE field = 'app_config'""")

        # "display.pinned_pages": json.dumps(['Blocks', 'Tools']),
        sql.execute("""
            UPDATE settings
            SET value = json_set(value, '$."display.pinned_pages"', '["Blocks", "Tools"]')
            WHERE field = 'app_config'""")

        tool_id_uuid_map = sql.get_results("SELECT id, uuid FROM tools", return_type='dict')
        entity_configs = sql.get_results("SELECT id, config FROM entities", return_type='dict')
        for row_id in entity_configs:
            config = self.patch_config_dict_recursive_0_4_0(json.loads(entity_configs[row_id]), tool_id_uuid_map)
            entity_configs[row_id] = config
        for entity_id, config in entity_configs.items():
            sql.execute("""
                UPDATE entities
                SET config = ?
                WHERE id = ?""", (json.dumps(config), entity_id))

        chat_configs = sql.get_results("SELECT id, config FROM contexts", return_type='dict')
        for row_id in chat_configs:
            config = self.patch_config_dict_recursive_0_4_0(json.loads(chat_configs[row_id]), tool_id_uuid_map)
            chat_configs[row_id] = config
        for chat_id, config in chat_configs.items():
            sql.execute("""
                UPDATE contexts
                SET config = ?
                WHERE id = ?""", (json.dumps(config), chat_id))

        # add table 'modules'
        sql.execute("""
            CREATE TABLE "modules" (
                "id"	INTEGER,
                "name"	TEXT NOT NULL DEFAULT '',
                "config"	TEXT NOT NULL DEFAULT '{}',
                "metadata"	TEXT NOT NULL DEFAULT '{}',
                "folder_id"	INTEGER DEFAULT NULL,
                "ordr"	INTEGER DEFAULT 0,
                PRIMARY KEY("id" AUTOINCREMENT)
            );""")

        # # change `settings` column `value` default to "{}"
        sql.execute("""
            CREATE TABLE `settings_new` (
                "id"	INTEGER,
                "field"	TEXT NOT NULL,
                "value"	TEXT NOT NULL DEFAULT '{}',
                PRIMARY KEY("id" AUTOINCREMENT)
            )""")
        sql.execute("""
            INSERT INTO settings_new (id, field, value)
            SELECT id, field, value
            FROM settings
        """)
        sql.execute("DROP TABLE settings")
        sql.execute("ALTER TABLE settings_new RENAME TO settings")

        # app config
        sql.execute("""
            UPDATE settings SET value = '0.4.0' WHERE field = 'app_version'""")

        tables = [
            'apis',
            'blocks',
            'contexts',
            'entities',
            'files',
            'folders',
            'models',
            'modules',
            'roles',
            'sandboxes',
            'tools',
            'vectordbs',
            'workspaces',
        ]
        # add column `pinned` INTEGER DEFAULT 0 to tables
        for table in tables:
            sql.execute(f"ALTER TABLE {table} ADD COLUMN pinned INTEGER DEFAULT 0")

        sql.execute("VACUUM")

    def patch_config_dict_recursive_0_4_0(self, config, tool_id_uuid_map):
        config_type = config.get('_TYPE', 'agent')
        if config_type == 'agent':
            if 'tools.data' in config:
                existing_tools = json.loads(config['tools.data'])
                existing_tool_ids = [int(tool['id']) for tool in existing_tools if tool['id'].isnumeric()]
                existing_tool_uuids = [tool['id'] for tool in existing_tools if not tool['id'].isnumeric()]
                existing_tool_uuids += [tool_id_uuid_map.get(tool_id, None) for tool_id in existing_tool_ids]
                existing_tool_uuids = [tool_uuid for tool_uuid in existing_tool_uuids if tool_uuid is not None]
                config['tools.data'] = json.dumps(existing_tool_uuids)
                pass
        elif config_type == 'workflow':
            members = config.get('members', [])
            for member in members:
                if 'id' in member:
                    member['id'] = str(member['id'])
                member['config'] = self.patch_config_dict_recursive_0_4_0(member.get('config', {}), tool_id_uuid_map)
            config['members'] = members

            inputs = config.get('inputs', [])
            for inp in inputs:
                input_config = inp['config']
                is_msg = input_config.get('input_type', 'Message') == 'Message'
                del input_config['input_type']
                if is_msg:
                    msg_mappings_data = [{'source': 'Output', 'target': 'Message'}]
                    input_config['mappings.data'] = msg_mappings_data
                inp['source_member_id'] = str(inp['input_member_id'])
                inp['target_member_id'] = str(inp['member_id'])
                del inp['member_id']
                del inp['input_member_id']
                inp['config'] = input_config
            config['inputs'] = inputs


        return config

    # def update_agent_tools_recursive(self):
    #     pass

    def v0_3_0(self):
        sql.execute("""
            CREATE TABLE "contexts_messages_new" (
                "id"	INTEGER,
                "unix"	INTEGER NOT NULL DEFAULT (CAST(strftime('%s', 'now') AS TYPE_NAME)),
                "context_id"	INTEGER,
                "member_id"	INTEGER NOT NULL,
                "role"	TEXT,
                "msg"	TEXT,
                "embedding_id"	INTEGER,
                "log"	TEXT NOT NULL DEFAULT '',
                "alt_turn"	INTEGER NOT NULL DEFAULT 0,
                "del"	INTEGER NOT NULL DEFAULT 0,
                PRIMARY KEY("id" AUTOINCREMENT)
            );""")

        message_contexts = sql.get_results("SELECT id, context_id FROM contexts_messages ORDER BY context_id, id", return_type='dict')
        message_roles = sql.get_results("SELECT id, role FROM contexts_messages", return_type='dict')
        context_branch_msg_ids = sql.get_results("SELECT id, branch_msg_id FROM contexts", return_type='dict')

        message_alt_turns = {}  # {message_id: alt_turn}

        current_context_id = None
        current_alt_turn = 0
        for message_id, context_id in message_contexts.items():
            if context_id != current_context_id:
                # Changed context, check if this context is a branch
                current_context_id = context_id
                branch_msg_id = context_branch_msg_ids.get(context_id, None)
                current_alt_turn = message_alt_turns.get(branch_msg_id, 0) if branch_msg_id else 0
            else:
                # Same context, so alternate if the role is "user" (Only for the migration, since multi user workflows weren't supported before)
                role = message_roles.get(message_id)
                if role == "user":
                    current_alt_turn = 1 - current_alt_turn
            message_alt_turns[message_id] = current_alt_turn

        # set alt turns to 0 initially, convert member_id to string
        sql.execute("""
            INSERT INTO contexts_messages_new (id, unix, context_id, member_id, role, msg, embedding_id, log, alt_turn, del)
            SELECT id, unix, context_id, COALESCE(member_id, 1), role, msg, embedding_id, log, 0, del FROM contexts_messages
        """)

        all_alternate_msg_ids = [message_id for message_id, alt_turn in message_alt_turns.items() if alt_turn == 1]

        # set alt turns to 1 for alternate messages
        sql.execute("""
            UPDATE contexts_messages_new
            SET alt_turn = 1
            WHERE id IN ({})""".format(','.join(map(str, all_alternate_msg_ids)))
        )
        sql.execute("""
            UPDATE contexts_messages_new
            SET member_id = 1
            WHERE role = 'user'
        """)
        sql.execute("""
            DROP TABLE contexts_messages""")
        sql.execute("""
            ALTER TABLE contexts_messages_new RENAME TO contexts_messages""")

        # add config field to contexts table
        sql.execute("DROP TABLE IF EXISTS contexts_new")
        sql.execute("""
            CREATE TABLE "contexts_new" (
                "id"	INTEGER,
                "parent_id"	INTEGER,
                "branch_msg_id"	INTEGER DEFAULT NULL,
                "name"	TEXT NOT NULL DEFAULT '',
                "active"	INTEGER NOT NULL DEFAULT 1,
                "folder_id"	INTEGER DEFAULT NULL,
                "ordr"	INTEGER DEFAULT 0,
                "config"	TEXT NOT NULL DEFAULT '{}',
                PRIMARY KEY("id" AUTOINCREMENT)
            )""")
        sql.execute("""
            INSERT INTO contexts_new (id, parent_id, branch_msg_id, name, active, folder_id, ordr, config)
            SELECT id, parent_id, branch_msg_id, summary, active, folder_id, ordr, '{}' FROM contexts""")

        sql.execute("""
            UPDATE contexts_new
            SET config = (
                SELECT json_object(
                    '_TYPE', 'workflow',
                    'members', (
                        SELECT json_group_array(
                            json_object(
                                'id', ordered_cm.id,
                                'agent_id', ordered_cm.agent_id,
                                'loc_x', ordered_cm.loc_x,
                                'loc_y', ordered_cm.loc_y,
                                'config', json(ordered_cm.config),
                                'del', ordered_cm.del
                            )
                        )
                        FROM (
                            SELECT 
                                1 as id, 
                                NULL as agent_id, 
                                -10 as loc_x,
                                64 as loc_y, 
                                '{"_TYPE": "user"}' as config, 
                                0 as del,
                                0 as order_col -- This is to ensure the user member comes first
                            UNION ALL
                            SELECT 
                                cm.id, 
                                cm.agent_id, 
                                cm.loc_x, 
                                cm.loc_y, 
                                cm.agent_config as config, 
                                cm.del,
                                1 as order_col -- This is for actual members to come after the user member
                            FROM contexts_members cm
                            WHERE cm.context_id = contexts_new.id
                        ) as ordered_cm
                        ORDER BY ordered_cm.order_col, ordered_cm.id -- Ensures correct order in the output
                    ),
                    'inputs', (
                        SELECT json_group_array(
                            json_object(
                                'member_id', cmi.member_id,
                                'input_member_id', COALESCE(cmi.input_member_id, 1),
                                'type', cmi.type
                            )
                        )
                        FROM contexts_members_inputs cmi
                        WHERE cmi.member_id IN (
                            SELECT id FROM contexts_members WHERE context_id = contexts_new.id
                        )
                    )
                )
            )""")
        sql.execute("""
            DROP TABLE contexts_members""")
        sql.execute("""
            DROP TABLE contexts_members_inputs""")
        sql.execute("""
            DROP TABLE contexts""")
        sql.execute("""
            ALTER TABLE contexts_new RENAME TO contexts""")

        sql.execute("""
            CREATE TABLE "entities" (
                "id"	INTEGER,
                "name"	TEXT NOT NULL DEFAULT '' UNIQUE,
                "desc"	TEXT NOT NULL DEFAULT '',
                "kind"    TEXT NOT NULL DEFAULT 'AGENT',
                "config"	TEXT NOT NULL DEFAULT '{}',
                "folder_id"	INTEGER DEFAULT NULL,
                "ordr"	INTEGER DEFAULT 0,
                PRIMARY KEY("id" AUTOINCREMENT)
            );""")

        sql.execute("""
            INSERT INTO entities (id, name, desc, kind, config, folder_id, ordr)
            SELECT id, name, desc, 'AGENT', config, folder_id, ordr FROM agents""")
        sql.execute("""
            DROP TABLE agents""")

        # add table 'themes' with name as index key
        sql.execute("""
            CREATE TABLE "themes" (
                "name"	TEXT NOT NULL UNIQUE,
                "config"	TEXT NOT NULL DEFAULT '{}',
                PRIMARY KEY("name")
            )""")
        themes = {
            'Dark': {
                'display': {
                    'primary_color': '#ff1b1a1b',
                    'secondary_color': '#ff292629',
                    'text_color': '#ffcacdd5',
                },
                'user': {
                    'bubble_bg_color': '#ff2e2e2e',
                    'bubble_text_color': '#ffd1d1d1',
                },
                'assistant': {
                    'bubble_bg_color': '#ff212122',
                    'bubble_text_color': '#ffb2bbcf',
                },
                'code': {
                    'bubble_bg_color': '#003b3b3b',
                    'bubble_text_color': '#ff949494',
                }
            },
            'Light': {
                'display': {
                    'primary_color': '#ffe2e2e2',
                    'secondary_color': '#ffd6d6d6',
                    'text_color': '#ff413d48',
                },
                'user': {
                    'bubble_bg_color': '#ffcbcbd1',
                    'bubble_text_color': '#ff413d48',
                },
                'assistant': {
                    'bubble_bg_color': '#ffd0d0d0',
                    'bubble_text_color': '#ff4d546d',
                },
                'code': {
                    'bubble_bg_color': '#003b3b3b',
                    'bubble_text_color': '#ff949494',
                }
            },
            'Dark blue': {
                'display': {
                    'primary_color': '#ff11121b',
                    'secondary_color': '#ff222332',
                    'text_color': '#ffb0bbd5',
                },
                'user': {
                    'bubble_bg_color': '#ff222332',
                    'bubble_text_color': '#ffd1d1d1',
                },
                'assistant': {
                    'bubble_bg_color': '#ff171822',
                    'bubble_text_color': '#ffb2bbcf',
                },
                'code': {
                    'bubble_bg_color': '#003b3b3b',
                    'bubble_text_color': '#ff949494',
                }
            },
        }
        for name, config in themes.items():
            sql.execute("""
                INSERT INTO themes (name, config) VALUES (?, ?)""", (name, json.dumps(config)))

        sql.execute("DROP TABLE IF EXISTS vectordbs")
        sql.execute("""
            CREATE TABLE "vectordbs" (
                "id"	INTEGER,
                "name"	TEXT NOT NULL,
                "folder_id"	INTEGER DEFAULT NULL,
                "config"	TEXT NOT NULL DEFAULT '{}',
                PRIMARY KEY("id" AUTOINCREMENT)
            )""")

        sql.execute("""
            CREATE TABLE "apis_new" (
                "id"	INTEGER,
                "name"	TEXT NOT NULL,
                "client_key"	TEXT NOT NULL DEFAULT '',
                "api_key"	TEXT NOT NULL DEFAULT '',
                "provider_plugin"	TEXT DEFAULT NULL,
                "config"	TEXT NOT NULL DEFAULT '{}',
                PRIMARY KEY("id" AUTOINCREMENT)
            );""")
        sql.execute("""
            INSERT INTO apis_new (id, name, client_key, api_key, config)
            SELECT id, name, client_key, priv_key, config
            FROM apis""")
        sql.execute("""
            DROP TABLE apis""")
        sql.execute("""
            ALTER TABLE apis_new RENAME TO apis""")
        sql.execute("""
            UPDATE apis SET provider_plugin='fakeyou' WHERE LOWER(name) = 'fakeyou'""")

        sql.execute("""
            CREATE TABLE "models_new" (
                "id"	INTEGER,
                "api_id"	INTEGER NOT NULL DEFAULT 0,
                "name"	TEXT NOT NULL DEFAULT '',
                "kind"	TEXT NOT NULL DEFAULT 'CHAT',
                "config"	TEXT NOT NULL DEFAULT '{}',
                "folder_id"	INTEGER DEFAULT NULL,
                PRIMARY KEY("id" AUTOINCREMENT)
            );""")
        sql.execute("""
            INSERT INTO models_new (id, api_id, name, kind, config, folder_id)
            SELECT id, api_id, name, kind, config, NULL FROM models""")
        sql.execute("""
            DROP TABLE models""")
        sql.execute("""
            ALTER TABLE models_new RENAME TO models""")

        sql.execute("""
            DROP TABLE IF EXISTS categories""")
        sql.execute("""
            DROP TABLE IF EXISTS character_categories""")
        sql.execute("""
            DROP TABLE IF EXISTS embeddings""")
        sql.execute("""
            DROP TABLE IF EXISTS example_tasks""")
        sql.execute("""
            DROP TABLE IF EXISTS examples_time_expressions""")
        sql.execute("""
            DROP TABLE IF EXISTS lists""")
        sql.execute("""
            DROP TABLE IF EXISTS lists_items""")
        sql.execute("""
            DROP TABLE IF EXISTS schedule_items""")
        sql.execute("""
            DROP TABLE IF EXISTS voices""")
        sql.execute("""
            DROP TABLE IF EXISTS files""")
        sql.execute("""
            DROP TABLE IF EXISTS file_exts""")

        sql.execute("""
            CREATE TABLE "files" (
                    "id"	INTEGER,
                    "name"	TEXT NOT NULL,
                    "folder_id"	INTEGER DEFAULT NULL,
                    "config"	TEXT NOT NULL DEFAULT '{}',
                    PRIMARY KEY("id" AUTOINCREMENT)
            )""")
        sql.execute("""
            CREATE TABLE "file_exts" (
                "id"	INTEGER,
                "name"	TEXT NOT NULL UNIQUE,
                "folder_id"	INTEGER DEFAULT NULL,
                "config"	TEXT NOT NULL DEFAULT '{}',
                PRIMARY KEY("id" AUTOINCREMENT)
            )""")

        # if 'output' not in roles
        if sql.get_scalar("SELECT COUNT(id) FROM roles WHERE name = 'output'") == 0:
            output_conf = {
                "bubble_bg_color": "#003b3b3b",
                "bubble_text_color": "#ff818365"
            }
            sql.execute("""
                INSERT INTO roles (name, config) VALUES ('output', ?)""", (json.dumps(output_conf),))

        sql.execute("DROP TABLE IF EXISTS `sandboxes`")
        sql.execute("""
            CREATE TABLE "sandboxes" (
                "id"	INTEGER,
                "name"	TEXT NOT NULL,
                "folder_id"	INTEGER DEFAULT NULL,
                "config"	TEXT NOT NULL DEFAULT '{}',
                PRIMARY KEY("id" AUTOINCREMENT)
            )""")
        local_sandbox = {
            "sandbox_type": ""
        }
        sql.execute("""
            INSERT INTO sandboxes (id, name, config) VALUES
                (1, 'Local', ?)""", (json.dumps(local_sandbox),))

        new_oi_system_msg = """You are Open Interpreter, a world-class programmer that can complete any goal by executing code.\nFirst, write a plan. **Always recap the plan between each code block** (you have extreme short-term memory loss, so you need to recap the plan between each message block to retain it).\nWhen you execute code, it will be executed **on the user's machine**. The user has given you **full and complete permission** to execute any code necessary to complete the task. Execute the code.\nYou can access the internet. Run **any code** to achieve the goal, and if at first you don't succeed, try again and again.\nYou can install new packages.\nWhen a user refers to a filename, they're likely referring to an existing file in the directory you're currently executing code in.\nWrite messages to the user in Markdown.\nIn general, try to **make plans** with as few steps as possible. As for actually executing code to carry out that plan, for *stateful* languages (like python, javascript, shell, but NOT for html which starts from 0 every time) **it's critical not to try to do everything in one code block.** You should try something, print information about it, then continue from there in tiny, informed steps. You will never get it on the first try, and attempting it in one go will often lead to errors you cant see.\nYou are capable of **any** task.\n\nUser's Name {machine-name}\nUser's OS: {machine-os}"""
        # Update entities where json text field 'info.use_plugin' == 'open_interpreter'
        # Set 'chat.sys_msg' to above variable
        sql.execute("""
            UPDATE entities
            SET config = json_patch(config, json_object('chat.sys_msg', ?))
            WHERE json_extract(config, '$."info.use_plugin"') = 'Open_Interpreter'""", (new_oi_system_msg,))

        sql.execute("""
            UPDATE settings SET value = '0.3.0' WHERE field = 'app_version'""")
        sql.execute("""
            INSERT INTO settings (field, value) VALUES ('accepted_tos', '0')""")
        sql.execute("""
            INSERT INTO settings (field, value) VALUES ('my_uuid', '')""")
        sql.execute("""
            VACUUM""")

    def v0_2_0(self):
        sql.execute("""
            CREATE TABLE "apis_new" (
                "id"	INTEGER,
                "name"	TEXT NOT NULL,
                "client_key"	TEXT NOT NULL DEFAULT '',
                "priv_key"	TEXT NOT NULL DEFAULT '',
                "config"	TEXT NOT NULL DEFAULT '{}',
                PRIMARY KEY("id" AUTOINCREMENT)
            )""")
        user_api_keys = sql.get_results("""
            SELECT name, client_key, priv_key
            FROM apis
            WHERE (priv_key != '' OR client_key != '') AND priv_key NOT LIKE '$%'
        """)
        
        # [MODEL ITEMS BLOAT REMOVED]

        sql.execute("""
            DROP TABLE apis""")
        sql.execute("""
            ALTER TABLE apis_new RENAME TO apis""")
        for name, client_key, priv_key in user_api_keys:
            sql.execute("""
                UPDATE apis
                SET client_key = ?, priv_key = ?
                WHERE name = ?""", (client_key, priv_key, name))

        sql.execute("""
        CREATE TABLE "models_new" (
            "id"	INTEGER,
            "api_id"	INTEGER NOT NULL DEFAULT 0,
            "name"	TEXT NOT NULL DEFAULT '',
            "kind"	TEXT NOT NULL DEFAULT 'CHAT',
            "config"	TEXT NOT NULL DEFAULT '{}',
            PRIMARY KEY("id" AUTOINCREMENT)
        )""")

        # [MODEL ITEMS BLOAT REMOVED]

        sql.execute("""
            DROP TABLE models""")
        sql.execute("""
            ALTER TABLE models_new RENAME TO models""")

        sql.execute("""
            CREATE TABLE "agents_new" (
                "id"	INTEGER,
                "name"	TEXT NOT NULL DEFAULT '' UNIQUE,
                "desc"	TEXT NOT NULL DEFAULT '',
                "config"	TEXT NOT NULL DEFAULT '{}',
                "folder_id"	INTEGER DEFAULT NULL,
                "ordr"	INTEGER DEFAULT 0,
                PRIMARY KEY("id" AUTOINCREMENT)
            )""")
        # set display markdown to true
        sql.execute("""
            INSERT INTO agents_new (id, name, desc, config, folder_id)
            SELECT 
                id, 
                name, 
                desc, 
                json_object(
                    'info.avatar_path', json_extract(config, '$."general.avatar_path"'),
                    'info.name', json_extract(config, '$."general.name"'),
                    'info.use_plugin', json_extract(config, '$."general.use_plugin"'),
                    'chat.model', json_extract(config, '$."context.model"'),
                    'chat.display_markdown', true,
                    'chat.sys_msg', json_extract(config, '$."context.sys_msg"'),
                    'chat.max_messages', json_extract(config, '$."context.max_messages"'),
                    'chat.max_turns', json_extract(config, '$."context.max_turns"'),
                    'chat.user_msg', json_extract(config, '$."context.user_msg"'),
                    'group.hide_responses', json_extract(config, '$."group.hide_responses"'),
                    'group.output_placeholder', json_extract(config, '$."group.output_context_placeholder"'),
                    'group.show_members_as_user_role', true,
                    'group.on_multiple_inputs', 'Merged user message',
                    'group.member_description', '',
                    'voice.current_id', json_extract(config, '$."voice.current_id"')
                ),
                NULL
            FROM agents""")
        sql.execute("""
            DROP TABLE agents""")
        sql.execute("""
            ALTER TABLE agents_new RENAME TO agents""")
        replaces = {
            'openinterpreter': 'Open_Interpreter',
            'openaiassistant': 'OpenAI_Assistant'
        }
        for k, v in replaces.items():
            sql.execute("""
                UPDATE agents SET config = json_replace(config, '$."info.use_plugin"', ?) WHERE json_extract(config, '$."info.use_plugin"') = ?""", (v, k))

        sql.execute("""
            CREATE TABLE "blocks_new" (
                "id"	INTEGER,
                "name"	TEXT NOT NULL,
                "config"	TEXT NOT NULL DEFAULT '{}',
                "folder_id"	INTEGER DEFAULT NULL,
                "ordr"	INTEGER DEFAULT 0,
                PRIMARY KEY("id" AUTOINCREMENT)
            )""")
        sql.execute("""
            INSERT INTO blocks_new (id, name, config, folder_id)
            SELECT 
                id, 
                name, 
                json_object('data', `text`),
                NULL
            FROM blocks""")
        sql.execute("""
            DROP TABLE blocks""")
        sql.execute("""
            ALTER TABLE blocks_new RENAME TO blocks""")

        sql.execute("""
        CREATE TABLE "folders" (
            "id"	INTEGER,
            "name"	TEXT NOT NULL,
            "parent_id"	INTEGER,
            "type"	TEXT,
            "config"	TEXT NOT NULL DEFAULT '{}',
            "ordr"	INTEGER DEFAULT 0,
            PRIMARY KEY("id")
        );
        """)

        sql.execute("""
            CREATE TABLE "roles_new" (
                "id"	INTEGER,
                "name"	TEXT NOT NULL,
                "config"	TEXT NOT NULL DEFAULT '{}',
                "schema"	TEXT NOT NULL DEFAULT '[]',
                PRIMARY KEY("id" AUTOINCREMENT)
            )""")
        # sql.execute("""
        #     INSERT INTO roles_new (id, name, config)
        #     SELECT
        #         id,
        #         name,
        #         config
        #     FROM roles""")
        sql.execute("""
            DROP TABLE roles""")
        sql.execute("""
            ALTER TABLE roles_new RENAME TO roles""")
        # sql.execute("""
        # DELETE FROM roles;
        # """)
        sql.execute("""
        INSERT INTO roles (name, config) VALUES
            ('user', '{"bubble_bg_color": "#3b3b3b", "bubble_text_color": "#d1d1d1", "bubble_image_size": 25}'),
            ('assistant', '{"bubble_bg_color": "#29282b", "bubble_text_color": "#b2bbcf", "bubble_image_size": 25}'),
            ('tool', '{"bubble_bg_color": "#3b3b3b", "bubble_text_color": "#c4c4c4", "bubble_image_size": 25}'),
            ('file', '{"bubble_bg_color": "#3b3b3b", "bubble_text_color": "#c4c4c4", "bubble_image_size": 25}'),
            ('code', '{"bubble_bg_color": "#3b3b3b", "bubble_text_color": "#c4c4c4", "bubble_image_size": 25}'),
            ('system', '{"bubble_bg_color": "#3b3b3b", "bubble_text_color": "#c4c4c4", "bubble_image_size": 25}')
        """)

        app_config = """{"system.language": "English", "system.dev_mode": false, "system.always_on_top": true, "system.auto_title": true, "system.auto_title_model": "claude-3-sonnet-20240229", "system.auto_title_prompt": "Write only a brief and concise title for a chat that begins with the following message:\\n\\n```{user_msg}```", "system.voice_input_method": "None", "display.primary_color": "#262326", "display.secondary_color": "#3f3a3f", "display.text_color": "#c1b5d5", "display.text_font": "", "display.text_size": 15, "display.show_bubble_name": "In Group", "display.show_bubble_avatar": "In Group", "display.bubble_avatar_position": "Top", "display.bubble_spacing": 7}"""
        sql.execute("""
        INSERT INTO settings (field, value) VALUES
            ('app_config', ?)""", (app_config,))

        default_agent = """{"info.name": "Assistant", "info.avatar_path": "", "info.use_plugin": "", "chat.model": "mistral/mistral-medium", "chat.display_markdown": true, "chat.sys_msg": "", "chat.max_messages": 15, "chat.max_turns": 10, "chat.on_consecutive_response": "REPLACE", "chat.user_msg": "", "chat.preload.data": "[]", "group.hide_responses": false, "group.output_placeholder": "", "group.on_multiple_inputs": "Merged user message", "group.show_members_as_user_role": true, "files.data": "[]", "tools.data": "[]"}"""
        sql.execute("""
        UPDATE settings SET field = 'default_agent', value = ? WHERE field = 'global_config'""", (default_agent,))

        sql.execute("""
        CREATE TABLE "tools" (
            "id"	INTEGER,
            "uuid"	TEXT NOT NULL UNIQUE,
            "name"	TEXT NOT NULL DEFAULT '' UNIQUE,
            "config"	TEXT NOT NULL DEFAULT '{}',
            "folder_id"	INTEGER DEFAULT NULL,
            PRIMARY KEY("id" AUTOINCREMENT)
        )""")
        sql.execute("""
        DROP TABLE IF EXISTS functions""")

        sql.execute("""
        CREATE TABLE "contexts_new" (
            "id"	INTEGER,
            "parent_id"	INTEGER,
            "branch_msg_id"	INTEGER DEFAULT NULL,
            "summary"	TEXT NOT NULL DEFAULT '',
            "active"	INTEGER NOT NULL DEFAULT 1,
            "folder_id"	INTEGER DEFAULT NULL,
            "ordr"	INTEGER DEFAULT 0,
            PRIMARY KEY("id" AUTOINCREMENT)
        )""")
        sql.execute("""
        INSERT INTO contexts_new (id, parent_id, branch_msg_id, summary, active)
        SELECT
            id,
            parent_id,
            branch_msg_id,
            summary,
            active
        FROM contexts""")
        sql.execute("""
        DROP TABLE contexts""")
        sql.execute("""
        ALTER TABLE contexts_new RENAME TO contexts""")

        sql.execute("""
        CREATE TABLE "contexts_members_new" (
            "id"	INTEGER,
            "context_id"	INTEGER NOT NULL,
            "agent_id"	INTEGER NOT NULL,
            "agent_config"	TEXT NOT NULL DEFAULT '{}',
            "ordr"	INTEGER NOT NULL DEFAULT 0,
            "loc_x"	INTEGER NOT NULL DEFAULT 37,
            "loc_y"	INTEGER NOT NULL DEFAULT 30,
            "del"	INTEGER NOT NULL DEFAULT 0,
            PRIMARY KEY("id" AUTOINCREMENT)
        )""")
        sql.execute("""
        INSERT INTO contexts_members_new (id, context_id, agent_id, agent_config, ordr, loc_x, loc_y, del)
        SELECT
            id,
            context_id,
            agent_id,
            json_object(
                'info.avatar_path', json_extract(agent_config, '$."general.avatar_path"'),
                'info.name', json_extract(agent_config, '$."general.name"'),
                'info.use_plugin', json_extract(agent_config, '$."general.use_plugin"'),
                'chat.model', json_extract(agent_config, '$."context.model"'),
                'chat.display_markdown', true,
                'chat.sys_msg', json_extract(agent_config, '$."context.sys_msg"'),
                'chat.max_messages', json_extract(agent_config, '$."context.max_messages"'),
                'chat.max_turns', json_extract(agent_config, '$."context.max_turns"'),
                'chat.user_msg', json_extract(agent_config, '$."context.user_msg"'),
                'group.hide_responses', json_extract(agent_config, '$."group.hide_responses"'),
                'group.output_placeholder', json_extract(agent_config, '$."group.output_context_placeholder"'),
                'group.show_members_as_user_role', true,
                'group.on_multiple_inputs', 'Merged user message',
                'group.member_description', '',
                'voice.current_id', json_extract(agent_config, '$."voice.current_id"')
            ),
            ordr,
            loc_x,
            loc_y,
            del
        FROM contexts_members""")
        sql.execute("""
        DROP TABLE contexts_members""")
        sql.execute("""
        ALTER TABLE contexts_members_new RENAME TO contexts_members""")
        for k, v in replaces.items():
            sql.execute("""
                UPDATE contexts_members SET agent_config = json_replace(agent_config, '$."info.use_plugin"', ?) WHERE json_extract(agent_config, '$."info.use_plugin"') = ?""", (v, k))

        sql.execute("""
            UPDATE settings SET value = '0.2.0' WHERE field = 'app_version'""")
        sql.execute("""
            VACUUM""")

    def v0_1_0(self):
        # Update global agent config
        glob_conf = """{"general.name": "Assistant", "general.avatar_path": "", "general.use_plugin": "", "context.model": "gpt-3.5-turbo", "context.sys_msg": "", "context.max_messages": 10, "context.max_turns": 5, "context.auto_title": true, "context.display_markdown": true, "context.on_consecutive_response": "REPLACE", "context.user_msg": "", "actions.enable_actions": false, "actions.source_directory": ".", "actions.replace_busy_action_on_new": false, "actions.use_function_calling": true, "actions.use_validator": false, "actions.code_auto_run_seconds": "5", "group.hide_responses": false, "group.output_context_placeholder": "", "group.on_multiple_inputs": "Use system message", "voice.current_id": 0}"""
        sql.execute("""
            UPDATE settings SET `value` = ? WHERE field = 'global_config'""", (glob_conf,))
            
        # Add key "general.name" to all agents config dict str
        sql.execute("""
            UPDATE agents SET config = json_insert(config, '$."general.name"', name)""")
        # Add new tables
        sql.execute("""
            CREATE TABLE "roles" (
                "id"	INTEGER,
                "name"	TEXT NOT NULL,
                "config"	TEXT NOT NULL DEFAULT '{}',
                PRIMARY KEY("id" AUTOINCREMENT)
            )""")
        sql.execute("""
            INSERT INTO roles (id, name, config) VALUES
                (1, 'user', '{"display.bubble_bg_color": "#3b3b3b", "display.bubble_text_color": "#d1d1d1", "display.bubble_image_size": "25"}'),
                (2, 'assistant', '{"display.bubble_bg_color": "#29282b", "display.bubble_text_color": "#b2bbcf", "display.bubble_image_size": "25"}'),
                (3, 'code', '{"display.bubble_bg_color": "#151515", "display.bubble_text_color": "#999999", "display.bubble_image_size": "0"}'),
                (4, 'note', '{"display.bubble_bg_color": "#1f1e21", "display.bubble_text_color": "#d1d1d1", "display.bubble_image_size": "0"}'),
                (6, 'output', '{"display.bubble_bg_color": "#111111", "display.bubble_text_color": "#ffffff", "display.bubble_image_size": "0"}')
            """)

        sql.execute("""
            CREATE TABLE "functions" (
                "id"	INTEGER,
                "name"	TEXT NOT NULL DEFAULT '' UNIQUE,
                "config"	TEXT NOT NULL DEFAULT '{}',
                PRIMARY KEY("id" AUTOINCREMENT)
            )""")
        sql.execute("""
            CREATE TABLE "contexts_members" (
                "id"	INTEGER,
                "context_id"	INTEGER NOT NULL,
                "agent_id"	INTEGER NOT NULL,
                "agent_config"	TEXT NOT NULL DEFAULT '{}',
                "ordr"	INTEGER NOT NULL DEFAULT 0,
                "loc_x"	INTEGER NOT NULL DEFAULT 37,
                "loc_y"	INTEGER NOT NULL DEFAULT 30,
                "del"	INTEGER NOT NULL DEFAULT 0,
                PRIMARY KEY("id" AUTOINCREMENT),
                FOREIGN KEY("context_id") REFERENCES "contexts"("id") ON DELETE CASCADE
            )""")
        sql.execute("""
            CREATE TABLE "contexts_members_inputs" (
                "id"	INTEGER,
                "member_id"	INTEGER NOT NULL,
                "input_member_id"	INTEGER,
                "type"	INTEGER NOT NULL DEFAULT 0,
                PRIMARY KEY("id" AUTOINCREMENT),
                FOREIGN KEY("member_id") REFERENCES "contexts_members"("id") ON DELETE CASCADE,
                FOREIGN KEY("input_member_id") REFERENCES "contexts_members"("id") ON DELETE CASCADE
            )""")

        # Set all contexts agent_id to the first agent if the agent_id = 0
        first_agent_id = sql.get_scalar("SELECT id FROM agents LIMIT 1")
        sql.execute("""
            UPDATE contexts SET agent_id = ? WHERE agent_id = 0""", (first_agent_id,))

        # Insert data from old "contexts" table to new "contexts_members" table
        sql.execute("""
            INSERT INTO contexts_members (context_id, agent_id, agent_config, loc_x, loc_y) 
            SELECT c.id, c.agent_id, a.config, 37, 30
            FROM contexts c
            LEFT JOIN agents a ON c.agent_id = a.id
            WHERE c.agent_id != 0""")

        sql.execute("""
            CREATE TABLE "contexts_messages_new" (
                "id"	INTEGER,
                "unix"	INTEGER NOT NULL DEFAULT (CAST(strftime('%s', 'now') AS TYPE_NAME)),
                "context_id"	INTEGER,
                "member_id"	INTEGER,
                "role"	TEXT,
                "msg"	TEXT,
                "embedding_id"	INTEGER,
                "log"	TEXT NOT NULL DEFAULT '',
                "del"	INTEGER NOT NULL DEFAULT 0,
                FOREIGN KEY("member_id") REFERENCES "contexts_members"("id") ON DELETE CASCADE,
                PRIMARY KEY("id" AUTOINCREMENT),
                FOREIGN KEY("context_id") REFERENCES "contexts"("id") ON DELETE CASCADE
            )""")
        sql.execute("""
            INSERT INTO contexts_messages_new (id, unix, context_id, member_id, role, msg, embedding_id, log, del)
            SELECT 
                cms.id, 
                cms.unix, 
                cms.context_id, 
                CASE WHEN cms.role = 'assistant' THEN cm.id ELSE NULL END, 
                cms.role, 
                cms.msg, 
                cms.embedding_id, 
                '', 
                cms.del
            FROM contexts_messages cms
            LEFT JOIN contexts_members cm 
                ON cms.context_id = cm.context_id""")
        sql.execute("""
            DROP TABLE contexts_messages""")
        sql.execute("""
            ALTER TABLE contexts_messages_new RENAME TO contexts_messages""")

        sql.execute("""
            ALTER TABLE contexts DROP COLUMN 'agent_id'""")
        sql.execute("""
            ALTER TABLE contexts ADD COLUMN "active" INTEGER DEFAULT 1""")

        sql.execute("""
            DELETE FROM apis""")

        # [MODEL ITEMS BLOAT REMOVED]

        sql.execute("""
            ALTER TABLE models DROP COLUMN 'name'""")
        sql.execute("""
            ALTER TABLE models ADD COLUMN "alias" TEXT DEFAULT ''""")
        sql.execute("""
            ALTER TABLE models ADD COLUMN "type" TEXT DEFAULT 'chat'""")
        sql.execute("""
            ALTER TABLE models ADD COLUMN "model_config" TEXT DEFAULT 'chat'""")
        sql.execute("""
            DELETE FROM models""")
            
        # [MODEL ITEMS BLOAT REMOVED]

        sql.execute("""
            DELETE FROM embeddings WHERE id > 1984""")

        sql.execute("""
            UPDATE settings SET value = '0.1.0' WHERE field = 'app_version'""")

        # vacuum
        sql.execute("""
            VACUUM""")


upgrade_script = SQLUpgrade()
