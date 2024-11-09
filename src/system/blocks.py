import asyncio
import json
import re

from PySide6.QtWidgets import QMessageBox

from src.members.workflow import Workflow
from src.utils import sql
from src.utils.helpers import display_messagebox, merge_config_into_workflow_config, receive_workflow


class BlockManager:
    def __init__(self, parent):
        self.parent = parent
        self.blocks = {}

        self.prompt_cache = {}  # dict((prompt, model_obj): response)

    def load(self):
        self.blocks = sql.get_results("""
            SELECT
                name,
                config
            FROM blocks""", return_type='dict')
        self.blocks = {k: json.loads(v) for k, v in self.blocks.items()}

    def to_dict(self):
        return self.blocks

    # async def receive_block(self, name, add_input=None):  # , visited=None, ):
    #     wf_config = merge_config_into_workflow_config(self.blocks[name])
    #     workflow = Workflow(config=wf_config, kind='BLOCK')
    #     if add_input is not None:
    #         nem = workflow.next_expected_member()
    #         if nem:
    #             if nem.config.get('_TYPE', 'agent') == 'user':
    #                 member_id = nem.member_id
    #                 workflow.save_message('user', add_input, member_id)
    #                 workflow.load()
    #
    #     try:
    #         async for key, chunk in workflow.run_member():
    #             yield key, chunk
    #     except StopIteration:
    #         raise Exception("Pausing nested workflows isn't implemented yet")

    async def compute_block_async(self, name, add_input=None):
        wf_config = self.blocks[name]
        chunks = []
        async for key, chunk in receive_workflow(wf_config, 'BLOCK', add_input):
            chunks.append(chunk)
        return ''.join(chunks)

    def compute_block(self, name, add_input=None):  # , visited=None, ):
        return asyncio.run(self.compute_block_async(name, add_input))

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
