"""One GPT-Live session plus its microphone and speaker, owned by the workflow on
behalf of a member. Knows nothing about message rows: the member drains
``events`` and decides what to persist.
"""
import asyncio

from plugins.workflows.live.audio_handler import AudioHandler
from plugins.workflows.live.session import LiveSession


class LiveClient:
    def __init__(self, member):
        self.member = member
        self.session = None
        self.audio = None
        self.pending_session_id = None  # an accepted phone call waiting for the member to attach
        self.pending_instructions = None  # sent once that call's session is open

    @property
    def is_open(self):
        return self.session is not None and self.session.is_open

    @property
    def events(self):
        return self.session.events

    async def start(self, api_key, model_name, voice, instructions, delegation, session_id=None):
        """With ``session_id``, join that session (a phone call) by sideband: no local audio devices."""
        await self.stop()
        self.session = LiveSession(
            api_key=api_key,
            model_name=model_name,
            voice=voice,
            instructions=instructions,
            delegation=delegation,
            session_id=session_id,
        )
        await self.session.connect()
        if self.pending_instructions:
            await self.session.append_instructions(self.pending_instructions)
            self.pending_instructions = None
        if session_id is None:
            self.audio = AudioHandler()
            self.audio.start_capture(self._on_mic_chunk)

    def _on_mic_chunk(self, pcm):
        if self.is_open:
            asyncio.ensure_future(self.session.send_audio(pcm))

    def play(self, pcm):
        if self.audio is not None:
            self.audio.play_pcm(pcm)

    async def append_commentary(self, content, delegation_id=None):
        if self.is_open:
            await self.session.append_commentary(content, delegation_id)

    async def stop(self):
        if self.audio is not None:
            self.audio.close()
            self.audio = None
        if self.session is not None:
            await self.session.close()
            self.session = None
