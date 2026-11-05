import asyncio
import json

from utils import sql
from utils.helpers import params_to_schema, get_llm_tools, llm_tool_params
from plugins.workflows.utils.workflows import receive_workflow
from utils.helpers import BaseManager

APP_FOLDER = 'Application'


class ToolManager(BaseManager):
    def __init__(self, system):
        super().__init__(
            system,
            table_name='tools',
            load_columns=['uuid', 'config'],
            default_fields={
                'config': {'_TYPE': 'code'}
            },
            config_is_workflow=True,
        )
        self.tool_id_names = {}

    def load(self):
        tools_data = sql.get_results("SELECT name, config FROM tools", return_type='dict')
        self.tool_id_names = sql.get_results("SELECT uuid, name FROM tools", return_type='dict')
        self.clear()
        self.update({name: json.loads(config) for name, config in tools_data.items()})

    def get_method_tools(self):
        """Collect `@llm_tool` decorated methods from every imported app
        class, keyed by the module they're defined in (their `kind`), plus
        the tools of every loaded manager."""
        import sys as _sys
        import inspect
        tools = self.get_manager_tools()
        roots = ('core', 'gui', 'plugins', 'utils')
        for mod_name, module in list(_sys.modules.items()):
            if module is None or mod_name.partition('.')[0] not in roots:
                continue
            kind = mod_name.rpartition('.')[2]
            for obj in list(vars(module).values()):
                if not inspect.isclass(obj) or obj.__module__ != mod_name:
                    continue
                if issubclass(obj, BaseManager):
                    continue
                for tool in get_llm_tools(obj):
                    if tool['owner'] is not obj:
                        continue
                    method = tool['fn'].__qualname__
                    tools.append({
                        **tool,
                        'kind': kind,
                        'method': method,
                        'id': f'method:{kind}.{method}',
                        'folder': f'{APP_FOLDER}/{kind}',
                    })
        return tools

    def get_manager_tools(self):
        """`@llm_tool` methods of each loaded manager instance, named after
        the manager (e.g. `blocks_add`). Generic CRUD tools are only
        included for managers with a table and `llm_crud` enabled."""
        tools = []
        for key, manager in vars(self.system).items():
            if key.startswith('_') or not isinstance(manager, BaseManager):
                continue
            has_crud = manager.table_name and manager.llm_crud
            for tool in get_llm_tools(type(manager)):
                if tool['owner'] is BaseManager and not has_crud:
                    continue
                tool_name = tool['fn']._ap_llm_tool['name']
                tools.append({
                    **tool,
                    'name': f'{key}_{tool_name}',
                    'is_root': True,
                    'manager': key,
                    'kind': 'managers',
                    'method': tool['fn'].__qualname__,
                    'id': f'method:managers.{key}.{tool_name}',
                    'folder': f'{APP_FOLDER}/managers/{key}',
                })
        return tools

    def entry_name(self, entry_id):
        """Display name of a non-workflow entry in an agent's tool list."""
        if entry_id.startswith('folder:'):
            folder = entry_id.removeprefix('folder:')
            if folder.isdigit():
                return sql.get_scalar("SELECT name FROM folders WHERE id = ?", (int(folder),))
            return folder
        return next((t['name'] for t in self.get_method_tools() if t['id'] == entry_id), None)

    def resolve_selection(self, entry_ids):
        """Expand an agent's tool list into (workflow tool uuids, method tools).
        Folders are expanded recursively at call time."""
        method_tools = self.get_method_tools()
        uuids, methods = [], []
        for entry_id in entry_ids:
            if entry_id.startswith('method:'):
                methods += [t for t in method_tools if t['id'] == entry_id]
            elif entry_id.startswith('folder:'):
                folder = entry_id.removeprefix('folder:')
                if folder.isdigit():
                    uuids += sql.get_results("""
                        WITH RECURSIVE sub(id) AS (
                            SELECT ?
                            UNION ALL
                            SELECT f.id FROM folders f JOIN sub ON f.parent_id = sub.id
                        )
                        SELECT uuid FROM tools WHERE folder_id IN (SELECT id FROM sub)
                    """, (int(folder),), return_type='list')
                else:
                    methods += [
                        t for t in method_tools
                        if t['folder'] == folder or t['folder'].startswith(folder + '/')
                    ]
            else:
                uuids.append(entry_id)
        unique_methods = list({t['id']: t for t in methods}.values())
        return list(dict.fromkeys(uuids)), unique_methods

    def method_tool_schema(self, tool):
        """JSON schema of a method tool's parameters, plus its `widget` reference."""
        json_types = {str: 'string', int: 'integer', bool: 'boolean', float: 'number'}
        properties, required = {}, []
        if not tool['is_root']:
            properties['widget'] = {
                'type': 'string',
                'description': 'Widget reference from view_ui, e.g. w3',
            }
            required.append('widget')
        descriptions = tool['params'] or {}
        for param in llm_tool_params(tool):
            prop = {'type': json_types.get(param.annotation, 'string')}
            if param.name in descriptions:
                prop['description'] = descriptions[param.name]
            properties[param.name] = prop
            if param.default is param.empty:
                required.append(param.name)
        return {'type': 'object', 'properties': properties, 'required': required}

    async def call_method_tool(self, tool, args, refs):
        """Run a method tool on a widget in the current view, or on its
        manager, awaiting async tools. `refs` is the caller's own reference
        record from its latest view_ui."""
        import inspect
        args = dict(args)
        main_pages = self.system._main_gui.main_pages
        try:
            if tool.get('manager'):
                widget = getattr(self.system, tool['manager'])
            elif tool['is_root']:
                widget = main_pages
            else:
                ref = args.pop('widget', '')
                index = int(ref[1:]) - 1 if ref[1:].isdigit() else -1
                if not 0 <= index < len(refs):
                    raise ValueError(f'Unknown widget reference {ref!r}, call view_ui again')
                widget = refs[index]
                in_view = []
                main_pages.get_agent_visualisation(in_view)
                if not any(w is widget for w in in_view):
                    raise ValueError(f'Widget {ref} is no longer in view, call view_ui again')
                if not isinstance(widget, tool['owner']):
                    raise ValueError(f"Widget {ref} has no tool {tool['name']}")
            if 'refs' in inspect.signature(tool['fn']).parameters:
                refs.clear()
                args['refs'] = refs
            result = getattr(widget, tool['attr'])(**args)
            if inspect.isawaitable(result):
                result = await result
            output, status = ('Done' if result is None else str(result)), 'success'
        except Exception as e:
            output, status = str(e), 'error'
        return json.dumps({'output': output, 'status': status})

    def get_param_schema(self, tool_uuid):
        tool_name = self.tool_id_names.get(tool_uuid)
        tool_config = self.get(tool_name)
        tool_params = tool_config.get('params', [])
        return params_to_schema(tool_params)

    async def compute_tool_async(self, tool_uuid, params=None):
        tool_name = self.tool_id_names.get(tool_uuid)
        tool_config = self.get(tool_name)
        output = ''
        status = 'success'
        async for key, chunk in receive_workflow(tool_config, 'TOOL', params, tool_uuid, main=self.system._main_gui):
            output += chunk
            if key == 'error':
                status = 'error'
        return json.dumps({'output': output, 'status': status, 'tool_uuid': tool_uuid})

    def compute_tool(self, tool_uuid, params=None):  # , visited=None, ):
        # return asyncio.run(self.receive_block(name, add_input))
        return asyncio.run(self.compute_tool_async(tool_uuid, params))