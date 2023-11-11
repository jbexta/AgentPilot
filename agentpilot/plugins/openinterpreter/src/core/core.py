"""
This file defines the Interpreter class.
It's the main file. `import interpreter` will import an instance of this class.
"""
import traceback

# from ..utils.get_config import get_config
from .respond import respond
from ..code_interpreters.create_code_interpreter import create_code_interpreter
from ..llm.setup_llm import setup_llm
import appdirs
import os

from ..utils.truncate_output import truncate_output


class Interpreter:

    def __init__(self):
        self.__name__ = 'Interpreter'  # Temp patch for pyqt
        # State
        self.current_deltas = {}
        self._code_interpreters = {}

        # Settings
        self.local = False
        self.auto_run = False
        self.debug_mode = True
        self.max_output = 2000

        # LLM settings
        self.model = ""
        self.temperature = 0
        self.system_message = ""
        self.context_window = None
        self.max_tokens = None
        self.api_base = None
        self.api_key = None
        self.max_budget = None
        self._llm = None

        # Load config defaults
        config = {}  # get_config()
        self.__dict__.update(config)

    def get_chat_stream(self, base_agent):
        return self._openinterpreter_chat(base_agent)
    
    def _openinterpreter_chat(self, base_agent):
        # Setup the LLM
        if not self._llm:
            self._llm = setup_llm(self)
        try:
            yield from self._respond(base_agent)
        except StopIteration as e:
            return e.value

    def _respond(self, base_agent):
        try:
            yield from respond(self, base_agent)
        except StopIteration as e:
            return e.value

    def run_code(self, language, code):
        output = ''
        code_interpreters = {}
        try:
            # Fix a common error where the LLM thinks it's in a Jupyter notebook
            if language == "python" and code.startswith("!"):
                code = code[1:]
                language = "shell"

            # Get a code interpreter to run it
            # language = self.messages[-1]["language"]
            if language not in code_interpreters:
                code_interpreters[language] = create_code_interpreter(language)
            code_interpreter = code_interpreters[language]

            # # Yield a message, such that the user can stop code execution if they want to
            # try:
            #     yield {"executing": {"code": code, "language": language}}
            # except GeneratorExit:
            #     # The user might exit here.
            #     # We need to tell python what we (the generator) should do if they exit
            #     break

            # Yield each line, also append it to last messages' output
            # self.messages[-1]["output"] = ""
            for line in code_interpreter.run(code):
                # yield line
                if "output" in line:
                    # output = self.messages[-1]["output"]
                    output += "\n" + line["output"]

                    # Truncate output
                    output = truncate_output(output, 1000)
        except:
            output = traceback.format_exc().strip()
            # yield {"output": output.strip()}
            # interpreter.messages[-1]["output"] = output.strip()

        return output

    # def reset(self):
    #     self.messages = []
    #     self.conversation_filename = None
    #     for code_interpreter in self._code_interpreters.values():
    #         code_interpreter.terminate()
    #     self._code_interpreters = {}
