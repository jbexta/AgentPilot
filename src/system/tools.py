import ast
import json
from textwrap import dedent

import astor

from src.utils import sql


class ToolManager:
    def __init__(self, parent):
        self.system = parent
        self.tools = {}
        self.tool_id_names = {}  # todo clean

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

        schema = [
            {
                'key': param.get('name', ''),
                'text': param.get('name', '').capitalize().replace('_', ' '),
                'type': type_convs.get(param.get('type'), str),
                'default': param.get('default', type_defaults.get(param.get('type'), '')),
                'minimum': 99999,
                'maximum': -99999,
                'step': 1,
            }
            for param in tool_params
        ]
        return schema

    def execute(self, tool_uuid, params):
        tool_name = self.tool_id_names.get(tool_uuid)
        tool_config = self.tools.get(tool_name)

        env_name = tool_config.get('environment', 'Local')
        if env_name is None:
            env_name = 'Local'  # todo
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

        import_block = ast.Import(names=[
            ast.alias(name='json', asname=None),
            ast.alias(name='os', asname=None),
        ])

        # # define helper function to get os.environ, if doesn't exist raise an error
        helpers_ast = ast.parse(dedent("""
            def get_os_environ(key):
                val = os.environ.get(key)
                if val is None:
                    raise Exception(f"No environment variable found for `{key}`")
                return val
        """))

        # get_os_environ = ast.FunctionDef(
        #     name='get_os_environ',
        #     args=ast.arguments(
        #         posonlyargs=[],  # No positional-only arguments
        #         args=[ast.arg(arg='key', annotation=None)],  # Accept key
        #         kwonlyargs=[], kw_defaults=[], kwarg=None, defaults=[]
        #     ),
        #     body=[
        #         ast.Assign(
        #             targets=[ast.Name(id='val', ctx=ast.Store())],
        #             value=ast.Call(
        #                 func=ast.Attribute(
        #                     value=ast.Name(id='os', ctx=ast.Load()),
        #                     attr='get',
        #                     ctx=ast.Load()
        #                 ),
        #                 args=[ast.Name(id='key', ctx=ast.Load())],
        #                 keywords=[]
        #             )
        #         ),
        #         ast.If(
        #             test=ast.Compare(
        #                 left=ast.Name(id='val', ctx=ast.Load()),
        #                 ops=[ast.Is()],
        #                 comparators=[ast.NameConstant(value=None)]
        #             ),
        #             body=[
        #                 ast.Raise(
        #                     exc=ast.Call(
        #                         func=ast.Name(id='KeyError', ctx=ast.Load()),
        #                         args=[ast.Name(id='key', ctx=ast.Load())],
        #                         keywords=[]
        #                     )
        #                 )
        #             ],
        #             orelse=[]
        #         ),
        #         ast.Return(value=ast.Name(id='val', ctx=ast.Load()))
        #     ],
        #     decorator_list=[]
        # )

        # define tool code wrapped in a function
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
                                keys=[ast.Str(s='tool_uuid'), ast.Str(s='status'), ast.Str(s='result')],
                                values=[
                                    ast.Str(s=tool_uuid),
                                    ast.Str(s='success'),
                                    ast.Name(id='result', ctx=ast.Load())
                                ]
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
                                        keys=[ast.Str(s='tool_uuid'), ast.Str(s='status'), ast.Str(s='result')],
                                        values=[
                                            ast.Str(s=tool_uuid),
                                            ast.Str(s='error'),
                                            ast.Call(
                                                func=ast.Name(id='str', ctx=ast.Load()),
                                                args=[ast.Name(id='e', ctx=ast.Load())],
                                                keywords=[]
                                            )
                                        ]
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
        final_ast = ast.Module(body=[import_block, helpers_ast, func_block, define_params, try_block, print_response])

        # Convert the AST back to a code string
        wrapped_code = astor.to_source(final_ast)
        r = environment.run_code(lang, wrapped_code, venv_path=venv_path)

        if unique_str in r:
            r = r.split(unique_str)[-1].strip()
        return r
