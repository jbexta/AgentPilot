import logging
from pathlib import Path

import numpy as np
import onnxruntime
# import resampy  # silero-vad only supports 8000 Hz and 16000 Hz sampling rates, use a lightweight resample lib to handle, https://github.com/snakers4/silero-vad

logger = logging.getLogger(__name__)


class VoiceActivityDetector:
    def __init__(
            self,
            sample_rate,
            chunk_size,
            window_duration=1.0,
            silence_ratio=1.5,
            min_speech_duration=0.3,
            min_silence_duration=1.0,
            **kwargs
    ):
        """
        Initialize the Voice Activity Detector (VAD).

        :param sample_rate: Sampling rate of the audio stream.
        :param chunk_size: Number of frames per audio chunk.
        :param window_duration: Duration (in seconds) for noise RMS estimation.
        :param silence_ratio: Multiplier for noise RMS to set dynamic threshold.
        :param min_speech_duration: Minimum duration (in seconds) to consider as speech.
        :param min_silence_duration: Minimum duration (in seconds) to consider as silence.
        """
        self.sample_rate = sample_rate
        self.chunk_size = chunk_size
        self.window_size = int(window_duration * sample_rate / chunk_size)
        self.silence_ratio = silence_ratio
        self.min_speech_frames = int(min_speech_duration * sample_rate / chunk_size)
        self.min_silence_frames = int(min_silence_duration * sample_rate / chunk_size)

        self.noise_rms_history = []
        self.dynamic_threshold = None
        self.is_speech = False
        self.speech_counter = 0
        self.silence_counter = 0

    def calculate_rms(self, audio_data):
        """
        Calculate Root Mean Square (RMS) of the audio data.

        :param audio_data: Numpy array of audio samples.
        :return: RMS value.
        """
        # Ensure audio_data is a NumPy array of type float
        audio_data = np.array(audio_data, dtype=np.float32)

        # Replace NaNs and Infs with 0
        if not np.isfinite(audio_data).all():
            logger.warning("Audio data contains NaN or Inf. Replacing with zeros.")
            audio_data = np.nan_to_num(audio_data)

        # Calculate RMS with a small epsilon to prevent sqrt(0)
        mean_sq = np.mean(np.square(audio_data))

        # Handle cases where mean_sq might be negative due to numerical errors
        if mean_sq < 0:
            logger.warning(f"Mean square is negative ({mean_sq}). Setting to zero.")
            mean_sq = 0.0

        rms = np.sqrt(mean_sq + 1e-10)
        return rms

    def update_noise_rms(self, rms):
        """
        Update the noise RMS history and calculate dynamic threshold.

        :param rms: Current RMS value.
        """
        if len(self.noise_rms_history) < self.window_size:
            self.noise_rms_history.append(rms)
        else:
            self.noise_rms_history.pop(0)
            self.noise_rms_history.append(rms)

        if len(self.noise_rms_history) == self.window_size:
            noise_rms = np.mean(self.noise_rms_history)
            self.dynamic_threshold = noise_rms * self.silence_ratio
            logger.debug(f"Updated dynamic_threshold: {self.dynamic_threshold:.4f}")

    def is_speech_frame(self, rms):
        """
        Determine if the current frame contains speech.

        :param rms: Current RMS value.
        :return: Boolean indicating speech presence.
        """
        if self.dynamic_threshold is None:
            return False
        return rms > self.dynamic_threshold

    def process_audio_chunk(self, audio_data):
        """
        Process an audio chunk to detect speech activity.

        :param audio_data: Numpy array of audio samples.
        :return: Tuple (speech_detected, is_speech)
        """
        rms = self.calculate_rms(audio_data)

        # Update noise RMS during initial phase
        if len(self.noise_rms_history) < self.window_size:
            self.update_noise_rms(rms)
            logger.debug(f"Noise RMS updated: {rms:.4f}")
            return (False, self.is_speech)

        speech = self.is_speech_frame(rms)

        if speech:
            self.speech_counter += 1
            self.silence_counter = 0
            if not self.is_speech and self.speech_counter >= self.min_speech_frames:
                self.is_speech = True
                self.speech_counter = 0
                logger.info("Speech started")
                return (True, self.is_speech)
        else:
            self.silence_counter += 1
            self.speech_counter = 0
            if self.is_speech and self.silence_counter >= self.min_silence_frames:
                self.is_speech = False
                self.silence_counter = 0
                logger.info("Speech ended")
                return (True, self.is_speech)

        return (False, self.is_speech)

    def reset(self):
        """Reset the VAD state."""
        self.noise_rms_history.clear()
        self.dynamic_threshold = None
        self.is_speech = False
        self.speech_counter = 0
        self.silence_counter = 0
        logger.info("VAD state reset")


class SileroVoiceActivityDetector:
    def __init__(
            self,
            sample_rate: int,
            chunk_size: int,
            min_speech_duration: float = 0.3,
            min_silence_duration: float = 1.0,
            model_path: str = "silero_vad.onnx",
            threshold: float = 0.5,
            window_size_samples: int = 512,
            **kwargs
    ):
        """
        Initialize Silero VAD.
        Args:
            sample_rate: Sampling rate of the audio stream.
            chunk_size: Number of frames per audio chunk.
            min_speech_duration: Minimum duration (in seconds) to consider as speech.
            min_silence_duration: Minimum duration (in seconds) to consider as silence.
            model_path: Path to ONNX model file
            threshold: VAD threshold (0-1). Speech is detected if the model's output probability is above this value.
            window_size_samples: Window size (in samples) that the model processes internally. This affects the model's internal processing.
        """
        self.sample_rate = sample_rate
        self.chunk_size = chunk_size
        self.threshold = threshold
        self.window_size_samples = window_size_samples

        # Target sample rate for Silero VAD
        self.vad_sample_rate = 16000

        # Convert durations to frame counts
        self.min_speech_frames = int(min_speech_duration * sample_rate / chunk_size)
        self.min_silence_frames = int(min_silence_duration * sample_rate / chunk_size)

        # Initialize state variables
        self.is_speech = False
        self.speech_counter = 0
        self.silence_counter = 0

        # Initialize hidden states for ONNX model
        self.reset_states()

        # Load ONNX model
        self._init_onnx_model(model_path)

        logger.info(
            f"Initialized Silero VAD with: sample_rate={sample_rate}, "
            f"min_speech_frames={self.min_speech_frames}, "
            f"min_silence_frames={self.min_silence_frames}"
        )

    def reset_states(self):
        """Reset the hidden states for the model."""
        self.h = np.zeros((2, 1, 64), dtype=np.float32)
        self.c = np.zeros((2, 1, 64), dtype=np.float32)

    def _init_onnx_model(self, model_path: str):
        """Initialize ONNX runtime session with optimized settings."""
        if not Path(model_path).exists():
            raise FileNotFoundError(f"Model file not found: {model_path}")

        try:
            # Optimize ONNX Runtime settings
            sess_options = onnxruntime.SessionOptions()
            sess_options.intra_op_num_threads = 1  # Limit to single thread
            sess_options.graph_optimization_level = onnxruntime.GraphOptimizationLevel.ORT_ENABLE_ALL

            # Initialize ONNX Runtime session
            self.session = onnxruntime.InferenceSession(
                model_path,
                sess_options,
                providers=['CPUExecutionProvider']
            )
            logger.info(f"Successfully loaded ONNX model from {model_path}")
        except Exception as e:
            logger.error(f"Failed to load ONNX model: {str(e)}")
            raise

    def _preprocess_audio(self, audio_data: np.ndarray) -> np.ndarray:
        """
        Preprocess audio data for VAD.

        Args:
            audio_data: Input audio chunk

        Returns:
            Preprocessed audio data
        """
        try:
            # Convert to float32 and normalize if needed
            if audio_data.dtype != np.float32:
                audio_data = audio_data.astype(np.float32)
                np.divide(audio_data, 32768.0, out=audio_data)  # In-place normalization

            # Resample if needed
            if self.sample_rate != self.vad_sample_rate:
                # audio_data = resampy.resample(
                #    audio_data,
                #    self.sample_rate,
                #    self.vad_sample_rate,
                #    filter='kaiser_fast'  # Use fast filter for better performance
                # )
                pass  # todo numba import

            return audio_data

        except Exception as e:
            logger.error(f"Error in audio preprocessing: {str(e)}")
            raise

    def process_audio_chunk(self, audio_data: np.ndarray) -> tuple[bool, bool]:
        """
        Process audio chunk and detect voice activity.

        Args:
            audio_data: Input audio chunk (numpy array)

        Returns:
            Tuple (speech_detected, is_speech):
                speech_detected: True if speech state changed
                is_speech: Current speech state
        """
        try:
            # Preprocess audio
            audio_data = self._preprocess_audio(audio_data)

            # Prepare input for ONNX model
            input_data = {
                'input': audio_data.reshape(1, -1),
                'sr': np.array(self.vad_sample_rate, dtype=np.int64),
                'h': self.h,
                'c': self.c
            }

            # Get VAD prediction and update hidden states
            outputs = self.session.run(
                None,  # Get all outputs
                input_data
            )

            # Update hidden states
            self.h = outputs[1]  # New hidden state
            self.c = outputs[2]  # New cell state
            speech_prob = outputs[0][0]  # Speech probability

            # Determine if speech is present
            speech = speech_prob > self.threshold

            # Update speech/silence counters and state
            if speech:
                self.speech_counter += 1
                self.silence_counter = 0
                if not self.is_speech and self.speech_counter >= self.min_speech_frames:
                    self.is_speech = True
                    self.speech_counter = 0
                    logger.debug("Speech started")
                    return True, True
            else:
                self.silence_counter += 1
                self.speech_counter = 0
                if self.is_speech and self.silence_counter >= self.min_silence_frames:
                    self.is_speech = False
                    self.silence_counter = 0
                    logger.debug("Speech ended")
                    return True, False

            return False, self.is_speech

        except Exception as e:
            logger.error(f"Error processing audio chunk: {str(e)}")
            return False, self.is_speech

    def reset(self):
        """Reset VAD state and hidden states."""
        self.is_speech = False
        self.speech_counter = 0
        self.silence_counter = 0
        self.reset_states()
        logger.info("VAD state reset")