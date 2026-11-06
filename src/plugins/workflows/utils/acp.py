import asyncio
import json
import os
import shutil
import sys
import uuid

import psutil
from PySide6.QtWidgets import QApplication

from gui import system
from plugins.workflows.members import LlmMember
from plugins.workflows.utils import mcp_server
from plugins.workflows.utils.jsonrpc import JsonRpcClient, JsonRpcError
from plugins.workflows.utils.runs import get_run_manager
from utils import sql
from utils.filesystem import get_application_path
from utils.helpers import convert_to_safe_case

# Inherited by everything a run's CLI spawns, even detached processes,
# so they can be found and stopped with it. Valued '<app pid>:<run id>'.
RUN_TAG_VAR = 'AP_AGENT_RUN'
ACP_PROTOCOL_VERSION = 1


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


def acp_agent_classes():
    """The loaded ``AcpAgent`` member classes."""
    return [
        cls for _, cls in system.manager.modules.get_modules_in_folder(
            'Members', fetch_keys=('name', 'class'))
        if isinstance(cls, type) and issubclass(cls, AcpAgent)
    ]


def acp_agents():
    """The loaded ``AcpAgent`` classes by agent name."""
    return {cls.agent_name: cls for cls in acp_agent_classes()}


def agent_member_type(agent):
    """The member type of *agent*, e.g. ``claude_code``, or None."""
    return next((
        name for name, cls in system.manager.modules.get_modules_in_folder(
            'Members', fetch_keys=('name', 'class'))
        if getattr(cls, 'agent_name', None) == agent
    ), None)


# Items that belong to an agent (skills, plans) have a kind naming it,
# ``Claude`` for a global item or ``PROJECT:<id>:Claude`` for a project item.

def agent_of(kind):
    """``PROJECT:9:Claude`` -> ``Claude``."""
    return (kind or '').rsplit(':', 1)[-1]


def scope_of(kind):
    """``PROJECT:9:Claude`` -> ``PROJECT:9``, ``Claude`` -> ``''``."""
    return (kind or '').rpartition(':')[0]


def is_acp_agent(member_type):
    member_class = system.manager.modules.get_module_class(
        'Members', module_name=member_type)
    return isinstance(member_class, type) and issubclass(member_class, AcpAgent)


class AcpAgent(LlmMember):
    """Base of the coding agent members, which run an agent CLI in a
    working dir and resume its session across turns.

    ``stream()`` runs the agent over ACP, started by ``command``
    (``install_hint`` says how to install it). Members that run their
    agent another way override ``stream()``, yielding ``(role, text)``
    blocks and keeping the CLI's session id in ``self._session_id``.

    Subclasses name the agent in ``agent_name`` and list the context files
    it reads, e.g. ``CLAUDE.md``, in ``context_files``, and the subdirs it
    also finds them in, e.g. ``.claude``, in ``context_dirs``.
    ``skills_dir`` is where it finds skills, relative to the home and
    project dirs, and ``plans_dir`` where it writes plans, relative to the
    home dir. ``file_editor_config`` is the member config that limits it to
    reading and editing files. With ``chat.force_subscription`` on, the
    ``api_key_env_vars`` are hidden from the agent and it authenticates
    with ``subscription_auth_method``.
    """
    workflow_insert_mode = 'single'
    agent_name = ''
    context_files = ()
    context_dirs = ()
    skills_dir = ''
    plans_dir = ''
    file_editor_config = {}
    command = ()
    install_hint = ''
    api_key_env_vars = ()
    subscription_auth_method = ''

    def __init__(self, **kwargs):
        super().__init__(**kwargs, model_config_key='chat.model')
        self._question_future = None
        self._session_id = None
        self._ui_refs = []
        self._replaying = False
        self._reset_turn()

    def default_working_dir(self):
        """The working dir of chats outside a project, created if missing."""
        key = self.agent_name.lower()
        cwd = system.manager.config.get(f'{key}.default_working_dir', '') or os.path.join(
            get_application_path(), key)
        os.makedirs(cwd, exist_ok=True)
        return cwd

    def app_tools(self):
        """The selected app and workflow tools, as dicts of ``name``,
        ``description``, ``schema``, ``confirm`` and an async
        ``handler(args) -> (text, is_error)``."""
        tools_manager = system.manager.tools
        uuids, method_tools = tools_manager.resolve_selection(
            self.config.get('custom_tools.data', [])
        )

        def as_result(result_json):
            result = json.loads(result_json)
            return result['output'], result['status'] == 'error'

        def method_handler(method_tool):
            async def handler(args):
                return as_result(
                    await tools_manager.call_method_tool(method_tool, args, self._ui_refs)
                )
            return handler

        def workflow_handler(tool_uuid):
            async def handler(args):
                return as_result(await tools_manager.compute_tool_async(tool_uuid, args))
            return handler

        tools = [{
            'name': t['name'],
            'description': t['description'],
            'schema': tools_manager.method_tool_schema(t),
            'confirm': bool(t.get('confirm')),
            'handler': method_handler(t),
        } for t in method_tools]
        for tool_uuid in uuids:
            name = tools_manager.tool_id_names.get(tool_uuid)
            tool_config = tools_manager.get(name)
            if tool_config is None:
                continue
            tools.append({
                'name': convert_to_safe_case(name),
                'description': tool_config.get('description', ''),
                'schema': self.transform_parameters(tool_config.get('params', [])),
                'confirm': bool(tool_config.get('options', {}).get('confirm')),
                'handler': workflow_handler(tool_uuid),
            })
        return tools

    # -- ACP ---------------------------------------------------------------

    async def _start_turn(self):
        """The prompt, system message, working dir, run tag and agent
        environment of a new turn, after resetting the turn state."""
        system_msg = await self.system_message()
        messages = await self.get_messages()
        if len(messages) == 0:
            raise NotImplementedError()
        prompt = messages[-1].get('content', None)
        if prompt is None:
            raise NotImplementedError()

        working_dir = await self.format_config_value('working_dir', '{{ cwd }}') or self.default_working_dir()
        self.restore_session_id()
        self._reset_turn()
        run_tag = f'{os.getpid()}:{uuid.uuid4().hex}'
        env = {**os.environ, RUN_TAG_VAR: run_tag}
        if self.config.get('chat.force_subscription', True):
            # The app keeps provider keys in its own environment for LiteLLM;
            # an agent seeing them would bill the key instead of the plan.
            for var in self.api_key_env_vars:
                env.pop(var, None)
        return prompt, system_msg, working_dir, run_tag, env

    async def _register_app_tools(self):
        """Serve the selected app tools over MCP. Returns ``(url, token)``,
        or ``(None, None)`` without tools."""
        tools = self.app_tools()
        if not tools:
            return None, None
        return await mcp_server.register([
            {**t, 'handler': self._confirmed_handler(t)} if t['confirm'] else t
            for t in tools
        ])

    def not_installed_message(self):
        """The message to show when the agent's CLI isn't on the PATH."""
        if shutil.which(self.command[0]) is None:
            return f'{self.agent_name} is not installed. {self.install_hint}'.strip()

    async def stream(self, *args, **kwargs):
        if message := self.not_installed_message():
            yield 'system', message
            return
        prompt, system_msg, working_dir, run_tag, env = await self._start_turn()
        mcp_token = None

        async with JsonRpcClient(
            self.command, working_dir, env,
            on_notification=self._on_notification,
            on_request=self._on_request,
            on_stderr=self.print_stderr,
        ) as client:
            stop_task = asyncio.create_task(self._watch_stop(
                lambda: client.notify('session/cancel', {'sessionId': self._session_id}),
                client.disconnect,
            ))
            try:
                init = await client.request('initialize', {
                    'protocolVersion': ACP_PROTOCOL_VERSION,
                    'clientCapabilities': {
                        'fs': {'readTextFile': False, 'writeTextFile': False},
                        'terminal': False,
                    },
                    'clientInfo': {'name': 'agentpilot', 'version': '0.6.0'},
                })
                auth_methods = [m.get('id') for m in init.get('authMethods') or []]
                if (self.config.get('chat.force_subscription', True)
                        and self.subscription_auth_method in auth_methods):
                    await client.request('authenticate', {'methodId': self.subscription_auth_method})
                caps = init.get('agentCapabilities') or {}

                mcp_servers = []
                if (caps.get('mcpCapabilities') or {}).get('http'):
                    url, mcp_token = await self._register_app_tools()
                    if url:
                        mcp_servers.append({'type': 'http', 'name': 'ui', 'url': url, 'headers': []})

                new_session = await self._open_session(client, caps, working_dir, mcp_servers)

                blocks = [{'type': 'text', 'text': prompt}]
                if new_session and system_msg:
                    # ACP has no system prompt, so a new session gets it first.
                    blocks.insert(0, {'type': 'text', 'text': system_msg})
                prompt_task = asyncio.create_task(client.request(
                    'session/prompt', {'sessionId': self._session_id, 'prompt': blocks}))
                async for block in self._relay(prompt_task):
                    yield block
                if self.workflow and self.workflow.stop_requested:
                    return
                stop_reason = (prompt_task.result() or {}).get('stopReason')
                if stop_reason not in (None, 'end_turn', 'cancelled'):
                    yield 'system', f'Stopped: {stop_reason}'
            finally:
                stop_task.cancel()
                if mcp_token:
                    mcp_server.unregister(mcp_token)
                if self.workflow and self.workflow.stop_requested:
                    await client.disconnect()
                    await asyncio.to_thread(kill_tagged, run_tag)

    async def _open_session(self, client, caps, working_dir, mcp_servers):
        """Resume (or load) the saved session if the agent can, else start a
        new one. Returns whether it's new. History replayed by
        ``session/load`` is dropped."""
        if self._session_id:
            resume = 'resume' in (caps.get('sessionCapabilities') or {})
            if resume or caps.get('loadSession'):
                self._replaying = not resume
                try:
                    await client.request(
                        'session/resume' if resume else 'session/load',
                        {'sessionId': self._session_id, 'cwd': working_dir, 'mcpServers': mcp_servers},
                    )
                    return False
                except JsonRpcError:
                    pass
                finally:
                    self._replaying = False
        session = await client.request('session/new', {'cwd': working_dir, 'mcpServers': mcp_servers})
        self._session_id = session['sessionId']
        return True

    def _reset_turn(self):
        self._queue = asyncio.Queue()
        self._chunks = (None, [])
        self._tool_calls = {}
        self._shown = set()

    async def _relay(self, done):
        """Yield the queued blocks until the future *done* completes, then
        the rest, including the bubbles of tool calls not yet shown. Stops
        early when the user stops the run."""
        # A stop disconnects the agent, failing *done* unread.
        done.add_done_callback(lambda f: f.cancelled() or f.exception())
        while not (self.workflow and self.workflow.stop_requested):
            getter = asyncio.create_task(self._queue.get())
            finished, _ = await asyncio.wait({getter, done}, return_when=asyncio.FIRST_COMPLETED)
            if getter not in finished:
                getter.cancel()
                break
            yield getter.result()
        if self.workflow and self.workflow.stop_requested:
            return
        self._flush_chunks()
        for tool_call_id in list(self._tool_calls):
            self._show_tool_call(tool_call_id)
        while not self._queue.empty():
            yield self._queue.get_nowait()

    def _put(self, role, text):
        self._queue.put_nowait((role, text))

    def _flush_chunks(self):
        role, texts = self._chunks
        if role and ''.join(texts).strip():
            self._put(role, ''.join(texts))
        self._chunks = (None, [])

    def _on_notification(self, method, params):
        if method != 'session/update' or self._replaying:
            return
        update = params.get('update') or {}
        kind = update.get('sessionUpdate')
        chunk_roles = {'agent_message_chunk': 'assistant', 'agent_thought_chunk': 'thinking'}
        if kind in chunk_roles:
            content = update.get('content') or {}
            if content.get('type') != 'text':
                return
            role = chunk_roles[kind]
            if self._chunks[0] != role:
                self._flush_chunks()
                self._chunks = (role, [])
            self._chunks[1].append(content.get('text', ''))
        elif kind in ('tool_call', 'tool_call_update'):
            tool_call = self._merge_tool_call(update)
            status = tool_call.get('status')
            if status in ('in_progress', 'completed', 'failed'):
                self._show_tool_call(update['toolCallId'])
            if status in ('completed', 'failed') and not tool_call.get('result_shown'):
                tool_call['result_shown'] = True
                self._put('agent_tool_result', self._tool_result_text(tool_call))

    def _merge_tool_call(self, update):
        tool_call = self._tool_calls.setdefault(update['toolCallId'], {})
        tool_call.update({k: v for k, v in update.items() if v is not None and k != 'sessionUpdate'})
        # Later updates replace the content, e.g. with the result.
        diff = next((c for c in update.get('content') or [] if c.get('type') == 'diff'), None)
        if diff:
            tool_call['diff'] = diff
        return tool_call

    def _show_tool_call(self, tool_call_id):
        """Yield a tool call's bubble, once."""
        if tool_call_id in self._shown:
            return
        self._shown.add(tool_call_id)
        self._flush_chunks()
        tool_call = self._tool_calls.get(tool_call_id, {})
        raw_input = tool_call.get('rawInput')
        payload = {
            'id': tool_call_id,
            'name': tool_call.get('title') or tool_call.get('name') or 'Tool',
            'kind': tool_call.get('kind') or 'other',
            'input': raw_input if isinstance(raw_input, dict) else ({'input': raw_input} if raw_input else {}),
            'paths': [loc['path'] for loc in tool_call.get('locations') or [] if loc.get('path')],
        }
        diff = tool_call.get('diff')
        if diff:
            payload['diff'] = {
                'path': diff['path'],
                'old_text': diff.get('oldText') or '',
                'new_text': diff.get('newText') or '',
            }
            payload['paths'] = payload['paths'] or [diff['path']]
        self._put('agent_tool', json.dumps(payload))

    @staticmethod
    def _tool_result_text(tool_call):
        texts = [
            c['content'].get('text', '') for c in tool_call.get('content') or []
            if c.get('type') == 'content' and isinstance(c.get('content'), dict)
        ]
        body = '\n'.join(texts)
        if not body and tool_call.get('rawOutput') is not None:
            raw = tool_call['rawOutput']
            body = raw if isinstance(raw, str) else json.dumps(raw)
        body = body.strip()[:500]
        prefix = 'Error: ' if tool_call.get('status') == 'failed' else 'Result: '
        return (prefix + body) if body else prefix.rstrip(': ')

    async def _on_request(self, method, params):
        """Ask the user to approve a tool call on its bubble."""
        if method != 'session/request_permission':
            return None
        tool_call_id = params['toolCall']['toolCallId']
        self._merge_tool_call(params['toolCall'])
        self._show_tool_call(tool_call_id)
        title = self._tool_calls[tool_call_id].get('title', '')
        approval = get_run_manager().request_confirm(self.workflow.context_id, tool_call_id, label=title)
        approved = bool(approval is not None and await approval)
        kinds = ('allow_once', 'allow_always') if approved else ('reject_once', 'reject_always')
        options = params.get('options') or []
        option = next((o for k in kinds for o in options if o.get('kind') == k), None)
        if option is None or self.workflow.stop_requested:
            return {'outcome': {'outcome': 'cancelled'}}
        return {'outcome': {'outcome': 'selected', 'optionId': option['optionId']}}

    def _confirmed_handler(self, tool):
        """Wrap a confirm tool's handler to await the user's approval on the
        agent's bubble for the call, or on a new bubble if none matches."""
        async def handler(args):
            tool_call_id = next((
                tid for tid, tc in reversed(self._tool_calls.items())
                if tool['name'] in f"{tc.get('title', '')} {tc.get('name', '')}"
                and tc.get('status') not in ('completed', 'failed')
            ), None)
            if tool_call_id is None:
                tool_call_id = f'ui-{uuid.uuid4().hex}'
                self._tool_calls[tool_call_id] = {'title': tool['name'], 'rawInput': args}
            self._show_tool_call(tool_call_id)
            approval = get_run_manager().request_confirm(
                self.workflow.context_id, tool_call_id, label=tool['name'])
            if approval is None:
                return 'This tool requires user approval, which is unavailable in this run', True
            if not await approval:
                return 'User rejected tool use', True
            return await tool['handler'](args)
        return handler

    def restore_session_id(self):
        """The session id saved with this member's latest message."""
        if not self._session_id:
            self._session_id = sql.get_scalar(
                "SELECT json_extract(log, '$.session_id') FROM contexts_messages "
                "WHERE context_id = ? AND member_id = ? "
                "AND json_extract(log, '$.session_id') IS NOT NULL "
                "ORDER BY id DESC LIMIT 1",
                (self.workflow.context_id, self.full_member_id()))
        return self._session_id

    async def ask_question(self, input_dict):
        """Render a ``QuestionBubble`` for an AskUserQuestion payload and
        return the user's answers, keyed by question text."""
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
        return answers or {}

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

    def print_stderr(self, line):
        print(f'[{self.agent_name} stderr] {line}', file=sys.stderr, flush=True)

    async def _watch_stop(self, interrupt, disconnect):
        """Background watcher: when the user clicks the stop button
        ``workflow.stop_requested`` flips to True. The client may be
        blocked on a subprocess read, so awaiting *interrupt* unblocks the
        current turn and the stream loop then observes the flag, before
        *disconnect* is awaited."""
        while not (self.workflow and self.workflow.stop_requested):
            await asyncio.sleep(0.1)
        get_run_manager().reject_pending(self.workflow.context_id)
        if self._question_future and not self._question_future.done():
            self._question_future.set_result(None)
        try:
            await asyncio.wait_for(interrupt(), timeout=3)
            await asyncio.sleep(3)
        except Exception:
            pass
        await disconnect()

    def _get_current_page_source(self):
        """Get the source file path of the currently active page, or '' for
        a run without a chat, e.g. one resumed after a restart."""
        if self.workflow.chat_widget is None:
            return ''
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
