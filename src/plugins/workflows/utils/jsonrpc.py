"""A minimal JSON-RPC 2.0 client over the stdio of an agent subprocess, one
JSON message per line, as used by ACP (https://agentclientprotocol.com)
and the Codex app-server."""

import asyncio
import itertools
import json

METHOD_NOT_FOUND = -32601


class JsonRpcError(Exception):
    def __init__(self, error):
        super().__init__(f"{error.get('message', 'JSON-RPC error')} {error.get('data') or ''}".strip())
        self.code = error.get('code')


class JsonRpcClient:
    """Runs an agent and exchanges messages with it.

    *on_notification(method, params)* receives the agent's notifications,
    e.g. ``session/update``. *on_request(method, params)* is awaited for
    the agent's requests, e.g. ``session/request_permission``, and returns
    the result, or None if the method isn't supported. Use as an async
    context manager, which starts and stops the agent. Without
    *jsonrpc_header*, messages leave out ``"jsonrpc": "2.0"``. The future
    ``exited`` completes when the agent closes its output.
    """

    def __init__(self, command, cwd, env, on_notification, on_request, on_stderr=None,
                 jsonrpc_header=True):
        self.command = command
        self.cwd = cwd
        self.env = env
        self.on_notification = on_notification
        self.on_request = on_request
        self.on_stderr = on_stderr
        self._header = {'jsonrpc': '2.0'} if jsonrpc_header else {}
        self._proc = None
        self._ids = itertools.count(1)
        self._pending = {}
        self._tasks = []

    async def __aenter__(self):
        self._proc = await asyncio.create_subprocess_exec(
            *self.command,
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            cwd=self.cwd,
            env=self.env,
            limit=32 * 1024 * 1024,
        )
        self.exited = asyncio.get_running_loop().create_future()
        self._tasks = [
            asyncio.create_task(self._read_stdout()),
            asyncio.create_task(self._read_stderr()),
        ]
        return self

    async def __aexit__(self, *exc):
        await self.disconnect()

    async def request(self, method, params):
        msg_id = next(self._ids)
        future = asyncio.get_running_loop().create_future()
        self._pending[msg_id] = future
        await self._send({**self._header, 'id': msg_id, 'method': method, 'params': params})
        return await future

    async def notify(self, method, params):
        await self._send({**self._header, 'method': method, 'params': params})

    async def disconnect(self):
        for task in self._tasks:
            task.cancel()
        if self._proc and self._proc.returncode is None:
            self._proc.terminate()
            try:
                await asyncio.wait_for(self._proc.wait(), timeout=3)
            except asyncio.TimeoutError:
                self._proc.kill()
        self._fail_pending(ConnectionError('The agent process exited'))

    async def _send(self, msg):
        self._proc.stdin.write((json.dumps(msg) + '\n').encode())
        await self._proc.stdin.drain()

    def _fail_pending(self, exc):
        for future in self._pending.values():
            if not future.done():
                future.set_exception(exc)
        self._pending.clear()

    async def _read_stdout(self):
        try:
            while line := await self._proc.stdout.readline():
                try:
                    msg = json.loads(line)
                except ValueError:
                    continue  # agents may log non-JSON lines
                if 'method' not in msg:
                    future = self._pending.pop(msg.get('id'), None)
                    if future and not future.done():
                        if 'error' in msg:
                            future.set_exception(JsonRpcError(msg['error']))
                        else:
                            future.set_result(msg.get('result'))
                elif 'id' in msg:
                    self._tasks.append(asyncio.create_task(self._answer(msg)))
                else:
                    self.on_notification(msg['method'], msg.get('params') or {})
        finally:
            self._fail_pending(ConnectionError('The agent process exited'))
            self.exited.set_result(None)

    async def _answer(self, msg):
        reply = {**self._header, 'id': msg['id']}
        try:
            result = await self.on_request(msg['method'], msg.get('params') or {})
            if result is None:
                reply['error'] = {'code': METHOD_NOT_FOUND, 'message': f"Method not found: {msg['method']}"}
            else:
                reply['result'] = result
        except Exception as e:
            reply['error'] = {'code': -32603, 'message': str(e)}
        await self._send(reply)

    async def _read_stderr(self):
        while line := await self._proc.stderr.readline():
            if self.on_stderr:
                self.on_stderr(line.decode(errors='replace').rstrip())
