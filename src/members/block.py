import re
from src.gui.config import ConfigFields
from src.gui.widgets import PythonHighlighter
from src.members.base import Member

from src.plugins.openinterpreter.src import interpreter


class Block(Member):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        pass

    async def run_member(self):
        """The entry response method for the member."""
        async for key, chunk in self.compute():  # stream=True):
            if self.workflow.stop_requested:
                self.workflow.stop_requested = False
                break
            self.main.new_sentence_signal.emit(key, self.member_id, chunk)  # todo check if order of this is causing scroll issue
        # from src.utils.helpers import convert_model_json_to_obj
        # # if visited is None:  todo reimplement
        # #     visited = set()
        # #
        # # nestable_block_types = ['Text', 'Prompt', 'Metaprompt']
        # # if block_type in nestable_block_types:
        # #     # Check for circular references
        # #     if name in visited:
        # #         raise RecursionError(f"Circular reference detected in blocks: {name}")
        # #     visited.add(name)
        # #
        # #     # Recursively process placeholders
        # #     placeholders = re.findall(r'\{(.+?)\}', content)
        # #
        # #     # Process each placeholder
        # #     for placeholder in placeholders:
        # #         if placeholder in self.blocks:
        # #             replacement = self.compute_block(placeholder, visited.copy())
        # #             content = content.replace(f'{{{placeholder}}}', replacement)
        # #         # If placeholder doesn't exist, leave it as is
        #
        # if block_type == 'Text':
        #     return content  # self.format_string(content, visited)  # recursion happens here
        #
        # elif block_type == 'Prompt' or block_type == 'Metaprompt':
        #     from src.system.base import manager
        #     # # source_Text can contain the block name in curly braces {name}. check if it contains it
        #     # in_source = '{' + name + '}' in source_text
        #     # if not in_source:
        #     #     return None
        #     model = config.get('prompt_model', '')
        #     # model_params = self.parent.providers.get_model_parameters(model)
        #     # model_obj = (model_name, model_params)
        #     model_obj = convert_model_json_to_obj(model)
        #     # model_name = model_obj['model_name']
        #     model_params = model_obj.get('model_config', {})
        #     flat_model_obj = json.dumps((model, model_params))
        #     cache_key = (content, flat_model_obj)
        #     if cache_key in self.prompt_cache.keys():
        #         return self.prompt_cache[cache_key]
        #     else:
        #         r = manager.providers.get_scalar(prompt=content, model_obj=model_obj)
        #         self.prompt_cache[cache_key] = r
        #         return r
        #
        # elif block_type == 'Code':
        #     code_lang = config.get('code_language', 'Python')
        #     try:
        #         oi_res = interpreter.computer.run(code_lang, content)
        #         output = next(r for r in oi_res if r['format'] == 'output').get('content', '')
        #     except Exception as e:
        #         output = str(e)
        #     return output.strip()
        #
        # else:
        #     raise NotImplementedError(f'Block type {block_type} not implemented')

    async def get_content(self):
        content = self.config.get('data', '')
        return content
        # block_type = self.config.get('block_type', 'Text')
        # nestable_block_types = ['Text', 'Prompt', 'Metaprompt']
        # if block_type in nestable_block_types:
        #     # Check for circular references
        #     if name in visited:
        #         raise RecursionError(f"Circular reference detected in blocks: {name}")
        #     visited.add(name)
        #
        #     # Recursively process placeholders
        #     placeholders = re.findall(r'\{(.+?)\}', content)
        #
        #     # Process each placeholder
        #     for placeholder in placeholders:
        #         if placeholder in self.blocks:
        #             replacement = self.compute_block(placeholder, visited.copy())
        #             content = content.replace(f'{{{placeholder}}}', replacement)
        #         # If placeholder doesn't exist, leave it as is


class TextBlock(Block):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        pass

    async def compute(self):
        """The entry response method for the member."""
        content = await self.get_content()
        self.workflow.save_message('block', content, self.member_id)  # , logging_obj)
        yield 'block', content


class CodeBlock(Block):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        pass

    async def compute(self):
        """The entry response method for the member."""
        code_lang = self.config.get('code_language', 'Python')
        content = await self.get_content()
        try:
            oi_res = interpreter.computer.run(code_lang, content)
            output = next(r for r in oi_res if r['format'] == 'output').get('content', '')
        except Exception as e:
            output = str(e)
        return output.strip()


class PromptBlock(Block):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        pass

    async def compute(self):
        """The entry response method for the member."""
        from src.system.base import manager
        # # source_Text can contain the block name in curly braces {name}. check if it contains it
        # in_source = '{' + name + '}' in source_text
        # if not in_source:
        #     return None
        model = config.get('prompt_model', '')
        # model_params = self.parent.providers.get_model_parameters(model)
        # model_obj = (model_name, model_params)
        model_obj = convert_model_json_to_obj(model)
        # model_name = model_obj['model_name']
        model_params = model_obj.get('model_config', {})
        flat_model_obj = json.dumps((model, model_params))
        cache_key = (content, flat_model_obj)
        if cache_key in self.prompt_cache.keys():
            return self.prompt_cache[cache_key]
        else:
            r = manager.providers.get_scalar(prompt=content, model_obj=model_obj)
            self.prompt_cache[cache_key] = r
            return r


# class BlockSettings(ConfigFields):
#     def __init__(self, parent):
#         self.member_type = 'block'
#         super().__init__(parent=parent)
#         self.schema = [
#             {
#                 'text': 'Type',
#                 'key': 'block_type',
#                 'type': ('Text', 'Prompt', 'Code', 'Metaprompt'),
#                 'width': 100,
#                 'default': 'Text',
#                 'row_key': 0,
#             },
#             {
#                 'text': 'Model',
#                 'key': 'prompt_model',
#                 'type': 'ModelComboBox',
#                 'label_position': None,
#                 'default': 'default',
#                 'row_key': 0,
#             },
#             {
#                 'text': 'Language',
#                 'type':
#                 ('AppleScript', 'HTML', 'JavaScript', 'Python', 'PowerShell', 'R', 'React', 'Ruby', 'Shell',),
#                 'width': 100,
#                 'tooltip': 'The language of the code, to be passed to open interpreter',
#                 'label_position': None,
#                 'row_key': 0,
#                 'default': 'Python',
#             },
#             {
#                 'text': 'Data',
#                 'type': str,
#                 'default': '',
#                 'num_lines': 23,
#                 'stretch_x': True,
#                 # 'stretch_y': True,
#                 'label_position': None,
#                 # 'exec_type_field': 'block_type',
#                 # 'lang_field': 'language',
#                 # 'model_field': 'prompt_model',
#             },
#         ]


class TextBlockSettings(ConfigFields):
    def __init__(self, parent):
        super().__init__(parent=parent)
        self.schema.extend([
            {
                'text': 'Block type',
                'type': 'PluginComboBox',
                'plugin_type': 'Block',
                'allow_none': False,
                'default': 'Text',
                'row_key': 0,
            },
            {
                'text': 'Data',
                'type': str,
                'default': '',
                'num_lines': 23,
                'stretch_x': True,
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
                'num_lines': 23,
                'stretch_x': True,
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
                'num_lines': 23,
                'stretch_x': True,
                'label_position': None,
            },
        ])