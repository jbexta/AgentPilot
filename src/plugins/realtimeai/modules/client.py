import asyncio
import base64
import json

from src.plugins.realtimeai.src.aio.realtime_ai_client import RealtimeAIClient
from src.plugins.realtimeai.src.aio.realtime_ai_event_handler import RealtimeAIEventHandler
from src.plugins.realtimeai.src.models.audio_stream_options import AudioStreamOptions
from src.plugins.realtimeai.src.models.realtime_ai_events import *
from src.plugins.realtimeai.src.models.realtime_ai_options import RealtimeAIOptions
from src.plugins.realtimeai.src.utils.audio_capture import AudioCaptureEventHandler
from src.plugins.realtimeai.src.utils.audio_playback import AudioPlayer

import logging

from src.plugins.realtimeai.src.utils.function_tool import FunctionTool

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[logging.StreamHandler()]  # Streaming logs to the console
)

# Specific loggers for mentioned packages
logging.getLogger("utils.audio_playback").setLevel(logging.ERROR)
logging.getLogger("utils.audio_capture").setLevel(logging.ERROR)
logging.getLogger("utils.vad").setLevel(logging.ERROR)
logging.getLogger("realtime_ai").setLevel(logging.ERROR)
logging.getLogger("websockets.client").setLevel(logging.ERROR)

# Root logger for general logging
logger = logging.getLogger()


class RealtimeAIClientWrapper:
    """
    Initialized for each member to handle RealtimeAI interaction.
    """
    def __init__(self, member):
        from src.system.base import manager
        model_params = manager.providers.get_model_parameters('gpt-4o')  # todo temp
        api_key = model_params.get('api_key', None)

        self.member = member
        self.audio_player = AudioPlayer()

        options = RealtimeAIOptions(
            api_key=api_key,
            model="gpt-4o-realtime-preview",
            instructions="",
            modalities=["audio", "text"],
        )
        stream_options = AudioStreamOptions(
            sample_rate=24000,
            channels=1,
            bytes_per_sample=2
        )

        # Initialize RealtimeAIClient with event handler, creates websocket connection to service and set up to handle user's audio
        event_handler = MyRealtimeEventHandler(audio_player=self.audio_player, functions=None)
        self.client = RealtimeAIClient(options, stream_options, event_handler)  # self.MemberRealtimeClient(self, model_obj)
        event_handler.set_client(self.client)

    def load(self, model_obj, system_msg=''):
        from src.system.base import manager
        model_params = manager.providers.get_model_parameters(model_obj)
        api_key = model_params.get('api_key', None)
        temperature = model_params.get('temperature', 0.8)
        voice = model_params.get('voice', 'sage')

        options = RealtimeAIOptions(
            api_key=api_key,
            model="gpt-4o-realtime-preview",
            modalities=["audio", "text"],
            instructions=system_msg,  # You are a helpful assistant. Respond concisely.",
            turn_detection=None,  # or server vad
            # tools=functions.definitions,
            tool_choice="auto",
            temperature=temperature,
            max_output_tokens=1000,
            voice=voice,
            enable_auto_reconnect=True,
        )
        self.client.update_session(options)

    async def stream_realtime(self, model, messages, system_msg):
        await self.client.start()
        self.load(model, system_msg)
        # self.client._event_handler.on_audio_delta = lambda audio: self.audio_player.enqueue_audio_data(audio)
        try:
            # await self.client.connect()
            # asyncio.create_task(self.client.handle_messages())
            #
            # # Create a queue to store incoming text deltas
            output_transcript_queue = asyncio.Queue()
            output_audio_queue = asyncio.Queue()  # clear queue

            self.client._event_handler.on_audio_transcript_delta = lambda text: output_transcript_queue.put_nowait(text)
            # self.client._event_handler.on_audio_delta = lambda audio: output_audio_queue.put_nowait(audio)
            # Send the message to the realtime client
            await self.client.send_text('who are you')

            responding = True
            while responding or not output_transcript_queue.empty():
                try:
                    # Wait for text deltas with a timeout
                    text = await asyncio.wait_for(output_transcript_queue.get(), timeout=1.0)
                    yield self.member.default_role(), text
                except asyncio.TimeoutError:
                    responding = False

            all_audio_bytes = []
            while not output_audio_queue.empty():
                audio_bytestring: str = await output_audio_queue.get()
                audio_bytes = base64.b64decode(audio_bytestring)
                all_audio_bytes.append(audio_bytes)

            # Combine all audio bytes
            all_audio = b''.join(all_audio_bytes)

            # # Write audio to WAV file
            # with wave.open('/home/jb/Documents/output.wav', 'wb') as wav_file:
            #     # Set parameters (adjust these based on your audio format)
            #     n_channels = 1
            #     sample_width = 2  # Assuming 16-bit audio
            #     frame_rate = 24000  # Adjust this to match your audio's sample rate
            #     n_frames = len(all_audio) // (n_channels * sample_width)
            #     comp_type = 'NONE'
            #     comp_name = 'not compressed'
            #
            #     wav_file.setparams((n_channels, sample_width, frame_rate, n_frames, comp_type, comp_name))
            #     wav_file.writeframes(all_audio)

            base64_audio = base64.b64encode(all_audio).decode('utf-8')
            # # write audio to file

            yield 'audio', base64_audio

        except Exception as e:
            raise e

    # def stream_realtime(self, system_msg):
    #     try:
    #         await self.client.connect()
    #         asyncio.create_task(self.client.handle_messages())
    #
    #         # Create a queue to store incoming text deltas
    #         output_transcript_queue = asyncio.Queue()
    #         self.output_audio_queue = asyncio.Queue()  # clear queue
    #
    #         self.client.on_output_transcript = lambda text: output_transcript_queue.put_nowait(text)
    #         # self.client.on_audio_delta = lambda audio: output_audio_queue.put_nowait(audio)
    #         # Send the message to the realtime client
    #         await self.client.send_text('who are you')
    #
    #         responding = True
    #         while responding or not output_transcript_queue.empty():
    #             try:
    #                 # Wait for text deltas with a timeout
    #                 text = await asyncio.wait_for(output_transcript_queue.get(), timeout=1.0)
    #                 yield self.member.default_role(), text
    #             except asyncio.TimeoutError:
    #                 responding = False
    #
    #         all_audio_bytes = []
    #         while not self.output_audio_queue.empty():
    #             audio_bytes = await self.output_audio_queue.get()
    #             all_audio_bytes.append(audio_bytes)
    #
    #         # Combine all audio bytes
    #         all_audio = b''.join(all_audio_bytes)
    #
    #         # Write audio to WAV file
    #         with wave.open('/home/jb/Documents/output.wav', 'wb') as wav_file:
    #             # Set parameters (adjust these based on your audio format)
    #             n_channels = 1
    #             sample_width = 2  # Assuming 16-bit audio
    #             frame_rate = 24000  # Adjust this to match your audio's sample rate
    #             n_frames = len(all_audio) // (n_channels * sample_width)
    #             comp_type = 'NONE'
    #             comp_name = 'not compressed'
    #
    #             wav_file.setparams((n_channels, sample_width, frame_rate, n_frames, comp_type, comp_name))
    #             wav_file.writeframes(all_audio)
    #
    #         base64_audio = base64.b64encode(all_audio).decode('utf-8')
    #         # # write audio to file
    #         # with open('/home/jb/Documents/output.wav', 'wb') as f:
    #         #     for audio in all_audio_bytes:
    #         #         f.write(audio)
    #         #     f.flush()
    #         # all_audio = b''.join(all_audio_bytes)
    #         # str_all_audio = all_audio.decode('utf-8')
    #         yield 'audio', base64_audio
    #
    #     except Exception as e:
    #         raise e



class MyAudioCaptureEventHandler(AudioCaptureEventHandler):
    def __init__(self, client: RealtimeAIClient, event_handler: "MyRealtimeEventHandler", event_loop):
        """
        Initializes the event handler.

        :param client: Instance of RealtimeClient.
        :param event_handler: Instance of MyRealtimeEventHandler
        :param event_loop: The asyncio event loop.
        """
        self._client = client
        self._event_handler = event_handler
        self._event_loop = event_loop

    def send_audio_data(self, audio_data: bytes):
        """
        Sends audio data to the RealtimeClient.

        :param audio_data: Raw audio data in bytes.
        """
        logger.debug("Sending audio data to the client.")
        asyncio.run_coroutine_threadsafe(self._client.send_audio(audio_data), self._event_loop)

    def on_speech_start(self):
        """
        Handles actions to perform when speech starts.
        """
        logger.info("Local VAD: User speech started")
        if (self._client.options.turn_detection is None and
                self._event_handler.is_audio_playing()):
            logger.info("User started speaking while assistant is responding; interrupting the assistant's response.")
            asyncio.run_coroutine_threadsafe(self._client.clear_input_audio_buffer(), self._event_loop)
            asyncio.run_coroutine_threadsafe(self._client.cancel_response(), self._event_loop)
            self._event_handler.audio_player.drain_and_restart()

    def on_speech_end(self):
        """
        Handles actions to perform when speech ends.
        """
        logger.info("Local VAD: User speech ended")

        if self._client.options.turn_detection is None:
            logger.debug("Using local VAD; requesting the client to generate a response after speech ends.")
            asyncio.run_coroutine_threadsafe(self._client.generate_response(), self._event_loop)

    def on_keyword_detected(self, result):
        pass


class MyRealtimeEventHandler(RealtimeAIEventHandler):
    def __init__(self, audio_player: AudioPlayer, functions: FunctionTool):
        super().__init__()
        self._audio_player = audio_player
        self._lock = asyncio.Lock()
        self._client = None
        self._current_item_id = None
        self._current_audio_content_index = None
        self._call_id_to_function_name = {}
        self._functions = functions
        self._function_processing = False

        self.on_audio_delta = None
        self.on_audio_transcript_delta = None  # todo

    @property
    def audio_player(self):
        return self._audio_player

    def get_current_conversation_item_id(self):
        return self._current_item_id

    def get_current_audio_content_id(self):
        return self._current_audio_content_index

    def is_audio_playing(self):
        return self._audio_player.is_audio_playing()

    def is_function_processing(self):
        return self._function_processing

    def set_client(self, client: RealtimeAIClient):
        self._client = client

    async def on_error(self, event: ErrorEvent) -> None:
        logger.error(f"Error occurred: {event.error.message}")

    async def on_input_audio_buffer_speech_stopped(self, event: InputAudioBufferSpeechStopped) -> None:
        logger.info(f"Server VAD: Speech stopped at {event.audio_end_ms}ms, Item ID: {event.item_id}")

    async def on_input_audio_buffer_committed(self, event: InputAudioBufferCommitted) -> None:
        logger.debug(f"Audio Buffer Committed: {event.item_id}")

    async def on_conversation_item_created(self, event: ConversationItemCreated) -> None:
        logger.debug(f"New Conversation Item: {event.item}")

    async def on_response_created(self, event: ResponseCreated) -> None:
        logger.debug(f"Response Created: {event.response}")

    async def on_response_content_part_added(self, event: ResponseContentPartAdded) -> None:
        logger.debug(f"New Part Added: {event.part}")

    async def on_response_audio_delta(self, event: ResponseAudioDelta) -> None:
        logger.debug(
            f"Received audio delta for Response ID {event.response_id}, Item ID {event.item_id}, Content Index {event.content_index}")
        self._current_item_id = event.item_id
        self._current_audio_content_index = event.content_index
        self.handle_audio_delta(event)
        if self.on_audio_delta:
            self.on_audio_delta(event.delta)  # todo

    async def on_response_audio_transcript_delta(self, event: ResponseAudioTranscriptDelta) -> None:
        logger.info(f"Assistant transcription delta: {event.delta}")
        if self.on_audio_transcript_delta:
            self.on_audio_transcript_delta(event.delta)

    async def on_rate_limits_updated(self, event: RateLimitsUpdated) -> None:
        for rate in event.rate_limits:
            logger.debug(f"Rate Limit: {rate.name}, Remaining: {rate.remaining}")

    async def on_conversation_item_input_audio_transcription_completed(self,
                                                                       event: ConversationItemInputAudioTranscriptionCompleted) -> None:
        logger.info(f"User transcription complete: {event.transcript}")

    async def on_response_audio_done(self, event: ResponseAudioDone) -> None:
        logger.debug(f"Audio done for response ID {event.response_id}, item ID {event.item_id}")

    async def on_response_audio_transcript_done(self, event: ResponseAudioTranscriptDone) -> None:
        logger.debug(f"Audio transcript done: '{event.transcript}' for response ID {event.response_id}")

    async def on_response_content_part_done(self, event: ResponseContentPartDone) -> None:
        part_type = event.part.get("type")
        part_text = event.part.get("text", "")
        logger.debug(f"Content part done: '{part_text}' of type '{part_type}' for response ID {event.response_id}")

    async def on_response_output_item_done(self, event: ResponseOutputItemDone) -> None:
        item_content = event.item.get("content", [])
        if item_content:
            for item in item_content:
                if item.get("type") == "audio":
                    transcript = item.get("transcript")
                    if transcript:
                        logger.info(f"Assistant transcription complete: {transcript}")

    async def on_response_done(self, event: ResponseDone) -> None:
        logger.debug(
            f"Assistant's response completed with status '{event.response.get('status')}' and ID '{event.response.get('id')}'")

    async def on_session_created(self, event: SessionCreated) -> None:
        logger.info(f"Session created: {event.session}")

    async def on_session_updated(self, event: SessionUpdated) -> None:
        logger.info(f"Session updated: {event.session}")

    async def on_input_audio_buffer_speech_started(self, event: InputAudioBufferSpeechStarted) -> None:
        logger.info(f"Server VAD: User speech started at {event.audio_start_ms}ms for item ID {event.item_id}")
        if self._client.options.turn_detection is not None:
            await self._client.clear_input_audio_buffer()
            await self._client.cancel_response()
            await asyncio.threads.to_thread(self._audio_player.drain_and_restart)

    async def on_response_output_item_added(self, event: ResponseOutputItemAdded) -> None:
        logger.debug(f"Output item added for response ID {event.response_id} with item: {event.item}")
        if event.item.get("type") == "function_call":
            call_id = event.item.get("call_id")
            function_name = event.item.get("name")
            if call_id and function_name:
                # Properly acquire the lock with 'await' and spread the usage over two lines
                await self._lock.acquire()  # Wait until the lock is available, then acquire it
                try:
                    self._call_id_to_function_name[call_id] = function_name
                    logger.debug(f"Registered function call. Call ID: {call_id}, Function Name: {function_name}")
                finally:
                    # Ensure the lock is released even if an exception occurs
                    self._lock.release()
            else:
                logger.warning("Function call item missing 'call_id' or 'name' fields.")

    async def on_response_function_call_arguments_delta(self, event: ResponseFunctionCallArgumentsDelta) -> None:
        logger.debug(f"Function call arguments delta for call ID {event.call_id}: {event.delta}")

    async def on_response_function_call_arguments_done(self, event: ResponseFunctionCallArgumentsDone) -> None:
        call_id = event.call_id
        arguments_str = event.arguments

        # Acquire lock using asynchronous method
        await self._lock.acquire()
        try:
            function_name = self._call_id_to_function_name.pop(call_id, None)
        finally:
            # Make sure the lock is released even if an exception is raised
            self._lock.release()

        if not function_name:
            logger.error(f"No function name found for call ID: {call_id}")
            return

        try:
            self._function_processing = True
            logger.info(f"Executing function '{function_name}' with arguments: {arguments_str} for call ID {call_id}")
            function_output = await asyncio.threads.to_thread(self._functions.execute, function_name, arguments_str)
            logger.info(f"Function output for call ID {call_id}: {function_output}")
            await self._client.generate_response_from_function_call(call_id, function_output)
        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse arguments for call ID {call_id}: {e}")
            return
        finally:
            self._function_processing = False

    def on_unhandled_event(self, event_type: str, event_data: Dict[str, Any]):
        logger.warning(f"Unhandled Event: {event_type} - {event_data}")

    def handle_audio_delta(self, event: ResponseAudioDelta):
        delta_audio = event.delta
        if delta_audio:
            try:
                audio_bytes = base64.b64decode(delta_audio)
                self._audio_player.enqueue_audio_data(audio_bytes)
            except base64.binascii.Error as e:
                logger.error(f"Failed to decode audio delta: {e}")
        else:
            logger.warning("Received 'ResponseAudioDelta' event without 'delta' field.")


def get_vad_configuration(use_server_vad=False):
    """
    Configures the VAD settings based on the specified preference.

    :param use_server_vad: Boolean indicating whether to use server-side VAD.
                           Default is False for local VAD.
    :return: Dictionary representing the VAD configuration suitable for RealtimeAIOptions.
    """
    if use_server_vad:
        return {
            "type": "server_vad",
            "threshold": 0.5,
            "prefix_padding_ms": 300,
            "silence_duration_ms": 200
        }
    else:
        return None  # Local VAD typically requires no special configuration

