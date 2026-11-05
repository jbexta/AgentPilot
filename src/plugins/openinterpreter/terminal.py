from plugins.openinterpreter.languages.applescript import AppleScript
from plugins.openinterpreter.languages.html import HTML
from plugins.openinterpreter.languages.javascript import JavaScript
from plugins.openinterpreter.languages.powershell import PowerShell
from plugins.openinterpreter.languages.python import Python
from plugins.openinterpreter.languages.r import R
from plugins.openinterpreter.languages.react import React
from plugins.openinterpreter.languages.ruby import Ruby
from plugins.openinterpreter.languages.shell import Shell


class Terminal:
    def __init__(self, computer):
        self.computer = computer
        self.languages = [
            Ruby,
            Python,
            Shell,
            JavaScript,
            HTML,
            AppleScript,
            R,
            PowerShell,
            React,
        ]
        self._active_languages = {}

    def get_language(self, language):
        for lang in self.languages:
            if language.lower() == lang.name.lower() or (
                hasattr(lang, "aliases")
                and language.lower() in (alias.lower() for alias in lang.aliases)
            ):
                return lang
        return None

    def run(self, language, code, stream=False, display=False):
        if stream == False:
            # If stream == False, *pull* from _streaming_run.
            output_messages = []
            for chunk in self._streaming_run(language, code, display=display):
                if chunk.get("format") != "active_line":
                    # Should we append this to the last message, or make a new one?
                    if (
                        output_messages != []
                        and output_messages[-1].get("type") == chunk["type"]
                        and output_messages[-1].get("format") == chunk["format"]
                    ):
                        output_messages[-1]["content"] += chunk["content"]
                    else:
                        output_messages.append(chunk)
            return output_messages

        elif stream == True:
            # If stream == True, replace this with _streaming_run.
            return self._streaming_run(language, code, display=display)

    def _streaming_run(self, language, code, display=False):
        if language not in self._active_languages:
            # Get the language. Pass in self.computer *if it takes a single argument*
            # but pass in nothing if not. This makes custom languages easier to add / understand.
            lang_class = self.get_language(language)
            if lang_class.__init__.__code__.co_argcount > 1:
                self._active_languages[language] = lang_class(self.computer)
            else:
                self._active_languages[language] = lang_class()
        try:
            for chunk in self._active_languages[language].run(code):
                yield chunk

                # Print it also if display = True
                if (
                    display
                    and chunk.get("format") != "active_line"
                    and chunk.get("content")
                ):
                    print(chunk["content"], end="")

        except GeneratorExit:
            self.stop()

    def stop(self):
        for language in self._active_languages.values():
            language.stop()

    def terminate(self):
        for language_name in list(self._active_languages.keys()):
            language = self._active_languages[language_name]
            if (
                language
            ):  # Not sure why this is None sometimes. We should look into this
                language.terminate()
            del self._active_languages[language_name]
