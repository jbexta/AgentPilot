from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

@dataclass
class EventBase:
    event_id: str
    type: str

# Error Event
@dataclass
class ErrorDetails:
    type: str
    code: str
    message: str
    param: Optional[str]
    event_id: Optional[str]

@dataclass
class ErrorEvent(EventBase):
    error: ErrorDetails

# Input Audio Buffer Events
@dataclass
class InputAudioBufferSpeechStopped(EventBase):
    audio_end_ms: int
    item_id: str

@dataclass
class InputAudioBufferCommitted(EventBase):
    previous_item_id: str
    item_id: str

# Conversation Events
@dataclass
class ConversationItemCreated(EventBase):
    previous_item_id: str
    item: Dict[str, Any]

# Response Events
@dataclass
class ResponseCreated(EventBase):
    response: Dict[str, Any]

@dataclass
class ResponseContentPartAdded(EventBase):
    response_id: str
    item_id: str
    output_index: int
    content_index: int
    part: Dict[str, Any]

@dataclass
class ResponseAudioDelta(EventBase):
    response_id: str
    item_id: str
    output_index: int
    content_index: int
    delta: str

@dataclass
class ResponseAudioTranscriptDelta(EventBase):
    response_id: str
    item_id: str
    output_index: int
    content_index: int
    delta: str

# Rate Limits Event
@dataclass
class RateLimit:
    name: str
    limit: int
    remaining: int
    reset_seconds: int

@dataclass
class RateLimitsUpdated(EventBase):
    rate_limits: List[RateLimit]

@dataclass
class ConversationItemInputAudioTranscriptionCompleted(EventBase):
    item_id: str
    content_index: int
    transcript: str

@dataclass
class ResponseAudioDone(EventBase):
    response_id: str
    item_id: str
    output_index: int
    content_index: int

@dataclass
class ResponseAudioTranscriptDone(EventBase):
    response_id: str
    item_id: str
    output_index: int
    content_index: int
    transcript: str

@dataclass
class ResponseContentPartDone(EventBase):
    response_id: str
    item_id: str
    output_index: int
    content_index: int
    part: Dict[str, Any]

@dataclass
class ResponseOutputItemDone(EventBase):
    response_id: str
    output_index: int
    item: Dict[str, Any]

@dataclass
class ResponseDone(EventBase):
    response: Dict[str, Any]

@dataclass
class SessionCreated(EventBase):
    session: Dict[str, Any]

@dataclass
class SessionUpdated(EventBase):
    session: Dict[str, Any]

@dataclass
class InputAudioBufferSpeechStarted(EventBase):
    audio_start_ms: int
    item_id: str

@dataclass
class ResponseOutputItemAdded(EventBase):
    response_id: str
    output_index: int
    item: Dict[str, Any]

@dataclass
class ResponseFunctionCallArgumentsDelta(EventBase):
    response_id: str
    item_id: str
    output_index: int
    call_id: str
    delta: str

@dataclass
class ResponseFunctionCallArgumentsDone(EventBase):
    response_id: str
    item_id: str
    output_index: int
    call_id: str
    arguments: str

@dataclass
class InputAudioBufferCleared(EventBase):
    pass

@dataclass
class ReconnectedEvent(EventBase):
    pass
