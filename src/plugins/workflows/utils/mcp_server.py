"""A local MCP server (streamable HTTP, JSON responses) serving app tools to
agent CLIs. Each session registers its tools under a secret URL."""

import secrets

from aiohttp import web

MCP_PROTOCOL_VERSION = '2025-06-18'

_runner = None
_port = None
_sessions = {}  # token -> {name: tool}


async def register(tools):
    """Serve *tools*, dicts of ``name``, ``description``, ``schema`` and an
    async ``handler(args) -> (text, is_error)``. Returns ``(url, token)``,
    unregister with the token when the session ends."""
    global _runner, _port
    if _runner is None:
        app = web.Application()
        app.router.add_post('/mcp/{token}', _handle)
        app.router.add_get('/mcp/{token}', lambda request: web.Response(status=405))
        _runner = web.AppRunner(app)
        await _runner.setup()
        await web.TCPSite(_runner, '127.0.0.1', 0).start()
        _port = _runner.addresses[0][1]
    token = secrets.token_urlsafe(24)
    _sessions[token] = {t['name']: t for t in tools}
    return f'http://127.0.0.1:{_port}/mcp/{token}', token


def unregister(token):
    _sessions.pop(token, None)


async def _handle(request):
    tools = _sessions.get(request.match_info['token'])
    if tools is None:
        return web.Response(status=404)
    msg = await request.json()
    if 'id' not in msg:
        return web.Response(status=202)  # a notification
    result = await _result(tools, msg.get('method'), msg.get('params') or {})
    if result is None:
        reply = {'error': {'code': -32601, 'message': f"Method not found: {msg.get('method')}"}}
    else:
        reply = {'result': result}
    return web.json_response({'jsonrpc': '2.0', 'id': msg['id'], **reply})


async def _result(tools, method, params):
    if method == 'initialize':
        return {
            'protocolVersion': params.get('protocolVersion', MCP_PROTOCOL_VERSION),
            'capabilities': {'tools': {}},
            'serverInfo': {'name': 'agentpilot', 'version': '1.0'},
        }
    if method == 'ping':
        return {}
    if method == 'tools/list':
        return {'tools': [
            {'name': t['name'], 'description': t['description'], 'inputSchema': t['schema']}
            for t in tools.values()
        ]}
    if method == 'tools/call':
        tool = tools.get(params.get('name'))
        if tool is None:
            text, is_error = f"Unknown tool: {params.get('name')}", True
        else:
            text, is_error = await tool['handler'](params.get('arguments') or {})
        return {'content': [{'type': 'text', 'text': text}], 'isError': is_error}
    return None
