import asyncio
import pyaudio
import wave
import queue
import io
from typing import Optional

from pydub import AudioSegment
import threading

from ..client.realtime_client import RealtimeClient


class AudioHandler:
    """
    Handles audio input and output for the chatbot.

    Uses PyAudio for audio input and output, and runs a separate thread for recording and playing audio.

    When playing audio, it uses a buffer to store audio data and plays it continuously to ensure smooth playback.

    Attributes:
        format (int): The audio format (paInt16).
        channels (int): The number of audio channels (1).
        rate (int): The sample rate (24000).
        chunk (int): The size of the audio buffer (1024).
        audio (pyaudio.PyAudio): The PyAudio object.
        recording_stream (pyaudio.Stream): The stream for recording audio.
        recording_thread (threading.Thread): The thread for recording audio.
        recording (bool): Whether the audio is currently being recorded.
        streaming (bool): Whether the audio is currently being streamed.
        stream (pyaudio.Stream): The stream for streaming audio.
        playback_stream (pyaudio.Stream): The stream for playing audio.
        playback_buffer (queue.Queue): The buffer for playing audio.
        stop_playback (bool): Whether the audio playback should be stopped.
    """
    def __init__(self):
        # Audio parameters
        self.format = pyaudio.paInt16
        self.channels = 1
        self.rate = 24000
        self.chunk = 1024

        self.audio = pyaudio.PyAudio()

        # Recording params
        self.recording_stream: Optional[pyaudio.Stream] = None
        self.recording_thread = None
        self.recording = False

        # streaming params
        self.streaming = False
        self.stream = None

        # Playback params
        self.playback_stream = None
        self.playback_buffer = queue.Queue(maxsize=20)
        self.playback_event = threading.Event()
        self.playback_thread = None
        self.stop_playback = False

    def start_recording(self) -> bytes:
        """Start recording audio from microphone and return bytes"""
        if self.recording:
            return b''
        
        self.recording = True
        self.recording_stream = self.audio.open(
            format=self.format,
            channels=self.channels,
            rate=self.rate,
            input=True,
            frames_per_buffer=self.chunk
        )
        
        print("\nRecording... Press 'space' to stop.")
        
        self.frames = []
        self.recording_thread = threading.Thread(target=self._record)
        self.recording_thread.start()
        
        return b''  # Return empty bytes, we'll send audio later

    def _record(self):
        while self.recording:
            try:
                data = self.recording_stream.read(self.chunk)
                self.frames.append(data)
            except Exception as e:
                print(f"Error recording: {e}")
                break

    def stop_recording(self) -> bytes:
        """Stop recording and return the recorded audio as bytes"""
        if not self.recording:
            return b''
        
        self.recording = False
        if self.recording_thread:
            self.recording_thread.join()
        
        # Clean up recording stream
        if self.recording_stream:
            self.recording_stream.stop_stream()
            self.recording_stream.close()
            self.recording_stream = None
        
        # Convert frames to WAV format in memory
        wav_buffer = io.BytesIO()
        with wave.open(wav_buffer, 'wb') as wf:
            wf.setnchannels(self.channels)
            wf.setsampwidth(self.audio.get_sample_size(self.format))
            wf.setframerate(self.rate)
            wf.writeframes(b''.join(self.frames))
        
        # Get the WAV data
        wav_buffer.seek(0)
        return wav_buffer.read()

    async def start_streaming(self, client: RealtimeClient):
        """Start continuous audio streaming."""
        if self.streaming:
            return
        
        self.streaming = True
        self.stream = self.audio.open(
            format=self.format,
            channels=self.channels,
            rate=self.rate,
            input=True,
            frames_per_buffer=self.chunk
        )
        
        print("\nStreaming audio... Press 'q' to stop.")
        
        while self.streaming:
            try:
                # Read raw PCM data
                data = self.stream.read(self.chunk, exception_on_overflow=False)
                # Stream directly without trying to decode
                await client.stream_audio(data)
            except Exception as e:
                print(f"Error streaming: {e}")
                break
            await asyncio.sleep(0.01)

    def stop_streaming(self):
        """Stop audio streaming."""
        self.streaming = False
        if self.stream:
            self.stream.stop_stream()
            self.stream.close()
            self.stream = None

    def play_audio(self, audio_data: bytes):
        """Add audio data to the buffer"""
        try:
            self.playback_buffer.put_nowait(audio_data)
        except queue.Full:
            # If the buffer is full, remove the oldest chunk and add the new one
            self.playback_buffer.get_nowait()
            self.playback_buffer.put_nowait(audio_data)
        
        if not self.playback_thread or not self.playback_thread.is_alive():
            self.stop_playback = False
            self.playback_event.clear()
            self.playback_thread = threading.Thread(target=self._continuous_playback)
            self.playback_thread.start()

    def _continuous_playback(self):
        """Continuously play audio from the buffer"""
        self.playback_stream = self.audio.open(
            format=self.format,
            channels=self.channels,
            rate=self.rate,
            output=True,
            frames_per_buffer=self.chunk
        )

        while not self.stop_playback:
            try:
                audio_chunk = self.playback_buffer.get(timeout=0.1)
                self._play_audio_chunk(audio_chunk)
            except queue.Empty:
                continue
            
            if self.playback_event.is_set():
                break

        if self.playback_stream:
            self.playback_stream.stop_stream()
            self.playback_stream.close()
            self.playback_stream = None

    def _play_audio_chunk(self, audio_chunk):
        try:
            # Convert the audio chunk to the correct format
            audio_segment = AudioSegment(
                audio_chunk,
                sample_width=2,
                frame_rate=24000,
                channels=1
            )
            
            # Ensure the audio is in the correct format for playback
            audio_data = audio_segment.raw_data
            
            # Play the audio chunk in smaller portions to allow for quicker interruption
            chunk_size = 1024  # Adjust this value as needed
            for i in range(0, len(audio_data), chunk_size):
                if self.playback_event.is_set():
                    break
                chunk = audio_data[i:i+chunk_size]
                self.playback_stream.write(chunk)
        except Exception as e:
            print(f"Error playing audio chunk: {e}")

    def stop_playback_immediately(self):
        """Stop audio playback immediately."""
        self.stop_playback = True
        self.playback_buffer.queue.clear()  # Clear any pending audio
        self.currently_playing = False
        self.playback_event.set()

    def cleanup(self):
        """Clean up audio resources"""
        self.stop_playback_immediately()

        self.stop_playback = True
        if self.playback_thread:
            self.playback_thread.join()

        self.recording = False
        if self.recording_stream:
            self.recording_stream.stop_stream()
            self.recording_stream.close()
        
        if self.stream:
            self.stream.stop_stream()
            self.stream.close()

        self.audio.terminate()