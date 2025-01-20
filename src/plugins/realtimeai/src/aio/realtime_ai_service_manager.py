import asyncio
import json
import logging
import uuid
from typing import Optional, Type
from ..models.realtime_ai_options import RealtimeAIOptions
from ..aio.web_socket_manager import WebSocketManager
from ..models.realtime_ai_events import (
    EventBase,
    ErrorEvent,
    ErrorDetails,
    InputAudioBufferSpeechStopped,
    InputAudioBufferCommitted,
    ConversationItemCreated,
    ConversationItemInputAudioTranscriptionCompleted,
    ResponseCreated,
    ResponseContentPartAdded,
    ResponseAudioTranscriptDelta,
    RateLimit,
    RateLimitsUpdated,
    ResponseAudioDelta,
    ResponseAudioDone,
    ResponseAudioTranscriptDone,
    ResponseContentPartDone,
    ResponseOutputItemDone,
    ResponseDone,
    SessionCreated,
    SessionUpdated,
    InputAudioBufferSpeechStarted,
    ResponseOutputItemAdded,
    ResponseFunctionCallArgumentsDelta,
    ResponseFunctionCallArgumentsDone,
    InputAudioBufferCleared,
    ReconnectedEvent
)

logger = logging.getLogger(__name__)


class RealtimeAIServiceManager:
    """
    Manages WebSocket connection and communication with OpenAI's Realtime API.
    """

    def __init__(self, options: RealtimeAIOptions):
        self._options = options
        self._websocket_manager = WebSocketManager(options, self)
        self._event_queue = asyncio.Queue()
        self._is_connected = False

    async def connect(self):
        try:
            await self._websocket_manager.connect()
        except asyncio.CancelledError:
            logger.info("RealtimeAIServiceManager: Connection was cancelled.")
        except Exception as e:
            logger.error(f"RealtimeAIServiceManager: Unexpected error during connect: {e}")

    async def disconnect(self):
        try:
            await self._event_queue.put(None)  # Signal the event loop to stop
            await self._websocket_manager.disconnect()
        except asyncio.CancelledError:
            logger.info("RealtimeAIServiceManager: Disconnect was cancelled.")
        except Exception as e:
            logger.error(f"RealtimeAIServiceManager: Unexpected error during disconnect: {e}")

    async def send_event(self, event: dict):
        try:
            await self._websocket_manager.send(event)
            logger.debug(f"RealtimeAIServiceManager: Sent event: {event.get('type')}")
        except Exception as e:
            logger.error(f"RealtimeAIServiceManager: Failed to send event {event.get('type')}: {e}")

    async def on_connected(self, reconnection: bool = False):
        self._is_connected = True
        logger.info("RealtimeAIServiceManager: Connected to WebSocket.")
        await self.update_session(self._options)
        if reconnection:
            # If it's a reconnection, trigger a ReconnectedEvent
            reconnect_event = ReconnectedEvent(
                event_id=self._generate_event_id(), 
                type="reconnect",
            )
            await self.on_message_received(json.dumps(reconnect_event.__dict__))  # Sending ReconnectedEvent as JSON string
            logger.debug("RealtimeAIServiceManager: ReconnectedEvent sent.")
        logger.debug("RealtimeAIServiceManager: session.update event sent.")

    async def on_disconnected(self, status_code: int, reason: str):
        self._is_connected = False
        logger.warning(f"RealtimeAIServiceManager: WebSocket disconnected: {status_code} - {reason}")

    async def on_error(self, error: Exception):
        logger.error(f"RealtimeAIServiceManager: WebSocket error: {error}")

    async def on_message_received(self, message: str):
        try:
            json_object = json.loads(message)
            event = self.parse_realtime_event(json_object)
            if event:
                await self._event_queue.put(event)
                logger.debug(f"RealtimeAIServiceManager: Event queued: {event.type}")
        except json.JSONDecodeError as e:
            logger.error(f"RealtimeAIServiceManager: JSON parse error: {e}")

    def parse_realtime_event(self, json_object: dict) -> Optional[EventBase]:
        event_type = json_object.get("type")
        event_class = self._get_event_class(event_type)
        if event_class:
            try:
                if event_type == "error" and 'error' in json_object:
                    # Convert error dict to ErrorDetails dataclass
                    error_data = json_object['error']
                    error_details = ErrorDetails(**error_data)
                    return ErrorEvent(event_id=json_object['event_id'], type=event_type, error=error_details)
                elif event_type == "rate_limits.updated" and 'rate_limits' in json_object:
                    rate_limits_data = json_object['rate_limits']
                    rate_limits = [RateLimit(**rate) for rate in rate_limits_data]
                    return RateLimitsUpdated(event_id=json_object['event_id'], type=event_type, rate_limits=rate_limits)
                elif event_type == "response.content_part.done":
                    # Ensure only relevant fields are passed
                    return ResponseContentPartDone(
                        event_id=json_object['event_id'], 
                        type=event_type,
                        response_id=json_object.get('response_id'),
                        item_id=json_object.get('item_id'),
                        output_index=json_object.get('output_index'),
                        content_index=json_object.get('content_index'),
                        part=json_object.get('part')
                    )
                elif event_type == "response.content_part.added":
                    # Ensure only relevant fields are passed
                    return ResponseContentPartAdded(
                        event_id=json_object['event_id'], 
                        type=event_type,
                        response_id=json_object.get('response_id'),
                        item_id=json_object.get('item_id'),
                        output_index=json_object.get('output_index'),
                        content_index=json_object.get('content_index'),
                        part=json_object.get('part')
                    )
                elif event_type == "response.function_call_arguments.done":
                    # Ensure only relevant fields are passed
                    return ResponseFunctionCallArgumentsDone(
                        event_id=json_object['event_id'], 
                        type=event_type,
                        response_id=json_object.get('response_id'),
                        item_id=json_object.get('item_id'),
                        output_index=json_object.get('output_index'),
                        call_id=json_object.get('call_id'),
                        arguments=json_object.get('arguments')
                    )
                else:
                        return event_class(**json_object)
            except TypeError as e:
                logger.error(f"Error creating event object for {event_type}: {e}")
        else:
            logger.warning(f"RealtimeAIServiceManager: Unknown message type received: {event_type}")
        return None

    async def update_session(self, options: RealtimeAIOptions) -> dict:
        event = {
            "event_id": self._generate_event_id(),
            "type": "session.update",
            "session": {
                "modalities": options.modalities,
                "instructions": options.instructions,
                "voice": options.voice,
                "input_audio_format": options.input_audio_format,
                "output_audio_format": options.output_audio_format,
                "input_audio_transcription": {
                    "model": options.input_audio_transcription_model
                },
                "turn_detection": options.turn_detection,
                "tools": options.tools,
                "tool_choice": options.tool_choice,
                "temperature": options.temperature,
                "max_response_output_tokens": options.max_output_tokens
            }
        }
        await self.send_event(event)

    async def clear_event_queue(self):
        """Clears all events in the event queue."""
        try:
            while not self._event_queue.empty():
                await self._event_queue.get()
                self._event_queue.task_done()
            logger.info("RealtimeAIServiceManager: Event queue cleared.")
        except Exception as e:
            logger.error(f"RealtimeAIServiceManager: Failed to clear event queue: {e}")

    def _get_event_class(self, event_type: str) -> Optional[Type[EventBase]]:
        event_mapping = {
            "error": ErrorEvent,
            "input_audio_buffer.speech_stopped": InputAudioBufferSpeechStopped,
            "input_audio_buffer.committed": InputAudioBufferCommitted,
            "conversation.item.created": ConversationItemCreated,
            "response.created": ResponseCreated,
            "response.content_part.added": ResponseContentPartAdded,
            "response.audio.delta": ResponseAudioDelta,
            "response.audio_transcript.delta": ResponseAudioTranscriptDelta,
            "conversation.item.input_audio_transcription.completed": ConversationItemInputAudioTranscriptionCompleted,
            "rate_limits.updated": RateLimitsUpdated,
            "response.audio.done": ResponseAudioDone,
            "response.audio_transcript.done": ResponseAudioTranscriptDone,
            "response.content_part.done": ResponseContentPartDone,
            "response.output_item.done": ResponseOutputItemDone,
            "response.done": ResponseDone,
            "session.created": SessionCreated,
            "session.updated": SessionUpdated,
            "input_audio_buffer.speech_started": InputAudioBufferSpeechStarted,
            "response.output_item.added": ResponseOutputItemAdded,
            "response.function_call_arguments.delta": ResponseFunctionCallArgumentsDelta,
            "response.function_call_arguments.done": ResponseFunctionCallArgumentsDone,
            "input_audio_buffer.cleared": InputAudioBufferCleared,
            "reconnected": ReconnectedEvent
        }
        return event_mapping.get(event_type)

    async def get_next_event(self) -> Optional[EventBase]:
        try:
            logger.debug("RealtimeAIServiceManager: Waiting for next event...")
            return await asyncio.wait_for(self._event_queue.get(), timeout=5.0)
        except asyncio.TimeoutError:
            return None

    def _generate_event_id(self) -> str:
        return f"event_{uuid.uuid4()}"
    
    @property
    def options(self):
        return self._options

    @options.setter
    def options(self, options: RealtimeAIOptions):
        self._options = options
        logger.info("RealtimeAIServiceManager: Options updated.")
