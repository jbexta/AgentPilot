import json
import re
import string

from PySide6.QtWidgets import QMessageBox

from src.plugins.openinterpreter.src import interpreter
# import interpreter

from src.utils import sql, helpers
from src.utils.helpers import display_messagebox


# from src.utils.helpers import SafeFormatter
# from src.utils.llm import get_scalar


class BlockManager:
    def __init__(self, parent):
        self.parent = parent
        self.blocks = {}

        self.prompt_cache = {}  # dict((prompt, model_obj): response)

    def load(self):
        self.blocks = sql.get_results("""
            SELECT
                name,
                config -- json_extract(config, '$.data')
            FROM blocks""", return_type='dict')
        self.blocks = {k: json.loads(v) for k, v in self.blocks.items()}

    def to_dict(self):
        return self.blocks

    def compute_block(self, name, visited=None):  # , source_text=''):
        from src.utils.helpers import convert_model_json_to_obj
        config = self.blocks.get(name, None)
        if config is None:
            return None
        block_type = config.get('block_type', 'Text')
        content = config.get('data', '')

        if visited is None:
            visited = set()

        nestable_block_types = ['Text', 'Prompt', 'Metaprompt']
        if block_type in nestable_block_types:
            # Check for circular references
            if name in visited:
                raise RecursionError(f"Circular reference detected in blocks: {name}")
            visited.add(name)

            # Recursively process placeholders
            placeholders = re.findall(r'\{(.+?)\}', content)

            # Process each placeholder
            for placeholder in placeholders:
                if placeholder in self.blocks:
                    replacement = self.compute_block(placeholder, visited.copy())
                    content = content.replace(f'{{{placeholder}}}', replacement)
                # If placeholder doesn't exist, leave it as is

        if block_type == 'Text':
            return content  # self.format_string(content, visited)  # recursion happens here

        elif block_type == 'Prompt' or block_type == 'Metaprompt':
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

        elif block_type == 'Code':
            code_lang = config.get('code_language', 'Python')
            try:
                oi_res = interpreter.computer.run(code_lang, content)
                output = next(r for r in oi_res if r['format'] == 'output').get('content', '')
            except Exception as e:
                output = str(e)
            return output.strip()

        else:
            raise NotImplementedError(f'Block type {block_type} not implemented')

    def format_string(self, content, additional_blocks=None):  # , ref_config=None):
        try:
            if not additional_blocks:
                additional_blocks = {}
            # Recursively process placeholders
            placeholders = re.findall(r'\{(.+?)\}', content)

            visited = set()

            # Process each placeholder  todo clean duplicate code
            for placeholder in placeholders:
                if placeholder in self.blocks:
                    replacement = self.compute_block(placeholder, visited.copy())
                    content = content.replace(f'{{{placeholder}}}', replacement)
                # If placeholder doesn't exist, leave it as is

            for key, text in additional_blocks.items():
                content = content.replace(f'{{{key}}}', text)

            return content

        except RecursionError as e:
            display_messagebox(
                icon=QMessageBox.Critical,
                text=str(e),
                title="Warning",
                buttons=QMessageBox.Ok,
            )
            return content

        # if additional_blocks is None:
        #     additional_blocks = {}
        # # if ref_config is None:
        # #     ref_config = {}
        #
        # computed_blocks_dict = {k: self.compute_block(k)  # , source_text=source_text)
        #                         for k in self.blocks.keys()
        #                         if '{' + k + '}' in source_text}
        #
        # blocks_dict = helpers.SafeDict({**additional_blocks, **computed_blocks_dict})
        # # blocks_dict['agent_name'] = ref_config.get('info.name', 'Assistant')
        # # blocks_dict['char_name'] = ref_config.get('info.name', 'Assistant')
        #
        # try:
        #     formatted_string = string.Formatter().vformat(
        #         source_text, (), blocks_dict,
        #     )
        # except Exception as e:
        #     formatted_string = source_text
        #
        # return formatted_string
