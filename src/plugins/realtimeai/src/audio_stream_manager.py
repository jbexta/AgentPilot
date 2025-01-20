import logging
import base64
import threading
import queue
from realtime_ai.models.audio_stream_options import AudioStreamOptions
from realtime_ai.realtime_ai_service_manager import RealtimeAIServiceManager

logger = logging.getLogger(__name__)


class AudioStreamManager:
    """
    Manages streaming audio data to the Realtime API via the Service Manager in a synchronous manner.
    """

    def __init__(self, stream_options: AudioStreamOptions, service_manager: RealtimeAIServiceManager):
        self._stream_options = stream_options
        self._service_manager = service_manager
        self._audio_queue = queue.Queue()
        self._is_streaming = False
        self._stream_thread = None
        self._stop_event = threading.Event()
        self._lock = threading.RLock()

    def _start_stream(self):
        with self._lock:
            if not self._is_streaming:
                self._is_streaming = True
                self._stop_event.clear()
                self._stream_thread = threading.Thread(target=self._stream_audio)
                self._stream_thread.start()
                logger.info("Audio streaming started.")

    def stop_stream(self):
        with self._lock:
            if self._is_streaming:
                self._is_streaming = False
                self._stop_event.set()  # Signal to the thread to stop
                if self._stream_thread:
                    self._stream_thread.join()
                logger.info("Audio streaming stopped.")

    def write_audio_buffer_sync(self, audio_data: bytes):
        with self._lock:
            if not self._is_streaming:
                self._start_stream()
        logger.info("Enqueuing audio data for streaming.")
        self._audio_queue.put_nowait(audio_data)
        logger.info("Audio data enqueued for streaming.")

    def _stream_audio(self):
        logger.info(f"Streaming audio task started, is_streaming: {self._is_streaming}")

        while self._is_streaming and not self._stop_event.is_set():
            try:
                audio_chunk = self._audio_queue.get(timeout=1)  # Block for a short moment
                processed_audio = self._process_audio(audio_chunk)
                encoded_audio = base64.b64encode(processed_audio).decode()

                # Send input_audio_buffer.append event
                append_event = {
                    "event_id": self._service_manager._generate_event_id(),
                    "type": "input_audio_buffer.append",
                    "audio": encoded_audio
                }

                self._service_manager.send_event(append_event)
                logger.info("input_audio_buffer.append event sent.")

            except queue.Empty:
                # If the queue is empty, just continue looping
                continue
            except Exception as e:
                logger.error(f"Streaming error: {e}")
                break

    def _process_audio(self, audio_data: bytes) -> bytes:
        """
        Process audio data if needed (e.g., resampling, normalization).
        Currently, it returns the audio data as-is.
        """
        return audio_data
