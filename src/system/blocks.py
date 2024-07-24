import json
import string

from src.plugins.openinterpreter.src import interpreter
# import interpreter

from src.utils import sql, helpers
from src.utils.llm import get_scalar


class BlockManager:
    def __init__(self, parent):
        self.parent = parent
        self.blocks = {}

    def load(self):
        self.blocks = sql.get_results("""
            SELECT
                name,
                config -- json_extract(config, '$.data')
            FROM blocks""", return_type='dict')
        self.blocks = {k: json.loads(v) for k, v in self.blocks.items()}

    def to_dict(self):
        return self.blocks

    def compute_block(self, name, source_text=''):
        config = self.blocks.get(name, None)
        if config is None:
            return None
        block_type = config.get('block_type', 'Text')
        block_data = config.get('data', '')

        if block_type == 'Text':
            return block_data
        elif block_type == 'Prompt':
            # source_Text can contain the block name in curly braces {name}. check if it contains it
            in_source = '{' + name + '}' in source_text
            if not in_source:
                return None
            model_name = config.get('prompt_model', '')
            model_obj = (model_name, self.parent.models.get_llm_parameters(model_name))
            r = get_scalar(prompt=block_data, model_obj=model_obj)
            return r
        elif block_type == 'Code':
            code_lang = config.get('code_language', 'Python')
            try:
                oi_res = interpreter.computer.run(code_lang, block_data)
                output = next(r for r in oi_res if r['format'] == 'output').get('content', '')
            except Exception as e:
                output = str(e)
            return output.strip()

    def format_string(self, source_text, additional_blocks=None, ref_config=None):
        if additional_blocks is None:
            additional_blocks = {}
        if ref_config is None:
            ref_config = {}

        computed_blocks_dict = {k: self.compute_block(k, source_text=source_text)
                                for k in self.blocks.keys()}

        blocks_dict = helpers.SafeDict({**additional_blocks, **computed_blocks_dict})
        blocks_dict['agent_name'] = ref_config.get('info.name', 'Assistant')
        blocks_dict['char_name'] = ref_config.get('info.name', 'Assistant')

        formatted_string = string.Formatter().vformat(
            source_text, (), blocks_dict,
        )
        return formatted_string
