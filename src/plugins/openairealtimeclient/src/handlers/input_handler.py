import asyncio
from pynput import keyboard


class InputHandler:
    """
    Handles keyboard input for the chatbot.

    This class is responsible for capturing keyboard input and translating it into commands for the chatbot.

    Attributes:
        text_input (str): The current text input from the user.
        text_ready (asyncio.Event): An event that is set when the user has finished typing.
        command_queue (asyncio.Queue): A queue that stores commands for the chatbot.
        loop (asyncio.AbstractEventLoop): The event loop for the input handler.
    """
    def __init__(self):
        self.text_input = ""
        self.text_ready = asyncio.Event()
        self.command_queue = asyncio.Queue()
        self.loop = None

    def on_press(self, key):
        try:
            if key == keyboard.Key.space:
                self.loop.call_soon_threadsafe(
                    self.command_queue.put_nowait, ('space', None)
                )
            elif key == keyboard.Key.enter:
                self.loop.call_soon_threadsafe(
                    self.command_queue.put_nowait, ('enter', self.text_input)
                )
                self.text_input = ""
            elif key == keyboard.KeyCode.from_char('r'):
                self.loop.call_soon_threadsafe(
                    self.command_queue.put_nowait, ('r', None)
                )
            elif key == keyboard.KeyCode.from_char('q'):
                self.loop.call_soon_threadsafe(
                    self.command_queue.put_nowait, ('q', None)
                )
            elif hasattr(key, 'char'):
                if key == keyboard.Key.backspace:
                    self.text_input = self.text_input[:-1]
                else:
                    self.text_input += key.char
        except AttributeError:
            pass