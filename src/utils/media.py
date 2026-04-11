
import os
import platform
import subprocess
import tempfile
import time

_current_process = None


def play_file(filepath, blocking=False, wait_percent=0.0):
    """Plays an audio file using platform-native commands."""
    global _current_process
    if not filepath or not os.path.isfile(filepath):
        return

    if wait_percent > 0.0:
        blocking = True

    stop_playback()

    system = platform.system()
    if system == 'Darwin':
        cmd = ['afplay', filepath]
    elif system == 'Windows':
        cmd = ['powershell', '-NoProfile', '-Command',
               f'(New-Object Media.SoundPlayer "{filepath}").PlaySync()']
    else:
        cmd = ['ffplay', '-nodisp', '-autoexit', '-loglevel', 'quiet', filepath]

    try:
        _current_process = subprocess.Popen(
            cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    except FileNotFoundError:
        return

    if blocking:
        if wait_percent > 0.0 and wait_percent < 1.0:
            duration = _estimate_duration(filepath)
            wait_secs = duration * wait_percent
            start = time.monotonic()
            while time.monotonic() - start < wait_secs:
                if _current_process.poll() is not None:
                    return
                time.sleep(0.05)
        else:
            _current_process.wait()


def _estimate_duration(filepath):
    """Estimate audio duration in seconds from file size."""
    try:
        size = os.path.getsize(filepath)
    except OSError:
        return 0
    ext = os.path.splitext(filepath)[1].lower()
    if ext == '.wav':
        return size / (44100 * 2 * 2)
    return size / (128000 / 8)


def get_audio_file_duration(filepath):
    """Returns the duration of an audio file in milliseconds."""
    from PySide6.QtMultimedia import QMediaPlayer
    from PySide6.QtCore import QUrl
    player = QMediaPlayer()
    player.setSource(QUrl.fromLocalFile(filepath))
    timeout = 5.0
    elapsed = 0.0
    while player.duration() <= 0 and elapsed < timeout:
        time.sleep(0.015)
        elapsed += 0.015
    return player.duration()


def stop_playback():
    """Stop any currently playing audio."""
    global _current_process
    if _current_process and _current_process.poll() is None:
        _current_process.terminate()
        _current_process = None


def play_audio_bytes(audio_bytes):
    """Play audio from raw bytes via a temp file."""
    if not audio_bytes:
        return
    with tempfile.NamedTemporaryFile(suffix='.wav', delete=False) as f:
        f.write(audio_bytes)
        path = f.name
    try:
        play_file(path, blocking=True)
    finally:
        try:
            os.unlink(path)
        except OSError:
            pass