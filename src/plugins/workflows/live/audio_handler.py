"""Qt Multimedia audio I/O for live voice.

Mic capture via ``QAudioSource`` and streaming PCM16 playback via ``QAudioSink``
at 24 kHz / mono / int16 (the GPT-Live API's native format). All Qt audio
objects must be created and used on the GUI thread (the qasync loop thread).
"""
import wave

from PySide6.QtCore import QObject, QTimer
from PySide6.QtMultimedia import QAudioFormat, QAudioSource, QAudioSink, QMediaDevices

SAMPLE_RATE = 24000
SAMPLE_WIDTH = 2  # int16
CHANNELS = 1


def _pcm_format():
    fmt = QAudioFormat()
    fmt.setSampleRate(SAMPLE_RATE)
    fmt.setChannelCount(CHANNELS)
    fmt.setSampleFormat(QAudioFormat.SampleFormat.Int16)
    return fmt


class AudioHandler(QObject):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._fmt = _pcm_format()

        self._source = None
        self._cap_io = None
        self._capture_cb = None
        self._captured = bytearray()

        self._sink = None
        self._play_io = None
        self._play_buffer = bytearray()
        self._drain_timer = QTimer(self)
        self._drain_timer.setInterval(10)
        self._drain_timer.timeout.connect(self._drain)

    # ---- capture ----
    def start_capture(self, callback=None):
        """Start mic capture. ``callback(pcm_bytes)`` is invoked per chunk (may be None)."""
        self._capture_cb = callback
        self._captured = bytearray()
        device = QMediaDevices.defaultAudioInput()
        self._source = QAudioSource(device, self._fmt, self)
        self._cap_io = self._source.start()
        if self._cap_io is not None:
            self._cap_io.readyRead.connect(self._on_capture_ready)

    def _on_capture_ready(self):
        if self._cap_io is None:
            return
        data = self._cap_io.readAll()
        if not data:
            return
        chunk = bytes(data.data())
        self._captured.extend(chunk)
        if self._capture_cb is not None:
            self._capture_cb(chunk)

    def stop_capture(self):
        """Stop mic capture and return all captured PCM bytes."""
        if self._source is not None:
            self._source.stop()
            self._source = None
        self._cap_io = None
        self._capture_cb = None
        return bytes(self._captured)

    # ---- playback ----
    def start_playback(self):
        if self._sink is not None:
            return
        device = QMediaDevices.defaultAudioOutput()
        self._sink = QAudioSink(device, self._fmt, self)
        self._play_io = self._sink.start()
        self._play_buffer = bytearray()
        self._drain_timer.start()

    def play_pcm(self, pcm_bytes):
        if self._sink is None:
            self.start_playback()
        self._play_buffer.extend(pcm_bytes)
        self._drain()

    def _drain(self):
        if self._sink is None or self._play_io is None:
            return
        while self._play_buffer:
            free = self._sink.bytesFree()
            if free <= 0:
                break
            chunk = bytes(self._play_buffer[:free])
            written = self._play_io.write(chunk)
            if written <= 0:
                break
            del self._play_buffer[:written]

    def stop(self):
        """Instant silence — used for barge-in."""
        self._drain_timer.stop()
        self._play_buffer = bytearray()
        if self._sink is not None:
            self._sink.stop()
            self._sink = None
        self._play_io = None

    def close(self):
        self.stop()
        self.stop_capture()

    # ---- files ----
    @staticmethod
    def write_wav(path, pcm_bytes):
        with wave.open(path, 'wb') as wav:
            wav.setnchannels(CHANNELS)
            wav.setsampwidth(SAMPLE_WIDTH)
            wav.setframerate(SAMPLE_RATE)
            wav.writeframes(pcm_bytes)
        return path

    @staticmethod
    def read_wav_pcm(path):
        """Read a WAV file and return raw PCM16 mono 24 kHz bytes (resampling if needed)."""
        import audioop
        with wave.open(path, 'rb') as wav:
            n_channels = wav.getnchannels()
            sampwidth = wav.getsampwidth()
            framerate = wav.getframerate()
            pcm = wav.readframes(wav.getnframes())
        if sampwidth != SAMPLE_WIDTH:
            pcm = audioop.lin2lin(pcm, sampwidth, SAMPLE_WIDTH)
            sampwidth = SAMPLE_WIDTH
        if n_channels == 2:
            pcm = audioop.tomono(pcm, sampwidth, 0.5, 0.5)
        if framerate != SAMPLE_RATE:
            pcm, _ = audioop.ratecv(pcm, sampwidth, 1, framerate, SAMPLE_RATE, None)
        return pcm
