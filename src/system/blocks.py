import asyncio
import json
import re

from PySide6.QtWidgets import QMessageBox

from src.utils import sql
from src.utils.helpers import display_messagebox, receive_workflow


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

    async def compute_block_async(self, name, add_input=None):
        wf_config = self.blocks[name]
        chunks = []
        async for key, chunk in receive_workflow(wf_config, 'BLOCK', add_input):
            chunks.append(chunk)
        return ''.join(chunks)

    def compute_block(self, name, add_input=None):  # , visited=None, ):
        return asyncio.run(self.compute_block_async(name, add_input))

    def format_string(self, content, ref_workflow=None, additional_blocks=None):  # , ref_config=None):
        all_params = {}

        if ref_workflow:
            members = ref_workflow.members
            member_names = {m_id: member.config.get('info.name', 'Assistant') for m_id, member in members.items()}
            member_placeholders = {
                m_id: member.config.get('group.output_placeholder', f'{member_names[m_id]}_{str(m_id)}')
                for m_id, member in members.items()}
            member_last_outputs = {member.member_id: member.last_output for k, member in ref_workflow.members.items()
                                   if member.last_output != ''}

            member_blocks_dict = {member_placeholders[k]: v for k, v in member_last_outputs.items() if v is not None}
            # params_dict = ref_workflow.params
            all_params = {**member_blocks_dict, **ref_workflow.params}

        if additional_blocks:
            all_params.update(additional_blocks)

        try:
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

            for key, text in all_params.items():
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
