import inspect
import json
import os
import shutil
import sys

from PySide6.QtWidgets import QMessageBox

from gui import system
from utils import sql
from utils.helpers import display_message_box, get_id_from_folder_path, get_module_type_folder_id, hash_config


def reset_application(force=False, preserve_audio_msgs=False, bootstrap=True, reset_models_=True, reset_tos=True):  # todo temp preserve_audio_msgs
    if not force:
        retval = display_message_box(
            icon=QMessageBox.Warning,
            text="Are you sure you want to reset the database and config? This will permanently delete everything.",
            title="Reset Database",
            buttons=QMessageBox.Ok | QMessageBox.Cancel,
        )
        if retval != QMessageBox.Ok:
            return

    db_path = sql.get_db_path()
    if force:
        db_name = os.path.basename(db_path)
        if db_name == 'data.db':  # protection
            raise Exception("Cannot force reset the main database.")

    # # Wait for any running threads to complete before resetting
    # from PySide6.QtCore import QThreadPool
    # threadpool = QThreadPool.globalInstance()
    # if threadpool:
    #     threadpool.waitForDone(5000)  # Wait up to 5 seconds for threads to finish

    # Disposable dummy DBs (demo/test) only ever go through the force
    # path; they are throwaway copies, so skip the costly backup there.
    if not force:
        backup_filepath = db_path + '.backup'
        counter = 1
        while os.path.isfile(backup_filepath):
            backup_filepath = db_path + f'.backup{counter}'
            counter += 1

        shutil.copyfile(db_path, backup_filepath)

    audio_msgs = None
    if preserve_audio_msgs:
        audio_msgs = sql.get_results("""
            SELECT msg, log
            FROM contexts_messages
            WHERE role = 'audio'
        """, return_type='rows')

    keep_tables = [
        'addons',
        'apis',
        'blocks',
        'contexts',
        'contexts_messages',
        'entities',
        'environments',
        'folders',
        'logs',
        'models',
        'modules',
        'plans',
        'projects',
        'project_concepts',
        'pypi_packages',
        'roles',
        'settings',
        'skills',
        'slopify_artists',
        'slopify_tracks',
        'slopify_pending',
        'slopify_artist_songs',
        'slopify_playlists',
        'slopify_playlist_tracks',
        'tasks',
        'themes',
        'todo',
        'tools',
        'tasks',
        'vectordbs',
        'voices',
    ]
    preserved_tables = ['sqlite_sequence', 'settings']
    if not reset_models_:
        preserved_tables += ['apis', 'models']
    all_tables = sql.get_results("SELECT name FROM sqlite_master WHERE type='table'", return_type='list')
    for table in all_tables:
        if table in preserved_tables:
            continue
        if table in keep_tables:
            sql.execute(f"DELETE FROM {table}")
        else:
            sql.execute(f"DROP TABLE {table}")

    sql.execute("""
        DELETE FROM settings
        WHERE `field` NOT IN ('app_version', 'app_config', 'accepted_tos', 'my_uuid', 'pinned_pages', 'enhancement_blocks',
                              'window_size', 'page_path', 'page_editor')
    """)

    # ############################# FOLDERS ############################### #
    reset_folders()

    if reset_models_:
        reset_models(preserve_keys=False)

    reset_table(
        table_name='environments',
        item_configs={
            "Local": {
                "env_vars.data": [],
                "sandbox_type": "",
                "venv": "default"
            },
        }
    )



    # ############################# ROLES ############################### #
    # Roles table is no longer the source of truth for bubble styling.
    # Bubble styling is defined as class attributes on bubble modules in
    # src/plugins/workflows/bubbles/ (see MessageBubble + subclasses).
    #
    # reset_table(
    #     table_name='roles',
    #     item_configs={
    #         "user": {
    #             "bubble_bg_color": "#ff222332",
    #             "bubble_text_color": "#ffd1d1d1",
    #             "bubble_image_size": 25,
    #             "module": "user_bubble",
    #         },
    #         "assistant": {
    #             "bubble_bg_color": "#ff171822",
    #             "bubble_text_color": "#ffb2bbcf",
    #             "bubble_image_size": 25,
    #             "module": "assistant_bubble",
    #         },
    #         "system": {
    #             "bubble_bg_color": "#00ffffff",
    #             "bubble_text_color": "#ff949494",
    #             "bubble_image_size": 25,
    #         },
    #         "audio": {
    #             "bubble_bg_color": "#00ffffff",
    #             "bubble_text_color": "#ff949494",
    #             "bubble_image_size": 25,
    #             "module": "audio_bubble",
    #         },
    #         "code": {
    #             "bubble_bg_color": "#00ffffff",
    #             "bubble_text_color": "#ff949494",
    #             "bubble_image_size": 25,
    #             "module": "code_bubble",
    #         },
    #         "tool": {
    #             "bubble_bg_color": "#00ffffff",
    #             "bubble_text_color": "#ffb2bbcf",
    #             "bubble_image_size": 25,
    #             "module": "tool_bubble",
    #         },
    #         "output": {
    #             "bubble_bg_color": "#00ffffff",
    #             "bubble_text_color": "#ff818365",
    #             "bubble_image_size": 25,
    #         },
    #         "result": {
    #             "bubble_bg_color": "#00ffffff",
    #             "bubble_text_color": "#ff818365",
    #             "bubble_image_size": 25,
    #             "module": "result_bubble",
    #         },
    #         "image": {
    #             "bubble_bg_color": "#00000000",
    #             "bubble_text_color": "#ff949494",
    #             "bubble_image_size": 25,
    #             "module": "image_bubble",
    #         },
    #         "instruction": {
    #             "bubble_bg_color": "#00ffffff",
    #             "bubble_text_color": "#ff818365",
    #             "bubble_image_size": 25,
    #         },
    #     }
    # )

    # ############################# THEMES ############################### #

    reset_table(
        table_name='themes',
        item_configs={
            "Dark": {
                "assistant": {
                    "bubble_bg_color": "#ff212122",
                    "bubble_text_color": "#ffb2bbcf"
                },
                "code": {
                    "bubble_bg_color": "#003b3b3b",
                    "bubble_text_color": "#ff949494"
                },
                "display": {
                    "primary_color": "#ff1b1a1b",
                    "secondary_color": "#ff292629",
                    "text_color": "#ffcacdd5"
                },
                "user": {
                    "bubble_bg_color": "#ff2e2e2e",
                    "bubble_text_color": "#ffd1d1d1"
                },
            },
            "Light": {
                "assistant": {
                    "bubble_bg_color": "#ffd0d0d0",
                    "bubble_text_color": "#ff4d546d"
                },
                "code": {
                    "bubble_bg_color": "#003b3b3b",
                    "bubble_text_color": "#ff949494"
                },
                "display": {
                    "primary_color": "#ffe2e2e2",
                    "secondary_color": "#ffd6d6d6",
                    "text_color": "#ff413d48"
                },
                "user": {
                    "bubble_bg_color": "#ffcbcbd1",
                    "bubble_text_color": "#ff413d48"
                },
            },
            "Dark Blue": {
                "assistant": {
                    "bubble_bg_color": "#ff171822",
                    "bubble_text_color": "#ffb2bbcf"
                },
                "code": {
                    "bubble_bg_color": "#003b3b3b",
                    "bubble_text_color": "#ff949494"
                },
                "display": {
                    "primary_color": "#ff11121b",
                    "secondary_color": "#ff222332",
                    "text_color": "#ffb0bbd5"
                },
                "user": {
                    "bubble_bg_color": "#ff222332",
                    "bubble_text_color": "#ffd1d1d1"
                },
            },
        }
    )

    # ############################# APP CONFIG ############################### #

    app_settings = {
        # "display.bubble_avatar_position": "Top",
        "display.bubble_spacing": 7,
        "display.primary_color": "#ff11121b",
        "display.secondary_color": "#ff222332",
        "display.show_bubble_avatar": "In Group",
        "display.show_bubble_name": "In Group",
        "display.show_waiting_bar": "In Group",
        "display.text_color": "#ffb0bbd5",
        "display.text_font": "",
        "display.text_size": 15,
        "display.window_margin": 6,
        # "display.pinned_pages": ['Blocks', 'Tools'],
        "system.always_on_top": True,
        # "system.auto_complete": True,
        "system.default_chat_model": {
            "_model_name": "claude-sonnet-4-6",
            "kind": "CHAT",
            "model_params": {
                "structure.data": [],
                "xml_roles.data": []
            },
            "provider": "litellm"
        },
        "system.default_image_model": {
            "_model_name": "google/nano-banana-2:71516450bdbeafc41df33ad538bc8cc6a90f80038a563b1260531c02d694f4fd",
            "kind": "IMAGE",
            "model_params": {},
            "provider": "replicate"
        },
        "system.default_video_model": {
            "_model_name": "fal-ai/ltx-2-19b/audio-to-video",
            "kind": "VIDEO",
            "model_params": {},
            "provider": "fal"
        },
        "system.default_audio_model": {
            "_model_name": "v3",
            "kind": "AUDIO",
            "model_params": {},
            "provider": "sonauto"
        },
        "system.default_voice_model": {
            "_model_name": "fal-ai/elevenlabs/tts/eleven-v3",
            "kind": "AUDIO",
            "model_params": {
                "apply_text_normalization": "auto",
                "stability": 0.5,
                "text": "",
                "timestamps": False,
                "voice": "lXyLz3Gu0YqdG8RfvIyZ"
            },
            "provider": "fal"
        },
        "system.auto_title_model": {
            "_model_name": "claude-sonnet-4-6",
            "kind": "CHAT",
            "model_params": {
                "structure.data": [],
                "xml_roles.data": []
            },
            "provider": "litellm"
        },
        "system.auto_title_prompt": "Write only a brief and concise title for a chat that begins with the following message:\n\n```{user_msg}```",
        "system.dev_mode": False,
        "system.language": "English",
        "system.voice_input_method": "None"
    }

    sql.execute("UPDATE settings SET value = '' WHERE `field` = 'my_uuid'")
    # tos_val = 1 if accept_tos else 0
    # sql.execute("UPDATE settings SET value = ? WHERE `field` = 'accepted_tos'", (str(tos_val),))
    if reset_tos:
        sql.execute("UPDATE settings SET value = '0' WHERE `field` = 'accepted_tos'")
    sql.execute("UPDATE settings SET value = ? WHERE `field` = 'app_config'", (json.dumps(app_settings),))
    sql.execute("UPDATE settings SET value = json(?) WHERE `field` = 'pinned_pages'", (json.dumps(['blocks', 'tools']),))
    sql.execute("UPDATE settings SET value = '{}' WHERE `field` IN ('window_size', 'page_path')")
    sql.execute("UPDATE settings SET value = 'null' WHERE `field` = 'page_editor'")
    sql.execute("UPDATE settings SET value = json(?) WHERE `field` = 'enhancement_blocks'",
                (json.dumps({
                    'main_input': ['2637891c-69ba-4f41-bc54-c4c26f32bc66']
                }),))

    if audio_msgs:
        values_list = []
        placeholders = []
        for msg, log in audio_msgs:
            values_list.extend(('', 0, msg, log, 'audio'))
            placeholders.append("(?, ?, ?, ?, ?)")

        if placeholders:
            query = f"""
                INSERT INTO contexts_messages (member_id, context_id, msg, log, role)
                VALUES {', '.join(placeholders)}
            """
            sql.execute(query, values_list)

    if bootstrap:
        bootstrap_app()

    sql.execute('VACUUM')

    if not force:
        display_message_box(
            icon=QMessageBox.Information,
            title="Reset complete",
            text="The app has been reset, and will now restart to apply the changes."
        )
        from utils.process import restart_app
        restart_app()


def create_blank_db():
    db_dir = os.path.dirname(sql.get_db_path())
    blanking_path = os.path.join(db_dir, 'blanking.db')
    shutil.copyfile(sql.get_db_path(), blanking_path)
    with sql.write_to_file(blanking_path):
        reset_application(force=True)
    os.replace(blanking_path, os.path.join(db_dir, 'blank.db'))

    display_message_box(
        icon=QMessageBox.Information,
        title="Blank database created",
        text="blank.db has been created, the app will now restart."
    )
    from utils.process import restart_app
    restart_app()


# BAKED_DOC_PATHS = {
#     # 'readme': 'README.md',
#     'overview': 'docs/overview.md',
#     'gui_architecture': 'docs/gui_architecture.md',
#     'plugins': 'docs/plugins.md',
#     'coding_style': 'docs/coding_style.md',
#     'module_doc': 'docs/modules.md',
#     'widgets_doc': 'docs/widgets.md',
#     'fields_doc': 'docs/fields.md',
#     'pages_doc': 'docs/pages.md',
#     'workflows': 'docs/workflows.md',
# }


async def bake_block_maps(mappings, base_dir=''):
    """Compute blocks and write to mapped file paths.

    Parameters
    ----------
    mappings : list
        A list of (block_name, file_path) pairs.
    base_dir : str, optional
        Base directory to prepend to each file path.

    Returns
    -------
    list
        A list of error strings, empty on full success.
    """
    blocks = system.manager.blocks
    blocks.load()
    errors = []
    for raw_name, file_path in mappings:
        block_name = raw_name.rsplit(':', 2)[0]
        try:
            if base_dir:
                file_path = os.path.join(base_dir, file_path.lstrip('/\\'))
            output = await blocks.compute_block_async(block_name)
            os.makedirs(os.path.dirname(file_path) or '.', exist_ok=True)
            with open(file_path, 'w', encoding='utf-8') as f:
                f.write(output)
        except Exception as e:
            errors.append(f"{block_name}: {e}")
    return errors


# async def bake_docs():
#     """Compute baked documentation blocks and write to mapped files."""
#     return await bake_block_maps(BAKED_DOC_PATHS)


def run_bake_block_maps(config, button, finished_callback=None):
    """Extract block maps from a project config, confirm, and run bake.

    Parameters
    ----------
    config : dict
        A project config dict containing 'block_maps.data' and optionally
        'working_dir'.
    button : QPushButton
        The button to disable during the bake operation.
    finished_callback : callable, optional
        Called with (errors_list) after bake completes, before
        re-enabling the button. Receives a list of error strings
        (empty on success) or an exception string.
    """
    import asyncio
    from utils.helpers import display_message

    block_maps_data = config.get('block_maps.data', [])
    mappings = [
        (row['block'], row['path'])
        for row in block_maps_data
        if row.get('block') and row.get('path')
    ]
    if not mappings:
        display_message('No block maps to bake.')
        return

    reply = display_message_box(
        icon=QMessageBox.Question,
        title='Bake Block Maps',
        text=f'Bake {len(mappings)} block map(s)?',
        buttons=QMessageBox.Yes | QMessageBox.No,
    )
    if reply != QMessageBox.Yes:
        return

    base_dir = config.get('working_dir', '')
    button.setEnabled(False)

    def _on_done(future):
        try:
            errors = future.result()
            if errors:
                msg = 'Bake completed with errors:\n' + '\n'.join(errors)
            else:
                msg = 'Bake completed successfully.'
        except Exception as e:
            msg = f'Bake failed: {e}'

        button.setEnabled(True)
        display_message(msg)
        if finished_callback:
            finished_callback()

    future = asyncio.ensure_future(bake_block_maps(mappings, base_dir))
    future.add_done_callback(_on_done)


def bootstrap_app():
    bootstrap_entities()
    bootstrap_modules()
    delete_stale_modules()
    # pass


def bootstrap_entities():
    from utils.filesystem import get_baked_dirs

    table_names = {
        table_folder.name
        for baked_dir in get_baked_dirs() if baked_dir.is_dir()
        for table_folder in baked_dir.iterdir() if table_folder.is_dir()
    }
    for table_name in table_names:
        manager_name = 'agents' if table_name == 'entities' else table_name

        mgr = getattr(system.manager, manager_name, None)
        # Managers are BaseManager (a dict subclass); an empty manager is falsy
        # but still a valid manager to call ``add`` on, so check ``is None``.
        if mgr is None:
            print(f"Manager for {table_name} not found")
            continue

        from utils.filesystem import get_all_baked_items
        baked_items = get_all_baked_items(table_name)

        deferred_parents = []
        for _, item_config in baked_items.items():
            kwargs = {
                'name': item_config['name'],
                'uuid': item_config['uuid'],
                'config': item_config['config'],
                'baked': 1,
            }
            kind = item_config.get('kind', None)
            if kind:
                kwargs['kind'] = kind
            folder_path = item_config.get('folder_path', None)
            folder_id = get_id_from_folder_path(folder_path, mgr.folder_key)
            if folder_id:
                kwargs['folder_id'] = folder_id
            mgr.add(**kwargs)

            parent_uuid = item_config.get('parent_uuid', None)
            if parent_uuid:
                deferred_parents.append((item_config['uuid'], parent_uuid))

        for child_uuid, parent_uuid in deferred_parents:
            parent_id = sql.get_scalar(
                f"SELECT id FROM `{mgr.table_name}` WHERE uuid = ?",
                (parent_uuid,),
            )
            if parent_id:
                sql.execute(
                    f"UPDATE `{mgr.table_name}` SET parent_id = ? WHERE uuid = ?",
                    (parent_id, child_uuid),
                )


def split_module_source_description(module_source):
    """Split module source into description and data, description is the triple `"` block at the top of the file"""

    description = ""
    if module_source.strip().startswith('"""'):
        description = module_source.split('"""')[1].strip()
        # to get the data, we need to find the location of the second `"""`
        second_quote_index = module_source.find('"""', module_source.find('"""') + 1)
        data = module_source[second_quote_index + 3:]
        first_newline_index = data.find('\n')
        if first_newline_index == -1:
            data = ""
        else:
            data = data[first_newline_index:].strip('\n')
    else:
        data = module_source
    return description, data


def bootstrap_modules():
    def add_module(module_class, module_name, module_type, bake_mode='FILE', extra_imports=''):
        # module_file = module_class.__module__
        module_file_path = inspect.getfile(module_class)

        with open(module_file_path, 'r', encoding='utf-8') as file:
            module_source = file.read()

        if extra_imports:
            module_source = f'{extra_imports}\n{module_source}'

        description, module_source = split_module_source_description(module_source)
        config = {
            "name": module_name,
            "description": description,
            "data": module_source,
            "load_on_startup": True,
        }
        system.manager.modules.add(
            name=module_name,
            config=config,
            module_type=module_type,
            baked=1,
            locked=1,
            skip_load=True,
        )

    sql.execute("DELETE FROM modules WHERE baked = 1")

    module_types = {name: controller for name, controller in system.manager.modules.type_controllers.items()
                    if name is not None}
    for module_type in module_types:
        module_type_modules = system.manager.modules.get_modules_in_folder(
            module_type=module_type,
            fetch_keys=('name', 'class', 'baked', 'kind_folder',)
        )
        for module_name, module_class, baked, kind_folder in module_type_modules:
            if baked == 0:
                continue
            if module_class is None:
                print(f"Module class for {module_name} in {module_type} is None, skipping.")
                continue
            if module_name == 'config':
                pass
            # module = module_class.__module__
            add_module(
                module_class=module_class,
                module_name=module_name,
                module_type=module_type,
            )


def delete_stale_modules():
    stale = {tuple(row[:2]): row[2] for row in sql.get_results("SELECT folder_id, name, id FROM modules WHERE baked = 1")}
    for module_type in system.manager.modules.type_controllers:
        if module_type is None:
            continue
        folder_id = get_module_type_folder_id(module_type.replace('_', ' ').title())
        for module_name, baked in system.manager.modules.get_modules_in_folder(module_type, fetch_keys=('name', 'baked')):
            if baked:
                stale.pop((folder_id, module_name), None)
    sql.execute(f"DELETE FROM modules WHERE id IN ({','.join('?' * len(stale))})", tuple(stale.values()))


def reset_table(table_name, item_configs=None, folder_type=None, folder_items=None, delete_existing=True, case_insensitive=False, match_on=('name',)):
    if delete_existing:
        sql.execute(f'DELETE FROM {table_name}')

    item_configs = item_configs or {}
    folder_items = folder_items or {}
    folders_ids = {}
    if folder_type:
        if delete_existing:
            sql.execute(f'DELETE FROM folders WHERE type = "{folder_type}" AND locked != 1')  # todo locked

        for folder, blocks in folder_items.items():
            folder_id = sql.get_scalar(f'SELECT id FROM folders WHERE `name` = "{folder}" AND `type` = "{folder_type}" LIMIT 1')
            if not folder_id:
                sql.execute(f'INSERT INTO folders (name, type) VALUES (?, "{folder_type}")', (folder,))
                folder_id = sql.get_scalar(f'SELECT MAX(id) FROM folders')
            print(folder_id)
            folders_ids[folder] = folder_id

    # Fetch existing name->id once instead of a COUNT query per row, and collect all
    # writes into a single transaction (via execute_many) so bulk resets don't open
    # thousands of connections and freeze the app. Updates match on the primary key
    # `id` (indexed) rather than `name` (unindexed) to avoid a full table scan per
    # row — otherwise a reset of thousands of rows is O(rows * table_size).
    # When case_insensitive, match/dedup on the lowercased name so e.g. litellm's
    # 'Openai' updates the curated 'OpenAI' row instead of inserting a duplicate.
    # match_on sets which fields identify a row — model syncs pass ('name', 'api_id')
    # because different APIs expose identically-named models (e.g. 'seedance-2.0' on
    # both Replicate and ModelArk), and matching on name alone would let one
    # provider's sync overwrite another provider's row.
    norm = str.lower if case_insensitive else (lambda s: s)
    # Tables without an `id` column (e.g. themes) map to None and are
    # updated by their match_on fields instead.
    has_id = any(col[1] == 'id' for col in sql.get_results(f'PRAGMA table_info({table_name})'))
    match_cols = ', '.join(f'`{f}`' for f in match_on)
    id_col = 'id' if has_id else 'NULL'
    existing_ids = {
        tuple(norm(v) if f == 'name' else v for f, v in zip(match_on, row[:-1])): row[-1]
        for row in sql.get_results(f'SELECT {match_cols}, {id_col} FROM {table_name}')
    }
    inserted_keys = set()
    statements = []
    for key, conf in item_configs.items():
        # name = key.get('name') if isinstance(key, tuple) else key
        name = key
        field_vals = {}
        if isinstance(key, tuple):
            # key is a tuple(n) of tuples(2), a key value pair, find the value for 'name'
            name = next((kvp[1] for kvp in key if kvp[0] == 'name'), None)
            field_vals = {kvp[0]: kvp[1] for kvp in key}
        # field_vals = key if isinstance(key, tuple) else {}

        item_folder = next((folder_name for folder_name, item_list in folder_items.items() if name in item_list),
                            None)
        folder_id = folders_ids.get(item_folder, None)

        field_vals['name'] = name
        field_vals['config'] = json.dumps(conf)
        if folder_id:
            field_vals['folder_id'] = folder_id

        set_fields = [field for field in field_vals.keys() if field != 'name']
        set_values = [field_vals[field] for field in set_fields]
        match_key = tuple(norm(field_vals.get(f)) if f == 'name' else field_vals.get(f) for f in match_on)
        if existing_ids.get(match_key) is not None:
            # todo clean
            statements.append((f"UPDATE `{table_name}` SET {' = ?, '.join(set_fields)} = ? WHERE id = ?", set_values + [existing_ids[match_key]]))
        elif match_key in existing_ids or match_key in inserted_keys:
            # no id (table has no id column, or inserted earlier in this same
            # batch), so fall back to matching by the match_on fields.
            where = ' AND '.join(
                'LOWER(`name`) = ?' if f == 'name' and case_insensitive else f'`{f}` = ?'
                for f in match_on
            )
            statements.append((f"UPDATE `{table_name}` SET {' = ?, '.join(set_fields)} = ? WHERE {where}", set_values + list(match_key)))
        else:
            statements.append((
                f"INSERT INTO `{table_name}` ({', '.join(field_vals.keys())}) VALUES ({', '.join(['?'] * len(field_vals))})",
                tuple(field_vals.values())))
            inserted_keys.add(match_key)

    if statements:
        sql.execute_many(statements)


def ensure_system_folders():
    sys_folders = {
        'modules': {
            'Controllers': ':/resources/icon-settings-solid.png',
            'Managers': ':/resources/icon-settings-solid.png',
            'Connectors': ':/resources/icon-settings-solid.png',
            'Pages': ':/resources/icon-pages.png',
            'Widgets': ':/resources/icon-widgets.png',
            'Fields': ':/resources/icon-pencil.png',
            'Members': ':/resources/icon-agent-group.png',
            'Bubbles': ':/resources/icon-paste.png',
            'Behaviors': ':/resources/icon-settings-solid.png',
            'Providers': ':/resources/icon-archive3.png',
            'Toolkits': ':/resources/icon-tool-small.png',
            'Daemons': ':/resources/icon-settings-solid.png',
            'Highlighters': ':/resources/icon-settings-solid.png',
            'Environments': ':/resources/icon-settings-solid.png',
            'Utils': ':/resources/icon-settings-solid.png',
            'Gui Utils': ':/resources/icon-widgets.png',
        },
    }

    for folder_type, folders in sys_folders.items():
        ex_type_folders = sql.get_results("""
            SELECT 
                name
            FROM folders
            WHERE locked = 1 AND type = ?
        """, (folder_type,), return_type='list')

        ordr = 0
        for folder_name, icon_path in folders.items():
            ordr += 1
            config = json.dumps({
                'icon_path': icon_path,
                'name': folder_name,
            })

            exists = folder_name in ex_type_folders
            if not exists:
                sql.execute("""
                    INSERT INTO folders (`name`, `type`, `config`, `ordr`, `locked`, `expanded`, `parent_id`) 
                    VALUES (?, ?, ?, ?, ?, ?, ?)""", (folder_name, folder_type, config, ordr, 1, 0, None)
                )
                parent_id = sql.get_scalar("SELECT MAX(id) FROM folders")
            else:
                parent_id = sql.get_scalar("SELECT id FROM folders WHERE `name` = ? AND `type` = ? AND `locked` = 1 LIMIT 1",
                                        (folder_name, folder_type))
                sql.execute("""
                    UPDATE folders
                    SET config = ?, 
                        ordr = ?
                    WHERE id = ?""", (config, ordr, parent_id))


def reset_folders():
    reset_table(
        table_name='folders',
        item_configs={},
    )
    ensure_system_folders()


async def scrape_models():
    retval = display_message_box(
        icon=QMessageBox.Warning,
        title='Scrape new models',
        text='This will take a while.',
        buttons=QMessageBox.Ok | QMessageBox.Cancel,
    )
    if retval != QMessageBox.Ok:
        return
    # ws = system.manager.providers["litellm"]
    # ws.sync_models()
    for name, provider in system.manager.providers.items():
        if hasattr(provider, 'sync_models'):
            print(f"Syncing {name}")
            result = provider.sync_models()
            if inspect.isawaitable(result):
                await result
    apis = sql.get_results("SELECT name, provider_plugin, config, pinned FROM apis", return_type='rows')
    rows = sql.get_results("SELECT a.name, m.name, m.kind, m.config, m.schema_plugin, m.ordr, m.pinned, "
                           "json_extract(m.metadata,'$.input_schema'), m.provider_plugin "
                           "FROM models m JOIN apis a ON m.api_id = a.id", return_type='rows')
    models = [r[:7] + (json.loads(r[7]) if r[7] else None, r[8]) for r in rows]

    # Collapse case-variant provider rows (e.g. litellm's 'Openai' vs curated 'OpenAI')
    # so the shipped models.json carries one row per provider. Keep the curated casing
    # — the variant that isn't plain Title Case — and re-point models to the survivor.
    survivors = {}
    for a in apis:
        low = a[0].lower()
        kept = survivors.get(low)
        if kept is None or (a[0] != a[0].title() and kept[0] == kept[0].title()):
            survivors[low] = a
    canonical = {low: a[0] for low, a in survivors.items()}
    apis = list(survivors.values())
    models = [(canonical[m[0].lower()],) + tuple(m[1:]) for m in models]

    with open(os.path.join(os.path.dirname(__file__), 'models.json'), 'w') as f:
        json.dump({'apis': apis, 'models': models}, f, indent=2)


def reset_models(preserve_keys=True):
    api_key_vals = {}
    if preserve_keys:
        api_key_vals = sql.get_results("SELECT LOWER(name), api_key FROM apis WHERE api_key != ''", return_type='dict')

    base = os.path.join(sys._MEIPASS, 'utils') if getattr(sys, 'frozen', False) else os.path.dirname(__file__)
    with open(os.path.join(base, 'models.json')) as f:
        data = json.load(f)

    reset_table('apis', {(('name', a[0]), ('provider_plugin', a[1]), ('pinned', a[3])): json.loads(a[2] or '{}') for a in data['apis']}, delete_existing=False, case_insensitive=True)
    # Case-insensitive api-name lookup so models referencing a case-variant provider
    # name (e.g. 'Openai') still attach to the collapsed 'OpenAI' row rather than being dropped.
    ids = sql.get_results("SELECT LOWER(name), id FROM apis", return_type='dict')
    reset_table('models', {(('name', m[1]), ('kind', m[2]), ('api_id', ids[m[0].lower()]), ('schema_plugin', m[4]), ('ordr', m[5]), ('pinned', m[6]), ('metadata', json.dumps({'input_schema': m[7]} if m[7] else {})), ('provider_plugin', m[8])): json.loads(m[3] or '{}') for m in data['models'] if m[0].lower() in ids}, delete_existing=False)

    default_api_key_vals = {
        'anthropic': '$ANTHROPIC_API_KEY',
        'mistral': '$MISTRAL_API_KEY',
        'perplexity': '$PERPLEXITY_API_KEY',
        'openai': '$OPENAI_API_KEY',
        'elevenlabs': '$ELEVENLABS_API_KEY',
        'gemini': '$GEMINI_API_KEY',
        'xai': '$XAI_API_KEY',
        'fal ai': '$FAL_API_KEY',
        'replicate': '$REPLICATE_API_KEY',
        'wavespeed': '$WAVESPEED_API_KEY',
        'sonauto': '$SONAUTO_API_KEY',
        'seedance': '$ARK_API_KEY',
    }
    for name, key in default_api_key_vals.items():
        if name not in api_key_vals:
            api_key_vals[name] = key
    for name, key in api_key_vals.items():
        sql.execute("UPDATE apis SET api_key = ? WHERE LOWER(name) = ?", (key, name))
