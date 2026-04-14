import ast
import asyncio
import hashlib
import re

from sqlite3 import IntegrityError
from typing import Dict, Any, List

from PySide6.QtCore import QSize, Qt
from PySide6.QtGui import QPixmap, QPainter, QPainterPath, QColor

from utils.filesystem import unsimplify_path
from contextlib import contextmanager
from PySide6.QtWidgets import QWidget, QMessageBox
import requests

from gui import system

import json
from utils import resources_rc, sql

AUDIO_EXTS = {'.mp3', '.wav', '.flac', '.ogg', '.m4a', '.aac', '.wma'}
IMAGE_EXTS = {'.png', '.jpg', '.jpeg', '.gif', '.bmp', '.webp', '.tiff'}
VIDEO_EXTS = {'.mp4', '.avi', '.mov', '.mkv', '.webm', '.wmv', '.flv'}
ALL_MEDIA_EXTS = VIDEO_EXTS | IMAGE_EXTS | AUDIO_EXTS


def get_media_type_from_ext(ext):
    if ext in VIDEO_EXTS:
        return 'video'
    elif ext in IMAGE_EXTS:
        return 'image'
    elif ext in AUDIO_EXTS:
        return 'audio'
    return None


def get_media_preview_class(media_type=None, ext=None):
    from gui.media_previews.image import ImagePreview
    from gui.media_previews.video import VideoPreview
    from gui.media_previews.audio import AudioPreview

    if not media_type:
        media_type = get_media_type_from_ext(ext)
    preview_dict = {
        'video': VideoPreview,
        'image': ImagePreview,
        'audio': AudioPreview,
    }
    return preview_dict.get(media_type, None)


def get_media_icon_path(media_type=None, ext=None):
    if not media_type:
        media_type = get_media_type_from_ext(ext)
    icon_dict = {
        'video': ':/resources/icon-video.png',
        'image': ':/resources/icon-image.png',
        'audio': ':/resources/icon-audio.png',
    }
    return icon_dict.get(media_type, ':/resources/icon-file.png')


class BaseManager(dict):
    """
    The `BaseManager` class provides a base for managing data, including loading, saving, adding, and deleting items from a database table.
    """
    def __init__(self, system, **kwargs):
        super().__init__()
        self.system = system

        # Initialize connector # todo dedupe
        # connector_param = kwargs.get('db_connector', None)
        # connector_kwargs = kwargs.get('connector_kwargs', {})
        # if connector_param is None:
        #     connector_param = 'SqliteConnector'
        from core.connectors.sqlite import SqliteConnector
        self.db_connector = kwargs.get('db_connector', SqliteConnector())
        # if isinstance(connector_param, str):
        #     from gui import system as system
        #     connector_class = system.get_module_class(module_type='Connectors', module_name=connector_param)
        #     if connector_class:
        #         self.db_connector = connector_class(**connector_kwargs)
        #     else:
        #         raise ValueError(f"Connector '{connector_param}' not found")
        # else:
            
        self.table_name = kwargs.get('table_name', None)
        self.query = kwargs.get('query', None)
        self.query_params = kwargs.get('query_params', None)
        self.load_columns = kwargs.get('load_columns', None if self.query else ['id', 'config'])
        self.folder_key = kwargs.get('folder_key', None)
        # self.key_column = kwargs.get('key_column', 'uuid')
        # self.default_kind = kwargs.get('default_kind', None)
        self.default_fields = kwargs.get('default_fields', {})
        self.add_item_options = kwargs.get('add_item_options', None)
        self.del_item_options = kwargs.get('del_item_options', None)
        self.store_data = kwargs.get('store_data', True)
        self.config_is_workflow = kwargs.get('config_is_workflow', False)
        # self.default_config = kwargs.get('default_config', {})

        if self.table_name and not self.query and self.load_columns:
            has_pinned_column = self.db_connector.get_scalar(f"SELECT COUNT(*) FROM pragma_table_info('{self.table_name}') WHERE name = 'pinned'") > 0
            has_ordr_column = self.db_connector.get_scalar(f"SELECT COUNT(*) FROM pragma_table_info('{self.table_name}') WHERE name = 'ordr'") > 0
            order_by = ""  # todo clean
            if has_pinned_column:
                order_by += "pinned DESC, "
            if has_ordr_column:
                order_by += "ordr, "
            order_by += "name"
            self.query = f"""
                SELECT {', '.join(self.load_columns)}
                FROM {self.table_name}
                ORDER BY {order_by}
            """
            # else:
            #     self.query = f"""
            #         SELECT {', '.join(self.load_columns)}
            #         FROM {self.table_name}
            #         ORDER BY ordr, name
            #     """

        self.db_connector.define_table(self.table_name)  # incase it's not defined yet
    
    def load(self):
        if not self.store_data:
            return

        if self.query:
            rows = self.db_connector.get_results(self.query, self.query_params)
        else:
            columns = ', '.join(f'`{col}`' for col in self.load_columns)
            rows = self.db_connector.get_results(f"SELECT {columns} FROM `{self.table_name}`")

        self.clear()
        if len(self.load_columns) > 2:
            self.update({row[0]: row for row in rows})
        else:
            self.update({key.replace('-', '_').replace(' ', '_'): json.loads(config) for key, config in rows})

    def add(self, name, **kwargs):
        skip_load = kwargs.pop('skip_load', False)

        all_values = {'name': name}
        all_values.update({k: v for k, v in kwargs.items() if v is not None})

        if 'config' not in self.default_fields:
            self.default_fields['config'] = {}
        # all_values['config'] = self.default_fields.get('config', {})
        for key, value in self.default_fields.items():
            if key not in all_values:
                all_values[key] = value

        if self.config_is_workflow and 'name' not in all_values['config']:
            all_values['config']['name'] = name

        all_values['config'] = json.dumps(all_values['config'])

        # Create SQL query with dynamic columns
        columns = ', '.join(f'`{col}`' for col in all_values.keys())
        placeholders = ', '.join(['?'] * len(all_values))
        values = tuple(all_values.values())
 
        try:
            if 'uuid' in all_values:
                uuid = all_values['uuid']
                item_exists = self.db_connector.get_scalar(f"SELECT id FROM `{self.table_name}` WHERE `uuid` = ?", (uuid,))
                if item_exists:
                    set_query = ', '.join([f'`{col}` = ?' for col in all_values.keys()])
                    values += (uuid,)
                    # query = f"UPDATE `{self.table_name}` SET {set_query} WHERE `uuid` = ?"
                    self.db_connector.execute(f"UPDATE `{self.table_name}` SET {set_query} WHERE `uuid` = ?", values)
                    return

            self.db_connector.execute(f"INSERT INTO `{self.table_name}` ({columns}) VALUES ({placeholders})", values)

        except IntegrityError:
            display_message(
                message='Item already exists',
                icon=QMessageBox.Warning,
            )
        finally:
            if not skip_load:
                self.load()

    def delete(self, key, where_field='id'):
        if self.table_name == 'contexts':  # todo create contexts manager
            # context_id = item_id
            all_context_ids = self.db_connector.get_results("""
                WITH RECURSIVE context_tree AS (
                    SELECT id FROM contexts WHERE id = ?
                    UNION ALL
                    SELECT c.id
                    FROM contexts c
                    JOIN context_tree ct ON c.parent_id = ct.id
                )
                SELECT id FROM context_tree;""", (key,), return_type='list')
            if all_context_ids:
                all_context_ids = tuple(all_context_ids)
                self.db_connector.execute(f"DELETE FROM contexts_messages WHERE context_id IN ({','.join('?' * len(all_context_ids))});", all_context_ids)
                self.db_connector.execute(f"DELETE FROM contexts WHERE id IN ({','.join('?' * len(all_context_ids))});", all_context_ids)

        try:
            self.db_connector.execute(f"DELETE FROM `{self.table_name}` WHERE `{where_field}` = ?", (key,))
            self.load()

        except Exception as e:
            display_message(
                message=f'Item could not be deleted:\n' + str(e),
                icon=QMessageBox.Warning,
            )

    def save(self):
        pass

    def get_cell(self, key, column):
        """
        Get a value from the specified column for the given key.
        If `column` is a string, it will be converted to an index based on load_columns.
        """
        if isinstance(column, str):
            if column not in self.load_columns:
                raise ValueError(f"Column `{column}` not found in module table.")
            column = self.load_columns.index(column)
        return self[key][column]


def convert_model_json_to_obj(model_json: Any) -> Dict[str, Any]:
    if model_json is None:
        return {
            'kind': 'CHAT',
            '_model_name': 'mistral/mistral-large-latest',
            'model_params': {},
            'provider': 'litellm',
        }
    try:
        obj = convert_json_to_obj(model_json)
        if 'model_name' in obj and '_model_name' not in obj:
            obj['_model_name'] = obj.pop('model_name')
        return obj

    except json.JSONDecodeError:  # temp patch until 0.4.0
        return {
            'kind': 'CHAT',
            '_model_name': model_json,
            'model_params': {},
            'provider': 'litellm',
        }


def convert_json_to_obj(json_inp):
    if not json_inp:
        return {}
    if isinstance(json_inp, dict):
        return json_inp
    return json.loads(json_inp)


def hash_config(config, exclude=None) -> str:
    exclude = exclude or []
    hash_config = {k: v for k, v in config.items() if k not in exclude}
    return hashlib.sha1(json.dumps(hash_config).encode()).hexdigest()


def get_json_value(json_str, key, default=None):
    """Get a value from a JSON string by key"""
    try:
        data = json.loads(json_str)
        return data.get(key, default)
    except json.JSONDecodeError:
        return default


def get_id_from_folder_path(folder_path, folder_type=None):
    """
    Get the folder ID from a folder path, optionally creating
    missing folders when ``folder_type`` is provided.
    """
    if not folder_path:
        return None

    path_parts = folder_path.split('/')
    current_parent_id = None

    for part in path_parts:
        parent_clause = "IS NULL" if current_parent_id is None else "= ?"
        params = (part,) if current_parent_id is None else (part, current_parent_id)
        folder_id = sql.get_scalar(
            f"SELECT id FROM folders WHERE name = ? AND parent_id {parent_clause}",
            params,
        )
        if not folder_id:
            if not folder_type:
                return None
            sql.execute(
                "INSERT INTO folders (name, parent_id, type) VALUES (?, ?, ?)",
                (part, current_parent_id, folder_type),
            )
            folder_id = sql.get_scalar("SELECT MAX(id) FROM folders")
        current_parent_id = folder_id

    return current_parent_id


def get_module_type_folder_id(module_type, config={}):  # todo clean
    if 'icon_path' not in config:
        config['icon_path'] = ':/resources/icon-settings-solid.png'
    folder_id = sql.get_scalar(f"""
        SELECT id
        FROM folders
        WHERE REPLACE(LOWER(name), ' ', '_') = ?
            AND type = 'modules'
    """, (module_type.lower().replace(' ', '_'),))
    
    if not folder_id:
        sql.execute("""
            INSERT INTO folders (name, type, config)
            VALUES (?, 'modules', ?)
        """, (module_type, json.dumps(config)))
        folder_id = sql.get_scalar("""
            SELECT id
            FROM folders
            WHERE REPLACE(LOWER(name), ' ', '_') = ?
                AND type = 'modules'
        """, (module_type.lower().replace(' ', '_'),))
    # # if not folder_id:
    # #     raise ValueError(f"Module type '{module_type}' not found in database.")
    return folder_id


def set_module_type(module_type, plugin=None, settings=None):
    def decorator(cls):
        cls._ap_module_type = module_type.lower()
        if plugin:
            cls._ap_plugin_type = plugin
        if settings:
            cls._ap_settings_module = settings
        return cls
    return decorator


def message_button(name):
    def decorator(cls):
        cls._ap_message_button = name
        return cls
    return decorator


def widget_button(name, **kwargs):
    def decorator(obj):
        obj._ap_widget_button = name
        # if inspect.isclass(obj):
        for key, value in kwargs.items():
            setattr(obj, f'_ap_widget_button_{key}', value)
        return obj
        # else:
        #     # If obj is a function/method, attach attributes to the function
        #     # obj._ap_widget_button = name
        #     obj._ap_widget_button_kwargs = kwargs.copy()
        #     return obj
    return decorator


def message_extension(name):
    def decorator(cls):
        cls._ap_message_extension = name
        return cls
    return decorator


def network_connected() -> bool:
    try:
        requests.get("https://google.com", timeout=5)
        return True
    except requests.ConnectionError:
        return False


def convert_to_safe_case(text) -> str:
    """Use regex to return only a-z A-Z 0-9 and _"""
    text = text.replace(' ', '_').replace('-', '_')  # .lower()  todo
    return re.sub(r'[^a-zA-Z0-9_.]', '_', text)


def get_avatar_paths_from_config(config, merge_multiple=False) -> Any:
    member_type = config.get('_TYPE', 'agent')
    if member_type == 'workflow':
        if 'avatar_path' in config:
            return config['avatar_path']

        paths = []
        members = config.get('members', [])
        for member_data in members:
            member_config = member_data.get('config', {})
            member_type = member_config.get('_TYPE', 'agent')
            if member_type == 'user':
                continue
            paths.append(get_avatar_paths_from_config(member_config))
        return paths if paths else ':/resources/icon-user.png'
        # return paths # if not merge_multiple else '//##//##//'.join(flatten_list(paths))

    member_class = system.manager.modules.get_module_class('Members', module_name=member_type)
    if not member_class:
        display_message(
            message=f"Member module '{member_type}' not found.",
            icon=QMessageBox.Warning,
        )
        return ':/resources/icon-agent-solid.png'  # todo error icon

    avatar_key = getattr(member_class, 'avatar_key', None)
    default_avatar = getattr(member_class, 'default_avatar', ':/resources/icon-agent-solid.png')
    if avatar_key:
        avatar_path = config.get(avatar_key, default_avatar)
        return avatar_path
    else:
        return default_avatar


def flatten_list(lst) -> List:  # todo dirty
    flat_list = []
    for item in lst:
        if isinstance(item, list):
            flat_list.extend(flatten_list(item))
        elif isinstance(item, tuple):
            flat_list.extend(list(item))
        else:
            flat_list.append(item)
    return flat_list


def get_member_name_from_config(config, incl_types=('agent', 'workflow')) -> str:
    member_type = config.get('_TYPE', 'agent')
    if member_type == 'workflow':
        names = []
        members = config.get('members', [])
        for member_data in members:
            member_config = member_data.get('config', {})
            member_type = member_config.get('_TYPE', 'agent')
            if member_type == 'user':
                continue
            names.append(get_member_name_from_config(member_config))
        return ', '.join(flatten_list(names))
        # return paths  # if not merge_multiple else '//##//##//'.join(flatten_list(paths))

    member_class = system.manager.modules.get_module_class('Members', module_name=member_type)
    if not member_class:
        display_message(
            message=f"Member module '{member_type}' not found.",
            icon=QMessageBox.Warning,
        )
        return 'Invalid member'

    name_key = getattr(member_class, 'name_key', None)
    default_name = getattr(member_class, 'default_name', 'Assistant')
    if name_key:
        name = config.get(name_key, default_name)
        return name
    else:
        return default_name


def resolve_linked_config(linked_id, visited=None):
    """Fetch config from DB for a linked_id like 'entities.{uuid}'.

    Recursively resolves nested linked_ids in the config.
    Uses visited set to detect circular references.

    Parameters
    ----------
    linked_id : str
        Format: 'table.uuid'
    visited : set, optional
        Set of already-visited linked_ids for cycle detection.

    Returns
    -------
    dict or None
        Resolved config, or None if entity not found.
    """
    if not linked_id:
        return None

    if visited is None:
        visited = set()

    if linked_id in visited:
        return None

    visited.add(linked_id)

    parts = linked_id.split('.', 1)
    if len(parts) != 2:
        return None

    table, entity_uuid = parts

    config_json = sql.get_scalar(
        f"SELECT config FROM `{table}` WHERE uuid = ?",
        (entity_uuid,)
    )
    if config_json is None:
        return None

    config = json.loads(config_json) if isinstance(config_json, str) else config_json

    # Recursively resolve nested linked_ids in members
    members = config.get('members', [])
    for member in members:
        nested_linked_id = member.get('linked_id')
        if nested_linked_id:
            nested_config = resolve_linked_config(nested_linked_id, visited=set(visited))
            if nested_config is not None:
                member['config'] = nested_config

    return config


def save_linked_config(linked_id, config):
    """Write config back to the source entity.

    Parameters
    ----------
    linked_id : str
        Format: 'table.uuid'
    config : dict
        Config to save.
    """
    if not linked_id:
        return

    parts = linked_id.split('.', 1)
    if len(parts) != 2:
        return

    table, entity_uuid = parts
    config_to_save = {k: v for k, v in config.items() if k != 'linked_id'}
    sql.execute(
        f"UPDATE `{table}` SET config = ? WHERE uuid = ?",
        (json.dumps(config_to_save), entity_uuid)
    )

    # Recursively save nested linked members
    for member in config_to_save.get('members', []):
        nested_linked_id = member.get('linked_id')
        if nested_linked_id:
            nested_config = member.get('config', {})
            save_linked_config(nested_linked_id, nested_config)


def has_circular_link(linked_id, existing_chain=None):
    """Check if linking to linked_id would create a cycle.

    Parameters
    ----------
    linked_id : str
        The linked_id to check.
    existing_chain : set, optional
        Set of linked_ids already in the chain.

    Returns
    -------
    bool
        True if a cycle would be created.
    """
    if not linked_id:
        return False

    if existing_chain is None:
        existing_chain = set()

    if linked_id in existing_chain:
        return True

    existing_chain.add(linked_id)

    parts = linked_id.split('.', 1)
    if len(parts) != 2:
        return False

    table, entity_uuid = parts
    config_json = sql.get_scalar(
        f"SELECT config FROM `{table}` WHERE uuid = ?",
        (entity_uuid,)
    )
    if config_json is None:
        return False

    config = json.loads(config_json) if isinstance(config_json, str) else config_json

    members = config.get('members', [])
    for member in members:
        nested_linked_id = member.get('linked_id')
        if nested_linked_id:
            if has_circular_link(nested_linked_id, existing_chain=set(existing_chain)):
                return True

    return False


def get_entity_workflow_config(entity_val):
    """Build a workflow config from an entity field value.

    Parameters
    ----------
    entity_val : str
        Stored value in ``name:table:uuid`` format.

    Returns
    -------
    dict
        A workflow config, or empty dict if the value is invalid.
    """
    if not entity_val:
        return {}
    parts = entity_val.rsplit(':', 2)
    if len(parts) != 3:
        return {}
    _, table, uuid = parts
    from utils import sql
    raw = sql.get_scalar(
        f"SELECT config FROM `{table}` WHERE uuid = ?", (uuid,),
    )
    if not raw:
        return {}
    config = json.loads(raw) if isinstance(raw, str) else raw
    return merge_config_into_workflow_config(
        config, entity_id=uuid, entity_table=table,
    )


def merge_config_into_workflow_config(config, entity_id=None, entity_table=None) -> Dict[str, Any]:
    """Wrap a non-workflow config into a workflow structure.

    Parameters
    ----------
    entity_id : str or None
        The *uuid* of the source entity (not the integer id).
    entity_table : str or None
        Table name, e.g. 'entities', 'blocks', 'tools'.
    """
    linked_id = f'{entity_table}.{entity_id}' if entity_id is not None else None

    member_type = config.get('_TYPE', 'agent')
    if member_type == 'workflow':
        if linked_id:
            config['linked_id'] = linked_id
        return config
    else:
        name = config.pop('name', 'Workflow')

    if member_type == 'agent':  # !wfdiff! #
        members = [
            {'id': '1', 'linked_id': None, 'loc_x': 20, 'loc_y': 64, 'config': {"_TYPE": "user", "name": "You"}},
            {'id': '2', 'linked_id': linked_id, 'loc_x': 100, 'loc_y': 80, 'config': config | {"name": "Agent"}}
        ]
    else:
        pretty_name = member_type.replace('_', ' ').title()
        members = [{'id': '1', 'linked_id': linked_id, 'loc_x': 100, 'loc_y': 80, 'config': config | {"name": pretty_name}}]

    config_json = {
        '_TYPE': 'workflow',
        'name': name,
        'description': config.get('description', ''),
        'avatar_path': config.get('avatar_path', None),
        'members': members,
        'inputs': [],
    }
    return config_json


def merge_multiple_into_workflow_config(members, inputs) -> Dict[str, Any]:
    """Merge multiple configs into a single workflow config."""
    if not members:
        return {}
    if len(members) == 1 and '_TYPE' in members[0] and members[0]['_TYPE'] == 'workflow':
        return members[0]

    merged_config = {
        '_TYPE': 'workflow',
        'members': [
            {'id': str(i + 1), 'linked_id': None, 'loc_x': 100 + qpoint.x(), 'loc_y': 80 + qpoint.y(), 'config': config}
            for i, (qpoint, config) in enumerate(members)
        ],
        'inputs': [
            {
                'source_member_id': str(source_member_index + 1), 
                'target_member_id': str(target_member_index + 1), 
                'config': input_config
            }
            for source_member_index, target_member_index, input_config in inputs
        ]
    }

    return merged_config


async def receive_workflow(
    config: Dict[str, Any] = None,
    kind: str = 'BLOCK',
    params: Dict[str, Any] = None,
    tool_uuid: str = None,
    chat_title: str = '',
    main=None,
    workflow = None,
):
    if workflow is None:
        from plugins.workflows.members.workflow import Workflow
        wf_config = merge_config_into_workflow_config(config)
        workflow = Workflow(main=main, config=wf_config, kind=kind, params=params, tool_uuid=tool_uuid, chat_title=chat_title)

    try:
        async for key, chunk in workflow.run():
            yield key, chunk
    except StopIteration:  # !nestmember! #
        raise Exception("Pausing nested workflows isn't implemented yet")


async def compute_workflow_async(  # todo rename, clean
    config: Dict[str, Any] = None,
    kind: str = 'BLOCK',
    params: Dict[str, Any] = None,
    tool_uuid: str = None,
    chat_title: str = '',
    main=None,
    workflow = None,
):
    response = ''
    async for key, chunk in receive_workflow(config=config, kind=kind, params=params, tool_uuid=tool_uuid, chat_title=chat_title, main=main, workflow=workflow):
        response += chunk
    return response


def compute_workflow(  # todo rename
    config: Dict[str, Any],
    kind: str = 'BLOCK',
    params: Dict[str, Any] = None,
    tool_uuid: str = None,
    chat_title: str = '',
    main=None,
    workflow = None,
):
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        loop = None
    if loop is None:
        from gui.main import loop as main_loop
        if main_loop is not None and main_loop.is_running():
            future = asyncio.run_coroutine_threadsafe(
                compute_workflow_async(config=config, kind=kind, params=params, tool_uuid=tool_uuid, chat_title=chat_title, main=main, workflow=workflow),
                main_loop,
            )
            return future.result()
    return asyncio.run(compute_workflow_async(config=config, kind=kind, params=params, tool_uuid=tool_uuid, chat_title=chat_title, main=main, workflow=workflow))


def params_to_schema(params):
    type_convs = {
        'String': str,
        'Bool': bool,
        'Int': int,
        'Float': float,
    }
    type_defaults = {
        'String': '',
        'Bool': False,
        'Int': 0,
        'Float': 0.0,
    }

    ignore_names = ['< enter a parameter name >']
    schema = [
        {
            'key': param.get('name', ''),
            'text': param.get('name', '').capitalize().replace('_', ' '),
            'type': type_convs.get(param.get('type'), str),
            'default': param.get('default', type_defaults.get(param.get('type'), '')),
            'tooltip': param.get('description', None),
            'minimum': -99999,
            'maximum': 99999,
            'step': 1,
            **({'has_toggle': True} if not param.get('req', True) else {}),
        }
        for param in params
        if param.get('name').lower() not in ignore_names
    ]
    return schema


def get_metadata(config):
    def get_type_annotation(annotation):
        if isinstance(annotation, ast.Name):
            return annotation.id
        elif isinstance(annotation, ast.Subscript):
            return f"{get_type_annotation(annotation.value)}[{get_type_annotation(annotation.slice)}]"
        elif isinstance(annotation, ast.Constant):
            return str(annotation.value)
        elif isinstance(annotation, ast.Index):  # For Python 3.8 and earlier
            return get_type_annotation(annotation.value)
        else:
            return 'complex_type'

    def get_params(ast_node):
        params = {}
        args = ast_node.args.args
        defaults = ast_node.args.defaults
        default_start_idx = len(args) - len(defaults)

        for i, arg in enumerate(args):
            param_type = get_type_annotation(arg.annotation) if arg.annotation else 'untyped'

            if i >= default_start_idx and isinstance(defaults[i - default_start_idx], ast.Constant):
                default_value = defaults[i - default_start_idx].value
            else:
                default_value = None

            params[arg.arg] = (param_type, default_value)

        return params

    def get_super_kwargs(init_node):
        # Look for a call to super().__init__(...) in init_node.body
        super_kwargs = {}
        for stmt in init_node.body:
            if isinstance(stmt, ast.Expr) and isinstance(stmt.value, ast.Call):
                call = stmt.value
                # Check if it's super().__init__
                if (
                    isinstance(call.func, ast.Attribute) and
                    call.func.attr == '__init__' and
                    isinstance(call.func.value, ast.Call) and
                    isinstance(call.func.value.func, ast.Name) and
                    call.func.value.func.id == 'super'
                ):
                    # Collect keyword args
                    for kw in call.keywords:
                        # Skip things like **kwargs
                        if kw.arg is None:
                            continue
                        # Store literal or some placeholder
                        if isinstance(kw.value, ast.Constant):
                            super_kwargs[kw.arg] = kw.value.value
                        elif isinstance(kw.value, ast.Tuple):
                            tuple_as_list = [elt.value for elt in kw.value.elts if isinstance(elt, ast.Constant)]
                            super_kwargs[kw.arg] = tuple_as_list
                        # elif isinstance(kw.value, ast.Dict):
                        #     dict_as_dict = {k.value: e for k, v in zip(kw.value.keys, kw.value.values)}
                        #     super_kwargs[kw.arg] = dict_as_dict
                        else:
                            super_kwargs[kw.arg] = 'complex_value'
                    break

        return super_kwargs

    def get_class_metadata(class_node):
        # Collect basic info for this class
        super_kwargs = None
        class_params = None
        superclass = getattr(class_node.bases[0], 'id', None) if class_node.bases else None

        # Find __init__ to get parameters
        init_node = None
        for child in class_node.body:
            if isinstance(child, ast.FunctionDef) and child.name == '__init__':
                init_node = child
                break

        if init_node:
            class_params = get_params(init_node)
            super_kwargs = get_super_kwargs(init_node)

        # Recursively process nested classes
        nested_classes = {}
        for child in class_node.body:
            if isinstance(child, ast.ClassDef):
                nested_classes[child.name] = get_class_metadata(child)

        # Return a dict describing this class
        class_data = {
            'superclass': superclass,
            'params': class_params,
            'super_kwargs': super_kwargs,
            'classes': nested_classes,
        }
        return {k: v for k, v in class_data.items() if v is not None}


    json_hash = hash_config(config, exclude=['load_on_startup'])

    code = config.get('data')
    if not code:
        return {
            'hash': json_hash,
            'attributes': {},
            'methods': {},
            'classes': {},
        }

    attributes = {}
    methods = {}
    classes = {}
    
    try:
        tree = ast.parse(code)
        for node in tree.body:
            if isinstance(node, ast.Assign):
                for target in node.targets:
                    if isinstance(target, ast.Name):
                        attributes[target.id] = {'type': 'untyped'}

            elif isinstance(node, ast.AnnAssign):
                if isinstance(node.target, ast.Name):
                    attributes[node.target.id] = {'type': get_type_annotation(node.annotation)}

            elif isinstance(node, ast.FunctionDef):
                params = get_params(node)
                methods[node.name] = {'params': params}

            elif isinstance(node, ast.ClassDef):
                classes[node.name] = get_class_metadata(node)

            # else:
            #     print(node.__class__)

    except Exception as e:
        print(f"Error parsing code: {str(e)}")

    return {
        'hash': json_hash,
        'attributes': attributes,
        'methods': methods,
        'classes': classes,
    }


def try_parse_json(text):
    try:
        return True, json.loads(text)
    except Exception as e:
        return False, {}


async def download_url_to_file(url, base_dir=None, filename_without_ext=None):
    """Download a URL to a local file and return the path.

    Parameters
    ----------
    url : str
        Remote URL to download.

    Returns
    -------
    str or None
        Local file path, or ``None`` on failure.
    """
    import os
    from utils.filesystem import get_application_path

    import aiofiles
    import aiohttp

    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(url) as response:
                response.raise_for_status()
                content = await response.read()
    except Exception as e:
        print(f"Download error: {e}")
        return None

    remote_filename = os.path.basename(url.split('?')[0])
    remote_filename_without_ext, remote_fileext = os.path.splitext(remote_filename)

    if not filename_without_ext:
        filename_without_ext = remote_filename_without_ext or 'download'
    else:
        # Guard against callers accidentally passing a filename with extension.
        filename_without_ext = os.path.splitext(filename_without_ext)[0]
    if not base_dir:
        ext = remote_fileext.lower()
        if ext in VIDEO_EXTS:
            subdir = 'videos'
        elif ext in AUDIO_EXTS:
            subdir = 'music'
        else:
            subdir = 'images'
        base_dir = os.path.join(get_application_path(), subdir)
    os.makedirs(base_dir, exist_ok=True)

    local_path = os.path.join(
        base_dir, f"{filename_without_ext}{remote_fileext}")
    async with aiofiles.open(local_path, 'wb') as f:
        await f.write(content)
    return local_path


@contextmanager
def block_signals(*widgets, recurse_children=True):
    """Context manager to block signals for a widget and all its child pages."""
    all_widgets = []
    original_states = []
    try:
        # Get all child pages - use more efficient method
        for widget in widgets:
            all_widgets.append(widget)
            if recurse_children:
                # Use Qt's built-in findChildren which is more efficient than our custom function
                children = widget.findChildren(QWidget)
                all_widgets.extend(children)

        # Store original states and block signals
        for widget in all_widgets:
            original_states.append(widget.signalsBlocked())
            widget.blockSignals(True)

        yield
    finally:
        # Restore original signal states
        for widget, original_state in zip(all_widgets, original_states):
            widget.blockSignals(original_state)


def display_message(message, title=None, icon='Information', duration=5000):
    from gui.util import find_main
    main = find_main()
    if main:
        main.notification_manager.show_notification(
            message=message,
            title=title or str(icon),
            color='blue' if icon == QMessageBox.Information else None,
            icon=icon,
            duration=duration
        )
    else:
        if isinstance(icon, str):
            icon = getattr(QMessageBox, icon, QMessageBox.Information)
        display_message_box(
            icon=icon,
            title=title or icon.name,
            text=message,
        )


def display_message_box(icon, text, title, buttons=(QMessageBox.Ok), custom_buttons=None):
    msg = QMessageBox()
    msg.setIcon(icon)
    msg.setText(text)
    msg.setWindowTitle(title)
    msg.setStandardButtons(buttons)
    if QMessageBox.Yes in buttons:
        msg.setDefaultButton(QMessageBox.Yes)
    elif QMessageBox.Ok in buttons:
        msg.setDefaultButton(QMessageBox.Ok)
    msg.setWindowFlags(msg.windowFlags() | Qt.WindowStaysOnTopHint)
    if custom_buttons:
        for button_text, role in custom_buttons:
            msg.addButton(button_text, role)
    # msg.addButton('Archive', QMessageBox.ActionRole)
    return msg.exec()


def apply_alpha_to_hex(hex_color, alpha):
    color = QColor(hex_color)
    color.setAlphaF(alpha)
    return color.name(QColor.HexArgb)


def split_lang_and_code(text):
    if text.startswith('```') and text.endswith('```'):
        lang, code = text[3:-3].split('\n', 1)
        return lang, code
    return None, text


def path_to_pixmap(paths, circular=False, diameter=30, opacity=1, def_avatar=None):
    if isinstance(paths, list):
        count = len(paths)
        dia_mult = 0.7 if count > 1 else 1  # 1 - (0.08 * min(count - 1, 8))
        small_diameter = int(diameter * dia_mult)

        pixmaps = []
        for path in paths:
            pixmaps.append(path_to_pixmap(path, diameter=small_diameter, def_avatar=def_avatar))

        # Create a new QPixmap to hold all the stacked pixmaps
        stacked_pixmap = QPixmap(diameter, diameter)
        stacked_pixmap.fill(Qt.transparent)

        painter = QPainter()
        if not painter.begin(stacked_pixmap):
            return stacked_pixmap  # Return empty pixmap if painting fails
        painter.setRenderHint(QPainter.Antialiasing)
        painter.setRenderHint(QPainter.SmoothPixmapTransform)

        only_two = count == 2
        only_one = count == 1

        offset = (diameter - small_diameter) // 2
        for i, pixmap in enumerate(pixmaps):
            # Calculate the shift for each pixmap
            # random either -1 or 1
            x_shift = (i % 2) * 2 - 1
            y_shift = ((i // 2) % 2) * 2 - 1
            x_shift *= 5
            y_shift *= 5
            if only_two and i == 1:
                y_shift *= -1
            if only_one:
                x_shift = 0
                y_shift = 0
            painter.drawPixmap(offset - x_shift, offset - y_shift, pixmap)
        painter.end()

        return stacked_pixmap

    else:
        from gui.util import colorize_pixmap

        try:
            path = unsimplify_path(paths)
            if path == '':
                raise Exception('Empty path')
            pic = QPixmap(path)
            if path.startswith(':/'):
                pic = colorize_pixmap(pic)
        except Exception as e:
            default_img_path = def_avatar or ':/resources/icon-agent-solid.png'
            pic = colorize_pixmap(QPixmap(default_img_path))

        if circular:
            pic = create_circular_pixmap(pic, diameter=diameter)

        if opacity < 1:
            temp_pic = QPixmap(pic.size())
            temp_pic.fill(Qt.transparent)

            painter = QPainter()
            if not painter.begin(temp_pic):
                return pic  # Return original pixmap if painting fails
            painter.setOpacity(opacity)
            painter.drawPixmap(0, 0, pic)
            painter.end()

            pic = temp_pic

        # resize the pixmap to the desired diameter
        if not pic.isNull() and (pic.width() != diameter or pic.height() != diameter):
            pic = pic.scaled(diameter, diameter, Qt.KeepAspectRatioByExpanding, Qt.SmoothTransformation)

        return pic


def create_circular_pixmap(src_pixmap, diameter=30):
    if src_pixmap.isNull():
        return QPixmap()

    # Desired size of the profile picture
    size = QSize(diameter, diameter)

    # Create a new QPixmap for our circular image with the same size as our QLabel
    circular_pixmap = QPixmap(size)
    circular_pixmap.fill(Qt.transparent)  # Ensure transparency for the background

    # Create a painter to draw on the pixmap
    painter = QPainter()
    if not painter.begin(circular_pixmap):
        return QPixmap()  # Return empty pixmap if painting fails
    painter.setRenderHint(QPainter.Antialiasing)  # For smooth rendering
    painter.setRenderHint(QPainter.SmoothPixmapTransform)

    # Draw the ellipse (circular mask) onto the pixmap
    path = QPainterPath()
    path.addEllipse(0, 0, size.width(), size.height())
    painter.setClipPath(path)

    # Scale the source pixmap while keeping its aspect ratio
    src_pixmap = src_pixmap.scaled(size, Qt.KeepAspectRatioByExpanding, Qt.SmoothTransformation)

    # Calculate the coordinates to ensure the pixmap is centered
    x = (size.width() - src_pixmap.width()) / 2
    y = (size.height() - src_pixmap.height()) / 2

    painter.drawPixmap(x, y, src_pixmap)
    painter.end()

    return circular_pixmap
