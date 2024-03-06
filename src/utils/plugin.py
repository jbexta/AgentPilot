import importlib
import inspect

from PySide6.QtGui import QPalette, Qt
from PySide6.QtWidgets import QStyle, QStyleOptionComboBox, QStylePainter

from src.agent.base import Agent
from src.gui.widgets.base import BaseComboBox, AlignDelegate

# AGENT PLUGINS
from src.plugins.openinterpreter.modules.agent_plugin import Open_Interpreter
from src.plugins.openaiassistant.modules.agent_plugin import OpenAI_Assistant
from src.plugins.crewai.modules.agent_plugin import CrewAI_Agent
from src.plugins.crewai.modules.context_plugin import CrewAI_Workflow
# from agentpilot.plugins.autogen.modules.agent_plugin import


all_plugins = {
    'Agent': [
        Open_Interpreter,
        CrewAI_Agent,
        OpenAI_Assistant,
    ],
    'Workflow': {
        'crewai': CrewAI_Workflow,
    },
}


def get_plugin_agent_class(plugin_name, kwargs=None):
    if not plugin_name:
        return None  # Agent(**kwargs)
    if kwargs is None:
        kwargs = {}

    clss = next((AC(**kwargs) for AC in all_plugins['Agent'] if AC.__name__ == plugin_name), None)
    return clss


# def get_plugin_workflow_class(plugin_name, kwargs=None):
#     if not plugin_name:
#         return None  # Agent(**kwargs)
#     if kwargs is None:
#         kwargs = {}
#
#     clss = next((AC(**kwargs) for AC in agent_plugins['Workflow'] if AC.__name__ == plugin_name), None)
#     return clss


class PluginComboBox(BaseComboBox):
    def __init__(self, parent, **kwargs):
        super().__init__(parent=parent)
        self.setItemDelegate(AlignDelegate(self))
        self.setFixedWidth(175)
        self.setStyleSheet(
            "QComboBox::drop-down {border-width: 0px;} QComboBox::down-arrow {image: url(noimg); border-width: 0px;}")
        self.none_text = kwargs.get('none_text', "Choose Plugin")
        self.plugin_type = kwargs.get('plugin_type', None)
        self.load()

    def load(self):
        self.clear()
        self.addItem(self.none_text, "")

        for plugin in all_plugins[self.plugin_type]:
            self.addItem(plugin.__name__.replace('_', ' '), plugin.__name__)

        # plugins_package = importlib.import_module("agentpilot.plugins")
        # plugins_dir = os.path.dirname(plugins_package.__file__)
        # # Iterate over all directories in 'plugins_dir'
        # for plugin_name in os.listdir(plugins_dir):
        #     plugin_path = os.path.join(plugins_dir, plugin_name)
        #
        #     # Make sure it's a directory
        #     if not os.path.isdir(plugin_path):
        #         continue
        #
        #     try:
        #         plugin_module = importlib.import_module(f"agentpilot.plugins.{plugin_name}.modules.{type_str}_plugin")
        #
        #     except ImportError as e:
        #         continue
        #
        #     # Iterate over all classes in the 'agent_plugin' module
        #     for name, obj in inspect.getmembers(plugin_module):
        #         if inspect.isclass(obj) and issubclass(obj, self.plugin_type) and obj != self.plugin_type:
        #             self.addItem(name.replace('_', ' '), plugin_name)

    def paintEvent(self, event):
        painter = QStylePainter(self)
        option = QStyleOptionComboBox()

        # Init style options with the current state of this widget
        self.initStyleOption(option)

        # Draw the combo box without the current text (removes the default left-aligned text)
        painter.setPen(self.palette().color(QPalette.Text))
        painter.drawComplexControl(QStyle.CC_ComboBox, option)

        # Manually draw the text, centered
        text_rect = self.style().subControlRect(QStyle.CC_ComboBox, option, QStyle.SC_ComboBoxEditField)
        text_rect.adjust(18, 0, 0, 0)  # left, top, right, bottom

        current_text = self.currentText()
        painter.drawText(text_rect, Qt.AlignCenter, current_text)
