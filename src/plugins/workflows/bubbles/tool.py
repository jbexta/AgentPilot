import json
from typing import Dict, Any

import qasync
from PySide6.QtWidgets import QPushButton, QWidget

from gui import system
from plugins.workflows.bubbles import MessageBubble, MessageButton
from plugins.workflows.utils.runs import get_run_manager
from gui.gui_utils.helpers import find_main
from gui.gui_utils.layouts import CHBoxLayout
from utils.helpers import try_parse_json, message_button, message_extension, get_json_value
from gui.widgets.config_fields import ConfigFields


class ToolBubble(MessageBubble):
    def __init__(self, parent, message):
        super().__init__(
            parent=parent,
            message=message,
        )

    def setMarkdownText(self, text):
        display_text = get_json_value(text, 'text', 'Error parsing tool')
        super().setMarkdownText(text, display_text=display_text)

    @message_extension('tool_params')
    class ToolParams(ConfigFields):
        def __init__(self, parent):
            super().__init__(parent)
            parsed, config = try_parse_json(parent.message.content)
            if not parsed or 'method' in config:
                return
            tool_schema = system.manager.tools.get_param_schema(config['tool_uuid'])
            self.config: Dict[str, Any] = json.loads(config.get('args', '{}'))
            self.schema = tool_schema
            self.build_schema()
            self.load()

    @message_extension('confirm_bar')
    class ConfirmBar(QWidget):
        """Approve / Reject buttons, shown while the run awaits the user's
        decision on this tool call."""
        def __init__(self, parent):
            super().__init__(parent)
            self.msg_container = parent
            self.tool_call_id = get_json_value(parent.message.content, 'tool_call_id')
            self.layout = CHBoxLayout(self)
            btn_approve = QPushButton('Approve', self)
            btn_reject = QPushButton('Reject', self)
            btn_approve.clicked.connect(lambda: self.resolve(True))
            btn_reject.clicked.connect(lambda: self.resolve(False))
            self.layout.addWidget(btn_approve)
            self.layout.addWidget(btn_reject)
            self.layout.addStretch(1)
            get_run_manager().changed.connect(self.refresh)
            self.refresh()

        def refresh(self):
            context_id = self.msg_container.parent.workflow.context_id
            self.setVisible(get_run_manager().is_awaiting_confirm(context_id, self.tool_call_id))

        def resolve(self, approved):
            context_id = self.msg_container.parent.workflow.context_id
            get_run_manager().resolve_confirm(context_id, self.tool_call_id, approved)

    @message_button('btn_rerun')
    class RerunButton(MessageButton):
        def __init__(self, parent):
            super().__init__(parent=parent,
                             icon_path=':/resources/icon-run-solid.png')

        @qasync.asyncSlot()
        async def on_clicked(self):
            if self.msg_container.parent.workflow.responding:
                return
            # self.msg_container.btn_countdown.hide()

            bubble = self.msg_container.bubble
            member_id = self.msg_container.member_id
            parsed, tool_dict = try_parse_json(bubble.text)
            if not parsed:
                return

            method_id = tool_dict.get('method', None)
            if method_id:
                tool_args = json.loads(tool_dict.get('args') or '{}')
            else:
                tool_params_widget = self.msg_container.tool_params
                tool_args = tool_params_widget.get_config()
                tool_dict['args'] = json.dumps(tool_args)

            self.msg_container.check_to_start_a_branch(
                role=bubble.role,
                new_message=json.dumps(tool_dict),
                member_id=member_id
            )

            if method_id:
                method_tool = next(t for t in system.manager.tools.get_method_tools() if t['id'] == method_id)
                member = self.msg_container.parent.workflow.get_member_by_full_member_id(member_id)
                result = await system.manager.tools.call_method_tool(method_tool, tool_args, member.ui_refs)
            else:
                result = await system.manager.tools.compute_tool_async(tool_dict.get('tool_uuid', None), tool_args)
            tmp = json.loads(result)
            tmp['tool_call_id'] = tool_dict.get('tool_call_id', None)
            result = json.dumps(tmp)
            await self.msg_container.parent.workflow.send_message(result, role='result', as_member_id=member_id, feed_back=True)

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
            main = find_main()
            main.main_pages.settings_sidebar.page_buttons['tools'].click()
            tools_tree = main.main_pages.pages['Tools'].tree
            # select the tool
            for i in range(tools_tree.topLevelItemCount()):
                row_uuid = tools_tree.topLevelItem(i).text(2)
                if row_uuid == self.tool_id:
                    tools_tree.setCurrentItem(tools_tree.topLevelItem(i))