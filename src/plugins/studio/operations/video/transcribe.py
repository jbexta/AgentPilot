from plugins.studio.operations.audio.transcribe import (
    Transcribe as AudioTranscribe,
)


class Transcribe(AudioTranscribe):
    """Transcribe video clips to SRT subtitles.

    Reuses the audio transcription logic since the underlying
    process is identical — extract audio, run STT model.
    """

    display_name = 'Transcribe'
    description = 'Transcribe video audio to SRT subtitles'
    icon_path = ':/resources/icon-chat.png'