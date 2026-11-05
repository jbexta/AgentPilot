"""Zero-dependency voice-activity detection for the User member.

A simple RMS/energy detector over PCM16 frames using the stdlib ``audioop``.
Good enough to endpoint an utterance; swap in a real model later if needed.
"""
import audioop

# TODO: webrtcvad / silero-vad seam for more robust endpointing.


class LocalVAD:
    def __init__(
        self,
        silence_threshold_rms=500,
        min_silence_ms=700,
        min_speech_ms=200,
        sample_rate=24000,
        sample_width=2,
    ):
        self.silence_threshold_rms = silence_threshold_rms
        self.min_silence_ms = min_silence_ms
        self.min_speech_ms = min_speech_ms
        self.sample_rate = sample_rate
        self.sample_width = sample_width

        self._in_speech = False
        self._speech_ms = 0.0
        self._silence_ms = 0.0

    def reset(self):
        self._in_speech = False
        self._speech_ms = 0.0
        self._silence_ms = 0.0

    def _frame_ms(self, pcm_bytes):
        n_samples = len(pcm_bytes) / self.sample_width
        return (n_samples / self.sample_rate) * 1000.0

    def feed(self, pcm_bytes):
        """Feed a PCM16 chunk; return 'speech_started' / 'speech_stopped' on transitions, else None."""
        if not pcm_bytes:
            return None
        rms = audioop.rms(pcm_bytes, self.sample_width)
        dur_ms = self._frame_ms(pcm_bytes)

        if rms >= self.silence_threshold_rms:
            self._speech_ms += dur_ms
            self._silence_ms = 0.0
            if not self._in_speech and self._speech_ms >= self.min_speech_ms:
                self._in_speech = True
                return 'speech_started'
        else:
            if self._in_speech:
                self._silence_ms += dur_ms
                if self._silence_ms >= self.min_silence_ms:
                    self._in_speech = False
                    self._speech_ms = 0.0
                    self._silence_ms = 0.0
                    return 'speech_stopped'
            else:
                self._speech_ms = 0.0
        return None
