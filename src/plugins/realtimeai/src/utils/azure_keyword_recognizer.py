import azure.cognitiveservices.speech as speechsdk
from scipy.signal import resample_poly
import numpy as np


def convert_sample_rate(audio_data: np.ndarray, orig_sr: int = 24000, target_sr: int = 16000) -> np.ndarray:
    """
    Converts the sample rate of the given audio data from orig_sr to target_sr using polyphase filtering.

    Parameters:
    - audio_data: np.ndarray
        The input audio data as a NumPy array of type int16.
    - orig_sr: int
        Original sample rate of the audio data.
    - target_sr: int
        Desired sample rate after conversion.

    Returns:
    - np.ndarray
        The resampled audio data as a NumPy array of type int16.
    """
    from math import gcd
    divisor = gcd(orig_sr, target_sr)
    up = target_sr // divisor
    down = orig_sr // divisor

    # Convert to float for high-precision processing
    audio_float = audio_data.astype(np.float32)

    # Perform resampling
    resampled_float = resample_poly(audio_float, up, down)

    # Ensure the resampled data is within int16 range
    resampled_float = np.clip(resampled_float, -32768, 32767)

    # Convert back to int16
    resampled_int16 = resampled_float.astype(np.int16)

    return resampled_int16


class AzureKeywordRecognizer:
    """
    A class to recognize specific keywords from PCM audio streams using Azure Cognitive Services.
    """

    def __init__(self, model_file: str, callback, sample_rate: int = 16000, channels: int = 1):
        """
        Initializes the AzureKeywordRecognizer.

        :param model_file: Path to the keyword recognition model file.
        :type model_file: str
        """

        # Create a push stream to which we'll write PCM audio data
        self.sample_rate = sample_rate
        self.channels = channels

        # Validate the sample rate is either 16000 or 24000
        if sample_rate not in [16000, 24000]:
            raise ValueError("Invalid sample rate. Supported rates are 16000 and 24000.")
        # Validate the number of channels is 1
        if channels != 1:
            raise ValueError("Invalid number of channels. Only mono audio is supported.")

        self.audio_stream = speechsdk.audio.PushAudioInputStream()
        self.audio_config = speechsdk.audio.AudioConfig(stream=self.audio_stream)

        # Initialize the speech recognizer
        self.recognizer = speechsdk.KeywordRecognizer(
            audio_config=self.audio_config
        )

        # Connect callback functions to the recognizer
        self.recognizer.recognized.connect(self._on_recognized)
        self.recognizer.canceled.connect(self._on_canceled)

        # Define the keyword recognition model
        self.keyword_model = speechsdk.KeywordRecognitionModel(filename=model_file)

        if not callable(callback):
            raise ValueError("Callback must be a callable function.")

        self.keyword_detected_callback = callback

    def start_recognition(self):
        """
        Starts the keyword recognition process.

        :param callback: A function to be called when the keyword is detected.
                         It should accept a single argument with the recognition result.
        """
        # Start continuous keyword recognition
        self.recognizer.recognize_once_async(model=self.keyword_model)

    def stop_recognition(self):
        """
        Stops the keyword recognition process.
        """
        self.recognizer.stop_recognition_async()

    def push_audio(self, pcm_data):
        """
        Pushes PCM audio data to the recognizer.

        :param pcm_data: Numpy array of PCM audio samples.
        """
        if self.sample_rate == 24000:
            converted_audio = convert_sample_rate(pcm_data, orig_sr=24000, target_sr=16000)
            self.audio_stream.write(converted_audio.tobytes())
        else:
            self.audio_stream.write(pcm_data.tobytes())

    def _on_recognized(self, event: speechsdk.SpeechRecognitionEventArgs):
        """
        Internal callback when a keyword is recognized.
        """
        result = event.result
        if result.reason == speechsdk.ResultReason.RecognizedKeyword:
            print(f"Keyword detected")
            if self.keyword_detected_callback:
                self.keyword_detected_callback(result)

    def _on_canceled(self, event: speechsdk.SpeechRecognitionCanceledEventArgs):
        """
        Internal callback when recognition is canceled.
        """
        print(f"Recognition canceled: {event.reason}")
        if event.result.reason == speechsdk.ResultReason.Canceled:
            print(f"Cancellation details: {event.cancellation_details}")