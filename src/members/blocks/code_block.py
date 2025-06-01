
import ast
import json
from textwrap import dedent

import astor

from src.members import Block
from src.utils.helpers import set_module_type


@set_module_type(module_type='Members', plugin='BLOCK', settings='code_block_settings')
class CodeBlock(Block):
    default_role = 'block'
    default_avatar = ':/resources/icon-code.png'
    default_name = 'Code'

    def __init__(self, **kwargs):
        super().__init__(**kwargs)

    async def receive(self):
        """The entry response method for the member."""
        from src.system import manager
        env_id = self.config.get('environment', None)
        # if env_id is None:
        #     # env_name = 'Local'  # todo

        environment_tup = manager.environments.environments.get(env_id, None)
        if environment_tup is None:
            environment_tup = manager.environments.get_env_from_name('Local')  # todo
        if environment_tup is None:
            raise Exception(f"Environment not found for block")

        name, environment = environment_tup

        lang = self.config.get('language', 'Python')
        code = self.get_content(run_sub_blocks=False)
        venv_name = environment.config.get('venv', 'default')
        venv = manager.venvs.venvs.get(venv_name)

        if venv_name == 'default' or not venv.has_package('ipykernel'):
            print(f"WARNING: ipykernel not installed in venv `{venv_name}`, using default...")
            venv_path = None
        else:
            venv_path = venv.path

        params = self.workflow.params

        if code.strip() == '':
            result = 'No code provided'
        else:
            try:
                wrapped_code = self.wrap_code(lang, code, params)
                result = environment.run_code(lang, wrapped_code, venv_path)
                unique_str = '##%##@##!##%##@##!##'
                if unique_str in result:
                    result = result.split(unique_str)[-1].strip()
            except Exception as e:
                result = json.dumps({'status': 'error', 'output': str(e)})

        try:
            code_response_json = json.loads(result)
            output = code_response_json['output'] or ''
            status = code_response_json['status']
        except Exception as e: # use current output as fallback, in case code is not wrapped
            output = result
            status = 'success'

        role = self.default_role if status == 'success' else 'error'
        yield role, output
        self.workflow.save_message(role, output, self.full_member_id())

        if status == 'error':
            raise Exception(result)

        # yield 'block', output
        # self.workflow.save_message('block', output, self.full_member_id())

    def wrap_code(self, lang, code, params=None):
        params = params or {}
        if lang != 'Python':
            return code  # only wrap python for now

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

        # define tool code wrapped in a function
        func_block = ast.FunctionDef(
            name='wrapped_method',
            args=ast.arguments(
                posonlyargs=[],
                args=[ast.arg(arg=param_name, annotation=None) for param_name in params.keys()],  # Create argument for each parameter
                kwonlyargs=[],
                kw_defaults=[],
                kwarg=None,
                defaults=[ast.Constant(value=None) for _ in params.keys()]  # Default values for each parameter
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

        try_block = ast.Try(
            body=[
                ast.Assign(
                    targets=[ast.Name(id='result', ctx=ast.Store())],
                    value=ast.Call(
                        func=ast.Name(id='wrapped_method', ctx=ast.Load()),
                        args=[],
                        keywords=[
                            ast.keyword(arg=k, value=ast.Subscript(
                                value=ast.Name(id='params', ctx=ast.Load()),
                                slice=ast.Constant(value=k)
                            )) for k in params.keys()
                        ]
                    )
                ),
                ast.Assign(
                    targets=[ast.Name(id='response', ctx=ast.Store())],
                    value=ast.Call(
                        func=ast.Name(id='json.dumps', ctx=ast.Load()),
                        args=[
                            ast.Dict(
                                keys=[ast.Str(s='status'), ast.Str(s='output')],
                                values=[
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
                                        keys=[ast.Str(s='status'), ast.Str(s='output')],
                                        values=[
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
        return wrapped_code