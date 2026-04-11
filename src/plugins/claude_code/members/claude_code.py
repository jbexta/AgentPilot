"""Claude Code Member Module.

This module provides the ClaudeCode member class for integrating Claude Code SDK
into Agent Pilot workflows. It supports configurable built-in and custom tools.

Key Features:
- Integration with Claude Code SDK for code execution
- Configurable built-in tools (Bash, Read, Write, Edit, Glob, Grep, WebFetch, WebSearch)
- Custom tools from database
- System message formatting with blocks
"""

import asyncio
import json
from collections import defaultdict

from plugins.workflows.members import LlmMember
from utils.helpers import set_module_type
from claude_agent_sdk import (
    ClaudeAgentOptions, ClaudeSDKClient, AssistantMessage, TextBlock,
    HookMatcher, ThinkingBlock, ToolUseBlock,
    PermissionResultAllow, PermissionResultDeny,
)


@set_module_type(module_type='Members', settings='claude_code_settings')
class ClaudeCode(LlmMember):
    workflow_insert_mode = 'single'

    def __init__(self, **kwargs):
        super().__init__(**kwargs, model_config_key='chat.model')
        self._approval_future = None

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
        """Format tool name and input into a readable string.

        Parameters
        ----------
        tool_name : str
            Name of the tool (e.g., 'Bash', 'Write', 'Edit').
        input_dict : dict
            Tool input parameters.

        Returns
        -------
        str
            Formatted tool info for display in approval bubble.
        """
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
            if len(detail) > 500:
                detail = detail[:500] + '...'
            return f"{header}\n{detail}"
        summary = json.dumps(input_dict, indent=2, default=str)
        if len(summary) > 500:
            summary = summary[:500] + '...'
        return f"{header}\n{summary}"

    async def _can_use_tool(self, tool_name, input_dict, context):
        """Callback for Claude Code SDK tool permission requests.

        Shows an approval bubble in the chat and waits for user decision.

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

    async def receive(self):
        stream = self.stream()

        role_responses = {}
        async for key, chunk in stream:
            if key not in role_responses:
                role_responses[key] = ''
            if key == 'tools':
                tool_list = chunk
                role_responses['tools'] = tool_list
            else:
                chunk = chunk or ''
                role_responses[key] += chunk
                yield key, chunk

        logging_obj = {
            'id': 0,
            'context_id': self.workflow.context_id,
            'member_id': self.full_member_id(),
            'role_responses': role_responses,
        }

        for key, response in role_responses.items():
            if response != '':
                self.workflow.save_message(key, response, self.full_member_id(), logging_obj)

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

        options = ClaudeAgentOptions(
            system_prompt=system_msg,
            max_turns=max_turns,
            tools=allowed_tools,
            can_use_tool=self._can_use_tool,
            **({"cwd": working_dir} if working_dir else {}),
            **({"hooks": hooks} if hooks else {}),
        )
        async with ClaudeSDKClient(options=options) as client:
            print(f"User: {prompt}")
            await client.query(prompt)
            async for msg in client.receive_response():
                print(str(msg))
                if isinstance(msg, AssistantMessage):
                    for block in msg.content:
                        if isinstance(block, TextBlock):
                            yield 'assistant', block.text
                        elif isinstance(block, ThinkingBlock):
                            yield 'thinking', block.thinking
                        elif isinstance(block, ToolUseBlock):
                            pass
                        else:
                            pass

    async def system_message(self, msgs_in_system=None, response_instruction='', msgs_in_system_len=0):
        name = self.config.get('name', '')
        builtin_blocks = {
            'char_name': name,
            'full_name': name,
            'response_type': 'response',
            'verb': '',
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
