import asyncio
import json

from plugins.workflows.utils import mcp_server
from plugins.workflows.utils.acp import AcpAgent, kill_tagged
from plugins.workflows.utils.jsonrpc import JsonRpcClient, JsonRpcError
from plugins.workflows.utils.runs import get_run_manager
from utils.helpers import set_module_type

APPROVAL_REQUESTS = ('item/commandExecution/requestApproval', 'item/fileChange/requestApproval')


def diff_texts(diff):
    """The old and new text of a unified diff's hunks, or of a diff that is
    just the new file's content."""
    old, new, in_hunk = [], [], False
    for line in diff.splitlines():
        if line.startswith('@@'):
            in_hunk = True
        elif in_hunk and line[:1] in (' ', '-', '+'):
            if line[0] != '+':
                old.append(line[1:])
            if line[0] != '-':
                new.append(line[1:])
    return ('\n'.join(old), '\n'.join(new)) if in_hunk else ('', diff)


def as_tool_call(item):
    """A Codex thread item as an ACP tool call, as ``AcpAgent`` shows them,
    or None if it isn't a tool call."""
    status = {'completed': 'completed', 'failed': 'failed', 'declined': 'failed'}.get(
        item.get('status'), 'in_progress')
    item_type = item.get('type')
    if item_type == 'commandExecution':
        command = item.get('command')
        output = item.get('aggregatedOutput') or ''
        if item.get('exitCode') not in (None, 0):
            output += f"\n(exit code {item['exitCode']})"
        return {
            'title': 'Shell',
            'kind': 'execute',
            'rawInput': {'command': ' '.join(command) if isinstance(command, list) else command},
            'rawOutput': output,
            'status': status,
        }
    if item_type == 'fileChange':
        changes = item.get('changes') or []
        tool_call = {
            'title': 'Edit',
            'kind': 'edit',
            'locations': [{'path': c['path']} for c in changes if c.get('path')],
            'status': status,
        }
        if changes:
            old, new = diff_texts(changes[0].get('diff') or '')
            tool_call['diff'] = {'path': changes[0]['path'], 'oldText': old, 'newText': new}
        return tool_call
    if item_type == 'mcpToolCall':
        return {
            'title': f"{item.get('server')}/{item.get('tool')}",
            'kind': 'other',
            'rawInput': item.get('arguments') or {},
            'rawOutput': item.get('error') or item.get('result'),
            'status': status,
        }
    if item_type == 'webSearch':
        return {
            'title': 'WebSearch',
            'kind': 'fetch',
            'rawInput': {'query': item.get('query', '')},
            'status': status,
        }
    return None


@set_module_type(module_type='Members', settings='codex_settings')
class Codex(AcpAgent):
    """Runs the official ``codex app-server`` (JSON-RPC over stdio) instead
    of ACP, configured with ``-c`` overrides per run."""
    agent_name = 'Codex'
    context_files = ('AGENTS.md',)
    skills_dir = '.agents/skills'
    file_editor_config = {'chat.sandbox': 'workspace-write', 'chat.approval_policy': 'never'}
    command = ('codex', 'app-server')
    install_hint = 'Install it with `npm i -g @openai/codex`, then run `codex login`.'
    api_key_env_vars = ('OPENAI_API_KEY', 'CODEX_API_KEY')

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self._turn_id = None
        self._turn_done = None

    def config_overrides(self, system_msg, mcp_url):
        overrides = {
            'approval_policy': self.config.get('chat.approval_policy', 'on-request'),
            'sandbox_mode': self.config.get('chat.sandbox', 'workspace-write'),
        }
        if model := self.config.get('chat.codex_model', ''):
            overrides['model'] = model
        if effort := self.config.get('chat.effort', None):
            overrides['model_reasoning_effort'] = effort
        if system_msg:
            overrides['developer_instructions'] = system_msg
        if self.config.get('chat.force_subscription', True):
            overrides['forced_login_method'] = 'chatgpt'
        if mcp_url:
            overrides['mcp_servers.ui.url'] = mcp_url
        return overrides

    async def stream(self, *args, **kwargs):
        if message := self.not_installed_message():
            yield 'system', message
            return
        prompt, system_msg, working_dir, run_tag, env = await self._start_turn()
        self._turn_id = None
        self._turn_done = asyncio.get_running_loop().create_future()
        mcp_url, mcp_token = await self._register_app_tools()
        # Values are TOML, which reads JSON strings, numbers and booleans.
        overrides = [
            arg for key, value in self.config_overrides(system_msg, mcp_url).items()
            for arg in ('-c', f'{key}={json.dumps(value)}')
        ]
        command = [self.command[0], *overrides, *self.command[1:]]
        try:
            async with JsonRpcClient(
                command, working_dir, env,
                on_notification=self._on_codex_notification,
                on_request=self._on_codex_request,
                on_stderr=self.print_stderr,
                jsonrpc_header=False,
            ) as client:
                stop_task = asyncio.create_task(self._watch_stop(
                    lambda: self._interrupt(client), client.disconnect))
                client.exited.add_done_callback(lambda _: self._turn_done.done() or self._turn_done.set_exception(
                    ConnectionError('Codex exited before finishing the turn')))
                try:
                    await client.request('initialize', {
                        'clientInfo': {'name': 'agentpilot', 'title': 'AgentPilot', 'version': '0.6.0'},
                    })
                    await client.notify('initialized', {})
                    thread = None
                    if self._session_id:
                        try:
                            thread = await client.request('thread/resume', {'threadId': self._session_id})
                        except JsonRpcError:
                            pass
                    if thread is None:
                        thread = await client.request('thread/start', {'cwd': working_dir})
                    self._session_id = thread['thread']['id']
                    turn = await client.request('turn/start', {
                        'threadId': self._session_id,
                        'input': [{'type': 'text', 'text': prompt}],
                    })
                    self._turn_id = turn['turn']['id']
                    async for block in self._relay(self._turn_done):
                        yield block
                    if self.workflow and self.workflow.stop_requested:
                        return
                    turn = self._turn_done.result()
                    if turn.get('status') == 'failed':
                        error = (turn.get('error') or {}).get('message', 'The turn failed')
                        yield 'system', f'Stopped: {error}'
                finally:
                    stop_task.cancel()
                    if self.workflow and self.workflow.stop_requested:
                        await client.disconnect()
                        await asyncio.to_thread(kill_tagged, run_tag)
        finally:
            if mcp_token:
                mcp_server.unregister(mcp_token)

    async def _interrupt(self, client):
        if self._turn_id:
            await client.request('turn/interrupt', {'threadId': self._session_id, 'turnId': self._turn_id})

    def _on_codex_notification(self, method, params):
        if method == 'turn/completed':
            if not self._turn_done.done():
                self._turn_done.set_result(params.get('turn') or {})
        elif method == 'error' and not params.get('willRetry'):
            self._flush_chunks()
            self._put('system', f"Error: {(params.get('error') or {}).get('message', params)}")
        elif method in ('item/started', 'item/completed'):
            item = params.get('item') or {}
            completed = method == 'item/completed'
            if item.get('type') in ('agentMessage', 'reasoning'):
                if completed:
                    self._put_message(item)
                return
            tool_call = as_tool_call(item)
            if tool_call is None:
                return
            self._tool_calls.setdefault(item['id'], {}).update(tool_call)
            self._show_tool_call(item['id'])
            if completed:
                self._put('agent_tool_result', self._tool_result_text(self._tool_calls[item['id']]))

    def _put_message(self, item):
        if item['type'] == 'agentMessage':
            role, text = 'assistant', item.get('text', '')
        else:
            role = 'thinking'
            text = '\n\n'.join(
                part if isinstance(part, str) else part.get('text', '')
                for part in item.get('summary') or item.get('content') or []
            )
        if text.strip():
            self._flush_chunks()
            self._put(role, text)

    async def _on_codex_request(self, method, params):
        """Ask the user to approve a command or file change on its bubble."""
        if method not in APPROVAL_REQUESTS:
            return None
        item_id = params['itemId']
        if item_id not in self._tool_calls:
            self._tool_calls[item_id] = {
                'title': 'Shell' if 'command' in method else 'Edit',
                'rawInput': {'command': params['command']} if params.get('command') else {},
            }
        self._show_tool_call(item_id)
        approval = get_run_manager().request_confirm(
            self.workflow.context_id, item_id,
            label=params.get('reason') or self._tool_calls[item_id].get('title', ''))
        approved = bool(approval is not None and await approval)
        if self.workflow.stop_requested:
            return {'decision': 'cancel'}
        return {'decision': 'accept' if approved else 'decline'}
