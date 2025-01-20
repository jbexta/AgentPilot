import logging
import pyaudio
import numpy as np
import queue
import threading
import time
import wave
from typing import Optional

# Constants for PyAudio Configuration
FORMAT = pyaudio.paInt16
CHANNELS = 1
RATE = 24000  # Default sample rate
FRAMES_PER_BUFFER = 1024

logger = logging.getLogger(__name__)


class AudioPlayer:
    """Handles audio playback for decoded audio data using PyAudio."""

    def __init__(
        self,
        min_buffer_fill=3,
        max_buffer_size=0,
        enable_wave_capture=False,
        output_filename: Optional[str] = None,
        output_device_index: Optional[int] = None
    ):
        """
        Initializes the AudioPlayer with a pre-fetch buffer threshold.

        :param min_buffer_fill: Minimum number of buffers that should be filled before starting playback.
        :param max_buffer_size: Maximum size of the buffer queue. 0 means unlimited.
        :param enable_wave_capture: Flag to enable capturing played audio to wave files.
        :param output_filename: Filename for the wave capture, defaults to 'playback_output.wav'.
        :param output_device_index: Specific output device index to use. None for default.
        """
        self.initial_min_buffer_fill = min_buffer_fill
        self.min_buffer_fill = min_buffer_fill
        self.buffer = queue.Queue(maxsize=max_buffer_size)
        self.pyaudio_instance = pyaudio.PyAudio()
        self.stream = None
        self.stop_event = threading.Event()
        self.playback_complete_event = threading.Event()
        self.buffer_lock = threading.Lock()
        self.enable_wave_capture = enable_wave_capture
        self.output_filename = output_filename or "playback_output.wav"
        self.wave_file = None
        self.buffers_played = 0
        self.is_running = False
        self.thread = None
        self.output_device_index = output_device_index

        # Lock for thread-safe operations
        self.lock = threading.RLock()

        # Initialize wave file if capture is enabled
        if self.enable_wave_capture:
            self._initialize_wave_file()

    def _initialize_wave_file(self):
        """Sets up the wave file for capturing playback if enabled."""
        if self.enable_wave_capture:
            try:
                self.wave_file = wave.open(self.output_filename, "wb")
                self.wave_file.setnchannels(CHANNELS)
                self.wave_file.setsampwidth(self.pyaudio_instance.get_sample_size(FORMAT))
                self.wave_file.setframerate(RATE)
                logger.info(f"Wave file '{self.output_filename}' initialized for capture.")
            except Exception as e:
                logger.error(f"Error opening wave file for playback capture: {e}")
                self.enable_wave_capture = False

    def _start_thread(self):
        """Starts the playback thread."""
        self.thread = threading.Thread(target=self.playback_loop, daemon=True)
        self.thread.start()
        logger.info("Playback thread started.")

    def start(self):
        """
        Starts the audio playback stream and initializes necessary components.
        """
        with self.lock:
            if self.is_running:
                logger.warning("AudioPlayer is already running.")
                return

            # ensure the pyaudio instance is initialized
            if self.pyaudio_instance is None:
                self.pyaudio_instance = pyaudio.PyAudio()

            try:
                self.stream = self.pyaudio_instance.open(
                    format=FORMAT,
                    channels=CHANNELS,
                    rate=RATE,
                    output=True,
                    frames_per_buffer=FRAMES_PER_BUFFER,
                    output_device_index=self.output_device_index
                )
                logger.info(f"AudioPlayer started, stream: {self.stream}")

                self.is_running = True
                self.stop_event.clear()
                self.playback_complete_event.clear()
                self._start_thread()
                logger.info("AudioPlayer started.")

            except Exception as e:
                logger.error(f"Failed to start AudioPlayer: {e}")
                self.is_running = False
                self.stop_event.set()
                self.playback_complete_event.set()

    def stop(self):
        """
        Stops the audio playback stream and releases resources.
        """
        with self.lock:
            if not self.is_running:
                logger.warning("AudioPlayer is already stopped.")
                return

            self.stop_event.set()
            logger.info("Stop event set. Attempting to stop playback thread.")

            # Wait for playback thread to finish
            if self.thread and self.thread.is_alive():
                self.playback_complete_event.wait(timeout=5)
                self.thread.join(timeout=5)
                logger.info("Playback thread joined.")

            # Stop and close the stream
            if self.stream is not None:
                logger.info(f"Stopping stream: {self.stream}")
                try:
                    if self.stream.is_active():
                        self.stream.stop_stream()
                    self.stream.close()
                    self.stream = None  # Ensure stream reference is cleared
                    logger.info("PyAudio stream stopped and closed.")
                except Exception as e:
                    logger.error(f"Error stopping PyAudio stream: {e}")

            # Close the wave file if enabled
            if self.enable_wave_capture and self.wave_file is not None:
                try:
                    self.wave_file.close()
                    self.wave_file = None
                    logger.info(f"Wave file '{self.output_filename}' closed.")
                except Exception as e:
                    logger.error(f"Error closing wave file: {e}")

            self.is_running = False
            self.stop_event.clear()
            self.playback_complete_event.set()
            logger.info("AudioPlayer stopped and resources released.")

    def playback_loop(self):
        """Main loop that manages the audio playback."""
        logger.debug("Playback loop started.")
        self.playback_complete_event.clear()
        self.initial_buffer_fill()

        while not self.stop_event.is_set():
            try:
                data = self.buffer.get(timeout=0.1)
                if data is None:
                    logger.debug("None received from buffer; breaking playback loop.")
                    break

                # Write data to stream
                self._write_data_to_stream(data)

                with self.buffer_lock:
                    self.buffers_played += 1
                logger.debug(f"Audio played. Buffers played count: {self.buffers_played}")

            except queue.Empty:
                logger.debug("Playback queue empty; waiting for data.")
                continue
            except Exception as e:
                logger.error(f"Unexpected error in playback loop: {e}")
                break  # Exit loop on unexpected errors

        logger.info("Playback loop exiting.")
        self.playback_complete_event.set()

    def _write_data_to_stream(self, data: bytes):
        """Writes audio data to the PyAudio stream and handles wave file capture if enabled."""
        try:
            if self.stream:
                self.stream.write(data, exception_on_underflow=False)
                logger.debug("Data written to PyAudio stream.")
            if self.enable_wave_capture and self.wave_file:
                self.wave_file.writeframes(data)
                logger.debug("Data written to wave file.")
        except IOError as e:
            logger.error(f"I/O error during stream write: {e}")
            # Attempt to restart the stream
            try:
                if self.stream and not self.stream.is_stopped():
                    self.stream.stop_stream()
                if self.stream:
                    self.stream.start_stream()
                logger.info("PyAudio stream restarted after I/O error.")
            except Exception as restart_error:
                logger.error(f"Failed to restart PyAudio stream: {restart_error}")
        except Exception as e:
            logger.error(f"Unexpected error during stream write: {e}")

    def initial_buffer_fill(self):
        """Fills the buffer initially to ensure smooth playback start."""
        logger.debug("Starting initial buffer fill.")
        while not self.stop_event.is_set():
            with self.buffer_lock:
                current_size = self.buffer.qsize()
            if current_size >= self.min_buffer_fill:
                logger.debug("Initial buffer fill complete.")
                break
            time.sleep(0.01)  # Sleep briefly to yield control

    def enqueue_audio_data(self, audio_data: bytes):
        """Queues data for playback."""
        try:
            self.buffer.put_nowait(audio_data)
            logger.debug(f"Enqueued audio data. Queue size: {self.buffer.qsize()}")
        except queue.Full:
            logger.warning("Queue is full; dropping audio data.")

    def is_audio_playing(self) -> bool:
        """Checks if audio is currently playing."""
        with self.buffer_lock:
            buffer_not_empty = not self.buffer.empty()
        is_playing = buffer_not_empty
        logger.debug(f"Checking if audio is playing: Buffer not empty = {buffer_not_empty}, "
                     f"Is playing = {is_playing}")
        return is_playing

    def drain_and_restart(self):
        """Resets the playback state and clears the audio buffer without stopping playback."""
        with self.buffer_lock:
            logger.info("Draining and restarting playback state.")
            self._clear_buffer()
            self.buffers_played = 0
            self.min_buffer_fill = self.initial_min_buffer_fill
            logger.debug("Playback state reset and buffer cleared.")

    def _clear_buffer(self):
        """Clears all pending audio data from the buffer."""
        cleared_items = 0
        while not self.buffer.empty():
            try:
                self.buffer.get_nowait()
                cleared_items += 1
            except queue.Empty:
                break
        logger.debug(f"Cleared {cleared_items} items from the buffer.")

    def close(self):
        """Ensures resources are released by stopping playback and terminating PyAudio."""
        logger.info("Closing AudioPlayer.")
        self.stop()
        # Terminate PyAudio instance when closing
        if self.pyaudio_instance is not None:
            try:
                self.pyaudio_instance.terminate()
                self.pyaudio_instance = None
                logger.info("PyAudio instance terminated.")
            except Exception as e:
                logger.error(f"Error terminating PyAudio instance: {e}")
        logger.info("AudioPlayer resources have been released.")

    def __del__(self):
        """Ensures that resources are released upon deletion."""
        self.close()