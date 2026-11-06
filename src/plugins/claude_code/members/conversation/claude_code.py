import asyncio
import json
import os
import sys
import time
import uuid
import warnings
from collections import defaultdict
from pathlib import Path

from gui import system
from plugins.workflows.utils.acp import AcpAgent, RUN_TAG_VAR, kill_tagged
from plugins.workflows.utils.runs import get_run_manager
from utils.helpers import set_module_type
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


TOOL_KINDS = {
    'Edit': 'edit', 'Write': 'edit', 'MultiEdit': 'edit',
    'NotebookEdit': 'edit', 'Read': 'read', 'Glob': 'search',
    'Grep': 'search', 'Bash': 'execute', 'WebFetch': 'fetch',
    'WebSearch': 'fetch',
}


def agent_tool_json(tool_id, name, tool_input):
    """A Claude tool use as an ``agent_tool`` message payload."""
    tool_input = tool_input or {}
    path = tool_input.get('file_path') or tool_input.get('notebook_path')
    payload = {
        'id': tool_id,
        'name': name,
        'kind': TOOL_KINDS.get(name, 'other'),
        'input': tool_input,
        'paths': [path] if path else [],
    }
    if name == 'Edit':
        payload['diff'] = {
            'path': path,
            'old_text': tool_input.get('old_string') or '',
            'new_text': tool_input.get('new_string') or '',
        }
    elif name == 'Write':
        payload['diff'] = {
            'path': path,
            'old_text': '',
            'new_text': tool_input.get('content') or '',
        }
    return json.dumps(payload)


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


@set_module_type(module_type='Members', settings='claude_code_settings')
class ClaudeCode(AcpAgent):
    agent_name = 'Claude'
    self_paced = True
    context_files = ('CLAUDE.md',)
    context_dirs = ('.claude',)
    skills_dir = '.claude/skills'
    plans_dir = '.claude/plans'
    file_editor_config = {
        'chat.permission_mode': 'default',
        'builtin_tools': {
            'bash': False,
            'read': True,
            'write': True,
            'edit': True,
            'glob': True,
            'grep': True,
            'webfetch': False,
            'websearch': False,
        },
    }

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
        app_tools = self.app_tools()
        if not app_tools:
            return None

        def as_mcp(handler):
            async def mcp_handler(args):
                text, is_error = await handler(args)
                return {'content': [{'type': 'text', 'text': text}], 'is_error': is_error}
            return mcp_handler

        sdk_tools = [
            tool(t['name'], t['description'], t['schema'])(as_mcp(t['handler']))
            for t in app_tools
        ]
        confirm_names = {f'mcp__ui__{t["name"]}' for t in app_tools if t['confirm']}
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

    async def _model_end_hook(self, input_dict, tool_use_id, context):
        """PreToolUse hook marking the end of the model's step."""
        if self._model_end is None:
            self._model_end = time.monotonic()
        return {}

    async def _speed_hook(self, input_dict, tool_use_id, context):
        """PostToolUse hook pausing for the task's `Speed`, in proportion
        to the model's last step."""
        if self._model_end is not None:
            model_time = self._model_end - self._step_start
            self._model_end = None
            await asyncio.sleep(model_time * self._slowdown)
        self._step_start = time.monotonic()
        return {}

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
                             system.manager.agents):
                    if lookup_name in mgr:
                        config = mgr[lookup_name]
                        async for _ in receive_workflow(
                            config,
                            params={**input_dict, 'context_id': self.workflow.context_id},
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
            # The SDK expects the original questions plus the answers
            # dict back as ``updated_input``.
            return PermissionResultAllow(updated_input={
                'questions': input_dict.get('questions', []),
                'answers': await self.ask_question(input_dict),
            })

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

    def _skills_options(self, working_dir):
        """Serve the app's Claude skills to this session from their one
        fixed ``app_skills/Claude`` folder, shaped as a local plugin. The
        folder can't vary per session, so the CWD rule — project-scoped
        skills are only available when the session's working_dir is that
        project's — is enforced by disallowing the Skill tool for every
        non-matching project skill.
        """
        from gui import system
        from utils import sql

        mgr = system.manager.skills
        plugin_dir = mgr.skills_dir(self.agent_name).parent
        plugin_json = plugin_dir / '.claude-plugin' / 'plugin.json'
        if not plugin_json.exists():
            plugin_json.parent.mkdir(parents=True, exist_ok=True)
            plugin_json.write_text(
                json.dumps({'name': 'agentpilot', 'version': '0.1.0'}),
                encoding='utf-8',
            )
        wd = os.path.realpath(working_dir) if working_dir else None
        disallowed = []
        rows = sql.get_results(
            "SELECT name, kind FROM skills WHERE kind LIKE 'PROJECT:%:' || ?",
            (self.agent_name,)
        ) or []
        for name, kind in rows:
            project_dir = sql.get_scalar(
                "SELECT json_extract(config, '$.working_dir') FROM projects WHERE id = ?",
                (int(kind.split(':')[1]),)
            )
            if not wd or not project_dir or os.path.realpath(project_dir) != wd:
                disallowed.append(f'Skill(agentpilot:{mgr._slug(name)})')
        return {
            'plugins': [{'type': 'local', 'path': str(plugin_dir)}],
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
        working_dir = await self.format_config_value('working_dir', '{{ cwd }}') or self.default_working_dir()
        hooks = self._build_hooks() or {}
        if ui_server and ui_server[2]:
            hooks.setdefault('PreToolUse', []).append(HookMatcher(
                matcher='|'.join(sorted(ui_server[2])),
                hooks=[self._confirm_hook],
                timeout=CONFIRM_HOOK_TIMEOUT,
            ))
        self._slowdown = 1 / system.manager.tasks.speed(self.workflow.context_id) - 1
        if self._slowdown > 0:
            self._model_end = None
            hooks.setdefault('PreToolUse', []).append(HookMatcher(hooks=[self._model_end_hook]))
            hooks.setdefault('PostToolUse', []).append(HookMatcher(
                hooks=[self._speed_hook],
                timeout=CONFIRM_HOOK_TIMEOUT,
            ))
        permission_mode = self.config.get('chat.permission_mode', 'default')
        self.restore_session_id()

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
            max_buffer_size=32 * 1024 * 1024,
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
            stop_task = asyncio.create_task(self._watch_stop(client.interrupt, client.disconnect))
            try:
                self._step_start = time.monotonic()
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
                                yield 'agent_tool', agent_tool_json(
                                    block.id, block.name, block.input)
                            elif isinstance(block, ServerToolResultBlock):
                                yield 'agent_tool_result', format_tool_result_content(block)
                    elif isinstance(msg, UserMessage) and isinstance(msg.content, list):
                        for block in msg.content:
                            if isinstance(block, ToolResultBlock):
                                yield 'agent_tool_result', format_tool_result_content(block)
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
