from dataclasses import dataclass, field

@dataclass
class AudioStreamOptions:
    """Configuration options for the AudioStreamManager."""
    sample_rate: int = 24000  # Hz
    channels: int = 1
    bytes_per_sample: int = 2  # 16-bit PCM