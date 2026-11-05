import asyncio
import json
import os
import uuid
from typing import Dict, Any

from plugins.workflows.members import Member
from utils.filesystem import get_application_path
from utils.helpers import set_module_type


@set_module_type(module_type='Members', settings='user_settings')
class User(Member):
    default_role = 'user'
    default_avatar = ':/resources/icon-user.png'
    default_name = 'You'
    workflow_insert_mode = 'single'
    output_type = 'OUTPUT'
    conversational = True
    break_on_run = True
    allow_condition = False

    @property
    def INPUTS(self):
        return {
            'CONFIG': {
                'message_template': str,
            },
        }

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.workflow = kwargs.get('workflow')
        self.config: Dict[str, Any] = kwargs.get('config', {})
        self.receivable_function = None
        # voice capture state
        self._audio = None
        self._vad = None
        self._capturing = False

    # async def run(self):
    #     yield 'SYS', 'BREAK'

    # ---- voice input ----

    def _new_user_audio_path(self):
        base = os.path.join(get_application_path(), 'audio')
        os.makedirs(base, exist_ok=True)
        return os.path.join(base, f'user_{uuid.uuid4().hex}.wav')

    async def start_capture(self):
        if self._capturing:
            return
        from plugins.workflows.live import AudioHandler, LocalVAD
        self._capturing = True
        self._audio = AudioHandler()

        if self.config.get('info.enable_vad', False):  # local VAD auto-endpointing
            self._vad = LocalVAD()

            def on_chunk(pcm):
                if self._vad.feed(pcm) == 'speech_stopped':
                    asyncio.ensure_future(self.stop_capture())

            self._audio.start_capture(on_chunk)
        else:  # push-to-talk: accumulate until the mic button is toggled off
            self._audio.start_capture(None)

    async def stop_capture(self):
        if not self._capturing:
            return
        self._capturing = False
        pcm = self._audio.stop_capture() if self._audio else b''
        if pcm:
            from plugins.workflows.live import AudioHandler
            path = self._new_user_audio_path()
            AudioHandler.write_wav(path, pcm)
            self.workflow.save_message('audio', json.dumps({'filepath': path}), member_id=self.member_id)
        await self._run_after_capture()

    async def _run_after_capture(self):
        # Uncheck the mic button (no-op re-entrancy is guarded by _capturing).
        chat_widget = self.workflow.chat_widget
        if chat_widget:
            mic = getattr(chat_widget.input_widget, 'mic_button', None)
            if mic is not None and mic.isChecked():
                mic.blockSignals(True)
                mic.setChecked(False)
                mic.blockSignals(False)
            self.workflow.message_history.load()
            chat_widget.message_collection.refresh(block_autorun=True)
            await chat_widget.run_workflow_async(from_member_id=self.member_id)
