import asyncio
import json
import re
import string

from PySide6.QtWidgets import QMessageBox

from src.members.workflow import Workflow
from src.utils import sql, helpers
from src.utils.helpers import display_messagebox, merge_config_into_workflow_config


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
        pass  # change to run the workflow
        wf_config = merge_config_into_workflow_config(self.blocks[name])
        workflow = Workflow(config=wf_config, kind='BLOCK')
        coroutine = workflow.run_member()
        # run coroutine in loop
        event_loop = asyncio.get_event_loop()
        result = event_loop.run_until_complete(coroutine)
        is_paused = result
        if is_paused:
            raise Exception("Pausing nested workflows isn't implemented yet")
        final_msg = workflow.get_final_message()
        return '' if not final_msg else final_msg.content

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
