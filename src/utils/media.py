
import os
import tempfile
import time

from PySide6.QtMultimedia import QMediaPlayer, QAudioOutput
from PySide6.QtCore import QUrl, QEventLoop

media_player = QMediaPlayer()
audio_output = QAudioOutput()
media_player.setAudioOutput(audio_output)


def play_url(url):
    if not url:
        return

    media_player.setSource(QUrl(url))
    media_player.play()


def get_audio_file_duration(filepath):
    """
    Returns the duration of a WAV audio file in milliseconds
    using the wave module.
    """
    import wave

    try:
        with wave.open(filepath, 'rb') as wav_file:
            # Get file properties
            frames = wav_file.getnframes()
            rate = wav_file.getframerate()

            # Calculate duration in milliseconds
            duration_ms = int((frames / rate) * 1000)
            return duration_ms
    except Exception as e:
        print(f"Error getting audio duration: {e}")
        return 0


def play_file(filepath, blocking=False, wait_percent=0.0):
    """
    Plays an audio file. If blocking, waits until wait_percent of the duration or end of media.
    """
    if not os.path.isfile(filepath):
        return

    media_player.setSource(QUrl.fromLocalFile(filepath))
    file_duration = get_audio_file_duration(filepath)
    media_player.play()

    if blocking:
        if wait_percent == 0.0:
            wait_percent = 1.0
        wait_duration = int(file_duration * wait_percent)
        playback_pos = 0
        while playback_pos < wait_duration:
            playback_pos = media_player.position()
            time.sleep(0.015)
    #
    # if blocking:
    #     loop = QEventLoop()
    #     wait_duration = int(file_duration * max(0.0, min(1.0, wait_percent))) if wait_percent > 0.0 else file_duration
    #
    #     def on_media_status_changed(status):
    #         if status == QMediaPlayer.EndOfMedia:
    #             loop.quit()
    #
    #     def on_position_changed(position):
    #         if wait_duration > 0 and position >= wait_duration:
    #             loop.quit()
    #
    #     # Connect signals
    #     media_player.mediaStatusChanged.connect(on_media_status_changed)
    #     if wait_duration > 0:
    #         media_player.positionChanged.connect(on_position_changed)
    #
    #     media_player.play()
    #     loop.exec_()  # Wait for playback to reach wait_percent or end
    #
    #     # Disconnect signals to prevent memory leaks
    #     media_player.mediaStatusChanged.disconnect(on_media_status_changed)
    #     if wait_duration > 0:
    #         media_player.positionChanged.disconnect(on_position_changed)
    # else:
    #     media_player.play()
    # # if not os.path.isfile(filepath):
    # #     return
    # #
    # # media_player.setSource(QUrl.fromLocalFile(filepath))
    # # file_duration = get_audio_file_duration(filepath)
    # # media_player.play()
    # #
    # # if blocking:
    # #     if wait_percent == 0.0:
    # #         wait_percent = 1.0
    # #     wait_duration = int(file_duration * wait_percent)
    # #     playback_pos = 0
    # #     while playback_pos < wait_duration:
    # #         playback_pos = media_player.position()
    # #         time.sleep(0.015)


def play_audio_bytes(audio_bytes):
    if not audio_bytes:
        return

    with tempfile.NamedTemporaryFile(delete=True) as temp_file:
        temp_file.write(audio_bytes)
        temp_file.flush()
        play_url(temp_file.name)