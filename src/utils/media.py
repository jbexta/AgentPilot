
import os
import platform
import shutil
import subprocess
import time

_current_process = None


def get_ffmpeg_exe():
    """Return the ffmpeg binary bundled with imageio-ffmpeg (a moviepy dependency)."""
    import imageio_ffmpeg
    return imageio_ffmpeg.get_ffmpeg_exe()


def _linux_play_cmd(filepath):
    """Return a command list for the first available Linux audio player.

    ``ffplay`` is preferred (handles every format), then ``cvlc`` and
    ``mpg123`` which also decode mp3, and finally PCM-only players. Returns
    ``None`` if no player is installed.
    """
    if shutil.which('ffplay'):
        return ['ffplay', '-nodisp', '-autoexit', '-loglevel', 'quiet', filepath]
    if shutil.which('cvlc'):
        return ['cvlc', '--play-and-exit', '--intf', 'dummy', '--quiet', filepath]
    if shutil.which('mpg123'):
        return ['mpg123', '-q', filepath]
    if shutil.which('paplay'):
        return ['paplay', filepath]
    if shutil.which('aplay'):
        return ['aplay', '-q', filepath]
    return None

AUDIO_EXTS = {'.mp3', '.wav', '.flac', '.ogg', '.m4a', '.aac', '.wma'}
IMAGE_EXTS = {'.png', '.jpg', '.jpeg', '.gif', '.bmp', '.webp', '.tiff'}
VIDEO_EXTS = {'.mp4', '.avi', '.mov', '.mkv', '.webm', '.wmv', '.flv'}
ALL_MEDIA_EXTS = VIDEO_EXTS | IMAGE_EXTS | AUDIO_EXTS


def get_media_type_from_ext(ext):
    if ext in VIDEO_EXTS:
        return 'video'
    elif ext in IMAGE_EXTS:
        return 'image'
    elif ext in AUDIO_EXTS:
        return 'audio'
    return None


def get_media_preview_class(media_type=None, ext=None):
    from gui.media_previews.image import ImagePreview
    from gui.media_previews.video import VideoPreview
    from gui.media_previews.audio import AudioPreview

    if not media_type:
        media_type = get_media_type_from_ext(ext)
    preview_dict = {
        'video': VideoPreview,
        'image': ImagePreview,
        'audio': AudioPreview,
    }
    return preview_dict.get(media_type, None)


def get_media_icon_path(media_type=None, ext=None):
    if not media_type:
        media_type = get_media_type_from_ext(ext)
    icon_dict = {
        'video': ':/resources/icon-video.png',
        'image': ':/resources/icon-image.png',
        'audio': ':/resources/icon-audio.png',
    }
    return icon_dict.get(media_type, ':/resources/icon-file.png')


def play_file(filepath, blocking=False, wait_percent=0.0, interrupt=True):
    """Plays an audio file using platform-native commands.

    When ``interrupt`` is False, waits for any audio already playing to
    finish instead of terminating it, so clips play back-to-back.
    """
    global _current_process
    if not filepath or not os.path.isfile(filepath):
        return

    if wait_percent > 0.0:
        blocking = True

    if interrupt:
        stop_playback()
    elif _current_process and _current_process.poll() is None:
        _current_process.wait()

    system = platform.system()
    if system == 'Darwin':
        cmd = ['afplay', filepath]
    elif system == 'Windows':
        cmd = ['powershell', '-NoProfile', '-Command',
               f'(New-Object Media.SoundPlayer "{filepath}").PlaySync()']
    else:
        cmd = _linux_play_cmd(filepath)
        if cmd is None:
            print('play_file: no audio player found '
                  '(install ffmpeg/vlc/mpg123) — cannot play', filepath)
            return

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


# def play_audio_bytes(audio_bytes):
#     """Play audio from raw bytes via a temp file."""
#     if not audio_bytes:
#         return
#     with tempfile.NamedTemporaryFile(suffix='.wav', delete=False) as f:
#         f.write(audio_bytes)
#         path = f.name
#     try:
#         play_file(path, blocking=True)
#     finally:
#         try:
#             os.unlink(path)
#         except OSError:
#             pass