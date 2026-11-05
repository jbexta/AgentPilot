import asyncio
import json
import os
import sys
import uuid
import warnings
from collections import defaultdict
from pathlib import Path

import psutil
from PySide6.QtWidgets import QApplication

from plugins.claude_code.utils.projects import resolve_cwd
from plugins.workflows.members import LlmMember
from plugins.workflows.utils.runs import get_run_manager
from utils import sql
from utils.helpers import convert_to_safe_case, set_module_type
from claude_agent_sdk import (
    ClaudeAgentOptions, ClaudeSDKClient, AssistantMessage, TextBlock,
    HookMatcher, ThinkingBlock, ToolUseBlock, ToolResultBlock,
    ServerToolUseBlock, ServerToolResultBlock, UserMessage, ResultMessage,
    ConversationResetMessage,
    PermissionResultAllow, PermissionResultDeny,
    create_sdk_mcp_server, tool,
)


def format_tool_result_content(content, is_error=False):
    """Format a tool-result block's content into a short display string.

    Accepts either a raw content payload (string or list of dict blocks,
    as found in JSONL session logs) or an SDK ``ToolResultBlock``.
    """
    if hasattr(content, 'content'):
        is_error = getattr(content, 'is_error', False)
        content = content.content or ''
    if isinstance(content, list):
        content = '\n'.join(
            s.get('text', '') if isinstance(s, dict) else str(s)
            for s in content
        )
    body = str(content or '').strip()[:500]
    prefix = 'Error: ' if is_error else 'Result: '
    return (prefix + body) if body else prefix.rstrip(': ')


CC_SETTINGS_PATH = Path.home() / '.claude' / 'agentpilot_cc_settings.json'


def force_subscription_settings():
    """Write (once) a settings file pinning Claude Code to subscription auth.

    AgentPilot resolves ``$ANTHROPIC_API_KEY`` from the environment for its
    own LiteLLM calls, and the CLI the SDK spawns inherits that environment.
    An API key beats stored OAuth, so without this the session bills the key
    rather than the user's logged-in plan. ``forceLoginMethod`` makes the CLI
    skip the key and use ``~/.claude/.credentials.json`` instead.

    Returns the path to pass as ``--settings``, or None if it can't be written.
    """
    desired = {'forceLoginMethod': 'claudeai'}
    try:
        CC_SETTINGS_PATH.parent.mkdir(parents=True, exist_ok=True)
        try:
            current = json.loads(CC_SETTINGS_PATH.read_text())
        except (OSError, ValueError):
            current = None
        if current != desired:
            CC_SETTINGS_PATH.write_text(json.dumps(desired, indent=2))
        return str(CC_SETTINGS_PATH)
    except OSError:
        return None


CONFIRM_HOOK_TIMEOUT = 7 * 24 * 3600  # the user may approve much later

# Inherited by everything a run's CLI spawns, even detached processes,
# so they can be found and stopped with it. Valued '<app pid>:<run id>'.
RUN_TAG_VAR = 'AP_CC_RUN'


def kill_tagged(prefix):
    """Kill every process whose run tag starts with *prefix*."""
    procs = []
    for proc in psutil.process_iter():
        try:
            if proc.environ().get(RUN_TAG_VAR, '').startswith(prefix):
                procs.append(proc)
        except psutil.Error:
            continue
    for proc in procs:
        try:
            proc.terminate()
        except psutil.NoSuchProcess:
            pass
    _, alive = psutil.wait_procs(procs, timeout=1)
    for proc in alive:
        try:
            proc.kill()
        except psutil.NoSuchProcess:
            pass


@set_module_type(module_type='Members', settings='claude_code_settings')
class ClaudeCode(LlmMember):
    workflow_insert_mode = 'single'

    def __init__(self, **kwargs):
        super().__init__(**kwargs, model_config_key='chat.model')
        self._question_future = None
        self._session_id = None
        self._ui_refs = []

    def _build_allowed_tools(self):
        """Build the list of built-in Claude Code tools from the toggle settings.

        Returns:
            list: List of allowed tool names
        """
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

        default_enabled = ('bash', 'read', 'write', 'edit', 'glob', 'grep')
        allowed = [
            name for key, name in tool_mapping.items()
            if self.config.get(f'builtin_tools.{key}', key in default_enabled)
        ]

        return allowed if allowed else ['Bash']

    def _ui_mcp_server(self):
        """An in-process MCP server serving the selected app and workflow tools,
        with the names to auto-approve and the names requiring the user's
        confirmation. None when no custom tools are selected."""
        from gui import system
        tools_manager = system.manager.tools
        uuids, method_tools = tools_manager.resolve_selection(
            self.config.get('custom_tools.data', [])
        )

        def as_mcp_result(result_json):
            result = json.loads(result_json)
            return {
                'content': [{'type': 'text', 'text': result['output']}],
                'is_error': result['status'] == 'error',
            }

        def method_handler(method_tool):
            async def handler(args):
                return as_mcp_result(
                    await tools_manager.call_method_tool(method_tool, args, self._ui_refs)
                )
            return handler

        def workflow_handler(tool_uuid):
            async def handler(args):
                return as_mcp_result(await tools_manager.compute_tool_async(tool_uuid, args))
            return handler

        sdk_tools = [
            tool(t['name'], t['description'], tools_manager.method_tool_schema(t))(method_handler(t))
            for t in method_tools
        ]
        confirm_names = {f'mcp__ui__{t["name"]}' for t in method_tools if t.get('confirm')}
        for tool_uuid in uuids:
            name = tools_manager.tool_id_names.get(tool_uuid)
            tool_config = tools_manager.get(name)
            if tool_config is None:
                continue
            sdk_tools.append(tool(
                convert_to_safe_case(name),
                tool_config.get('description', ''),
                self.transform_parameters(tool_config.get('params', [])),
            )(workflow_handler(tool_uuid)))
            if tool_config.get('options', {}).get('confirm'):
                confirm_names.add(f'mcp__ui__{convert_to_safe_case(name)}')
        if not sdk_tools:
            return None
        # Confirmation is enforced by `_confirm_hook` in every permission
        # mode, so all ui tools skip the SDK's own permission prompt.
        auto_approve = [f'mcp__ui__{t.name}' for t in sdk_tools]
        return create_sdk_mcp_server('ui', tools=sdk_tools), auto_approve, confirm_names

    async def _confirm_hook(self, input_dict, tool_use_id, context):
        """PreToolUse hook awaiting the user's approval of a confirm tool.
        Hooks run in every permission mode, unlike `_can_use_tool`."""
        label = input_dict.get('tool_name', '').removeprefix('mcp__ui__')
        approval = get_run_manager().request_confirm(self.workflow.context_id, tool_use_id, label=label)
        if approval is None:
            decision, reason = 'deny', 'This tool requires user approval, which is unavailable in this run'
        elif await approval:
            decision, reason = 'allow', 'Approved by the user'
        else:
            decision, reason = 'deny', 'User rejected tool use'
        return {
            'hookSpecificOutput': {
                'hookEventName': 'PreToolUse',
                'permissionDecision': decision,
                'permissionDecisionReason': reason,
            }
        }

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
                from gui import system
                from plugins.workflows.utils.workflows import receive_workflow
                lookup_name = name.replace('-', '_').replace(' ', '_')
                for mgr in (system.manager.blocks,
                             system.manager.tools,
                             system.manager.entities):
                    if lookup_name in mgr:
                        config = mgr[lookup_name]
                        async for _ in receive_workflow(
                            config, params=input_dict,
                            main=system.manager._main_gui,
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

    async def _can_use_tool(self, tool_name, input_dict, context):
        """Callback for Claude Code SDK tool permission requests.

        Shows accept/reject buttons on the matching tool-call bubble and
        waits for user decision.
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

        mode = self.config.get('chat.permission_mode', 'default')
        if mode == 'acceptEdits' and tool_name in (
            'Write', 'Edit', 'NotebookEdit',
        ):
            return PermissionResultAllow()

        prompt = '\n'.join(filter(None, (
            context.title, context.decision_reason, context.blocked_path,
        )))
        approval = get_run_manager().request_confirm(
            self.workflow.context_id, context.tool_use_id, label=prompt or tool_name,
        )
        if approval is None:
            return PermissionResultDeny(message='This tool requires user approval, which is unavailable in this run')
        if await approval:
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

    def _skills_options(self, working_dir):
        """Serve the app's skills to this session from the one fixed
        ``app_skills`` plugin folder. The folder can't vary per session, so
        the CWD rule — project-scoped skills are only available when the
        session's working_dir is that project's — is enforced by
        disallowing the Skill tool for every non-matching project skill.
        """
        from gui import system
        from utils import sql

        mgr = system.manager.skills
        wd = os.path.realpath(working_dir) if working_dir else None
        disallowed = []
        rows = sql.get_results("SELECT name, kind FROM skills") or []
        for name, kind in rows:
            if not (kind or '').startswith('PROJECT:'):
                continue
            project_dir = sql.get_scalar(
                "SELECT json_extract(config, '$.working_dir') FROM projects WHERE id = ?",
                (int(kind.split(':')[1]),)
            )
            if not wd or not project_dir or os.path.realpath(project_dir) != wd:
                disallowed.append(f'Skill(agentpilot:{mgr._slug(name)})')
        return {
            'plugins': [{'type': 'local', 'path': str(mgr.PLUGIN_DIR)}],
            **({'disallowed_tools': disallowed} if disallowed else {}),
        }

    async def stream(self, *args, **kwargs):
        system_msg = await self.system_message()
        max_turns = self.config.get('chat.max_turns', None)
        messages = await self.get_messages()
        if len(messages) == 0:
            raise NotImplementedError()
        prompt = messages[-1].get('content', None)
        if prompt is None:
            raise NotImplementedError()

        allowed_tools = self._build_allowed_tools()
        ui_server = self._ui_mcp_server()
        working_dir = resolve_cwd(
            await self.format_config_value('working_dir', '{{ cwd }}'))
        hooks = self._build_hooks() or {}
        if ui_server and ui_server[2]:
            hooks.setdefault('PreToolUse', []).append(HookMatcher(
                matcher='|'.join(sorted(ui_server[2])),
                hooks=[self._confirm_hook],
                timeout=CONFIRM_HOOK_TIMEOUT,
            ))
        permission_mode = self.config.get('chat.permission_mode', 'default')
        if not self._session_id:
            self._session_id = sql.get_scalar(
                "SELECT json_extract(log, '$.session_id') FROM contexts_messages "
                "WHERE context_id = ? AND member_id = ? "
                "AND json_extract(log, '$.session_id') IS NOT NULL "
                "ORDER BY id DESC LIMIT 1",
                (self.workflow.context_id, self.full_member_id()))

        def _stderr_cb(line):
            print(f"[claude-code stderr] {line}", file=sys.stderr, flush=True)

        extra_args = {}
        run_tag = f'{os.getpid()}:{uuid.uuid4().hex}'
        cc_env = {RUN_TAG_VAR: run_tag}
        if self.config.get('chat.force_subscription', False):
            cc_settings = force_subscription_settings()
            if cc_settings:
                extra_args["settings"] = cc_settings
            # Shadow the API-key vars for the spawned CLI only. AgentPilot
            # still needs them in its own environment for LiteLLM; the CLI
            # must not see them or it bills the key instead of the plan.
            cc_env |= {
                "ANTHROPIC_API_KEY": "",
                "ANTHROPIC_AUTH_TOKEN": "",
                "ANTHROPIC_BASE_URL": "",
            }

        if self.config.get('chat.sys_msg_mode', 'APPEND') == 'APPEND':
            system_msg = {
                'type': 'preset',
                'preset': 'claude_code',
                'append': system_msg,
            }

        model = self.config.get('chat.claude_model', '')
        options = ClaudeAgentOptions(
            system_prompt=system_msg,
            **({"model": model} if model else {}),
            max_turns=max_turns,
            effort=self.config.get('chat.effort', None),
            thinking={"type": "adaptive", "display": "summarized"},
            max_budget_usd=self.config.get('chat.max_budget', None),
            verbatim_prompts=self.config.get('chat.verbatim_prompts', False),
            strict_mcp_config=self.config.get('chat.strict_mcp', False),
            tools=allowed_tools,
            can_use_tool=self._can_use_tool,
            permission_mode=permission_mode,
            extra_args=extra_args,
            env=cc_env,
            stderr=_stderr_cb,
            cwd=working_dir,
            **({"hooks": hooks} if hooks else {}),
            **({"resume": self._session_id} if self._session_id else {}),
            **({"mcp_servers": {'ui': ui_server[0]}, "allowed_tools": ui_server[1]} if ui_server else {}),
            **self._skills_options(working_dir),
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
                await client.query(prompt)
                async for msg in client.receive_response():
                    if self.workflow and self.workflow.stop_requested:
                        break
                    if isinstance(msg, AssistantMessage):
                        if msg.session_id and not self._session_id:
                            self._session_id = msg.session_id
                        for block in msg.content:
                            if isinstance(block, TextBlock):
                                yield 'assistant', block.text
                            elif isinstance(block, ThinkingBlock):
                                if block.thinking.strip():
                                    yield 'thinking', block.thinking
                            elif isinstance(block, (ToolUseBlock, ServerToolUseBlock)):
                                yield 'claude_tool', json.dumps({
                                    'id': block.id,
                                    'name': block.name,
                                    'input': block.input or {},
                                })
                            elif isinstance(block, ServerToolResultBlock):
                                yield 'claude_tool_result', format_tool_result_content(block)
                    elif isinstance(msg, UserMessage) and isinstance(msg.content, list):
                        for block in msg.content:
                            if isinstance(block, ToolResultBlock):
                                yield 'claude_tool_result', format_tool_result_content(block)
                    elif isinstance(msg, ConversationResetMessage):
                        self._session_id = None
                    elif isinstance(msg, ResultMessage) and (
                        msg.is_error
                        or msg.terminal_reason not in (None, 'completed')
                    ):
                        reason = msg.terminal_reason or msg.subtype
                        details = '\n'.join(msg.errors or [])
                        yield 'system', f'Stopped: {reason}\n{details}'.strip()
            finally:
                stop_task.cancel()
                if self.workflow and self.workflow.stop_requested:
                    await client.disconnect()
                    await asyncio.to_thread(kill_tagged, run_tag)

    async def _watch_stop(self, client):
        while not (self.workflow and self.workflow.stop_requested):
            await asyncio.sleep(0.1)
        get_run_manager().reject_pending(self.workflow.context_id)
        if self._question_future and not self._question_future.done():
            self._question_future.set_result(None)
        try:
            await asyncio.wait_for(client.interrupt(), timeout=3)
            await asyncio.sleep(3)
        except Exception:
            pass
        await client.disconnect()

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


_app = QApplication.instance()
if _app:
    _app.aboutToQuit.connect(lambda: kill_tagged(f'{os.getpid()}:'))
