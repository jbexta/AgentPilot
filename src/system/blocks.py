import asyncio
import re

from PySide6.QtWidgets import QMessageBox

from src.utils.helpers import ManagerWorkflowController, receive_workflow, display_message


class BlockManager(ManagerWorkflowController):
    def __init__(self, parent):
        super().__init__(parent)
        self.parent = parent
        self.table_name = 'blocks'
        self.empty_config = {'_TYPE': 'block'}

        self.prompt_cache = {}  # dict((prompt, model_obj): response)

    async def receive_block(self, name, params=None):
        self.load()  # todo temp, find out why model_params getting reset
        wf_config = self[name]
        async for key, chunk in receive_workflow(wf_config, kind='BLOCK', params=params, chat_title=name, main=self.parent._main_gui):
            yield key, chunk

    async def compute_block_async(self, name, params=None):
        response = ''
        async for key, chunk in self.receive_block(name, params=params):
            response += chunk
        return response

    def compute_block(self, name, params=None):  # , visited=None, ):
        return asyncio.run(self.compute_block_async(name, params))

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

            member_blocks_dict = {member_placeholders[k].lower(): v for k, v in member_last_outputs.items() if v is not None}
            all_params = {**member_blocks_dict, **ref_workflow.params}

        if additional_blocks:
            all_params.update(additional_blocks)

        try:
            # Recursively process placeholders
            placeholders = re.findall(r'\{(.+?)\}', content)

            visited = set()

            # Process each placeholder  todo clean duplicate code
            for placeholder in placeholders:
                if placeholder in self:
                    replacement = self.compute_block(placeholder)
                    content = content.replace(f'{{{placeholder}}}', replacement)
                elif placeholder in all_params:
                    replacement = all_params[placeholder]
                    content = content.replace(f'{{{placeholder}}}', replacement)
                else:
                    # Leave content unchanged
                    pass

            # for key, text in all_params.items():
            #     content = content.replace(f'{{{key}}}', text)

            return content

        except RecursionError as e:
            display_message(self,
                message=str(e),
                icon=QMessageBox.Warning,
            )
            return content
