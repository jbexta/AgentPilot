import tempfile

from PySide6.QtMultimedia import QMediaPlayer, QAudioOutput
from PySide6.QtCore import QUrl

media_player = QMediaPlayer()
audio_output = QAudioOutput()
media_player.setAudioOutput(audio_output)


def play_url(url):
    if not url:
        return

    media_player.setSource(QUrl(url))
    media_player.play()


def play_audio_bytes(audio_bytes):
    if not audio_bytes:
        return

    with tempfile.NamedTemporaryFile(delete=True) as temp_file:
        temp_file.write(audio_bytes)
        temp_file.flush()
        play_url(temp_file.name)