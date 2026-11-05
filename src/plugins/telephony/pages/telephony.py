import asyncio

from PySide6.QtCore import QTimer

from gui import system
from gui.widgets.config_fields import ConfigFields


class Page_Telephony_Settings(ConfigFields):
    display_name = 'Telephony'
    icon_path = ':/resources/icon-call.png'
    page_type = 'settings'

    def __init__(self, parent):
        super().__init__(parent=parent)
        self.conf_namespace = 'telephony'
        self.propagate_config = True  # saves must bubble up to the settings root
        # the field saves on every keystroke: apply to Telnyx once typing has paused
        self._countries_timer = QTimer(self)
        self._countries_timer.setSingleShot(True)
        self._countries_timer.setInterval(1500)
        self._countries_timer.timeout.connect(
            lambda: asyncio.ensure_future(system.manager.telephony.apply_allowed_countries()))
        self.auto_label_width = True
        self.margin_left = 20
        self.schema = [
            {
                'text': 'Provider',
                'type': ('', 'telnyx', 'twilio'),
                'default': '',
                'tooltip': 'Credentials go on the APIs page: a "Telnyx" entry with its API key, '
                           'or a "Twilio" entry with the account SID as client key and the auth '
                           'token as API key. Leave blank to turn telephony off.',
            },
            {
                'text': 'From number',
                'type': str,
                'default': '',
                'tooltip': 'Your number at the provider, in E.164 form: the setup button verifies it '
                           'as caller ID, and inbound calls to it are answered by the agent below.',
            },
            {
                'text': 'Answer with agent',
                'key': 'answer_agent',
                'type': 'combo',
                'query': """
                    SELECT name, uuid
                    FROM entities e
                    WHERE kind = 'AGENT'
                        AND (json_extract(e.config, '$._TYPE') = 'live_agent'
                            OR EXISTS (
                                SELECT 1 FROM json_each(json_extract(e.config, '$.members')) m
                                WHERE json_extract(m.value, '$.config._TYPE') = 'live_agent'))
                    ORDER BY name""",
                'fetch_keys': ('name', 'uuid'),
                'width': 200,
                'default': '',
                'tooltip': 'The live agent that answers incoming calls.',
            },
            {
                'text': 'Auto-accept after',
                'key': 'auto_accept_after',
                'type': int,
                'has_toggle': True,
                'minimum': 0,
                'maximum': 15,
                'default': 0,
                'tooltip': 'Answer incoming calls automatically after this many seconds, unless '
                           'answered or rejected first.',
            },
            {
                'text': 'OpenAI project ID',
                'type': str,
                'default': '',
                'tooltip': 'Calls are bridged to sip:<project id>@sip.api.openai.com.',
            },
            {
                'text': 'Allowed countries',
                'type': str,
                'default': 'GB',
                'tooltip': 'Countries calls may be placed to, as comma-separated ISO codes such as '
                           'GB, US. Applied to the selected provider when changed, and by its '
                           'setup button.',
            },
            {
                'text': 'Telnyx connection ID',
                'type': str,
                'default': '',
                'tooltip': 'The Telnyx voice application calls are placed through. "Set up Telnyx" '
                           'creates it for you; its webhook URL is kept up to date automatically.',
                'row_key': 'telnyx',
            },
            {
                'text': 'Set up Telnyx',
                'type': 'button',
                'target': self.setup_telnyx,
                'label_position': None,
                'tooltip': 'Creates the voice application and outbound profile through the Telnyx '
                           'API, then verifies the From number as caller ID by SMS code.',
                'row_key': 'telnyx',
            },
            {
                'text': 'Set up Twilio',
                'type': 'button',
                'target': self.setup_twilio,
                'label_position': None,
                'tooltip': 'Enables the allowed countries and points the From number at the '
                           'webhook through the Twilio API, then verifies the From number as '
                           'caller ID with a call from Twilio if the account does not own it.',
            },
            {
                'text': 'Public URL',
                'type': str,
                'default': '',
                'readonly': True,
                'tooltip': 'Filled in automatically: a Cloudflare quick tunnel is opened to the '
                           'listener whenever a provider is set, and OpenAI and the provider are '
                           'pointed at it.',
            },
            {
                'text': 'Port',
                'type': int,
                'minimum': 1024,
                'maximum': 65535,
                'default': 8765,
            },
        ]

    def load(self):
        super().load()
        self.public_url_wgt.set_value(system.manager.telephony.public_url)

    def update_config(self):
        before = self.config.get('telephony.allowed_countries')
        super().update_config()
        if self.config.get('telephony.allowed_countries') != before:
            self._countries_timer.start()

    def setup_telnyx(self):
        asyncio.ensure_future(system.manager.telephony.setup_telnyx())

    def setup_twilio(self):
        asyncio.ensure_future(system.manager.telephony.setup_twilio())
