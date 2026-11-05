import ast
import hashlib
import os
import re
import sys

from sqlite3 import IntegrityError
from typing import Dict, Any, List

from PySide6.QtCore import QEventLoop, QObject, QSize, Qt, QResource, Signal
from PySide6.QtGui import QPixmap, QPainter, QPainterPath, QColor

from utils.filesystem import unsimplify_path
from contextlib import contextmanager
from PySide6.QtWidgets import QApplication, QDialog, QDialogButtonBox, QInputDialog, QWidget, QMessageBox
import requests

import json
from utils import sql

RESOURCES_RCC = os.path.join(
    os.path.join(sys._MEIPASS, 'utils') if getattr(sys, 'frozen', False) else os.path.dirname(__file__),
    'resources.rcc',
)
QResource.registerResource(RESOURCES_RCC)

LANG_DIR = os.path.join(os.path.dirname(RESOURCES_RCC), 'lang')
RTL_LANGUAGES = ('العربية', 'اردو')
TRANSLATIONS = {}


def get_languages():
    return ('English', *sorted(f[:-5] for f in os.listdir(LANG_DIR) if f.endswith('.json')))


def load_language(language):
    path = os.path.join(LANG_DIR, f'{language}.json')
    TRANSLATIONS.clear()
    QApplication.setLayoutDirection(
        Qt.RightToLeft if language in RTL_LANGUAGES else Qt.LeftToRight
    )
    if os.path.exists(path):
        with open(path, encoding='utf-8') as f:
            TRANSLATIONS.update(json.load(f))


def tr(text):
    return TRANSLATIONS.get(text, text)


def llm_tool(func=None, name=None, description=None, params=None, confirm=None):
    """Mark a widget/page method as a tool callable by the LLM.
    Usable bare (@llm_tool) or with args (@llm_tool(name='switch_page')).
    `params` maps exposed parameter names to descriptions; when omitted,
    every signature parameter is exposed.
    `confirm` makes the user accept or reject each call with the tool
    bubble's message buttons before it runs."""
    def decorator(fn):
        fn._ap_llm_tool = {
            'name': name or fn.__name__,
            'description': description or (fn.__doc__ or '').strip(),
            'params': params,
            'confirm': confirm,
        }
        return fn
    if func is not None:
        return decorator(func)
    return decorator


class ManagerSignals(QObject):
    changed = Signal()


class BaseManager(dict):
    """
    The `BaseManager` class provides a base for managing data, including loading, saving, adding, and deleting items from a database table.
    Managers with a `table_name` expose generic CRUD `@llm_tool`s unless `llm_crud` is False.
    """
    llm_crud = True

    def __init__(self, system, **kwargs):
        super().__init__()
        self.system = system
        self.signals = ManagerSignals()

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
                    self.signals.changed.emit()
                    return item_exists

            item_id = self.db_connector.execute(f"INSERT INTO `{self.table_name}` ({columns}) VALUES ({placeholders})", values)

        except IntegrityError:
            display_message(
                message='Item already exists',
                icon=QMessageBox.Warning,
            )
            return None
        finally:
            if not skip_load:
                self.load()

        self.signals.changed.emit()
        return item_id

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
            has_parent_id_col = self.db_connector.get_scalar(f"SELECT COUNT(*) FROM pragma_table_info('{self.table_name}') WHERE name = 'parent_id'") > 0
            if has_parent_id_col and where_field == 'id':
                self.db_connector.execute(f"""
                    UPDATE `{self.table_name}`
                    SET parent_id = (SELECT parent_id FROM `{self.table_name}` WHERE id = ?)
                    WHERE parent_id = ?
                """, (key, key))
            self.db_connector.execute(f"DELETE FROM `{self.table_name}` WHERE `{where_field}` = ?", (key,))
            self.load()

        except Exception as e:
            display_message(
                message=f'Item could not be deleted:\n' + str(e),
                icon=QMessageBox.Warning,
            )
            return

        self.signals.changed.emit()

    def save(self):
        pass

    def scope_filter(self):
        """SQL condition and params limiting rows to this manager's `kind`,
        for managers sharing a table (e.g. agents and contacts)."""
        kind = self.default_fields.get('kind')
        if kind is None:
            return '', ()
        return ' AND `kind` = ?', (kind,)

    def get_row(self, id):
        scope_sql, scope_params = self.scope_filter()
        row = self.db_connector.get_results(
            f"SELECT `id`, `name`, `config`, `folder_id` FROM `{self.table_name}` WHERE `id` = ?{scope_sql}",
            (id, *scope_params),
        )
        if not row:
            raise ValueError(f'No item with id {id}')
        item = dict(zip(('id', 'name', 'config', 'folder_id'), row[0]))
        item['config'] = json.loads(item['config'])
        return item

    @staticmethod
    def parse_config_arg(config):
        parsed = json.loads(config) if config else {}
        if not isinstance(parsed, dict):
            raise ValueError('config must be a JSON object')
        return parsed

    @llm_tool(
        name='list',
        description='List items as JSON, without their config',
        params={
            'search': 'Only items whose name contains this text',
            'folder_id': 'Only items in this folder',
        },
    )
    def list_items(self, search: str = '', folder_id: int = None):
        scope_sql, params = self.scope_filter()
        where = f'`name` LIKE ?{scope_sql}'
        params = (f'%{search}%', *params)
        if folder_id is not None:
            where += ' AND `folder_id` = ?'
            params += (folder_id,)
        rows = self.db_connector.get_results(
            f"SELECT `id`, `name`, `folder_id` FROM `{self.table_name}` WHERE {where} ORDER BY `name`",
            params,
        )
        return json.dumps([dict(zip(('id', 'name', 'folder_id'), row)) for row in rows])

    @llm_tool(
        name='get',
        description='Get an item with its config as JSON',
        params={'id': 'Id of the item'},
    )
    def get_item(self, id: int):
        return json.dumps(self.get_row(id))

    @llm_tool(
        name='add',
        description='Add an item, returns its id',
        params={
            'name': 'Name of the new item',
            'config': 'JSON object of config values, merged onto the defaults',
            'folder_id': 'Folder to add the item to',
        },
    )
    def add_item(self, name: str, config: str = '{}', folder_id: int = None):
        merged = {**self.default_fields.get('config', {}), **self.parse_config_arg(config)}
        item_id = self.add(name, config=merged, folder_id=folder_id)
        if item_id is None:
            raise ValueError(f'Could not add {name!r}, it may already exist')
        return json.dumps({'id': item_id})

    @llm_tool(
        name='update',
        description='Update an item\'s name and/or config, returns the '
                    'saved item with its config as JSON',
        params={
            'id': 'Id of the item',
            'name': 'New name',
            'config': 'JSON object of config values to merge into the '
                      'existing config, a null value removes the key',
        },
    )
    def update_item(self, id: int, name: str = None, config: str = None):
        item = self.get_row(id)
        merged = {**item['config'], **self.parse_config_arg(config)}
        new_config = {key: value for key, value in merged.items() if value is not None}
        self.db_connector.execute(
            f"UPDATE `{self.table_name}` SET `name` = ?, `config` = ? WHERE `id` = ?",
            (name or item['name'], json.dumps(new_config), id),
        )
        from gui.gui_utils.helpers import auto_bake_table_item
        auto_bake_table_item(self.table_name, id)
        self.load()
        self.signals.changed.emit()
        return json.dumps(self.get_row(id))

    @llm_tool(
        name='delete',
        description='Delete an item, its children are moved to its parent',
        params={'id': 'Id of the item'},
        confirm=True,
    )
    def delete_item(self, id: int):
        self.get_row(id)
        has_locked_col = self.db_connector.get_scalar(f"SELECT COUNT(*) FROM pragma_table_info('{self.table_name}') WHERE name = 'locked'") > 0
        if has_locked_col and self.db_connector.get_scalar(f"SELECT locked FROM `{self.table_name}` WHERE id = ?", (id,)) == 1:
            raise ValueError('Item is locked')
        self.delete(id)

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


def snake_class_name(name):
    """`ConfigDBTree` -> `config_db_tree`, `Project_File_Tree` -> `project_file_tree`."""
    return re.sub(r'(?<=[a-z0-9])(?=[A-Z])|(?<=[A-Z])(?=[A-Z][a-z])', '_', name).lower()


def readable_class_name(obj):
    return snake_class_name(type(obj).__name__).replace('_', ' ').capitalize()


def get_llm_tools(cls):
    """The `@llm_tool` methods available on cls. Names are prefixed with the
    defining class, unless that class is marked `_ap_llm_tool_root`."""
    tools = []
    attrs = [
        (attr, c) for c in reversed(cls.__mro__) for attr in vars(c)
        if next(o for o in cls.__mro__ if attr in vars(o)) is c
    ]
    for attr, owner in attrs:
        fn = getattr(cls, attr, None)
        meta = getattr(fn, '_ap_llm_tool', None)
        if not meta:
            continue
        is_root = vars(owner).get('_ap_llm_tool_root', False)
        tools.append({
            **meta,
            'name': meta['name'] if is_root else f"{snake_class_name(owner.__name__)}_{meta['name']}",
            'attr': attr,
            'fn': fn,
            'owner': owner,
            'is_root': is_root,
        })
    return tools


def llm_tool_params(tool):
    """The exposed signature parameters of a tool from `get_llm_tools`."""
    import inspect
    exposed = tool['params']
    return [
        param for param in list(inspect.signature(tool['fn']).parameters.values())[1:]
        if exposed is None or param.name in exposed
    ]


def format_llm_tools(obj, refs, tools=None):
    """The `Tools [wN]:` block listing the `@llm_tool` methods of obj's class,
    or the given tools. Appends obj to refs when any tool needs a widget
    reference."""
    if tools is None:
        tools = get_llm_tools(type(obj))
    if not tools:
        return ''
    header = 'Tools:'
    if not all(tool['is_root'] for tool in tools):
        refs.append(obj)
        header = f'Tools [w{len(refs)}]:'
    lines = [header]
    for tool in tools:
        args = []
        for param in llm_tool_params(tool):
            arg = param.name
            if param.annotation is not param.empty:
                arg += f': {getattr(param.annotation, "__name__", param.annotation)}'
            if param.default is not param.empty:
                arg += f' = {param.default!r}'
            args.append(arg)
        description = f" - {tool['description']}" if tool['description'] else ''
        lines.append(f"    - {tool['name']}({', '.join(args)}){description}")
    return '\n'.join(lines)


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
            **param,
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


# download_url_to_file moved to plugins.workflows.utils.download
# to keep the aiofiles/aiohttp deps inside the workflows plugin.


@contextmanager
def block_signals(*widgets, recurse_children=True, exclude=()):
    """Context manager to block signals for a widget and all its child pages, except `exclude`."""
    all_widgets = []
    original_states = []
    try:
        # Get all child pages - use more efficient method
        for widget in widgets:
            all_widgets.append(widget)
            if recurse_children:
                # Use Qt's built-in findChildren which is more efficient than our custom function
                children = widget.findChildren(QWidget)
                all_widgets.extend(c for c in children if c not in exclude)

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
    from gui.gui_utils.helpers import find_main
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
    return exec_non_modal(msg)


def exec_non_modal(dialog):
    """Like `dialog.exec()`, but non-modal, because some window managers
    hide the title bar buttons of modal dialogs."""
    dialog.setWindowModality(Qt.NonModal)
    loop = QEventLoop()
    dialog.finished.connect(loop.quit)
    dialog.show()
    mark_primary_buttons(dialog)
    loop.exec()
    return dialog.result()


def mark_primary_buttons(dialog):
    """Flags the accept buttons of a shown dialog's button boxes, for the
    stylesheet's `[primary="true"]` rules."""
    from gui.gui_utils.helpers import set_style_property
    for box in dialog.findChildren(QDialogButtonBox):
        for btn in box.buttons():
            role = box.buttonRole(btn)
            set_style_property(btn, 'primary', role in (
                QDialogButtonBox.AcceptRole, QDialogButtonBox.YesRole,
            ))


def get_text(parent, title, label, text=''):
    """Drop-in replacement for `QInputDialog.getText`, see `exec_non_modal`."""
    dialog = QInputDialog(parent)
    dialog.setWindowTitle(title)
    dialog.setLabelText(label)
    dialog.setTextValue(text)
    ok = exec_non_modal(dialog) == QDialog.Accepted
    return dialog.textValue(), ok


def apply_alpha_to_hex(hex_color, alpha):
    color = QColor(hex_color)
    color.setAlphaF(alpha)
    return color.name(QColor.HexArgb)


def blend_hex_colors(hex1, hex2, ratio=0.5):
    c1, c2 = QColor(hex1), QColor(hex2)
    r = int(c1.red() * (1 - ratio) + c2.red() * ratio)
    g = int(c1.green() * (1 - ratio) + c2.green() * ratio)
    b = int(c1.blue() * (1 - ratio) + c2.blue() * ratio)
    return QColor(r, g, b).name(QColor.HexRgb)


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
        from gui.gui_utils.helpers import colorize_pixmap

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
