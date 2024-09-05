import ast
import json

import astor

from src.utils import sql


class ToolManager:
    def __init__(self, parent):
        self.system = parent
        self.tools = {}
        self.tool_id_names = {}  # todo clean
        # self.executor = Executor(self)

    def load(self):
        tools_data = sql.get_results("SELECT name, config FROM tools", return_type='dict')
        self.tools = {name: json.loads(config) for name, config in tools_data.items()}
        self.tool_id_names = sql.get_results("SELECT uuid, name FROM tools", return_type='dict')

    def to_dict(self):
        return self.tools

    def get_param_schema(self, tool_uuid):
        tool_name = self.tool_id_names.get(tool_uuid)
        tool_config = self.tools.get(tool_name)
        tool_params = json.loads(tool_config.get('parameters.data', '[]'))
        types = {
            'String': str,
        }
        schema = [
            {
                'key': param.get('name', ''),
                'text': param.get('name', '').capitalize().replace('_', ' '),
                'type': types.get(param.get('type'), str),
                'default': param.get('default', ''),
            }
            for param in tool_params
        ]
        return schema

    def execute(self, tool_uuid, params):
        tool_name = self.tool_id_names.get(tool_uuid)
        tool_config = self.tools.get(tool_name)

        env_name = tool_config.get('environment', 'Local')
        environment = self.system.environments.environments.get(env_name)

        lang = tool_config.get('code.language', 'Python')
        code = tool_config.get('code.data', '')

        venv_name = environment.config.get('venv', 'default')
        venv = self.system.venvs.venvs.get(venv_name)

        if venv_name == 'default' or not venv.has_package('ipykernel'):
            print(f"WARNING: ipykernel not installed in venv `{venv_name}`, using default...")
            venv_path = None
        else:
            venv_path = venv.path

        # Parse the code template into an AST
        code_ast = ast.parse(code)

        import_block = ast.Import(names=[ast.alias(name='json', asname=None)])

        func_block = ast.FunctionDef(
            name='wrapped_method',
            args=ast.arguments(
                posonlyargs=[],  # No positional-only arguments
                args=[ast.arg(arg='**kwargs', annotation=None)],  # Accept **kwargs
                kwonlyargs=[], kw_defaults=[], kwarg=None, defaults=[]
            ),
            body=code_ast.body,
            decorator_list=[]
        )

        # define a params ast dict from params
        define_params = ast.Assign(
            targets=[ast.Name(id='params', ctx=ast.Store())],
            value=ast.Dict(
                keys=[ast.Str(s=k) for k in params.keys()],
                values=[ast.Str(s=v) for v in params.values()]
            )
        )

        # Create the try-except block
        try_block = ast.Try(
            body=[
                ast.Assign(
                    targets=[ast.Name(id='result', ctx=ast.Store())],
                    value=ast.Call(
                        func=ast.Name(id='wrapped_method', ctx=ast.Load()),
                        args=[],
                        keywords=[
                            ast.keyword(arg=None, value=ast.Name(id='params', ctx=ast.Load()))
                        ]
                    )
                ),
                ast.Assign(
                    targets=[ast.Name(id='response', ctx=ast.Store())],
                    value=ast.Call(
                        func=ast.Name(id='json.dumps', ctx=ast.Load()),
                        args=[
                            ast.Dict(
                                keys=[ast.Str(s='status'), ast.Str(s='result')],
                                values=[ast.Str(s='success'), ast.Name(id='result', ctx=ast.Load())]
                            )
                        ],
                        keywords=[]
                    )
                )
            ],
            handlers=[
                ast.ExceptHandler(
                    type=ast.Name(id='Exception', ctx=ast.Load()),
                    name='e',
                    body=[
                        ast.Assign(
                            targets=[ast.Name(id='response', ctx=ast.Store())],
                            value=ast.Call(
                                func=ast.Name(id='json.dumps', ctx=ast.Load()),
                                args=[
                                    ast.Dict(
                                        keys=[ast.Str(s='status'), ast.Str(s='result')],
                                        values=[ast.Str(s='error'), ast.Call(
                                            func=ast.Name(id='str', ctx=ast.Load()),
                                            args=[ast.Name(id='e', ctx=ast.Load())],
                                            keywords=[]
                                        )]
                                    )
                                ],
                                keywords=[]
                            )
                        )
                    ]
                )
            ],
            orelse=[],
            finalbody=[]
        )

        # Print the 'response' after the try block
        unique_str = '##%##@##!##%##@##!##'
        print_response = ast.Expr(
            value=ast.Call(
                func=ast.Name(id='print', ctx=ast.Load()),
                args=[
                    ast.BinOp(
                        left=ast.Str(s=unique_str),
                        op=ast.Add(),
                        right=ast.Call(
                            func=ast.Name(id='str', ctx=ast.Load()),
                            args=[ast.Name(id='response', ctx=ast.Load())],
                            keywords=[]
                        )
                    )
                ],
                keywords=[]
            )
        )

        # Construct the final AST
        final_ast = ast.Module(body=[import_block, func_block, define_params, try_block, print_response])

        # Convert the AST back to a code string
        wrapped_code = astor.to_source(final_ast)
        r = environment.run_code(lang, wrapped_code, venv_path=venv_path)

        if unique_str in r:
            r = r.split(unique_str)[-1].strip()
        return r
