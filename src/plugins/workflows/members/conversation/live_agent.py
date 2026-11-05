import asyncio
import json
import os
import uuid
from typing import Any

from gui import system
from plugins.workflows.members import LlmMember
from utils.filesystem import get_application_path
from utils.helpers import set_module_type, convert_model_json_to_obj


@set_module_type(module_type='Members', settings='live_agent_settings')
class LiveAgent(LlmMember):
    """A full duplex voice conversation with a GPT-Live model.

    Running the member opens the session and streams the microphone into it
    until the run is stopped. Both sides of the conversation are saved as
    message rows as they are spoken, so the transcript is the member's output.
    """
    default_role = 'assistant'
    avatar_key = 'avatar_path'
    default_avatar = ':/resources/icon-mic-member.png'
    name_key = 'name'
    default_name = 'Live Agent'
    workflow_insert_mode = 'list'
    conversational = True
    live_client = True
    OUTPUT = Any

    @property
    def INPUTS(self):
        return {
            'MESSAGE': Any,
            'CONFIG': {
                'live.sys_msg': str,
            },
        }

    @property
    def OUTPUTS(self):
        return {
            'OUTPUT': Any,
        }

    def __init__(self, **kwargs):
        super().__init__(**kwargs, model_config_key='live.model')
        self.name = self.config.get('name', self.default_name)
        self._row = {'role': None, 'id': None, 'text': ''}
        self._pcm = bytearray()
        self._backend_model = ''

    async def system_message(self, msgs_in_system=None, response_instruction='', msgs_in_system_len=0):
        builtin_blocks = {
            'char_name': self.name,
            'full_name': self.name,
            'response_type': 'response',
            'verb': '',
        }
        return await self.format_config_value('live.sys_msg', additional_blocks=builtin_blocks)

    def _live_config(self, model_obj):
        """Voice, delegation, backend model and api_key: the agent's model params,
        overridden by the Models page row (same precedence as run_model)."""
        model_key = (model_obj['provider'], model_obj['kind'], model_obj['_model_name'])
        return {**model_obj.get('model_params', {}), **system.manager.models.get(model_key, {})}

    def _delegation_config(self, cfg, system_msg):
        if cfg.get('delegation', 'Client') != 'Responses':
            return {'type': 'client'}
        backend = cfg.get('backend_model', '')
        if not backend:
            raise ValueError('Responses delegation requires a backend model.')
        return {
            'type': 'responses',
            'responses': {
                'model': convert_model_json_to_obj(backend)['_model_name'],
                'instructions': system_msg or '',
            },
        }

    async def session_params(self):
        """Everything needed to start, accept or attach a session for this agent."""
        model_obj = convert_model_json_to_obj(self.config.get(self.model_config_key))
        cfg = self._live_config(model_obj)
        system_msg = await self.system_message()
        self._backend_model = (cfg.get('backend_model')
                               or system.manager.config.get('system.default_chat_model', ''))
        return {
            'api_key': cfg.get('api_key'),
            'model_name': model_obj['_model_name'],
            'voice': cfg.get('voice', 'marin'),
            'instructions': system_msg or '',
            'delegation': self._delegation_config(cfg, system_msg),
        }

    async def receive(self):
        client = self.workflow.live_clients[self.member_id]
        params = await self.session_params()
        session_id, client.pending_session_id = client.pending_session_id, None
        await client.start(session_id=session_id, **params)
        self._row = {'role': None, 'id': None, 'text': ''}
        self._pcm = bytearray()
        try:
            while True:
                if self.workflow.stop_requested:
                    # self.workflow.stop_requested = False
                    break
                try:
                    tag, payload = await asyncio.wait_for(client.events.get(), timeout=0.5)
                except asyncio.TimeoutError:
                    continue
                if tag == 'transcript':
                    self._append('assistant', payload)
                elif tag == 'user_transcript':
                    self._append('user', payload)
                elif tag == 'audio':
                    self._pcm.extend(payload)
                    client.play(payload)
                elif tag == 'delegation':
                    task = asyncio.create_task(self._delegate(client, payload))
                    task.add_done_callback(self._report_task)
                elif tag == 'error':
                    print(f'GPT-Live error: {payload}')
                elif tag == 'closed':
                    break
        finally:
            await client.stop()
            self._flush_audio()
        return
        yield  # pragma: no cover  (marks this an async generator)

    def _append(self, role, delta):
        """Grow the current row for ``role``; start a new row when the speaker changes."""
        member_id = self.full_member_id()
        chat_widget = self.workflow.chat_widget
        row = self._row
        if row['role'] != role:
            if row['role'] == 'assistant':
                self._flush_audio()
            msg = self.workflow.save_message(role, delta, member_id)
            self._row = {'role': role, 'id': getattr(msg, 'id', None), 'text': delta}
            if chat_widget:
                chat_widget.message_collection.last_member_bubbles.pop((role, member_id), None)
        else:
            row['text'] += delta
            if row['id'] is not None:
                self.workflow.update_message(row['id'], row['text'])
        if chat_widget:
            chat_widget.new_sentence(role, member_id, delta)

    def _flush_audio(self):
        if not self._pcm:
            return
        from plugins.workflows.live import AudioHandler
        base = os.path.join(get_application_path(), 'audio')
        os.makedirs(base, exist_ok=True)
        path = os.path.join(base, f'live_{uuid.uuid4().hex}.wav')
        AudioHandler.write_wav(path, bytes(self._pcm))
        self._pcm = bytearray()
        self.workflow.save_message('audio', json.dumps({'filepath': path}), self.full_member_id())

    async def _delegate(self, client, delegation_id):
        """Client delegation: run the backend model over the transcript, speak the result."""
        if not self._backend_model:
            return
        messages = await self.get_messages()
        system_msg = await self.system_message()
        if system_msg != '':
            messages.insert(0, {'role': 'system', 'content': system_msg})
        text = ''
        async for key, chunk in self.stream(model=convert_model_json_to_obj(self._backend_model), messages=messages):
            if key != 'tools':
                text += chunk or ''
        if text.strip():
            await client.append_commentary(text, delegation_id)

    @staticmethod
    def _report_task(task):
        """Background task errors are otherwise only reported at garbage collection."""
        if not task.cancelled() and task.exception() is not None:
            task.print_stack()
