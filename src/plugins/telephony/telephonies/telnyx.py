
import aiohttp

from plugins.telephony.managers.telephony import Telephony

API = 'https://api.telnyx.com/v2'


class Telnyx(Telephony):
    name = 'telnyx'

    def _headers(self):
        return {'Authorization': f"Bearer {self.credentials().get('api_key', '')}"}

    async def _request(self, method, path, payload=None):
        async with aiohttp.ClientSession() as http:
            async with http.request(method, f'{API}{path}', json=payload, headers=self._headers()) as resp:
                if resp.status == 204:
                    return {}
                data = await resp.json()
                if resp.status >= 400:
                    raise Exception(data.get('errors', data))
                return data.get('data', {})

    # ---- one-time account setup, done through the API instead of the portal ----

    async def create_application(self, public_url, allowed_countries):
        """Ensure an outbound voice profile and a Voice API application bound to it exist,
        reusing what the account already has (accounts are limited to one profile).
        Returns the application id (the "connection id" calls are placed through)."""
        profile = await self.ensure_allowed_countries(allowed_countries)
        webhook = f'{public_url}/telephony/telnyx' if public_url else 'https://example.com/telephony/telnyx'
        apps = await self._request('GET', '/call_control_applications')
        app = next((a for a in apps if a.get('application_name') == 'AgentPilot'))
        if app is None:
            app = await self._request('POST', '/call_control_applications', {
                'application_name': 'AgentPilot',
                'webhook_event_url': webhook,
                'webhook_api_version': '2',
                'outbound': {'outbound_voice_profile_id': profile['id']},
            })
        elif not (app.get('outbound') or {}).get('outbound_voice_profile_id'):
            await self._request('PATCH', f"/call_control_applications/{app['id']}",
                                {'outbound': {'outbound_voice_profile_id': profile['id']}})
        return app['id']

    async def ensure_allowed_countries(self, allowed_countries):
        """Add ``allowed_countries`` to the outbound profile's whitelist; returns the profile."""
        profiles = await self._request('GET', '/outbound_voice_profiles')
        profile = profiles[0] if profiles else await self._request('POST', '/outbound_voice_profiles', {'name': 'AgentPilot'})
        current = set(profile.get('whitelisted_destinations') or [])
        wanted = sorted(current | set(allowed_countries))
        if set(wanted) != current:
            profile = await self._request('PATCH', f"/outbound_voice_profiles/{profile['id']}",
                                          {'whitelisted_destinations': wanted})
        return profile

    async def caller_ids(self):
        """Numbers the account owns or has verified, so can call from."""
        owned = await self._request('GET', '/phone_numbers')
        verified = await self._request('GET', '/verified_numbers')
        return [n['phone_number'] for n in owned] + [n['phone_number'] for n in verified if n.get('verified_at')]

    async def request_number_verification(self, number):
        await self._request('POST', '/verified_numbers', {'phone_number': number, 'verification_method': 'sms'})

    async def submit_number_verification(self, number, code):
        await self._request('POST', f'/verified_numbers/{number}/actions/verify', {'verification_code': code})

    async def register_webhook(self, public_url):
        connection_id = self.manager.setting('telnyx_connection_id')
        if connection_id:
            await self._request('PATCH', f'/call_control_applications/{connection_id}',
                                {'webhook_event_url': f'{public_url}/telephony/telnyx'})

    async def place_call(self, from_number, to_number, sip_uri, headers):
        data = await self._request('POST', '/calls', {
            'connection_id': self.manager.setting('telnyx_connection_id'),
            'to': sip_uri,
            'from': from_number,
            'sip_transport_protocol': 'TLS',
            'media_encryption': 'SRTP',  # OpenAI's SIP endpoint refuses unencrypted media
            'custom_headers': [{'name': k, 'value': v} for k, v in headers.items()],
        })
        return data['call_control_id']

    async def connect_contact(self, call_id, from_number, to_number):
        data = await self._request('POST', '/calls', {
            'connection_id': self.manager.setting('telnyx_connection_id'),
            'to': to_number,
            'from': from_number,
            'link_to': call_id,
            'bridge_on_answer': True,
        })
        return data['call_control_id']

    async def bridge(self, call_id, sip_uri, headers):
        await self._request('POST', f'/calls/{call_id}/actions/transfer', {
            'to': sip_uri,
            'sip_transport_protocol': 'TLS',
            'media_encryption': 'SRTP',  # OpenAI's SIP endpoint refuses unencrypted media
            'custom_headers': [{'name': k, 'value': v} for k, v in headers.items()],
        })

    async def hangup(self, call_id):
        await self._request('POST', f'/calls/{call_id}/actions/hangup', {})

    def parse_webhook(self, headers, body):
        data = body.get('data', {})
        payload = data.get('payload', {})
        events = {
            'call.initiated': 'incoming' if payload.get('direction') == 'incoming' else 'started',
            'call.answered': 'answered',
            'call.hangup': 'ended',
        }
        event = events.get(data.get('event_type'))
        print(f"Telnyx {data.get('event_type')}: direction={payload.get('direction')} "
              f"from={payload.get('from')} to={payload.get('to')}")
        if event is None:
            return None
        return {
            'event': event,
            'call_id': payload.get('call_control_id'),
            'direction': payload.get('direction'),
            'from': payload.get('from'),
            'to': payload.get('to'),
        }