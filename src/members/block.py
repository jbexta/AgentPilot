import json
from src.gui.config import ConfigFields
from src.gui.widgets import PythonHighlighter
from src.members.base import Member

from src.plugins.openinterpreter.src import interpreter
from src.utils.helpers import convert_model_json_to_obj
from src.utils.messages import CharProcessor


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
            yield key, chunk
            if self.main:
                self.main.new_sentence_signal.emit(key, self.full_member_id(), chunk)  # todo check if order of this is causing scroll issue

    async def get_content(self, run_sub_blocks=True):
        from src.system.base import manager
        content = self.config.get('data', '')
        members = self.workflow.members
        member_names = {m_id: member.config.get('info.name', 'Assistant') for m_id, member in members.items()}
        member_placeholders = {m_id: member.config.get('group.output_placeholder', f'{member_names[m_id]}_{str(m_id)}')
                               for m_id, member in members.items()}
        member_last_outputs = {member.member_id: member.last_output for k, member in self.workflow.members.items() if member.last_output != ''}
        member_blocks_dict = {member_placeholders[k]: v for k, v in member_last_outputs.items() if v is not None}

        if run_sub_blocks:
            block_type = self.config.get('block_type', 'Text')
            nestable_block_types = ['Text', 'Prompt', 'Metaprompt']
            if block_type in nestable_block_types:
                # # Check for circular references
                # if name in visited:
                #     raise RecursionError(f"Circular reference detected in blocks: {name}")
                # visited.add(name)
                content = manager.blocks.format_string(content, additional_blocks=member_blocks_dict)

        return manager.blocks.format_string(content, additional_blocks=member_blocks_dict)


class TextBlock(Block):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        pass

    async def compute(self):
        """The entry response method for the member."""
        content = await self.get_content()
        self.workflow.save_message('block', content, self.full_member_id())  # , logging_obj)
        self.last_output = content
        self.turn_output = content
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
        self.last_output = output
        self.turn_output = output
        yield 'block', output  # .strip()


class PromptBlock(Block):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        pass

    async def compute(self):
        """The entry response method for the member."""
        from src.system.base import manager
        model_json = self.config.get('prompt_model', manager.config.dict.get('system.default_chat_model', 'mistral/mistral-large-latest'))
        model_obj = convert_model_json_to_obj(model_json)

        xml_tag_roles = json.loads(model_obj.get('model_params', {}).get('xml_roles.data', '[]'))
        xml_tag_roles = {tag_dict['xml_tag'].lower(): tag_dict['map_to_role'] for tag_dict in xml_tag_roles}
        processor = CharProcessor(tag_roles=xml_tag_roles, default_role='block')  # {'instructions': 'instructions', 'potato': 'potato'})

        messages = [{'role': 'user', 'content': await self.get_content()}]
        stream = self.stream(model=model_obj, messages=messages)
        role_responses = {}

        async for key, chunk in stream:
            if key not in role_responses:
                role_responses[key] = ''

            chunk = chunk or ''

            async for role, content in processor.process_chunk(chunk):
                if role not in role_responses:
                    role_responses[role] = ''

                role_responses[role] += content
                yield role, content
        async for role, content in processor.process_chunk(None):
            role_responses[role] += content
            yield role, content  # todo to get last char

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
                if key in ('user', 'assistant', 'block'):
                    self.last_output = response
                    self.turn_output = response

    async def stream(self, model, messages):
        from src.system.base import manager
        stream = await manager.providers.run_model(
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
