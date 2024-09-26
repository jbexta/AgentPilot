import re
from src.gui.config import ConfigFields
from src.gui.widgets import PythonHighlighter
from src.members.base import Member

from src.plugins.openinterpreter.src import interpreter
from src.utils.helpers import convert_model_json_to_obj


class Parser(Member):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        pass

    async def run_member(self):
        """The entry response method for the member."""
        pass
        # async for key, chunk in self.compute():  # stream=True):
        #     if self.workflow.stop_requested:
        #         self.workflow.stop_requested = False
        #         break
        #     self.main.new_sentence_signal.emit(key, self.member_id, chunk)  # todo check if order of this is causing scroll issue


class RegexParser(Parser):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        pass

    # async def compute(self):
    #     """The entry response method for the member."""
    #     content = await self.get_content()
    #     self.workflow.save_message('block', content, self.member_id)  # , logging_obj)
    #     yield 'block', content


class XMLParser(Member):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        pass

    async def run_member(self):
        """The entry response method for the member."""

    # async def compute(self):
    #     """The entry response method for the member."""
    #     code_lang = self.config.get('code_language', 'Python')
    #     content = await self.get_content(run_sub_blocks=False)
    #     try:
    #         oi_res = interpreter.computer.run(code_lang, content)
    #         output = next(r for r in oi_res if r['format'] == 'output').get('content', '')
    #     except Exception as e:
    #         output = str(e)
    #     yield 'block', output.strip()


class XMLParserSettings(ConfigFields):
    def __init__(self, parent):
        super().__init__(parent=parent)
        self.schema.extend([
            {
                'text': 'Block type',
                'type': 'PluginComboBox',
                'plugin_type': 'Block',
                'allow_none': False,
                'default': 'Text',
                'row_key': 0,
            },
            {
                'text': 'Data',
                'type': str,
                'default': '',
                'num_lines': 23,
                'stretch_x': True,
                'label_position': None,
            },
        ])


class CodeBlockSettings(ConfigFields):
    def __init__(self, parent):
        super().__init__(parent=parent)
        self.schema.extend([
            {
                'text': 'Block type',
                'type': 'PluginComboBox',
                'plugin_type': 'Block',
                'allow_none': False,
                'default': 'Text',
                'row_key': 0,
            },
            {
                'text': 'Language',
                'type':
                ('AppleScript', 'HTML', 'JavaScript', 'Python', 'PowerShell', 'R', 'React', 'Ruby', 'Shell',),
                'width': 100,
                'tooltip': 'The language of the code to be passed to open interpreter',
                'label_position': None,
                'row_key': 0,
                'default': 'Python',
            },
            {
                'text': 'Data',
                'type': str,
                'default': '',
                'num_lines': 23,
                'stretch_x': True,
                'highlighter': PythonHighlighter,
                'label_position': None,
            },
        ])


class PromptBlockSettings(ConfigFields):
    def __init__(self, parent):
        super().__init__(parent=parent)
        self.schema.extend([
            {
                'text': 'Block type',
                'type': 'PluginComboBox',
                'plugin_type': 'Block',
                'allow_none': False,
                'default': 'Text',
                'row_key': 0,
            },
            {
                'text': 'Model',
                'key': 'prompt_model',
                'type': 'ModelComboBox',
                'label_position': None,
                'default': 'default',
                'row_key': 0,
            },
            {
                'text': 'Data',
                'type': str,
                'default': '',
                'num_lines': 23,
                'stretch_x': True,
                'label_position': None,
            },
        ])