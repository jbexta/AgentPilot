import json
from typing import Dict, Any

from src.gui.bubbles.base import MessageBubble, MessageButton
from src.utils.helpers import try_parse_json, message_button, message_extension, get_json_value
from src.gui.widgets.config_fields import ConfigFields


class ToolBubble(MessageBubble):
    def __init__(self, parent, message):
        super().__init__(
            parent=parent,
            message=message,
            autorun_button='btn_rerun',
            autorun_secs=5,
        )

    def setMarkdownText(self, text):
        display_text = get_json_value(text, 'text', 'Error parsing tool')
        super().setMarkdownText(text, display_text=display_text)

    @message_extension('tool_params')
    class ToolParams(ConfigFields):
        def __init__(self, parent):
            super().__init__(parent)
            from src.system import manager
            parsed, config = try_parse_json(parent.message.content)
            if not parsed:
                return
            tool_schema = manager.tools.get_param_schema(config['tool_uuid'])
            self.config: Dict[str, Any] = json.loads(config.get('args', '{}'))
            self.schema = tool_schema
            self.build_schema()
            self.load()

    @message_button('btn_rerun')
    class RerunButton(MessageButton):
        def __init__(self, parent):
            super().__init__(parent=parent,
                             icon_path=':/resources/icon-run-solid.png')

        def on_clicked(self):
            if self.msg_container.parent.workflow.responding:
                return
            # self.msg_container.btn_countdown.hide()

            bubble = self.msg_container.bubble
            member_id = self.msg_container.member_id
            parsed, tool_dict = try_parse_json(bubble.text)
            if not parsed:
                return

            tool_uuid = tool_dict.get('tool_uuid', None)
            tool_params_widget = self.msg_container.tool_params
            tool_args = tool_params_widget.get_config()
            tool_dict['args'] = json.dumps(tool_args)

            self.msg_container.check_to_start_a_branch(
                role=bubble.role,
                new_message=json.dumps(tool_dict),
                member_id=member_id
            )

            from src.system import manager
            result = manager.tools.compute_tool(tool_uuid, tool_args)
            tmp = json.loads(result)
            tmp['tool_call_id'] = tool_dict.get('tool_call_id', None)
            result = json.dumps(tmp)
            self.msg_container.parent.send_message(result, role='result', as_member_id=member_id, feed_back=True, clear_input=False)

    @message_button('btn_goto_tool')
    class GotoToolButton(MessageButton):
        def __init__(self, parent):
            super().__init__(parent=parent,
                             icon_path=':/resources/icon-tool-small.png')
            content = self.msg_container.message.content
            self.tool_id = get_json_value(content, 'tool_uuid')
            if not self.tool_id:
                self.hide()

        def on_clicked(self):  # todo dupe code
            from src.gui.util import find_main_widget
            main = find_main_widget(self)
            main.main_menu.settings_sidebar.page_buttons['Tools'].click()
            tools_tree = main.main_menu.pages['Tools'].tree
            # select the tool
            for i in range(tools_tree.topLevelItemCount()):
                row_uuid = tools_tree.topLevelItem(i).text(2)
                if row_uuid == self.tool_id:
                    tools_tree.setCurrentItem(tools_tree.topLevelItem(i))
