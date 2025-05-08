# import os
# import tempfile
# import wave
# from PySide6.QtMultimedia import QMediaPlayer, QAudioOutput
# from PySide6.QtCore import QUrl, QEventLoop, QTimer
# import logging
#
# # Set up logging for debugging
# logging.basicConfig(level=logging.DEBUG, format='%(asctime)s - %(levelname)s - %(message)s')
# logger = logging.getLogger(__name__)
#
# # Initialize media player and audio output
# media_player = QMediaPlayer()
# audio_output = QAudioOutput()
# media_player.setAudioOutput(audio_output)
#
# # Global state for tracking playback waiting conditions
# _wait_loop = None
# _wait_duration = 0
# _waiting = False
# _wait_ref_count = 0  # Tracks number of functions waiting on the loop
#
#
# def _on_media_status_changed(status):
#     """
#     Persistent handler for mediaStatusChanged signal.
#     Quits the event loop when playback reaches EndOfMedia or an error state.
#     """
#     global _wait_loop, _waiting, _wait_ref_count
#     logger.debug(
#         f"Media status changed: {status}, waiting: {_waiting}, loop: {_wait_loop is not None}, ref_count: {_wait_ref_count}")
#     if _waiting and status in [QMediaPlayer.EndOfMedia, QMediaPlayer.NoMedia, QMediaPlayer.InvalidMedia]:
#         if _wait_loop and _wait_ref_count > 0:
#             logger.debug("Quitting wait loop due to media status")
#             _wait_loop.quit()
#
#
# def _on_position_changed(position):
#     """
#     Persistent handler for positionChanged signal.
#     Quits the event loop when the playback position reaches the desired wait_duration.
#     """
#     global _wait_loop, _wait_duration, _waiting, _wait_ref_count
#     logger.debug(
#         f"Position changed: {position}, wait_duration: {_wait_duration}, waiting: {_waiting}, ref_count: {_wait_ref_count}")
#     if _waiting and _wait_duration > 0 and position >= _wait_duration:
#         if _wait_loop and _wait_ref_count > 0:
#             logger.debug("Quitting wait loop due to position reached")
#             _wait_loop.quit()
#
#
# def _on_error_occurred(error, error_string):
#     """
#     Handler for errorOccurred signal.
#     Logs errors and quits the wait loop to prevent hanging.
#     """
#     global _wait_loop, _waiting, _wait_ref_count
#     logger.error(f"Media player error: {error}, {error_string}")
#     if _waiting and _wait_loop and _wait_ref_count > 0:
#         logger.debug("Quitting wait loop due to error")
#         _wait_loop.quit()
#
#
# # Connect signals once at module initialization
# media_player.mediaStatusChanged.connect(_on_media_status_changed)
# media_player.positionChanged.connect(_on_position_changed)
# media_player.errorOccurred.connect(_on_error_occurred)
#
#
# def get_audio_file_duration(filepath):
#     """
#     Returns the duration of a WAV audio file in milliseconds using the wave module.
#     """
#     try:
#         with wave.open(filepath, 'rb') as wav_file:
#             frames = wav_file.getnframes()
#             rate = wav_file.getframerate()
#             duration_ms = int((frames / rate) * 1000)
#             logger.debug(f"Calculated duration for {filepath}: {duration_ms}ms")
#             return duration_ms
#     except Exception as e:
#         logger.error(f"Error getting audio duration for {filepath}: {e}")
#         return 0
#
#
# def _wait_for_playback(wait_duration, caller_name):
#     """
#     Shared function to wait for playback to reach wait_duration or EndOfMedia.
#     Manages QEventLoop, reference counting, and timeouts.
#     """
#     global _wait_loop, _wait_duration, _waiting, _wait_ref_count
#
#     # Update wait_duration to the minimum non-zero value (ensures positionChanged works)
#     _wait_duration = min(wait_duration, _wait_duration) if _wait_duration > 0 else wait_duration
#     logger.debug(f"{caller_name}: Setting wait_duration to {_wait_duration}ms")
#
#     # Only create a new loop if none exists
#     if not _wait_loop:
#         _wait_loop = QEventLoop()
#         _waiting = True
#     _wait_ref_count += 1
#     logger.debug(f"{caller_name}: Incremented ref_count to {_wait_ref_count}, wait_duration: {_wait_duration}ms")
#
#     # Fallback timeout to prevent infinite blocking (wait_duration + 1s or 5s minimum)
#     timeout = max(wait_duration + 1000, 5000)
#     QTimer.singleShot(timeout, lambda: _wait_loop.quit() if _wait_loop and _waiting else None)
#
#     logger.debug(f"{caller_name}: Starting wait loop")
#     if _wait_ref_count == 1:  # Only exec if this is the first waiter
#         _wait_loop.exec()
#         logger.debug(f"{caller_name}: Wait loop completed")
#
#     # Decrement ref count and clean up if no more waiters
#     _wait_ref_count -= 1
#     if _wait_ref_count == 0:
#         _waiting = False
#         _wait_loop = None
#         _wait_duration = 0
#     logger.debug(f"{caller_name}: Decremented ref_count to {_wait_ref_count}")
#
#
# def play_file(filepath, blocking=False, wait_percent=0.0):
#     """
#     Plays an audio file. If blocking, waits until wait_percent of the duration or end of media.
#     """
#     if not os.path.isfile(filepath):
#         logger.warning(f"File not found: {filepath}")
#         return
#
#     # Reset player state
#     media_player.stop()
#     media_player.setSource(QUrl.fromLocalFile(filepath))
#     file_duration = get_audio_file_duration(filepath)
#     logger.debug(
#         f"Playing file: {filepath}, duration: {file_duration}ms, blocking: {blocking}, wait_percent: {wait_percent}")
#
#     if blocking:
#         wait_duration = int(file_duration * max(0.0, min(1.0, wait_percent))) if wait_percent > 0.0 else file_duration
#         _wait_for_playback(wait_duration, "play_file")
#     else:
#         media_player.play()
#         logger.debug("Started non-blocking playback")
#
#
# def is_playing():
#     """
#     Returns True if audio is currently playing.
#     """
#     is_active = (media_player.playbackState() == QMediaPlayer.PlayingState and
#                  media_player.mediaStatus() not in [QMediaPlayer.EndOfMedia, QMediaPlayer.NoMedia,
#                                                     QMediaPlayer.InvalidMedia])
#     logger.debug(
#         f"is_playing check: playbackState={media_player.playbackState()}, mediaStatus={media_player.mediaStatus()}, result={is_active}")
#     return is_active
#
#
# def play_url(url):
#     """
#     Plays audio from a URL.
#     """
#     if not url:
#         logger.warning("No URL provided")
#         return
#     media_player.stop()
#     media_player.setSource(QUrl(url))
#     media_player.play()
#     logger.debug(f"Playing URL: {url}")
#
#
# def play_audio_bytes(audio_bytes):
#     """
#     Plays audio from bytes using a temporary file.
#     """
#     if not audio_bytes:
#         logger.warning("No audio bytes provided")
#         return
#     with tempfile.NamedTemporaryFile(delete=True) as temp_file:
#         temp_file.write(audio_bytes)
#         temp_file.flush()
#         play_url(temp_file.name)
#         logger.debug("Playing audio from bytes")
#
#
# def wait_until_finished_speaking():
#     """Wait until the media player finishes playing."""
#     if not is_playing():
#         logger.debug("wait_until_finished_speaking: Not playing, exiting")
#         return
#
#     # Use full duration for wait_until_finished_speaking
#     wait_duration = media_player.duration() if media_player.duration() > 0 else 5000
#     _wait_for_playback(wait_duration, "wait_until_finished_speaking")
#
#
# # import os
# # import tempfile
# # import time
# # import wave
# # from PySide6.QtMultimedia import QMediaPlayer, QAudioOutput
# # from PySide6.QtCore import QUrl, QEventLoop, QTimer
# # import logging
# #
# # # Set up logging for debugging
# # logging.basicConfig(level=logging.DEBUG, format='%(asctime)s - %(levelname)s - %(message)s')
# # logger = logging.getLogger(__name__)
# #
# # # Initialize media player and audio output
# # media_player = QMediaPlayer()
# # audio_output = QAudioOutput()
# # media_player.setAudioOutput(audio_output)
# #
# # # Global state for tracking playback waiting conditions
# # _wait_loop = None
# # _wait_duration = 0
# # _waiting = False
# # _wait_ref_count = 0  # Tracks number of functions waiting on the loop
# #
# # def _on_media_status_changed(status):
# #     """
# #     Persistent handler for mediaStatusChanged signal.
# #     Quits the event loop when playback reaches EndOfMedia or an error state.
# #     """
# #     global _wait_loop, _waiting, _wait_ref_count
# #     logger.debug(f"Media status changed: {status}, waiting: {_waiting}, loop: {_wait_loop is not None}, ref_count: {_wait_ref_count}")
# #     if _waiting and status in [QMediaPlayer.EndOfMedia, QMediaPlayer.NoMedia, QMediaPlayer.InvalidMedia]:
# #         if _wait_loop and _wait_ref_count > 0:
# #             logger.debug("Quitting wait loop due to media status")
# #             _wait_loop.quit()
# #
# # def _on_position_changed(position):
# #     """
# #     Persistent handler for positionChanged signal.
# #     Quits the event loop when the playback position reaches the desired wait_duration.
# #     """
# #     global _wait_loop, _wait_duration, _waiting, _wait_ref_count
# #     logger.debug(f"Position changed: {position}, wait_duration: {_wait_duration}, waiting: {_waiting}, ref_count: {_wait_ref_count}")
# #     if _waiting and _wait_duration > 0 and position >= _wait_duration:
# #         if _wait_loop and _wait_ref_count > 0:
# #             logger.debug("Quitting wait loop due to position reached")
# #             _wait_loop.quit()
# #
# # def _on_error_occurred(error, error_string):
# #     """
# #     Handler for errorOccurred signal.
# #     Logs errors and quits the wait loop to prevent hanging.
# #     """
# #     global _wait_loop, _waiting, _wait_ref_count
# #     logger.error(f"Media player error: {error}, {error_string}")
# #     if _waiting and _wait_loop and _wait_ref_count > 0:
# #         logger.debug("Quitting wait loop due to error")
# #         _wait_loop.quit()
# #
# # # Connect signals once at module initialization
# # media_player.mediaStatusChanged.connect(_on_media_status_changed)
# # media_player.positionChanged.connect(_on_position_changed)
# # media_player.errorOccurred.connect(_on_error_occurred)
# #
# # def get_audio_file_duration(filepath):
# #     """
# #     Returns the duration of a WAV audio file in milliseconds using the wave module.
# #     """
# #     try:
# #         with wave.open(filepath, 'rb') as wav_file:
# #             frames = wav_file.getnframes()
# #             rate = wav_file.getframerate()
# #             duration_ms = int((frames / rate) * 1000)
# #             logger.debug(f"Calculated duration for {filepath}: {duration_ms}ms")
# #             return duration_ms
# #     except Exception as e:
# #         logger.error(f"Error getting audio duration for {filepath}: {e}")
# #         return 0
# #
# # def play_file(filepath, blocking=False, wait_percent=0.0):
# #     """
# #     Plays an audio file. If blocking, waits until wait_percent of the duration or end of media.
# #     """
# #     global _wait_loop, _wait_duration, _waiting, _wait_ref_count
# #
# #     if not os.path.isfile(filepath):
# #         logger.warning(f"File not found: {filepath}")
# #         return
# #
# #     # Reset player state
# #     media_player.stop()
# #     media_player.setSource(QUrl.fromLocalFile(filepath))
# #     file_duration = get_audio_file_duration(filepath)
# #     logger.debug(f"Playing file: {filepath}, duration: {file_duration}ms, blocking: {blocking}, wait_percent: {wait_percent}")
# #
# #     if blocking:
# #         # Calculate wait duration (use full duration if wait_percent is 0 or invalid)
# #         _wait_duration = int(file_duration * max(0.0, min(1.0, wait_percent))) if wait_percent > 0.0 else file_duration
# #
# #         # Only create a new loop if none exists
# #         if not _wait_loop:
# #             _wait_loop = QEventLoop()
# #             _waiting = True
# #         _wait_ref_count += 1
# #         logger.debug(f"Incremented ref_count to {_wait_ref_count}, wait_duration: {_wait_duration}ms")
# #
# #         # Fallback timeout to prevent infinite blocking (full duration + 1s or 5s minimum)
# #         # timeout = max(file_duration + 1000, 5000)
# #         QTimer.singleShot(_wait_duration, lambda: _wait_loop.quit() if _wait_loop and _waiting else None)
# #
# #         media_player.play()
# #         logger.debug(f"Starting blocking playback, waiting for {_wait_duration}ms or EndOfMedia")
# #         if _wait_ref_count == 1:  # Only exec if this is the first waiter
# #             _wait_loop.exec()
# #             logger.debug("Blocking playback loop completed")
# #
# #         # Decrement ref count and clean up if no more waiters
# #         _wait_ref_count -= 1
# #         if _wait_ref_count == 0:
# #             _waiting = False
# #             _wait_loop = None
# #             _wait_duration = 0
# #         logger.debug(f"Decremented ref_count to {_wait_ref_count}")
# #     else:
# #         media_player.play()
# #         logger.debug("Started non-blocking playback")
# #
# # def is_playing():
# #     """
# #     Returns True if audio is currently playing.
# #     """
# #     is_active = (media_player.playbackState() == QMediaPlayer.PlayingState and
# #                  media_player.mediaStatus() not in [QMediaPlayer.EndOfMedia, QMediaPlayer.NoMedia, QMediaPlayer.InvalidMedia])
# #     logger.debug(f"is_playing check: playbackState={media_player.playbackState()}, mediaStatus={media_player.mediaStatus()}, result={is_active}")
# #     return is_active
# #
# # def play_url(url):
# #     """
# #     Plays audio from a URL.
# #     """
# #     if not url:
# #         logger.warning("No URL provided")
# #         return
# #     media_player.stop()
# #     media_player.setSource(QUrl(url))
# #     media_player.play()
# #     logger.debug(f"Playing URL: {url}")
# #
# # def play_audio_bytes(audio_bytes):
# #     """
# #     Plays audio from bytes using a temporary file.
# #     """
# #     if not audio_bytes:
# #         logger.warning("No audio bytes provided")
# #         return
# #     with tempfile.NamedTemporaryFile(delete=True) as temp_file:
# #         temp_file.write(audio_bytes)
# #         temp_file.flush()
# #         play_url(temp_file.name)
# #         logger.debug("Playing audio from bytes")
# #
# # def wait_until_finished_speaking():
# #     """Wait until the media player finishes playing."""
# #     # # while is_playing():
# #     # #     time.sleep(0.1)
# #     # def check_playing():
# #     #     if is_playing():
# #
# #     global _wait_loop, _waiting, _wait_ref_count, _wait_duration
# #
# #     if not is_playing():
# #         return
# #
# #     # # Use full duration for wait_until_finished_speaking
# #     # _wait_duration = media_player.duration() if media_player.duration() > 0 else 5000
# #
# #     # Only create a new loop if none exists
# #     if not _wait_loop:
# #         _wait_loop = QEventLoop()
# #         _waiting = True
# #     _wait_ref_count += 1
# #     logger.debug(f"wait_until_finished_speaking: Incremented ref_count to {_wait_ref_count}, wait_duration: {_wait_duration}ms")
# #
# #     # Fallback timeout to prevent infinite blocking
# #     timeout = max(_wait_duration + 1000, 5000)
# #     QTimer.singleShot(timeout, lambda: _wait_loop.quit() if _wait_loop and _waiting else None)
# #
# #     logger.debug("wait_until_finished_speaking: Starting wait loop")
# #     if _wait_ref_count == 1:  # Only exec if this is the first waiter
# #         _wait_loop.exec()
# #         logger.debug("wait_until_finished_speaking: Wait loop completed")
# #
# #     # Decrement ref count and clean up if no more waiters
# #     _wait_ref_count -= 1
# #     if _wait_ref_count == 0:
# #         _waiting = False
# #         _wait_loop = None
# #         _wait_duration = 0
# #     logger.debug(f"wait_until_finished_speaking: Decremented ref_count to {_wait_ref_count}")
# #
# # # import os
# # # import tempfile
# # # import wave
# # # from PySide6.QtMultimedia import QMediaPlayer, QAudioOutput
# # # from PySide6.QtCore import QUrl, QEventLoop, QTimer
# # # import logging
# # #
# # # # Set up logging for debugging
# # # logging.basicConfig(level=logging.DEBUG, format='%(asctime)s - %(levelname)s - %(message)s')
# # # logger = logging.getLogger(__name__)
# # #
# # # # Initialize media player and audio output
# # # media_player = QMediaPlayer()
# # # audio_output = QAudioOutput()
# # # media_player.setAudioOutput(audio_output)
# # #
# # # # Global state for tracking playback waiting conditions
# # # _wait_loop = None
# # # _wait_duration = 0
# # # _waiting = False
# # #
# # #
# # # def _on_media_status_changed(status):
# # #     """
# # #     Persistent handler for mediaStatusChanged signal.
# # #     Quits the event loop when playback reaches EndOfMedia or an error state.
# # #     """
# # #     global _wait_loop, _waiting
# # #     logger.debug(f"Media status changed: {status}, waiting: {_waiting}, loop: {_wait_loop is not None}")
# # #     if _waiting and status in [QMediaPlayer.EndOfMedia, QMediaPlayer.NoMedia, QMediaPlayer.InvalidMedia]:
# # #         if _wait_loop:
# # #             logger.debug("Quitting wait loop due to media status")
# # #             _wait_loop.quit()
# # #
# # #
# # # def _on_position_changed(position):
# # #     """
# # #     Persistent handler for positionChanged signal.
# # #     Quits the event loop when the playback position reaches the desired wait_duration.
# # #     """
# # #     global _wait_loop, _wait_duration, _waiting
# # #     logger.debug(f"Position changed: {position}, wait_duration: {_wait_duration}, waiting: {_waiting}")
# # #     if _waiting and _wait_duration > 0 and position >= _wait_duration:
# # #         if _wait_loop:
# # #             logger.debug("Quitting wait loop due to position reached")
# # #             _wait_loop.quit()
# # #
# # #
# # # def _on_error_occurred(error, error_string):
# # #     """
# # #     Handler for errorOccurred signal.
# # #     Logs errors and quits the wait loop to prevent hanging.
# # #     """
# # #     global _wait_loop, _waiting
# # #     logger.error(f"Media player error: {error}, {error_string}")
# # #     if _waiting and _wait_loop:
# # #         logger.debug("Quitting wait loop due to error")
# # #         _wait_loop.quit()
# # #
# # #
# # # # Connect signals once at module initialization
# # # media_player.mediaStatusChanged.connect(_on_media_status_changed)
# # # media_player.positionChanged.connect(_on_position_changed)
# # # media_player.errorOccurred.connect(_on_error_occurred)
# # #
# # #
# # # def get_audio_file_duration(filepath):
# # #     """
# # #     Returns the duration of a WAV audio file in milliseconds using the wave module.
# # #     """
# # #     try:
# # #         with wave.open(filepath, 'rb') as wav_file:
# # #             frames = wav_file.getnframes()
# # #             rate = wav_file.getframerate()
# # #             duration_ms = int((frames / rate) * 1000)
# # #             logger.debug(f"Calculated duration for {filepath}: {duration_ms}ms")
# # #             return duration_ms
# # #     except Exception as e:
# # #         logger.error(f"Error getting audio duration for {filepath}: {e}")
# # #         return 0
# # #
# # #
# # # def play_file(filepath, blocking=False, wait_percent=0.0):
# # #     """
# # #     Plays an audio file. If blocking, waits until wait_percent of the duration or end of media.
# # #     """
# # #     global _wait_loop, _wait_duration, _waiting
# # #
# # #     if not os.path.isfile(filepath):
# # #         logger.warning(f"File not found: {filepath}")
# # #         return
# # #
# # #     # Reset player state
# # #     media_player.stop()
# # #     media_player.setSource(QUrl.fromLocalFile(filepath))
# # #     file_duration = get_audio_file_duration(filepath)
# # #     logger.debug(
# # #         f"Playing file: {filepath}, duration: {file_duration}ms, blocking: {blocking}, wait_percent: {wait_percent}")
# # #
# # #     if blocking:
# # #         _wait_duration = int(file_duration * max(0.0, min(1.0, wait_percent))) if wait_percent > 0.0 else file_duration
# # #         _wait_loop = QEventLoop()
# # #         _waiting = True
# # #
# # #         # Fallback timeout to prevent infinite blocking
# # #         # timeout = max(file_duration + 1000, 5000)  # Duration + 1s or 5s minimum
# # #         QTimer.singleShot(_wait_duration, lambda: _wait_loop.quit() if _wait_loop else None)
# # #
# # #         media_player.play()
# # #         logger.debug(f"Starting blocking playback, waiting for {_wait_duration}ms or EndOfMedia")
# # #         _wait_loop.exec()  # Use exec() instead of exec_()
# # #         logger.debug("Blocking playback completed")
# # #
# # #         # Clean up global state
# # #         _waiting = False
# # #         _wait_loop = None
# # #         _wait_duration = 0
# # #     else:
# # #         media_player.play()
# # #         logger.debug("Started non-blocking playback")
# # #
# # #
# # # def is_playing():
# # #     """
# # #     Returns True if audio is currently playing.
# # #     """
# # #     is_active = (media_player.playbackState() == QMediaPlayer.PlayingState and
# # #                  media_player.mediaStatus() not in [QMediaPlayer.EndOfMedia, QMediaPlayer.NoMedia,
# # #                                                     QMediaPlayer.InvalidMedia])
# # #     logger.debug(
# # #         f"is_playing check: playbackState={media_player.playbackState()}, mediaStatus={media_player.mediaStatus()}, result={is_active}")
# # #     return is_active
# # #
# # #
# # # def play_url(url):
# # #     """
# # #     Plays audio from a URL.
# # #     """
# # #     if not url:
# # #         logger.warning("No URL provided")
# # #         return
# # #     media_player.stop()
# # #     media_player.setSource(QUrl(url))
# # #     media_player.play()
# # #     logger.debug(f"Playing URL: {url}")
# # #
# # #
# # # def play_audio_bytes(audio_bytes):
# # #     """
# # #     Plays audio from bytes using a temporary file.
# # #     """
# # #     if not audio_bytes:
# # #         logger.warning("No audio bytes provided")
# # #         return
# # #     with tempfile.NamedTemporaryFile(delete=True) as temp_file:
# # #         temp_file.write(audio_bytes)
# # #         temp_file.flush()
# # #         play_url(temp_file.name)
# # #         logger.debug("Playing audio from bytes")
# # #
# # #
# # # def wait_until_finished_speaking():
# # #     """Wait until the media player finishes playing."""
# # #     if not is_playing():
# # #         return
# # #     global _wait_loop, _waiting
# # #     # from src.utils.media import _wait_loop, _waiting
# # #     _wait_loop = QEventLoop()
# # #     _waiting = True
# # #
# # #     # Fallback timeout to prevent infinite blocking
# # #     QTimer.singleShot(5000, lambda: _wait_loop.quit() if _wait_loop else None)
# # #
# # #     _wait_loop.exec()  # Wait for EndOfMedia or error
# # #     _waiting = False
# # #     _wait_loop = None
# # #
# # # # import os
# # # # import tempfile
# # # # import wave
# # # # from PySide6.QtMultimedia import QMediaPlayer, QAudioOutput
# # # # from PySide6.QtCore import QUrl, QEventLoop
# # # #
# # # # # Initialize media player and audio output
# # # # media_player = QMediaPlayer()
# # # # audio_output = QAudioOutput()
# # # # media_player.setAudioOutput(audio_output)
# # # #
# # # # # Global state for tracking playback waiting conditions
# # # # _wait_loop = None
# # # # _wait_duration = 0
# # # # _waiting = False
# # # #
# # # # def _on_media_status_changed(status):
# # # #     """
# # # #     Persistent handler for mediaStatusChanged signal.
# # # #     Quits the event loop when playback reaches EndOfMedia or an error state.
# # # #     """
# # # #     global _wait_loop, _waiting
# # # #     if _waiting and status in [QMediaPlayer.EndOfMedia, QMediaPlayer.NoMedia, QMediaPlayer.InvalidMedia]:
# # # #         if _wait_loop:
# # # #             _wait_loop.quit()
# # # #
# # # # def _on_position_changed(position):
# # # #     """
# # # #     Persistent handler for positionChanged signal.
# # # #     Quits the event loop when the playback position reaches the desired wait_duration.
# # # #     """
# # # #     global _wait_loop, _wait_duration, _waiting
# # # #     if _waiting and _wait_duration > 0 and position >= _wait_duration:
# # # #         if _wait_loop:
# # # #             _wait_loop.quit()
# # # #
# # # # # Connect signals once at module initialization
# # # # media_player.mediaStatusChanged.connect(_on_media_status_changed)
# # # # media_player.positionChanged.connect(_on_position_changed)
# # # #
# # # # def get_audio_file_duration(filepath):
# # # #     """
# # # #     Returns the duration of a WAV audio file in milliseconds using the wave module.
# # # #     """
# # # #     try:
# # # #         with wave.open(filepath, 'rb') as wav_file:
# # # #             frames = wav_file.getnframes()
# # # #             rate = wav_file.getframerate()
# # # #             duration_ms = int((frames / rate) * 1000)
# # # #             return duration_ms
# # # #     except Exception as e:
# # # #         print(f"Error getting audio duration: {e}")
# # # #         return 0
# # # #
# # # # def play_file(filepath, blocking=False, wait_percent=0.0):
# # # #     """
# # # #     Plays an audio file. If blocking, waits until wait_percent of the duration or end of media.
# # # #     """
# # # #     global _wait_loop, _wait_duration, _waiting
# # # #
# # # #     if not os.path.isfile(filepath):
# # # #         return
# # # #
# # # #     # Stop any ongoing playback to ensure clean state
# # # #     media_player.stop()
# # # #     media_player.setSource(QUrl.fromLocalFile(filepath))
# # # #     file_duration = get_audio_file_duration(filepath)
# # # #
# # # #     if blocking:
# # # #         _wait_duration = int(file_duration * max(0.0, min(1.0, wait_percent))) if wait_percent > 0.0 else file_duration
# # # #         _wait_loop = QEventLoop()
# # # #         _waiting = True
# # # #
# # # #         media_player.play()
# # # #         _wait_loop.exec_()  # Wait for EndOfMedia or wait_duration
# # # #
# # # #         # Clean up global state
# # # #         _waiting = False
# # # #         _wait_loop = None
# # # #         _wait_duration = 0
# # # #     else:
# # # #         media_player.play()
# # # #
# # # # def is_playing():
# # # #     """
# # # #     Returns True if audio is currently playing.
# # # #     """
# # # #     return (media_player.playbackState() == QMediaPlayer.PlayingState and
# # # #             media_player.mediaStatus() not in [QMediaPlayer.EndOfMedia, QMediaPlayer.NoMedia, QMediaPlayer.InvalidMedia])
# # # #
# # # #
# # # # def wait_until_finished_speaking():
# # # #     """Wait until the media player finishes playing."""
# # # #     # from src.utils.media import is_playing
# # # #     if not is_playing():
# # # #         return
# # # #
# # # #     global _wait_loop, _waiting
# # # #     _wait_loop = QEventLoop()
# # # #     _waiting = True
# # # #     _wait_loop.exec()
# # # #     _waiting = False
# # # #     _wait_loop = None
# # # #
# # # #
# # # # def play_url(url):
# # # #     """
# # # #     Plays audio from a URL.
# # # #     """
# # # #     if not url:
# # # #         return
# # # #     media_player.stop()
# # # #     media_player.setSource(QUrl(url))
# # # #     media_player.play()
# # # #
# # # # def play_audio_bytes(audio_bytes):
# # # #     """
# # # #     Plays audio from bytes using a temporary file.
# # # #     """
# # # #     if not audio_bytes:
# # # #         return
# # # #     with tempfile.NamedTemporaryFile(delete=True) as temp_file:
# # # #         temp_file.write(audio_bytes)
# # # #         temp_file.flush()
# # # #         play_url(temp_file.name)
# # # #
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