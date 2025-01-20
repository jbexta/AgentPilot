import threading, logging
import concurrent.futures
import queue, time, uuid

from realtime_ai.models.realtime_ai_options import RealtimeAIOptions
from realtime_ai.models.audio_stream_options import AudioStreamOptions
from realtime_ai.realtime_ai_service_manager import RealtimeAIServiceManager
from realtime_ai.audio_stream_manager import AudioStreamManager
from realtime_ai.realtime_ai_event_handler import RealtimeAIEventHandler
from realtime_ai.models.realtime_ai_events import EventBase

logger = logging.getLogger(__name__)


class RealtimeAIClient:
    """
    Manages overall interaction with OpenAI's Realtime API.
    """
    def __init__(self, options: RealtimeAIOptions, stream_options: AudioStreamOptions, event_handler: RealtimeAIEventHandler):
        self._options = options
        self._service_manager = RealtimeAIServiceManager(options)
        self._audio_stream_manager = AudioStreamManager(stream_options, self._service_manager)
        self._event_handler = event_handler
        self._is_running = False
        self._lock = threading.Lock()
        
        # Initialize the consume thread and executor as None
        self._consume_thread = None
        self.executor = None
        self._stop_event = threading.Event()

    def start(self):
        """Starts the RealtimeAIClient."""
        with self._lock:
            if self._is_running:
                logger.warning("RealtimeAIClient: Client is already running.")
                return

            self._is_running = True
            self._stop_event.clear()
            try:
                self._service_manager.connect()  # Connect to the service
                logger.info("RealtimeAIClient: Client started.")

                # Initialize and start the ThreadPoolExecutor here
                self.executor = concurrent.futures.ThreadPoolExecutor(max_workers=5)
                logger.info("RealtimeAIClient: ThreadPoolExecutor initialized.")

                # Initialize and start the consume thread
                self._consume_thread = threading.Thread(target=self._consume_events, daemon=True, name="RealtimeAIClient_ConsumeThread")
                self._consume_thread.start()
                logger.info("RealtimeAIClient: Event consumption thread started.")
            except Exception as e:
                self._is_running = False
                logger.error(f"RealtimeAIClient: Error during client start: {e}")

    def stop(self, timeout: float = 5.0):
        """Stops the RealtimeAIClient gracefully."""
        with self._lock:
            if not self._is_running:
                logger.warning("RealtimeAIClient: Client is already stopped.")
                return

            self._is_running = False

            # Signal stop event
            self._stop_event.set()

            try:
                self._audio_stream_manager.stop_stream()
                self._service_manager.disconnect()

                if self._consume_thread is not None:
                    
                    # Attempt to join the consume thread within the timeout
                    self._consume_thread.join(timeout=timeout)
                    if self._consume_thread.is_alive():
                        logger.warning("RealtimeAIClient: Consume thread did not terminate within the timeout.")
                    else:
                        logger.info("RealtimeAIClient: Consume thread terminated.")
                    self._consume_thread = None

                if self.executor is not None:
                    self.executor.shutdown(wait=True)
                    logger.info("RealtimeAIClient: ThreadPoolExecutor shut down.")
                    self.executor = None

                self._service_manager.clear_event_queue()
                logger.info("RealtimeAIClient: Services stopped.")
            except Exception as e:
                logger.error(f"RealtimeAIClient: Error during client stop: {e}")

    def send_audio(self, audio_data: bytes):
        """Sends audio data to the audio stream manager for processing."""
        logger.info("RealtimeAIClient: Queuing audio data for streaming.")
        self._audio_stream_manager.write_audio_buffer_sync(audio_data)  # Ensure this is a sync method

    def send_text(self, text: str, role: str = "user", generate_response: bool = True):
        """Sends text input to the service manager."""
        event = {
            "event_id": self._service_manager._generate_event_id(),
            "type": "conversation.item.create",
            "item": {
                "type": "message",
                "role": role,
                "content": [
                    {
                        "type": "text" if role == "assistant" else "input_text",
                        "text": text
                    }
                ]
            }
        }
        self._send_event_to_manager(event)
        logger.info("RealtimeAIClient: Sent text input to server.")

        # Generate a response if required
        if generate_response:
            self.generate_response(commit_audio_buffer=False)

    def update_session(self, options: RealtimeAIOptions):
        """Updates the session configuration with the provided options."""
        if self._is_running:
            self._service_manager.update_session(options)

        self._service_manager.options = options
        self._options = options
        logger.info("RealtimeAIClient: Sent session update to server.")

    def generate_response(self, commit_audio_buffer: bool = True):
        """Sends a response.create event to generate a response."""
        logger.info("RealtimeAIClient: Generating response.")
        if commit_audio_buffer:
            self._send_event_to_manager({
                "event_id": self._service_manager._generate_event_id(),
                "type": "input_audio_buffer.commit",
            })

        self._send_event_to_manager({
            "event_id": self._service_manager._generate_event_id(),
            "type": "response.create",
            "response": {"modalities": self.options.modalities}
        })

    def cancel_response(self):
        """Sends a response.cancel event to interrupt the model when playback is interrupted by user."""
        self._send_event_to_manager({
            "event_id": self._service_manager._generate_event_id(),
            "type": "response.cancel"
        })
        logger.info("Client: Sent response.cancel event to server.")

        # Clear the event queue in the service manager
        self._service_manager.clear_event_queue()
        logger.info("RealtimeAIClient: Event queue cleared after cancellation.")

    def truncate_response(self, item_id: str, content_index: int, audio_end_ms: int):
        """Sends a conversation.item.truncate event to truncate the response."""
        self._send_event_to_manager({
            "event_id": self._service_manager._generate_event_id(),
            "type": "conversation.item.truncate",
            "item_id": item_id,
            "content_index": content_index,
            "audio_end_ms": audio_end_ms
        })
        logger.info("Client: Sent conversation.item.truncate event to server.")

    def clear_input_audio_buffer(self):
        """Sends an input_audio_buffer.clear event to the server."""
        self._send_event_to_manager({
            "event_id": self._service_manager._generate_event_id(),
            "type": "input_audio_buffer.clear"
        })
        logger.info("Client: Sent input_audio_buffer.clear event to server.")

    def generate_response_from_function_call(self, call_id: str, function_output: str):
        """
        Sends a conversation.item.create message as a function call output and optionally triggers a model response.
        
        :param call_id: The ID of the function call.
        :param function_output: The output of the function call.
        """
        # Create the function call output event
        item_create_event = {
            "event_id": self._service_manager._generate_event_id(),
            "type": "conversation.item.create",
            "item": {
                "id": str(uuid.uuid4()).replace('-', ''),
                "type": "function_call_output",
                "call_id": call_id,
                "output": function_output,
            }
        }

        # Send the function call output event
        self._send_event_to_manager(item_create_event)
        logger.info("Function call output event sent.")

        # Optionally trigger a response
        self._send_event_to_manager({
            "event_id": self._service_manager._generate_event_id(),
            "type": "response.create",
            "response": {"modalities": self.options.modalities}
        })

    def _consume_events(self):
        """Consume events from the service manager."""
        logger.info("Consume thread: Started consuming events.")
        while not self._stop_event.is_set():
            try:
                event = self._service_manager.get_next_event()
                if event is None:
                    logger.info("Consume thread: Received sentinel, exiting.")
                    break

                if self.executor is not None:
                    self.executor.submit(self._handle_event, event)
                else:
                    logger.warning("RealtimeAIClient: Executor is not available or shutting down. Event cannot be handled.")
                time.sleep(0.05)
            except queue.Empty:
                continue
            except Exception as e:
                logger.error(f"RealtimeAIClient: Error in consume_events: {e}")
                break
        logger.info("Consume thread: Stopped consuming events.")

    def _handle_event(self, event: EventBase):
        """Handles the received event based on its type using the event handler."""
        event_type = event.type
        method_name = f'on_{event_type.replace(".", "_")}'
        handler = getattr(self._event_handler, method_name, None)

        if callable(handler):
            try:
                handler(event)
            except Exception as e:
                logger.error(f"Error in handler {method_name} for event {event_type}: {e}")
        else:
            self._event_handler.on_unhandled_event(event_type, vars(event))

    def _send_event_to_manager(self, event):
        """Helper method to send an event to the manager."""
        self._service_manager.send_event(event)

    @property
    def options(self):
        return self._options
    
    @property
    def is_running(self):
        return self._is_running

    # Optional: Ensure that threads are cleaned up if the object is deleted while running
    def __del__(self):
        if self._is_running:
            self.stop()