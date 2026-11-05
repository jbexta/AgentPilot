import json
from urllib.parse import urlencode
from xml.sax.saxutils import escape

import aiohttp

from plugins.telephony.managers.telephony import Telephony

API = 'https://api.twilio.com/2010-04-01/Accounts'
VOICE_API = 'https://voice.twilio.com/v1'


class Twilio(Telephony):
    name = 'twilio'

    def _auth(self):
        creds = self.credentials()
        return aiohttp.BasicAuth(creds.get('client_key', ''), creds.get('api_key', ''))

    @staticmethod
    def sip_address(sip_uri, headers):
        # secure=true makes Twilio use SRTP, which OpenAI's SIP endpoint requires
        query = ('?' + urlencode(headers)) if headers else ''
        return f'{sip_uri};secure=true{query}'

    @classmethod
    def twiml(cls, sip_uri, headers):
        return f'<Response><Dial><Sip>{escape(cls.sip_address(sip_uri, headers))}</Sip></Dial></Response>'

    async def _request(self, method, path, params=None, form=None):
        url = path if path.startswith('https://') else f"{API}/{self.credentials().get('client_key', '')}{path}"
        async with aiohttp.ClientSession() as http:
            async with http.request(method, url, params=params, data=form, auth=self._auth()) as resp:
                data = await resp.json(content_type=None)
                if resp.status >= 400:
                    raise Exception(data.get('message', data))
                return data

    # ---- one-time account setup, done through the API instead of the console ----

    async def ensure_allowed_countries(self, allowed_countries):
        """Enable voice dialing (geo permissions) to ``allowed_countries``."""
        update = [{'iso_code': c, 'low_risk_numbers_enabled': 'true'} for c in allowed_countries]
        await self._request('POST', f'{VOICE_API}/DialingPermissions/BulkCountryUpdates',
                            form={'UpdateRequest': json.dumps(update)})

    async def caller_ids(self):
        """Numbers the account owns or has verified, so can call from."""
        owned = await self._request('GET', '/IncomingPhoneNumbers.json')
        verified = await self._request('GET', '/OutgoingCallerIds.json')
        return [n['phone_number'] for n in owned['incoming_phone_numbers'] + verified['outgoing_caller_ids']]

    async def request_number_verification(self, number):
        """Twilio calls ``number``; returns the code to enter on its keypad."""
        data = await self._request('POST', '/OutgoingCallerIds.json', form={'PhoneNumber': number})
        return data['validation_code']

    async def register_webhook(self, public_url):
        """Answer inbound calls to the from-number with TwiML that dials OpenAI."""
        number = self.manager.setting('from_number')
        if not number:
            return
        data = await self._request('GET', '/IncomingPhoneNumbers.json', params={'PhoneNumber': number})
        for entry in data.get('incoming_phone_numbers', []):
            await self._request('POST', f"/IncomingPhoneNumbers/{entry['sid']}.json",
                                form={'VoiceUrl': f'{public_url}/twilio/voice', 'VoiceMethod': 'POST'})

    async def place_call(self, from_number, to_number, sip_uri, headers):
        """The agent's SIP leg runs this TwiML once it answers: Twilio rings the
        contact and joins them the moment they pick up."""
        caller_id = escape(from_number, {'"': '&quot;'})
        data = await self._request('POST', '/Calls.json', form={
            'To': self.sip_address(sip_uri, headers),
            'From': from_number,
            'Twiml': f'<Response><Dial callerId="{caller_id}">{escape(to_number)}</Dial></Response>',
            'StatusCallback': f'{self.manager.public_url}/telephony/twilio',
        })
        return data['sid']

    async def hangup(self, call_id):
        await self._request('POST', f'/Calls/{call_id}.json', form={'Status': 'completed'})

    def parse_webhook(self, headers, body):
        status = body.get('CallStatus')
        print(f"Twilio {status}: direction={body.get('Direction')} from={body.get('From')} to={body.get('To')}")
        if status in ('completed', 'busy', 'failed', 'no-answer', 'canceled'):
            return {'event': 'ended', 'call_id': body.get('CallSid'),
                    'direction': body.get('Direction'), 'from': body.get('From'), 'to': body.get('To')}
        return None
