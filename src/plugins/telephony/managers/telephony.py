import asyncio
import json
import uuid
from abc import abstractmethod

from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import QMessageBox

from gui import system
from utils import sql
from utils.helpers import display_message, set_module_type

SIP_HOST = 'sip.api.openai.com'
TOKEN_HEADER = 'X-AP-Token'  # correlates an outbound call we placed with OpenAI's incoming webhook


def api_credentials(name):
    return next((v for k, v in system.manager.apis.items() if k.lower() == name.lower()), {})


class Telephony:
    """A carrier that can place calls and bridge them into OpenAI's SIP endpoint."""
    name = ''

    def __init__(self, manager):
        self.manager = manager

    def credentials(self):
        return api_credentials(self.name)

    @abstractmethod
    async def place_call(self, from_number, to_number, sip_uri, headers):
        """Dial the agent at ``sip_uri`` with the custom SIP ``headers`` first, so it is
        live before ``to_number`` rings. Returns the provider call id of the agent leg."""

    async def connect_contact(self, call_id, from_number, to_number):
        """Once the agent leg ``call_id`` answers, ring ``to_number`` and join it to that
        leg as soon as it answers. Returns the contact leg's call id. Providers that
        ring the contact themselves (from ``place_call``) leave this as is."""

    async def bridge(self, call_id, sip_uri, headers):
        """Transfer the inbound call ``call_id`` to ``sip_uri``."""

    @abstractmethod
    async def hangup(self, call_id):
        pass

    @abstractmethod
    async def caller_ids(self):
        """Phone numbers calls can be placed from."""

    def parse_webhook(self, headers, body):
        """Normalise a provider webhook into {'event', 'call_id', 'direction', 'from', 'to'} or None."""
        return None

    async def register_webhook(self, public_url):
        """Point the provider's call events at ``public_url`` (see the daemon's routes)."""

    async def ensure_allowed_countries(self, allowed_countries):
        """Permit outbound calls to ``allowed_countries`` (ISO codes)."""


@set_module_type(module_type='Managers')
class TelephonyManager:
    def __init__(self, system):
        self.system = system
        self.providers = {}
        self.pending = {}   # token: {'agent_uuid': str, 'to': str}
        self.calls = {}     # provider call id: {'from', 'to', 'partner': call id}
        self.public_url = ''  # the current tunnel; changes whenever the daemon reopens it
        self.handled_sessions = set()  # OpenAI redelivers webhooks; act on each session once

    def load(self):
        classes = system.manager.modules.get_modules_in_folder(
            module_type='Telephonies', fetch_keys=('name', 'class'))
        self.providers = {name: cls(self) for name, cls in classes}

    # ---- settings ----

    def setting(self, key, default=''):
        return system.manager.config.get(f'telephony.{key}', default)

    # Values the app manages itself (not settings-page fields) live in their own
    # settings row: the settings root rewrites app_config from its pages' fields,
    # which would drop anything else stored there.
    def state(self):
        row = sql.get_scalar("SELECT value FROM settings WHERE field = 'telephony_state'")
        return json.loads(row) if row else {}

    def save_state(self, **values):
        state = {**self.state(), **values}
        if sql.get_scalar("SELECT COUNT(*) FROM settings WHERE field = 'telephony_state'"):
            sql.execute("UPDATE settings SET value = ? WHERE field = 'telephony_state'", (json.dumps(state),))
        else:
            sql.execute("INSERT INTO settings (field, value) VALUES ('telephony_state', ?)", (json.dumps(state),))

    def provider(self):
        return self.providers.get(self.setting('provider'))

    def sip_uri(self):
        project_id = self.setting('openai_project_id')
        return f'sip:{project_id}@{SIP_HOST};transport=tls'

    def openai_client(self):
        from openai import AsyncOpenAI
        return AsyncOpenAI(api_key=api_credentials('openai').get('api_key'),
                           webhook_secret=self.state().get('openai_webhook_secret') or None)

    async def register_public_url(self, url):
        """The tunnel URL changes per launch: re-point OpenAI's and the provider's webhooks at it."""
        self.public_url = url
        client = self.openai_client()
        events = ['live.transport.incoming', 'realtime.call.incoming']
        endpoint_id = self.state().get('openai_webhook_id')
        try:
            if endpoint_id:
                await client.webhooks.update(endpoint_id, url=f'{url}/openai', event_types=events)
            else:
                # earlier launches created endpoints whose ids were lost: replace them,
                # since the signing secret is only returned on creation
                listing = await client.webhooks.list()
                for stale in listing.data:
                    if stale.name == 'AgentPilot telephony':
                        await client.webhooks.delete(stale.id)
                endpoint = await client.webhooks.create(
                    name='AgentPilot telephony', url=f'{url}/openai', event_types=events)
                self.save_state(openai_webhook_id=endpoint.id, openai_webhook_secret=endpoint.signing_secret)
        except Exception as e:
            display_message(f'Could not register the OpenAI call webhook: {e}', icon=QMessageBox.Warning)
        provider = self.provider()
        if provider is not None:
            try:
                await provider.register_webhook(url)
                print(f'Telephony: {provider.name} webhook set to {url}')
            except Exception as e:
                display_message(f'Could not register the {provider.name} webhook: {e}', icon=QMessageBox.Warning)

    def allowed_countries(self):
        return [c.strip().upper() for c in self.setting('allowed_countries', 'GB').split(',') if c.strip()]

    async def apply_allowed_countries(self):
        """Called when the Allowed countries setting changes."""
        provider = self.provider()
        if provider is None or not provider.credentials().get('api_key'):
            return
        try:
            await provider.ensure_allowed_countries(self.allowed_countries())
        except Exception as e:
            display_message(f'Could not update the {provider.name} allowed countries: {e}',
                            icon=QMessageBox.Warning)

    async def setup_telnyx(self):
        """Create the Telnyx voice application and verify the from-number as caller ID,
        all through the API, so the portal is never needed."""
        from PySide6.QtWidgets import QInputDialog
        telnyx = self.providers.get('telnyx')
        if telnyx is None or not telnyx.credentials().get('api_key'):
            display_message('Add a "Telnyx" entry with its API key on the APIs page first.',
                            icon=QMessageBox.Warning)
            return
        config = system.manager.config
        try:
            config['telephony.telnyx_connection_id'] = await telnyx.create_application(
                self.public_url, self.allowed_countries())
            number = self.setting('from_number')
            if not number:
                display_message('Voice application created. Set a From number, then run setup again '
                                'to verify it as your caller ID.')
                return
            if number in await telnyx.caller_ids():
                display_message(f'Telnyx is set up and {number} is verified as caller ID.')
                return
            await telnyx.request_number_verification(number)
            code, ok = QInputDialog.getText(None, 'Verify number',
                                            f'Enter the code Telnyx sent by SMS to {number}:')
            if not ok or not code.strip():
                return
            await telnyx.submit_number_verification(number, code.strip())
            display_message(f'{number} is now verified as your caller ID.')
        except Exception as e:
            display_message(f'Telnyx setup failed: {e}', icon=QMessageBox.Critical)

    async def setup_twilio(self):
        """Enable the allowed countries, point the from-number at the webhook and
        verify it as caller ID, all through the API, so the console is never needed."""
        twilio = self.providers.get('twilio')
        if twilio is None or not twilio.credentials().get('api_key'):
            display_message('Add a "Twilio" entry on the APIs page first: the account SID as '
                            'client key and the auth token as API key.', icon=QMessageBox.Warning)
            return
        try:
            await twilio.ensure_allowed_countries(self.allowed_countries())
            number = self.setting('from_number')
            if not number:
                display_message('Allowed countries enabled. Set a From number, then run setup again '
                                'to verify it as your caller ID.')
                return
            if self.public_url:
                await twilio.register_webhook(self.public_url)
            if number in await twilio.caller_ids():
                display_message(f'Twilio is set up and {number} can be used as caller ID.')
                return
            code = await twilio.request_number_verification(number)
            display_message(f'Twilio is calling {number}: answer and enter {code} on the keypad '
                            f'to verify it as your caller ID.')
        except Exception as e:
            display_message(f'Twilio setup failed: {e}', icon=QMessageBox.Critical)

    # ---- outbound ----

    async def caller_ids(self):
        provider = self.provider()
        if provider is None:
            return []
        try:
            return await provider.caller_ids()
        except Exception as e:
            display_message(f'Could not list the {provider.name} caller IDs: {e}', icon=QMessageBox.Warning)
            return []

    def start_call(self, to_number):
        """Place a call to ``to_number`` from the number and with the live agent in Call options."""
        provider = self.provider()
        if provider is None:
            display_message('Telephony is not set up: choose a provider in Settings > Telephony.',
                            icon=QMessageBox.Warning)
            return
        if not self.public_url:
            display_message('The call webhook is not reachable yet: wait for the tunnel to come up '
                            '(the console reports it), then try again.', icon=QMessageBox.Warning)
            return
        options = self.state()
        from_number = options.get('call_from')
        agent_uuid = (options.get('call_agent') or '').rsplit(':', 1)[-1]
        if not from_number or not agent_uuid:
            display_message('Choose a number to call from and a live agent in Call options first.',
                            icon=QMessageBox.Warning)
            return
        asyncio.ensure_future(self._place_call(provider, from_number, to_number, agent_uuid))

    async def _place_call(self, provider, from_number, to_number, agent_uuid):
        token = uuid.uuid4().hex
        headers = {TOKEN_HEADER: token}
        call = {'from': from_number, 'to': to_number}
        self.pending[token] = {'agent_uuid': agent_uuid, 'to': to_number, 'call': call}
        try:
            call_id = await self._with_retry(lambda: provider.place_call(
                from_number=from_number,
                to_number=to_number,
                sip_uri=self.sip_uri(),
                headers=headers,
            ))
        except Exception as e:
            self.pending.pop(token, None)
            display_message(f'Call failed: {e}', icon=QMessageBox.Critical)
            return
        self.calls[call_id] = call
        print(f'Telephony: placed call {call_id} to {to_number} from {from_number}')
        display_message(f'Calling {to_number}...')

    @staticmethod
    async def _with_retry(make_request):
        """The VM's DNS drops out now and then: retry a connection failure once."""
        import aiohttp
        try:
            return await make_request()
        except aiohttp.ClientConnectorError:
            await asyncio.sleep(3)
            return await make_request()

    # ---- webhooks (called by the daemon) ----

    async def on_openai_incoming(self, session_id, sip_headers):
        """OpenAI has a pending SIP session: ours (outbound) or a caller (inbound)."""
        if session_id in self.handled_sessions:
            return
        self.handled_sessions.add(session_id)
        token = next((h['value'] for h in sip_headers if h['name'].lower() == TOKEN_HEADER.lower()), None)
        outbound = self.pending.pop(token, None) if token else None
        print(f'Telephony: OpenAI incoming session {session_id} token={token} outbound={bool(outbound)} '
              f'headers={[h["name"] for h in sip_headers]}')
        if outbound:
            await self.answer(session_id, outbound['agent_uuid'])
            return
        caller = next((h['value'] for h in sip_headers if h['name'].lower() == 'from'), 'unknown caller')
        self._ask_to_answer(session_id, caller)

    def _ask_to_answer(self, session_id, caller):
        box = QMessageBox()
        box.setIcon(QMessageBox.Question)
        box.setWindowTitle('Incoming call')
        box.setText(f'Incoming call from {caller}')
        answer = box.addButton('Answer', QMessageBox.AcceptRole)
        box.addButton('Reject', QMessageBox.RejectRole)
        box.setWindowFlags(box.windowFlags() | Qt.WindowStaysOnTopHint)

        def on_click(button):
            if button is answer:
                asyncio.ensure_future(self.answer(session_id, self.setting('answer_agent'), caller))
            else:
                asyncio.ensure_future(self.reject(session_id))

        box.buttonClicked.connect(on_click)
        box.show()
        auto_accept = self.setting('auto_accept_after', None)
        if auto_accept is not None:
            QTimer.singleShot(int(auto_accept) * 1000, box, lambda: box.isVisible() and answer.click())
        self._incoming_box = box  # keep a reference while it is open

    async def reject(self, session_id):
        await self.openai_client().live.sessions.reject(session_id)

    async def answer(self, session_id, agent_uuid, caller=None):
        """Open a chat from the live agent entity, accept the call with its config, run it.
        ``caller`` is set for inbound calls, which the agent is told to greet."""
        if not agent_uuid:
            display_message('No live agent set to answer calls in Settings > Telephony.',
                            icon=QMessageBox.Warning)
            await self.reject(session_id)
            return
        from gui.gui_utils.helpers import find_main
        main = find_main()
        page_chat = main.main_pages.pages.get('chat')
        page_chat.new_context(entity_id=agent_uuid, entity_table='entities', kind='CHAT')
        main.main_pages.goto_page('chat')
        workflow = page_chat.workflow
        agent = next((m for m in workflow.members.values()
                      if m.config.get('_TYPE') == 'live_agent'), None)
        if agent is None:
            display_message('The chosen agent has no Live Agent member.', icon=QMessageBox.Warning)
            await self.reject(session_id)
            return
        params = await agent.session_params()
        from plugins.workflows.live import LiveSession
        session = LiveSession(**params)
        try:
            await self.openai_client().live.sessions.accept(session_id, session=session.accept_config())
        except Exception as e:
            print(f'Telephony: accept failed: {e}')
            display_message(f'Could not accept the call: {e}', icon=QMessageBox.Critical)
            return
        print(f'Telephony: accepted {session_id}, starting {agent.name}')
        client = workflow.live_clients[agent.member_id]
        client.pending_session_id = session_id
        if caller:
            client.pending_instructions = (f'You have just answered an incoming phone call from {caller}: '
                                           f'they are on the line now. Greet them.')
        asyncio.ensure_future(page_chat.run_workflow_async(from_member_id=agent.member_id))  # the run is the call

    async def on_provider_event(self, provider_name, headers, body):
        provider = self.providers.get(provider_name)
        if provider is None:
            return
        event = provider.parse_webhook(headers, body)
        if not event:
            return
        call = self.calls.get(event['call_id'])
        if event['event'] == 'answered' and call and 'to' in call and 'partner' not in call:
            print(f"Telephony: agent is on the line, ringing {call['to']}")
            try:
                contact_id = await provider.connect_contact(event['call_id'], call['from'], call['to'])
            except Exception as e:
                print(f'Telephony: dialling {call["to"]} failed: {e}')
                display_message(f'Call failed: {e}', icon=QMessageBox.Critical)
                await provider.hangup(event['call_id'])
                return
            if contact_id:
                call['partner'] = contact_id
                self.calls[contact_id] = {'partner': event['call_id']}
        elif event['event'] == 'incoming':
            print(f"Telephony: inbound call, transferring to {self.sip_uri()}")
            await provider.bridge(event['call_id'], self.sip_uri(), {})
        elif event['event'] == 'ended':
            partner = (self.calls.pop(event['call_id'], None) or {}).get('partner')
            if partner in self.calls:  # e.g. the contact never answered: drop the agent leg
                self.calls.pop(partner)
                try:
                    await provider.hangup(partner)
                except Exception as e:
                    print(f'Telephony: hanging up {partner} failed: {e}')