import asyncio
import json
import sys
from collections import defaultdict

from plugins.workflows.members import LlmMember
from utils.helpers import set_module_type
from claude_agent_sdk import (
    ClaudeAgentOptions, ClaudeSDKClient, AssistantMessage, TextBlock,
    HookMatcher, ThinkingBlock, ToolUseBlock, ToolResultBlock,
    UserMessage,
    PermissionResultAllow, PermissionResultDeny,
)


def _format_tool_result(block):
    content = block.content or ''
    if isinstance(content, list):
        content = '\n'.join(
            s.get('text', '') if isinstance(s, dict) else str(s)
            for s in content
        )
    body = str(content).strip()[:500]
    prefix = 'Error: ' if getattr(block, 'is_error', False) else 'Result: '
    return (prefix + body) if body else prefix.rstrip(': ')


@set_module_type(module_type='Members', settings='claude_code_settings')
class ClaudeCode(LlmMember):
    workflow_insert_mode = 'single'

    def __init__(self, **kwargs):
        super().__init__(**kwargs, model_config_key='chat.model')
        self._approval_future = None
        self._question_future = None
        self._session_id = None

    def _build_allowed_tools(self):
        """Build the list of allowed tools from config.

        Combines built-in Claude Code tools (based on toggle settings) with
        custom tools from the database.

        Returns:
            list: List of allowed tool names
        """
        builtin_config = self.config.get('builtin_tools', {})

        tool_mapping = {
            'bash': 'Bash',
            'read': 'Read',
            'write': 'Write',
            'edit': 'Edit',
            'glob': 'Glob',
            'grep': 'Grep',
            'webfetch': 'WebFetch',
            'websearch': 'WebSearch',
        }

        default_enabled = ('bash', 'read', 'glob', 'grep')
        allowed = [
            name for key, name in tool_mapping.items()
            if builtin_config.get(key, key in default_enabled)
        ]

        custom_tool_ids = self.config.get('custom_tools.data', [])
        if custom_tool_ids:
            # Custom tools from database can be loaded and added here
            # Implementation depends on how custom tools integrate with Claude Code SDK
            pass

        return allowed if allowed else ['Bash']

    def _build_hooks(self):
        """Build SDK hooks dict from config.

        Returns
        -------
        dict or None
            Mapping of HookEvent to list[HookMatcher], or None if no
            hooks are configured.
        """
        hook_rows = self.config.get('hooks.data', [])
        if not hook_rows:
            return None

        def _make_callback(name):
            async def _hook_callback(input_dict, tool_use_id, ctx):
                from utils import system
                from utils.helpers import receive_workflow
                lookup_name = name.replace('-', '_').replace(' ', '_')
                for mgr in (system.manager.blocks,
                             system.manager.tools,
                             system.manager.entities):
                    if lookup_name in mgr:
                        config = mgr[lookup_name]
                        async for _ in receive_workflow(
                            config, params=input_dict,
                            main=system._main_gui,
                        ):
                            pass
                        return {}
                return {}
            return _hook_callback

        grouped = defaultdict(list)
        for row in hook_rows:
            event = row.get('event', 'PreToolUse')
            matcher = row.get('matcher', 'All')
            entity_val = row.get('entity', '')
            entity_name = entity_val.rsplit(':', 2)[0] if entity_val else ''
            if not entity_name or entity_name == 'Select entity...':
                continue

            grouped[event].append(
                HookMatcher(
                    matcher=None if matcher == 'All' else matcher,
                    hooks=[_make_callback(entity_name)],
                )
            )

        return dict(grouped) if grouped else None

    def _format_tool_info(self, tool_name, input_dict):
        """Format tool name and input into a readable string."""
        header = f"Tool: {tool_name}"
        key_map = {
            'Bash': 'command',
            'Write': 'file_path',
            'Read': 'file_path',
            'Edit': 'file_path',
            'Glob': 'pattern',
            'Grep': 'pattern',
        }
        primary_key = key_map.get(tool_name)
        if primary_key and primary_key in input_dict:
            detail = str(input_dict[primary_key])
        else:
            detail = json.dumps(input_dict, indent=2, default=str)
        if len(detail) > 500:
            detail = detail[:500] + '...'
        return f"{header}\n{detail}"

    async def _can_use_tool(self, tool_name, input_dict, context):
        """Callback for Claude Code SDK tool permission requests.

        Shows an approval bubble in the chat and waits for user decision.
        ``AskUserQuestion`` is routed to a dedicated question bubble that
        returns the user's selections as ``updated_input`` for the SDK.

        Parameters
        ----------
        tool_name : str
            Name of the tool requesting permission.
        input_dict : dict
            Tool input parameters.
        context : ToolPermissionContext
            Permission context from the SDK.

        Returns
        -------
        PermissionResult
            Allow or Deny based on user's button click.
        """
        if tool_name == 'AskUserQuestion':
            return await self._handle_ask_user_question(input_dict)

        self._approval_future = asyncio.get_event_loop().create_future()
        text = self._format_tool_info(tool_name, input_dict)
        chat_widget = self.workflow.chat_widget
        if chat_widget:
            chat_widget.new_sentence(
                'tool_approval',
                self.full_member_id(),
                text,
            )
        approved = await self._approval_future
        self._approval_future = None
        if approved:
            return PermissionResultAllow()
        return PermissionResultDeny(message="User rejected tool use")

    async def _handle_ask_user_question(self, input_dict):
        """Surface an AskUserQuestion payload to the user.

        Renders a ``QuestionBubble`` in the chat and awaits the user's
        answers. Returns ``PermissionResultAllow`` with ``updated_input``
        containing the original questions plus an ``answers`` dict keyed
        by question text, as required by the Claude Agent SDK contract.
        """
        self._question_future = asyncio.get_running_loop().create_future()
        chat_widget = self.workflow.chat_widget
        if chat_widget:
            chat_widget.new_sentence(
                'question',
                self.full_member_id(),
                json.dumps(input_dict),
            )
        answers = await self._question_future
        self._question_future = None
        return PermissionResultAllow(
            updated_input={
                'questions': input_dict.get('questions', []),
                'answers': answers or {},
            }
        )

    async def receive(self):
        # Save every yielded block as its own row immediately. Deferring
        # to end-of-turn would leave streaming bubbles with msg_id=-1,
        # which ``message_collection.refresh()`` wipes — so any
        # context/branch switch mid-stream drops the thinking and
        # tool-call history from the display. Each block also pops its
        # bubble-grouping slot so the next block of the same role
        # creates a fresh bubble instead of appending.
        async for key, chunk in self.stream():
            chunk = chunk or ''
            yield key, chunk
            chat = self.workflow.chat_widget
            if chat:
                chat.message_collection.last_member_bubbles.pop(
                    (key, self.full_member_id()), None)
            log_obj = {
                'id': 0,
                'context_id': self.workflow.context_id,
                'member_id': self.full_member_id(),
                'session_id': self._session_id,
            }
            self.workflow.save_message(
                key, chunk, self.full_member_id(), log_obj)

    async def stream(self, *args, **kwargs):
        system_msg = await self.system_message()
        max_turns = self.config.get('max_turns', None)
        messages = await self.get_messages()
        if len(messages) == 0:
            raise NotImplementedError()
        prompt = messages[-1].get('content', None)
        if prompt is None:
            raise NotImplementedError()

        allowed_tools = self._build_allowed_tools()
        working_dir = self.config.get('working_dir', None)
        hooks = self._build_hooks()

        def _stderr_cb(line):
            print(f"[claude-code stderr] {line}", file=sys.stderr, flush=True)

        options = ClaudeAgentOptions(
            system_prompt=system_msg,
            max_turns=max_turns,
            tools=allowed_tools,
            can_use_tool=self._can_use_tool,
            extra_args={"debug-to-stderr": None},
            stderr=_stderr_cb,
            **({"cwd": working_dir} if working_dir else {}),
            **({"hooks": hooks} if hooks else {}),
            **({"resume": self._session_id} if self._session_id else {}),
        )
        async with ClaudeSDKClient(options=options) as client:
            # Background watcher: when the user clicks the stop button
            # ``workflow.stop_requested`` flips to True. The SDK may be
            # blocked on a subprocess read, so the ``async for`` below
            # won't see the flag on its own. Calling ``client.interrupt``
            # sends a control-request to the CLI which unblocks the
            # current turn; the loop then observes the flag and breaks.
            stop_task = asyncio.create_task(self._watch_stop(client))
            try:
                print(f"User: {prompt}")
                await client.query(prompt)
                async for msg in client.receive_response():
                    if self.workflow and self.workflow.stop_requested:
                        break
                    print(str(msg))
                    if isinstance(msg, AssistantMessage):
                        if msg.session_id and not self._session_id:
                            self._session_id = msg.session_id
                        for block in msg.content:
                            if isinstance(block, TextBlock):
                                yield 'assistant', block.text
                            elif isinstance(block, ThinkingBlock):
                                yield 'thinking', block.thinking
                            elif isinstance(block, ToolUseBlock):
                                yield 'claude_tool', json.dumps({
                                    'name': block.name,
                                    'input': block.input or {},
                                })
                    elif isinstance(msg, UserMessage) and isinstance(msg.content, list):
                        for block in msg.content:
                            if isinstance(block, ToolResultBlock):
                                yield 'claude_tool_result', _format_tool_result(block)
            finally:
                stop_task.cancel()

    async def _watch_stop(self, client):
        while True:
            await asyncio.sleep(0.1)
            if self.workflow and self.workflow.stop_requested:
                try:
                    await client.interrupt()
                except Exception:
                    pass
                return

    def _get_current_page_source(self):
        """Get the source file path of the currently active page."""
        import sys
        main = self.workflow.chat_widget.main
        current_widget = main.main_pages.content.currentWidget()
        module = sys.modules.get(type(current_widget).__module__)
        return getattr(module, '__file__', '') or ''

    async def system_message(self, msgs_in_system=None, response_instruction='', msgs_in_system_len=0):
        name = self.config.get('name', '')
        builtin_blocks = {
            'char_name': name,
            'full_name': name,
            'response_type': 'response',
            'verb': '',
            'current_page': self._get_current_page_source(),
        }
        formatted_sys_msg = await self.format_config_value(
            'chat.sys_msg', additional_blocks=builtin_blocks)

        message_str = ''
        if msgs_in_system:
            if msgs_in_system_len > 0:
                msgs_in_system = msgs_in_system[-msgs_in_system_len:]
            message_str = "\n".join(
                f"""{msg['role']}: \"{msg['content'].strip().strip('"')}\"""" for msg in msgs_in_system)
            message_str = f"\n\nCONVERSATION:\n\n{message_str}\nassistant: "
        if response_instruction != '':
            response_instruction = f"\n\n{response_instruction}\n\n"

        return formatted_sys_msg + response_instruction + message_str
