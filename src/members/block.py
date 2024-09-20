import re
from src.gui.config import ConfigFields
from src.gui.widgets import PythonHighlighter
from src.members.base import Member

from src.plugins.openinterpreter.src import interpreter
from src.utils.helpers import convert_model_json_to_obj


class Block(Member):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        pass

    async def run_member(self):
        """The entry response method for the member."""
        async for key, chunk in self.compute():
            if self.workflow.stop_requested:
                self.workflow.stop_requested = False
                break
            self.main.new_sentence_signal.emit(key, self.full_member_id(), chunk)  # todo check if order of this is causing scroll issue

    async def get_content(self, run_sub_blocks=True):
        from src.system.base import manager
        content = self.config.get('data', '')
        if run_sub_blocks:
            block_type = self.config.get('block_type', 'Text')
            nestable_block_types = ['Text', 'Prompt', 'Metaprompt']
            if block_type in nestable_block_types:
                # # Check for circular references
                # if name in visited:
                #     raise RecursionError(f"Circular reference detected in blocks: {name}")
                # visited.add(name)

                # Recursively process placeholders
                placeholders = re.findall(r'\{(.+?)\}', content)

                # Process each placeholder
                for placeholder in placeholders:
                    if placeholder in manager.blocks.blocks:
                        replacement = self.compute_block(placeholder, visited.copy())
                        content = content.replace(f'{{{placeholder}}}', replacement)
                    # If placeholder doesn't exist, leave it as is

        return content


class TextBlock(Block):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        pass

    async def compute(self):
        """The entry response method for the member."""
        content = await self.get_content()
        self.workflow.save_message('block', content, self.full_member_id())  # , logging_obj)
        yield 'block', content


class CodeBlock(Block):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        pass

    async def compute(self):
        """The entry response method for the member."""
        code_lang = self.config.get('code_language', 'Python')
        content = await self.get_content(run_sub_blocks=False)
        try:
            oi_res = interpreter.computer.run(code_lang, content)
            output = next(r for r in oi_res if r['format'] == 'output').get('content', '')
        except Exception as e:
            output = str(e)
        yield 'block', output.strip()


class PromptBlock(Block):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        pass

    async def compute(self):
        """The entry response method for the member."""
        from src.system.base import manager
        model_json = self.config.get('prompt_model', manager.config.dict.get('system.default_chat_model', 'mistral/mistral-large-latest'))
        model_obj = convert_model_json_to_obj(model_json)

        messages = [{'role': 'user', 'content': await self.get_content()}]
        stream = self.stream(model=model_obj, messages=messages)
        role_responses = {}

        async for key, chunk in stream:
            if key not in role_responses:
                role_responses[key] = ''

            chunk = chunk or ''
            role_responses[key] += chunk
            yield key, chunk

        if 'api_key' in model_obj['model_params']:
            model_obj['model_params'].pop('api_key')

        logging_obj = {
            'context_id': self.workflow.context_id,
            'member_id': self.full_member_id(),
            'model': model_obj,
            'messages': messages,
            'role_responses': role_responses,
        }

        for key, response in role_responses.items():
            if response != '':
                self.workflow.save_message(key, response, self.full_member_id(), logging_obj)

    async def stream(self, model, messages):
        stream = await self.main.system.providers.run_model(
            model_obj=model,
            messages=messages,
        )

        async for resp in stream:
            delta = resp.choices[0].get('delta', {})
            if not delta:
                continue
            content = delta.get('content', '')
            yield 'block', content or ''


class TextBlockSettings(ConfigFields):
    def __init__(self, parent):
        super().__init__(parent=parent)
        self.schema.extend([
            {
                'text': 'Block type',
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
                'text': 'Block type',
                'type': 'PluginComboBox',
                'plugin_type': 'Block',
                'allow_none': False,
                'width': 90,
                'default': 'Text',
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
                'text': 'Block type',
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
