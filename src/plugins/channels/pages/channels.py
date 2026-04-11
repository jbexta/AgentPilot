"""Channels Page.

ConfigDBTree-based management page for communication channels.
Each channel connects to an external messaging platform (e.g. WhatsApp
via Evolution API) and routes incoming messages to configured agents.
"""

import asyncio
import logging

import base64

from PySide6.QtCore import QByteArray
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import (
    QDialog, QLabel, QHBoxLayout, QVBoxLayout, QWidget,
)

from plugins.workflows.widgets.workflow_settings import WorkflowSettings
from gui.widgets.config_db_tree import ConfigDBTree
from gui.widgets.config_joined import ConfigJoined
from gui.widgets.config_fields import ConfigFields
from gui.util import IconButton, find_attribute
from utils.helpers import set_module_type
from gui import system

logger = logging.getLogger(__name__)


CHANNEL_TYPE_OPTIONS = (
    ('WhatsApp (Evolution API)', 'whatsapp_evolution'),
)


@set_module_type('Pages')
class Page_Channels(ConfigDBTree):
    """Main page for managing communication channels."""

    display_name = 'Channels'
    icon_path = ":/resources/icon-chat.png"
    page_type = 'main'

    def __init__(self, parent):
        super().__init__(
            parent=parent,
            table_name='channels',
            query="""
                SELECT
                    name,
                    id,
                    kind,
                    COALESCE(
                        json_extract(config, '$.channel_type'),
                        ''
                    ),
                    COALESCE(
                        json_extract(config, '$.enabled'),
                        0
                    ),
                    folder_id
                FROM channels
                ORDER BY pinned DESC, ordr, name COLLATE NOCASE
            """,
            schema=[
                {
                    'text': 'Channels',
                    'key': 'name',
                    'type': str,
                    'stretch': True,
                },
                {
                    'text': 'id',
                    'key': 'id',
                    'type': int,
                    'visible': False,
                },
                {
                    'text': 'Kind',
                    'key': 'kind',
                    'type': str,
                    'visible': False,
                },
                {
                    'text': 'Type',
                    'key': 'channel_type',
                    'type': str,
                    'is_config_field': True,
                    'width': 150,
                },
                {
                    'text': 'On',
                    'key': 'enabled',
                    'type': bool,
                    'is_config_field': True,
                },
            ],
            add_item_options={
                'title': 'Add Channel',
                'prompt': 'Enter a name for the channel:',
            },
            del_item_options={
                'title': 'Delete Channel',
                'prompt': (
                    'Are you sure you want to delete this channel?'
                ),
            },
            folder_key='channels',
            readonly=False,
            layout_type='vertical',
            config_widget=self.Channel_Config_Widget(self),
        )
        self.splitter.setSizes([400, 1000])

    def on_edited(self):
        """Notify daemon to reload after config changes."""
        daemon = system.manager.daemons.running_daemons.get('channels')
        if daemon:
            asyncio.ensure_future(daemon.load())

    class Channel_Config_Widget(ConfigJoined):
        """Nested config widget combining all channel settings."""

        def __init__(self, parent):
            super().__init__(
                parent=parent, layout_type='vertical'
            )
            self.widgets = [
                self.General_Fields(parent=self),
                self.Connection_Fields(parent=self),
                self.Docker_Fields(parent=self),
                self.Security_Fields(parent=self),
                self.Agent_Config(parent=self),
            ]

        class General_Fields(ConfigFields):
            """Channel type and enable toggle."""

            def __init__(self, parent):
                super().__init__(parent=parent)
                self.schema = [
                    {
                        'text': 'Channel type',
                        'key': 'channel_type',
                        'type': CHANNEL_TYPE_OPTIONS,
                        'default': 'whatsapp_evolution',
                        'width': 200,
                    },
                    {
                        'text': 'Enabled',
                        'key': 'enabled',
                        'type': bool,
                        'default': False,
                    },
                    {
                        'text': 'Webhook port',
                        'key': 'webhook_port',
                        'type': int,
                        'default': 8765,
                        'minimum': 1024,
                        'maximum': 65535,
                        'width': 100,
                    },
                ]

        class Connection_Fields(ConfigFields):
            """Evolution API connection settings."""

            def __init__(self, parent):
                super().__init__(parent=parent)
                self.schema = [
                    {
                        'text': 'Evolution URL',
                        'key': 'evolution_url',
                        'type': str,
                        'default': 'http://localhost:8080',
                        'width': 300,
                    },
                    {
                        'text': 'API Key',
                        'key': 'evolution_api_key',
                        'type': str,
                        'default': '',
                        'width': 300,
                    },
                    {
                        'text': 'Instance name',
                        'key': 'instance_name',
                        'type': str,
                        'default': 'agentpilot',
                        'width': 200,
                    },
                ]

        class Security_Fields(ConfigFields):
            """Whitelist and security settings."""

            def __init__(self, parent):
                super().__init__(parent=parent)
                self.schema = [
                    {
                        'text': 'Whitelisted numbers',
                        'key': 'whitelisted_numbers',
                        'type': str,
                        'num_lines': 4,
                        'width': 300,
                        'default': '',
                        'label_position': 'top',
                        'tooltip': (
                            'One phone number per line '
                            '(digits only, e.g. 1234567890). '
                            'Leave empty to allow all.'
                        ),
                    },
                    {
                        'text': 'Debounce (ms)',
                        'key': 'debounce_ms',
                        'type': int,
                        'default': 2000,
                        'minimum': 0,
                        'maximum': 30000,
                        'width': 100,
                    },
                    {
                        'text': 'Session timeout (min)',
                        'key': 'session_timeout_minutes',
                        'type': int,
                        'default': 30,
                        'minimum': 1,
                        'maximum': 1440,
                        'width': 100,
                    },
                ]

            def get_config(self):
                """Convert multiline text to list for storage."""
                config = super().get_config()
                raw = config.get('whitelisted_numbers', '')
                if isinstance(raw, str):
                    numbers = [
                        n.strip() for n in raw.split('\n')
                        if n.strip()
                    ]
                    config['whitelisted_numbers'] = numbers
                return config

            def load_config(self, json_config=None):
                """Convert stored list back to multiline text."""
                if json_config is None:
                    json_config = getattr(self.parent, 'config', {})
                numbers = json_config.get('whitelisted_numbers', [])
                if isinstance(numbers, list):
                    json_config = dict(json_config)
                    json_config['whitelisted_numbers'] = '\n'.join(
                        numbers
                    )
                super().load_config(json_config)

        class Docker_Fields(ConfigFields):
            """Docker container management for Evolution API."""

            def __init__(self, parent):
                super().__init__(parent=parent)
                self.add_stretch_to_end = False
                self.conf_namespace = 'docker'
                self.schema = [
                    {
                        'text': 'Manage container',
                        'key': 'managed',
                        'type': bool,
                        'default': True,
                        'tooltip': (
                            'Automatically start/stop the '
                            'Evolution API Docker container'
                        ),
                    },
                    {
                        'text': 'Image',
                        'key': 'image_name',
                        'type': str,
                        'default': 'atendai/evolution-api',
                        'width': 250,
                    },
                    {
                        'text': 'Host port',
                        'key': 'host_port',
                        'type': int,
                        'default': 8080,
                        'minimum': 1024,
                        'maximum': 65535,
                        'width': 100,
                    },
                ]

            def after_init(self):
                controls = QWidget(self)
                layout = QHBoxLayout(controls)
                layout.setContentsMargins(0, 4, 0, 4)

                self.status_label = QLabel('Stopped')
                self.status_label.setStyleSheet(
                    'color: #888; font-weight: bold;'
                )
                layout.addWidget(self.status_label)
                layout.addStretch(1)

                self.btn_start = IconButton(
                    parent=controls,
                    icon_path=':/resources/icon-run.png',
                    tooltip='Start container',
                    size=18,
                )
                self.btn_start.clicked.connect(
                    self._start_container
                )
                layout.addWidget(self.btn_start)

                self.btn_stop = IconButton(
                    parent=controls,
                    icon_path=':/resources/icon-stop.png',
                    tooltip='Stop container',
                    size=18,
                )
                self.btn_stop.clicked.connect(
                    self._stop_container
                )
                layout.addWidget(self.btn_stop)

                self.btn_connect = IconButton(
                    parent=controls,
                    icon_path=':/resources/icon-chat.png',
                    tooltip='Connect WhatsApp (QR code)',
                    size=18,
                )
                self.btn_connect.clicked.connect(
                    self._connect_whatsapp
                )
                layout.addWidget(self.btn_connect)

                self.layout.addWidget(controls)

            def _get_channel_uuid(self):
                """Get the UUID of the currently selected channel."""
                from utils import sql
                tree = find_attribute(self, 'tree')
                if tree is None:
                    return None
                item_id = tree.get_selected_item_id()
                if item_id is None:
                    return None
                return sql.get_scalar(
                    "SELECT uuid FROM channels WHERE id = ?",
                    (item_id,),
                )

            def _get_adapter(self):
                """Get the adapter for the current channel."""
                daemon = system.manager.daemons.running_daemons.get(
                    'channels'
                )
                if daemon is None:
                    return None
                ch_uuid = self._get_channel_uuid()
                if ch_uuid is None:
                    return None
                return daemon.adapters.get(ch_uuid)

            def _make_adapter(self):
                """Create adapter for Docker ops."""
                from plugins.channels.adapters.whatsapp_evolution \
                    import WhatsAppEvolutionAdapter
                ch_uuid = self._get_channel_uuid()
                if ch_uuid is None:
                    return None
                return WhatsAppEvolutionAdapter(
                    ch_uuid, self.parent.config, ''
                )

            def _get_or_make_adapter(self):
                """Get running adapter or create a standalone one."""
                adapter = self._get_adapter()
                if adapter is not None:
                    return adapter
                return self._make_adapter()

            def _set_status(self, text, running=False):
                """Update status label text and color."""
                self.status_label.setText(text)
                color = '#4a4' if running else '#888'
                self.status_label.setStyleSheet(
                    f'color: {color}; font-weight: bold;'
                )

            def _start_container(self):
                adapter = self._get_or_make_adapter()
                if adapter is None:
                    self._set_status('No channel selected')
                    return
                self._set_status('Starting...')
                try:
                    adapter.start_container()
                except Exception as e:
                    self._set_status(f'Error: {e}')
                    return
                asyncio.ensure_future(
                    self._wait_for_ready(adapter)
                )

            async def _wait_for_ready(self, adapter):
                """Poll the Evolution API until it responds."""
                import aiohttp
                for _ in range(30):
                    try:
                        async with aiohttp.ClientSession() as s:
                            async with s.get(
                                adapter.evolution_url,
                                timeout=aiohttp.ClientTimeout(
                                    total=3
                                ),
                            ):
                                self._set_status(
                                    'Running', running=True
                                )
                                return
                    except Exception:
                        await asyncio.sleep(2)
                self._set_status('Container started, API not ready')

            def _stop_container(self):
                adapter = self._get_or_make_adapter()
                if adapter is None:
                    self._set_status('No channel selected')
                    return
                try:
                    adapter.stop_container()
                    self._set_status('Stopped')
                except Exception as e:
                    self._set_status(f'Error: {e}')

            def _connect_whatsapp(self):
                """Create instance and show QR code popup."""
                adapter = self._get_or_make_adapter()
                if adapter is None:
                    self._set_status('No channel selected')
                    return
                if not adapter.is_container_running():
                    self._set_status('Start container first')
                    return
                self._set_status('Connecting...')
                asyncio.ensure_future(
                    self._fetch_qr(adapter)
                )

            async def _fetch_qr(self, adapter):
                """Try create_instance, fall back to get_qr_code."""
                result = await adapter.create_instance()
                qr_base64 = self._extract_qr(result)
                if not qr_base64:
                    result = await adapter.get_qr_code()
                    qr_base64 = self._extract_qr(result)
                if qr_base64:
                    self._show_qr_popup(qr_base64)
                    self._set_status('Running', running=True)
                else:
                    self._set_status('QR code unavailable')

            def _extract_qr(self, result):
                """Extract base64 QR string from API response.

                Parameters
                ----------
                result : dict or None
                    Response from create_instance or get_qr_code.

                Returns
                -------
                str or None
                    Base64-encoded image data, or None.
                """
                if not result:
                    return None
                # create_instance nests under 'qrcode'
                qr = result.get('qrcode', {})
                if isinstance(qr, dict):
                    b64 = qr.get('base64', '')
                else:
                    b64 = qr if isinstance(qr, str) else ''
                if not b64:
                    # get_qr_code may return at top level
                    b64 = result.get('base64', '')
                # Strip data URI prefix if present
                if b64 and ',' in b64:
                    b64 = b64.split(',', 1)[1]
                return b64 or None

            def _show_qr_popup(self, qr_base64):
                """Display QR code in a dialog.

                Parameters
                ----------
                qr_base64 : str
                    Base64-encoded PNG image data.
                """
                dialog = QDialog(self)
                dialog.setWindowTitle(
                    'Scan QR Code with WhatsApp'
                )
                dialog.setModal(True)
                dlg_layout = QVBoxLayout(dialog)

                pixmap = QPixmap()
                img_data = QByteArray(
                    base64.b64decode(qr_base64)
                )
                pixmap.loadFromData(img_data)
                if pixmap.isNull():
                    label = QLabel('Failed to load QR image')
                else:
                    label = QLabel()
                    label.setPixmap(pixmap)
                dlg_layout.addWidget(label)

                dialog.show()

            def _refresh_status(self):
                """Query Docker for actual status (used on load)."""
                if not hasattr(self, 'status_label'):
                    return
                adapter = self._get_or_make_adapter()
                if adapter is None:
                    self._set_status('Stopped')
                    return
                try:
                    running = adapter.is_container_running()
                    self._set_status(
                        'Running' if running else 'Stopped',
                        running=running,
                    )
                except Exception:
                    self._set_status('Stopped')

            def load_config(self, json_config=None):
                super().load_config(json_config)
                self._refresh_status()

        class Agent_Config(WorkflowSettings):
            """Workflow settings for the default agent."""

            def __init__(self, parent):
                super().__init__(parent=parent, compact_mode=True)

            def update_config(self):
                self.save_config()

            def save_config(self):
                self.parent.update_config()
