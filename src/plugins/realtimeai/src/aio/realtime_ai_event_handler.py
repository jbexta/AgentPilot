from abc import ABC, abstractmethod
from typing import Any, Dict
from ..models.realtime_ai_events import *


class RealtimeAIEventHandler(ABC):
    """Interface for handling real-time events."""

    @abstractmethod
    async def on_error(self, event: ErrorEvent) -> None:
        pass

    @abstractmethod
    async def on_input_audio_buffer_speech_stopped(self, event: InputAudioBufferSpeechStopped) -> None:
        pass

    @abstractmethod
    async def on_input_audio_buffer_committed(self, event: InputAudioBufferCommitted) -> None:
        pass

    @abstractmethod
    async def on_conversation_item_created(self, event: ConversationItemCreated) -> None:
        pass

    @abstractmethod
    async def on_response_created(self, event: ResponseCreated) -> None:
        pass

    @abstractmethod
    async def on_response_content_part_added(self, event: ResponseContentPartAdded) -> None:
        pass

    @abstractmethod
    async def on_response_audio_delta(self, event: ResponseAudioDelta) -> None:
        pass

    @abstractmethod
    async def on_response_audio_transcript_delta(self, event: ResponseAudioTranscriptDelta) -> None:
        pass

    @abstractmethod
    async def on_rate_limits_updated(self, event: RateLimitsUpdated) -> None:
        pass

    @abstractmethod
    async def on_conversation_item_input_audio_transcription_completed(self, event: ConversationItemInputAudioTranscriptionCompleted) -> None:
        pass

    @abstractmethod
    async def on_response_audio_done(self, event: ResponseAudioDone) -> None:
        pass

    @abstractmethod
    async def on_response_audio_transcript_done(self, event: ResponseAudioTranscriptDone) -> None:
        pass

    @abstractmethod
    async def on_response_content_part_done(self, event: ResponseContentPartDone) -> None:
        pass

    @abstractmethod
    async def on_response_output_item_done(self, event: ResponseOutputItemDone) -> None:
        pass

    @abstractmethod
    async def on_response_done(self, event: ResponseDone) -> None:
        pass

    @abstractmethod
    async def on_session_created(self, event: SessionCreated) -> None:
        pass

    @abstractmethod
    async def on_session_updated(self, event: SessionUpdated) -> None:
        pass

    @abstractmethod
    async def on_input_audio_buffer_speech_started(self, event: InputAudioBufferSpeechStarted) -> None:
        pass

    @abstractmethod
    async def on_response_output_item_added(self, event: ResponseOutputItemAdded) -> None:
        pass

    @abstractmethod
    async def on_response_function_call_arguments_delta(self, event: ResponseFunctionCallArgumentsDelta) -> None:
        pass

    @abstractmethod
    async def on_response_function_call_arguments_done(self, event: ResponseFunctionCallArgumentsDone) -> None:
        pass

    @abstractmethod
    async def on_unhandled_event(self, event_type: str, event_data: Dict[str, Any]) -> None:
        import logging
        logging.warning(f"Unhandled Event Type: {event_type}, Data: {event_data}")