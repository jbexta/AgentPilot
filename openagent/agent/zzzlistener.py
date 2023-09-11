import asyncio
import threading
import time
from queue import Queue
import speech_recognition as sr
import sounddevice as sd


class Listener:
    def __init__(self, is_speaking_func, send_message_func):
        self.__is_speaking_func = is_speaking_func
        self.__send_message_func = send_message_func

        # systemsound_thread = threading.Thread(target=self.systemsound_thread)
        # systemsound_thread.start()

        # listener_thread = threading.Thread(target=self.listen)
        # listener_thread.start()
        # # dialog_thread = threading.Thread(target=self.dialog_thread)
        # # dialog_thread.start()

    async def listen(self):  # , is_speaking_func, send_message_func):
        init_rec = sr.Recognizer()
        with sr.Microphone() as source:
            init_rec.adjust_for_ambient_noise(source, duration=2)
            while True:
                if await self.__is_speaking_func():
                    await asyncio.sleep(0.05)
                    continue
                try:
                    audio = init_rec.listen(source)  # , timeout=3)
                    text = init_rec.recognize_google(audio)
                    # if 'hey michael' not in text.lower(): continue
                    text = text.lower().split('hey michael')[-1].strip()
                    if text == '': continue
                    self.__send_message_func(text)

                except sr.UnknownValueError:
                    pass
                except Exception as e:
                    if e is not sr.UnknownValueError:
                        print(e)
                        await asyncio.sleep(0.05)
    #
    #
    # def systemsound_thread(self):
    #     # Query all input devices and print them
    #     devices = sd.query_devices()
    #     for idx, device in enumerate(devices):
    #         print(f"Index: {idx}, Device Name: {device['name']}")
    #
    #     # Change this index to the index of your loopback device
    #     device_index = 0
    #
    #     # Set default device to loopback device
    #     sd.default.device = device_index
    #
    #     # Sample rate and duration
    #     fs = 44100  # Sample rate
    #     seconds = 3  # Duration of recording
    #
    #     myrecording = sd.rec(int(seconds * fs), samplerate=fs, channels=2)
    #     print("Recording Audio")
    #     sd.wait()  # Wait until recording is finished
    #     print("Audio recording complete, saving to file")
    #     write('output.wav', fs, myrecording)  # Save as WAV file