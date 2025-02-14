import asyncio
import json
import re

from PySide6.QtWidgets import QMessageBox

from src.utils import sql
from src.utils.helpers import receive_workflow, display_message


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

    async def receive_block(self, name, params=None):
        self.load()  # todo temp, find out why model_params getting reset
        wf_config = self.blocks[name]
        async for key, chunk in receive_workflow(wf_config, kind='BLOCK', params=params, chat_title=name, main=self.parent._main_gui):
            yield key, chunk

    async def compute_block_async(self, name, params=None):
        response = ''
        async for key, chunk in self.receive_block(name, params=params):
            response += chunk
        return response

    def compute_block(self, name, params=None):  # , visited=None, ):
        return asyncio.run(self.compute_block_async(name, params))
        # loop = asyncio.get_event_loop()
        # return loop.run_until_complete(self.compute_block_async(name, params))

    def format_string(self, content, ref_workflow=None, additional_blocks=None):  # , ref_config=None):
        all_params = {}

        if ref_workflow:
            members = ref_workflow.members
            member_names = {m_id: member.config.get('info.name', 'Assistant') for m_id, member in members.items()}
            member_placeholders = {
                m_id: member.config.get('group.output_placeholder', f'{member_names[m_id]}_{str(m_id)}') if member.config.get('_TYPE') != 'workflow' else member.config.get('config', {}).get('group.output_placeholder', f'{member_names[m_id]}_{str(m_id)}')
                for m_id, member in members.items()}  # todo !
            member_last_outputs = {member.member_id: member.last_output for k, member in ref_workflow.members.items()
                                   if member.last_output != ''}

            member_blocks_dict = {member_placeholders[k]: v for k, v in member_last_outputs.items() if v is not None}
            # params_dict = ref_workflow.params
            all_params = {**member_blocks_dict, **(ref_workflow.params or {})}

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
            display_message(self,
                message=str(e),
                icon=QMessageBox.Warning,
            )
            return content
