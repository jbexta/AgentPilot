import asyncio
from src.plugins.openairealtimeclient.src import AudioHandler, InputHandler, RealtimeClient

# Initialize handlers
audio_handler = AudioHandler()
input_handler = InputHandler()
input_handler.loop = asyncio.get_running_loop()

# Initialize the realtime client
client = RealtimeClient(
    on_text_delta=lambda text: print(f"\nAssistant: {text}", end="", flush=True),
    on_audio_delta=lambda audio: audio_handler.play_audio(audio),
    on_input_transcript=lambda transcript: print(f"\nYou said: {transcript}\nAssistant: ", end="", flush=True),
    on_output_transcript=lambda transcript: print(f"{transcript}", end="", flush=True),
    # tools=tools,
)

# Start keyboard listener in a separate thread
listener = keyboard.Listener(on_press=input_handler.on_press)
listener.start()