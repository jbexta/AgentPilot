import asyncio
import json
import re

from PySide6.QtWidgets import QMessageBox

from src.members.workflow import Workflow
from src.utils import sql
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

    async def receive_block(self, name, add_input=None):  # , visited=None, ):
        wf_config = merge_config_into_workflow_config(self.blocks[name])
        workflow = Workflow(config=wf_config, kind='BLOCK')
        if add_input is not None:
            nem = workflow.next_expected_member()
            if nem:
                if nem.config.get('_TYPE', 'agent') == 'user':
                    member_id = nem.member_id
                    workflow.save_message('user', add_input, member_id)
                    workflow.load()
        # chunks = []
        try:
            async for key, chunk in workflow.run_member():
                yield key, chunk
                # chunks.append(chunk)
        except StopIteration:
            raise Exception("Pausing nested workflows isn't implemented yet")
        # return ''.join(chunks)

        # # run coroutine in loop
        # # event_loop = asyncio.get_event_loop()
        # # result = event_loop.run_until_complete(coroutine)
        # is_paused = result
        # if is_paused:
        #     raise Exception("Pausing nested workflows isn't implemented yet")
        # final_msg = workflow.get_final_message()
        # return '' if not final_msg else final_msg.content

    # def consume_block(self, name, add_input=None):
    #     chunks = []
    #     for key, chunk in self.receive_block(name, add_input):
    #         chunks.append(chunk)
    #     return ''.join(chunks)

    async def return_block(self, name, add_input=None):
        chunks = []
        async for key, chunk in self.receive_block(name, add_input):
            chunks.append(chunk)
        return ''.join(chunks)

    def compute_block(self, name, add_input=None):  # , visited=None, ):
        # return asyncio.run(self.receive_block(name, add_input))
        return asyncio.run(self.return_block(name, add_input))

    # def compute_block_iter(self, name, add_input=None):  # , visited=None, ):
    #     yield from

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
                    if placeholder == 'ok':
                        pass
                    replacement = self.compute_block(placeholder)  # , visited.copy())
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
