import asyncio
import time

import aiohttp
from aiohttp import web
from aiohttp.abc import AbstractResolver

from gui import system


class TelephonyWebhookDaemon:
    class FixedResolver(AbstractResolver):
        """Resolve every host to one address (the tunnel edge found over DoH)."""
        def __init__(self, ip):
            self.ip = ip

        async def resolve(self, host, port=0, family=0):
            return [{'hostname': host, 'host': self.ip, 'port': port, 'family': 2, 'proto': 0, 'flags': 0}]

        async def close(self):
            pass

    def __init__(self, system):
        self.system = system
        self._running = False
        self._runner = None

    @property
    def manager(self):
        return system.manager.telephony

    async def start(self):
        self._running = True
        self._tunnel = None
        try:
            while self._running:
                configured = bool(self.manager.setting('provider'))
                if configured and self._runner is None:
                    await self._serve()
                elif not configured and self._runner is not None:
                    await self._close()
                if self._tunnel is not None and self._tunnel.process.poll() is not None:
                    print('Telephony tunnel exited; reopening')  # cloudflared dies when DNS drops
                    self._forget_tunnel()
                if self._runner is not None and self._tunnel is None:
                    await self._open_tunnel()  # retried every loop until it comes up
                await asyncio.sleep(15 if self._runner is not None and self._tunnel is None else 3)
        finally:
            await self._close()

    def stop(self):
        self._running = False

    async def _serve(self):
        app = web.Application()
        app.router.add_post('/openai', self.on_openai)
        app.router.add_post('/telephony/{name}', self.on_provider)
        app.router.add_post('/twilio/voice', self.on_twilio_voice)
        app.router.add_get('/health', lambda request: web.Response(text='ok'))
        self._runner = web.AppRunner(app)
        await self._runner.setup()
        port = int(self.manager.setting('port', 8765) or 8765)
        await web.TCPSite(self._runner, '127.0.0.1', port).start()

    async def _open_tunnel(self):
        """Publish the listener through a Cloudflare quick tunnel and register its URL
        with OpenAI and the provider, so no manual webhook setup is needed."""
        from pycloudflared import try_cloudflare
        port = int(self.manager.setting('port', 8765) or 8765)
        try:
            urls = await asyncio.to_thread(try_cloudflare, port, None, False)
        except Exception as e:
            try_cloudflare.running.pop(port, None)
            print(f'Telephony tunnel failed to start ({e}); retrying in 15s')
            return
        self._tunnel = urls
        # A quick tunnel prints its URL before Cloudflare routes the hostname; only
        # register it once a request actually gets through, or webhooks are lost.
        if not await self._wait_reachable(urls.tunnel):
            print('Telephony tunnel never became reachable; reopening')
            urls.process.terminate()
            self._forget_tunnel()
            return
        print(f'Telephony tunnel reachable at {urls.tunnel}')
        await self.manager.register_public_url(urls.tunnel)

    async def _wait_reachable(self, url, timeout=120):
        """Fetch /health through the tunnel, resolving the hostname over Cloudflare's
        DNS-over-HTTPS so it works even where the local resolver lags."""
        host = url.split('//', 1)[1]
        deadline = time.time() + timeout
        while time.time() < deadline:
            try:
                async with aiohttp.ClientSession() as http:
                    async with http.get('https://cloudflare-dns.com/dns-query',
                                        params={'name': host, 'type': 'A'},
                                        headers={'accept': 'application/dns-json'}) as resp:
                        answers = (await resp.json(content_type=None)).get('Answer') or []
                    ip = next((a['data'] for a in answers if a.get('type') == 1), None)
                    if ip:
                        connector = aiohttp.TCPConnector(resolver=self.FixedResolver(ip))
                        async with aiohttp.ClientSession(connector=connector) as pinned:
                            async with pinned.get(f'{url}/health', timeout=aiohttp.ClientTimeout(total=15)) as resp:
                                if resp.status == 200 and (await resp.text()) == 'ok':
                                    return True
            except Exception:
                pass
            await asyncio.sleep(5)
        return False

    async def _close(self):
        if self._runner is not None:
            await self._runner.cleanup()
            self._runner = None
        if self._tunnel is not None:
            self._tunnel.process.terminate()
            self._forget_tunnel()

    def _forget_tunnel(self):
        from pycloudflared import try_cloudflare
        try_cloudflare.running.pop(int(self.manager.setting('port', 8765) or 8765), None)
        self._tunnel = None

    async def on_openai(self, request):
        event = self.manager.openai_client().webhooks.unwrap(await request.read(), request.headers)
        etype, data = event.type, event.data.model_dump()
        print(f'Telephony: OpenAI webhook {etype}')
        # The same call also raises realtime.call.incoming with a Realtime call id,
        # which the Live accept endpoint doesn't know: only the Live event carries
        # the session id we can accept.
        if etype in ('live.transport.incoming', 'live.call.incoming'):
            # reply at once: a slow response makes OpenAI redeliver the event
            asyncio.ensure_future(self.manager.on_openai_incoming(data['session_id'], data.get('sip_headers', [])))
        return web.Response(status=200)

    async def on_provider(self, request):
        if request.content_type == 'application/json':
            body = await request.json()
        else:
            body = dict(await request.post())
        await self.manager.on_provider_event(request.match_info['name'], request.headers, body)
        return web.Response(status=200)

    async def on_twilio_voice(self, request):
        twilio = self.manager.providers.get('twilio')
        twiml = twilio.twiml(self.manager.sip_uri(), {}) if twilio else '<Response><Reject/></Response>'
        return web.Response(text=twiml, content_type='text/xml')