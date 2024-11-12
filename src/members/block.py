import ast
from textwrap import dedent

import astor

from src.gui.config import ConfigFields
from src.gui.widgets import PythonHighlighter
from src.members.base import Member, LlmMember


class Block(Member):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.receivable_function = self.receive

    async def get_content(self, run_sub_blocks=True):  # todo dupe code 777
        from src.system.base import manager
        content = self.config.get('data', '')

        if run_sub_blocks:
            block_type = self.config.get('block_type', 'Text')
            nestable_block_types = ['Text', 'Prompt']
            if block_type in nestable_block_types:
                # # Check for circular references
                # if name in visited:
                #     raise RecursionError(f"Circular reference detected in blocks: {name}")
                # visited.add(name)
                content = manager.blocks.format_string(content, ref_workflow=self.workflow)  # additional_blocks=member_blocks_dict)

        return content  # manager.blocks.format_string(content, additional_blocks=member_blocks_dict)


class TextBlock(Block):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)

    async def receive(self):
        """The entry response method for the member."""
        content = await self.get_content()
        yield 'block', content
        self.workflow.save_message('block', content, self.full_member_id())  # , logging_obj)


class CodeBlock(Block):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)

    async def receive(self):
        """The entry response method for the member."""
        from src.system.base import manager
        env_name = self.config.get('environment', 'Local')
        if env_name is None:
            env_name = 'Local'  # todo
        environment = manager.environments.environments.get(env_name)

        lang = self.config.get('language', 'Python')
        code = await self.get_content(run_sub_blocks=False)
        venv_name = environment.config.get('venv', 'default')
        venv = manager.venvs.venvs.get(venv_name)

        if venv_name == 'default' or not venv.has_package('ipykernel'):
            print(f"WARNING: ipykernel not installed in venv `{venv_name}`, using default...")
            venv_path = None
        else:
            venv_path = venv.path

        params = self.workflow.params
        wrapped_code = self.wrap_code(lang, code, params)
        output = environment.run_code(lang, wrapped_code, venv_path)

        unique_str = '##%##@##!##%##@##!##'
        if unique_str in output:
            output = output.split(unique_str)[-1].strip()
        # try:
        #     oi_res = interpreter.computer.run(code_lang, content)
        #     output = next(r for r in oi_res if r['format'] == 'output').get('content', '')
        # except Exception as e:
        #     output = str(e)

        yield 'block', output

    def wrap_code(self, lang, code, params):
        if lang != 'Python':
            return code  # only wrap python for now

        tool_uuid = self.workflow.tool_uuid or ''
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
        return wrapped_code


class PromptBlock(LlmMember):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.receivable_function = self.receive
        self.model_config_key = 'prompt_model'
        self.tools_config_key = ''
        self.default_role = 'block'

    def get_content(self, run_sub_blocks=True):  # todo dupe code 777
        from src.system.base import manager
        content = self.config.get('data', '')

        if run_sub_blocks:
            block_type = self.config.get('block_type', 'Text')
            nestable_block_types = ['Text', 'Prompt']
            if block_type in nestable_block_types:
                content = manager.blocks.format_string(content, ref_workflow=self.workflow)

        return content

    def get_messages(self):  # todo
        return [{'role': 'user', 'content': self.get_content()}]


class TextBlockSettings(ConfigFields):
    def __init__(self, parent):
        super().__init__(parent=parent)
        self.schema.extend([
            {
                'text': 'Type',
                'key': 'block_type',
                'type': 'PluginComboBox',
                'plugin_type': 'Block',
                'allow_none': False,
                'width': 90,
                'default': 'Text',
                'row_key': 0,
            },
            {
                'text': 'Data',
                'type': str,
                'default': '',
                'num_lines': 2,
                'stretch_x': True,
                'stretch_y': True,
                'label_position': None,
            },
        ])


class CodeBlockSettings(ConfigFields):
    def __init__(self, parent):
        super().__init__(parent=parent)
        self.schema.extend([
            {
                'text': 'Type',
                'key': 'block_type',
                'type': 'PluginComboBox',
                'plugin_type': 'Block',
                'allow_none': False,
                'width': 90,
                'default': 'Text',
                'row_key': 0,
            },
            {
                'text': '',
                'key': 'environment',
                'type': 'EnvironmentComboBox',
                'width': 90,
                'default': 'Local',
                'row_key': 0,
            },
            {
                'text': 'Language',
                'type':
                ('AppleScript', 'HTML', 'JavaScript', 'Python', 'PowerShell', 'R', 'React', 'Ruby', 'Shell',),
                'width': 100,
                'tooltip': 'The language of the code to be passed to open interpreter',
                'label_position': None,
                'row_key': 0,
                'default': 'Python',
            },
            {
                'text': 'Data',
                'type': str,
                'default': '',
                'num_lines': 2,
                'stretch_x': True,
                'stretch_y': True,
                'highlighter': PythonHighlighter,
                'label_position': None,
            },
        ])


class PromptBlockSettings(ConfigFields):
    def __init__(self, parent):
        super().__init__(parent=parent)
        self.schema.extend([
            {
                'text': 'Type',
                'key': 'block_type',
                'type': 'PluginComboBox',
                'plugin_type': 'Block',
                'allow_none': False,
                'width': 90,
                'default': 'Text',
                'row_key': 0,
            },
            {
                'text': 'Model',
                'key': 'prompt_model',
                'type': 'ModelComboBox',
                'label_position': None,
                'default': 'default',
                'row_key': 0,
            },
            {
                'text': 'Data',
                'type': str,
                'default': '',
                'num_lines': 2,
                'stretch_x': True,
                'stretch_y': True,
                'label_position': None,
            },
        ])
