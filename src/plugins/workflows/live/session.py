"""Transport-only wrapper around the OpenAI GPT-Live websocket API.

This owns exactly one websocket connection and knows nothing about Qt, audio
devices, or ``message_history`` — the calling member orchestrates playback and
persistence. It lives on the qasync GUI-thread event loop.

Targets ``client.live.connect`` in openai>=3.16. GPT-Live is full duplex and
server-driven: there is no input commit, no response.create and no turn-done
event. Audio and transcript fragments simply stream in both directions while
the session is open.
"""
import asyncio
import base64

PCM_FORMAT = {'type': 'audio/pcm', 'rate': 24000}


class LiveSession:
    def __init__(self, api_key, model_name, voice='marin', instructions='', delegation=None, session_id=None):
        """With ``session_id`` the session already exists (a phone call accepted via
        the SIP webhook) and this attaches to it by sideband instead of starting one."""
        self.api_key = api_key
        self.model_name = model_name
        self.voice = (voice or 'marin').lower()
        self.instructions = instructions or ''
        self.delegation = delegation or {'type': 'client'}
        self.session_id = session_id

        self._client = None
        self._cm = None
        self._conn = None
        self._reader_task = None
        self._closed = False

        # A single ordered stream of tagged events the member drains:
        #   ('audio', bytes) | ('transcript', str) | ('user_transcript', str)
        #   | ('delegation', str) | ('closed', str) | ('error', str)
        self.events: asyncio.Queue = asyncio.Queue()

    @property
    def is_open(self):
        return self._conn is not None and not self._closed

    def _build_session_config(self, for_sip=False):
        audio = {'output': {'voice': self.voice}}
        if not for_sip:  # SIP media format is negotiated by the carrier
            audio['format'] = PCM_FORMAT
        return {
            'model': self.model_name,
            'instructions': self.instructions,
            'audio': audio,
            'delegation': self.delegation,
        }

    def accept_config(self):
        """Session config for ``client.live.sessions.accept`` on an incoming SIP call."""
        return {'type': 'live', **self._build_session_config(for_sip=True)}

    async def connect(self):
        from openai import AsyncOpenAI
        self._client = AsyncOpenAI(api_key=self.api_key)
        if self.session_id:
            self._cm = self._client.live.sideband.connect(session_id=self.session_id)
        else:
            self._cm = self._client.live.connect()
        self._conn = await self._cm.__aenter__()
        if not self.session_id:
            await self._conn.send({'type': 'session.start', 'session': self._build_session_config()})
            while True:
                event = await self._conn.recv()
                etype = getattr(event, 'type', '')
                if etype == 'session.started':
                    self.session_id = getattr(getattr(event, 'session', None), 'id', None)
                    break
                if etype == 'error':
                    await self.close()
                    raise Exception(f'GPT-Live error: {self._error_message(event)}')
        self._reader_task = asyncio.create_task(self._read_events())

    async def send_audio(self, pcm16_bytes):
        if not self.is_open:
            return
        b64 = base64.b64encode(pcm16_bytes).decode('utf-8')
        await self._conn.send({'type': 'session.input_audio.append', 'audio': b64})

    async def append_commentary(self, content, delegation_id=None):
        """Return delegated work as text the model should say aloud (max 500 tokens)."""
        if self.is_open:
            await self._conn.send({
                'type': 'session.commentary.append',
                'delegation_id': delegation_id,
                'content': content,
            })

    async def append_instructions(self, content):
        """Tell the running model something new, e.g. that a call has been answered."""
        if self.is_open:
            await self._conn.send({
                'type': 'session.instructions.append',
                'delegation_id': None,
                'content': content,
            })

    @staticmethod
    def _error_message(event):
        err = getattr(event, 'error', None)
        return getattr(err, 'message', str(err)) if err is not None else 'live error'

    async def _read_events(self):
        reason = 'disconnected'
        try:
            async for event in self._conn:
                etype = getattr(event, 'type', '')
                if etype == 'session.output_audio.delta':
                    delta = getattr(event, 'delta', '') or ''
                    if delta:
                        self.events.put_nowait(('audio', base64.b64decode(delta)))
                elif etype == 'session.output_transcript.delta':
                    delta = getattr(event, 'delta', '') or ''
                    if delta:
                        self.events.put_nowait(('transcript', delta))
                elif etype == 'session.input_transcript.delta':
                    delta = getattr(event, 'delta', '') or ''
                    if delta:
                        self.events.put_nowait(('user_transcript', delta))
                elif etype == 'session.delegation.created':
                    delegation = getattr(event, 'delegation', None)
                    if getattr(delegation, 'target', '') == 'client':
                        self.events.put_nowait(('delegation', delegation.id))
                elif etype == 'session.closed':
                    reason = getattr(event, 'reason', '')
                    break
                elif etype == 'error':
                    self.events.put_nowait(('error', self._error_message(event)))
        except asyncio.CancelledError:
            raise
        except Exception as e:
            self.events.put_nowait(('error', str(e)))
        finally:
            self.events.put_nowait(('closed', reason))

    async def close(self):
        if self._closed:
            return
        self._closed = True
        if self._conn is not None and self._reader_task is not None:
            try:
                await self._conn.send({'type': 'session.close'})
                await asyncio.wait_for(self._reader_task, timeout=5)
            except Exception:
                pass
        if self._reader_task is not None and not self._reader_task.done():
            self._reader_task.cancel()
            try:
                await self._reader_task
            except (asyncio.CancelledError, Exception):
                pass
        if self._cm is not None:
            try:
                await self._cm.__aexit__(None, None, None)
            except Exception:
                pass
        self._conn = None
