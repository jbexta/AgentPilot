import asyncio
import logging
import base64
from ..models.audio_stream_options import AudioStreamOptions
from ..aio.realtime_ai_service_manager import RealtimeAIServiceManager

logger = logging.getLogger(__name__)


class AudioStreamManager:
    """
    Manages streaming audio data to the Realtime API via the Service Manager.
    """
    def __init__(self, stream_options: AudioStreamOptions, service_manager: RealtimeAIServiceManager):
        self._stream_options = stream_options
        self._service_manager = service_manager
        self._audio_queue = asyncio.Queue()
        self._is_streaming = False
        self._stream_task = None

    def _start_stream(self):
        if not self._is_streaming:
            self._is_streaming = True
            self._stream_task = asyncio.create_task(self._stream_audio())
            logger.info("Audio streaming started.")

    async def stop_stream(self):
        if self._is_streaming:
            self._is_streaming = False
            if self._stream_task:
                self._stream_task.cancel()
                try:
                    await self._stream_task
                except asyncio.CancelledError:
                    logger.info("Audio streaming task cancelled.")
            logger.info("Audio streaming stopped.")

    async def write_audio_buffer(self, audio_data: bytes):
        if not self._is_streaming:
            self._start_stream()
        logger.info("Enqueuing audio data for streaming.")
        await self._audio_queue.put(audio_data)
        logger.info("Audio data enqueued for streaming.")

    async def _stream_audio(self):
        logger.info(f"Streaming audio task started, is_streaming: {self._is_streaming}")
        while self._is_streaming:
            try:
                audio_chunk = await self._audio_queue.get()
                processed_audio = self._process_audio(audio_chunk)
                encoded_audio = base64.b64encode(processed_audio).decode()

                # Send input_audio_buffer.append event
                append_event = {
                    "event_id": self._service_manager._generate_event_id(),
                    "type": "input_audio_buffer.append",
                    "audio": encoded_audio
                }

                await self._service_manager.send_event(append_event)
                logger.info("input_audio_buffer.append event sent.")

            except asyncio.CancelledError:
                logger.info("Streaming audio task cancelled.")
                break
            except Exception as e:
                logger.error(f"Streaming error: {e}")

    def _process_audio(self, audio_data: bytes) -> bytes:
        """
        Process audio data if needed (e.g., resampling, normalization).
        Currently, it returns the audio data as-is.
        """
        return audio_data
