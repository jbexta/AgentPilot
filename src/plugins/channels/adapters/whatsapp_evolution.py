"""WhatsApp Evolution API Adapter.

Integrates with Evolution API (open-source Baileys-based WhatsApp Web bridge)
to send and receive WhatsApp messages. Evolution API runs as a Docker
Compose stack (API + PostgreSQL + Redis) and exposes a REST API.
"""

import logging
import os
import subprocess
import textwrap

import aiohttp

from plugins.channels.adapters.base import BaseChannelAdapter

logger = logging.getLogger(__name__)

_COMPOSE_TEMPLATE = textwrap.dedent("""\
    version: "3.8"

    services:
      api:
        container_name: {api_name}
        image: {image}
        restart: unless-stopped
        depends_on:
          postgres:
            condition: service_started
          redis:
            condition: service_started
        ports:
          - "127.0.0.1:{host_port}:8080"
        environment:
          - DATABASE_PROVIDER=postgresql
          - DATABASE_CONNECTION_URI=postgresql://evo:evo@postgres:5432/evolution
          - CACHE_REDIS_ENABLED=true
          - CACHE_REDIS_URI=redis://redis:6379
          - AUTHENTICATION_API_KEY={api_key}

      postgres:
        container_name: {pg_name}
        image: postgres:15
        restart: unless-stopped
        environment:
          - POSTGRES_DB=evolution
          - POSTGRES_USER=evo
          - POSTGRES_PASSWORD=evo
        volumes:
          - pgdata:/var/lib/postgresql/data

      redis:
        container_name: {redis_name}
        image: redis:7
        restart: unless-stopped
        volumes:
          - redisdata:/data

    volumes:
      pgdata:
      redisdata:
""")


class WhatsAppEvolutionAdapter(BaseChannelAdapter):
    """Adapter for Evolution API WhatsApp bridge.

    Parameters
    ----------
    channel_uuid : str
        Unique identifier for the channel.
    config : dict
        Must contain evolution_url, evolution_api_key, instance_name.
    webhook_base_url : str
        Base URL the daemon's webhook server is reachable at.
    """

    def __init__(self, channel_uuid, config, webhook_base_url):
        super().__init__(channel_uuid, config)
        self.webhook_base_url = webhook_base_url
        self.evolution_url = config.get(
            'evolution_url', 'http://localhost:8080'
        ).rstrip('/')
        self.api_key = config.get('evolution_api_key', '')
        self.instance_name = config.get('instance_name', 'agentpilot')
        self._session = None

    def _headers(self):
        return {
            'Content-Type': 'application/json',
            'apikey': self.api_key,
        }

    # ------------------------------------------------------------------
    # Docker Compose management
    # ------------------------------------------------------------------

    @property
    def _docker_managed(self):
        return self.config.get('docker.managed', True)

    def _project_name(self):
        """Deterministic compose project name."""
        short = self.channel_uuid[:8]
        return f"agentpilot_evo_{short}"

    def _compose_dir(self):
        """Directory for this channel's docker-compose.yml."""
        from utils.filesystem import get_application_path
        d = os.path.join(
            get_application_path(), 'docker', self._project_name()
        )
        os.makedirs(d, exist_ok=True)
        return d

    def _write_compose_file(self):
        """Generate docker-compose.yml for this channel."""
        proj = self._project_name()
        image = self.config.get(
            'docker.image_name', 'atendai/evolution-api'
        )
        host_port = self.config.get('docker.host_port', 8080)
        content = _COMPOSE_TEMPLATE.format(
            api_name=f"{proj}_api",
            pg_name=f"{proj}_pg",
            redis_name=f"{proj}_redis",
            image=image,
            host_port=int(host_port),
            api_key=self.api_key or 'changeme',
        )
        path = os.path.join(self._compose_dir(), 'docker-compose.yml')
        with open(path, 'w') as f:
            f.write(content)
        return path

    def _run_compose(self, *args):
        """Run a docker compose command.

        Parameters
        ----------
        *args : str
            Arguments passed after ``docker compose``.

        Returns
        -------
        subprocess.CompletedProcess
        """
        compose_file = os.path.join(
            self._compose_dir(), 'docker-compose.yml'
        )
        cmd = [
            'docker', 'compose',
            '-f', compose_file,
            '-p', self._project_name(),
            *args,
        ]
        return subprocess.run(
            cmd, capture_output=True, text=True, timeout=120,
        )

    def start_container(self):
        """Start the Evolution API compose stack."""
        self._write_compose_file()
        result = self._run_compose('up', '-d')
        if result.returncode != 0:
            raise RuntimeError(
                result.stderr.strip() or result.stdout.strip()
            )
        logger.info("Started compose stack %s", self._project_name())

    def stop_container(self):
        """Stop the Evolution API compose stack."""
        compose_file = os.path.join(
            self._compose_dir(), 'docker-compose.yml'
        )
        if not os.path.exists(compose_file):
            return
        result = self._run_compose('down')
        if result.returncode != 0:
            logger.error(
                "Error stopping compose stack: %s",
                result.stderr.strip(),
            )
        else:
            logger.info(
                "Stopped compose stack %s", self._project_name()
            )

    def is_container_running(self):
        """Check if the Evolution API container is running.

        Returns
        -------
        bool
        """
        compose_file = os.path.join(
            self._compose_dir(), 'docker-compose.yml'
        )
        if not os.path.exists(compose_file):
            return False
        result = self._run_compose('ps', '--format', 'json')
        if result.returncode != 0:
            return False
        # Check that the api service is running
        output = result.stdout.strip()
        return '"running"' in output and 'api' in output

    # ------------------------------------------------------------------
    # Adapter lifecycle
    # ------------------------------------------------------------------

    async def start(self):
        """Start the adapter, optionally managing the Docker container."""
        if self._docker_managed:
            try:
                self.start_container()
            except Exception as e:
                logger.error(
                    "Failed to start Docker container: %s", e
                )

        self._session = aiohttp.ClientSession()
        webhook_url = (
            f"{self.webhook_base_url}/webhook/wa/{self.channel_uuid}"
        )
        payload = {
            'url': webhook_url,
            'webhook_by_events': False,
            'webhook_base64': False,
            'events': ['MESSAGES_UPSERT'],
        }
        try:
            url = (
                f"{self.evolution_url}/webhook/set/"
                f"{self.instance_name}"
            )
            async with self._session.post(
                url, json=payload, headers=self._headers()
            ) as resp:
                if resp.status == 200:
                    logger.info(
                        "Webhook registered for channel %s",
                        self.channel_uuid,
                    )
                else:
                    body = await resp.text()
                    logger.warning(
                        "Failed to register webhook (status %s): %s",
                        resp.status, body,
                    )
        except aiohttp.ClientError as e:
            logger.error(
                "Could not reach Evolution API at %s: %s",
                self.evolution_url, e,
            )

    async def stop(self):
        """Close the HTTP session and optionally stop the container."""
        if self._session and not self._session.closed:
            await self._session.close()
            self._session = None

        if self._docker_managed:
            try:
                self.stop_container()
            except Exception as e:
                logger.error(
                    "Failed to stop Docker container: %s", e
                )

    async def send_message(self, chat_id, text):
        """Send a text message via Evolution API.

        Parameters
        ----------
        chat_id : str
            WhatsApp JID (e.g. '1234567890@s.whatsapp.net').
        text : str
            Message body.
        """
        if not self._session or self._session.closed:
            self._session = aiohttp.ClientSession()

        url = (
            f"{self.evolution_url}/message/sendText/"
            f"{self.instance_name}"
        )
        payload = {
            'number': chat_id,
            'text': text,
        }
        try:
            async with self._session.post(
                url, json=payload, headers=self._headers()
            ) as resp:
                if resp.status != 201:
                    body = await resp.text()
                    logger.warning(
                        "send_message failed (status %s): %s",
                        resp.status, body,
                    )
        except aiohttp.ClientError as e:
            logger.error("send_message error: %s", e)

    def normalize_message(self, payload):
        """Extract sender, text, and chat_id from Evolution API webhook.

        Parameters
        ----------
        payload : dict
            Raw webhook POST body from Evolution API.

        Returns
        -------
        dict or None
            Normalized message dict, or None if not a user text message.
        """
        data = payload.get('data', {})
        key = data.get('key', {})

        # Ignore messages sent by us
        if key.get('fromMe', False):
            return None

        message = data.get('message', {})
        text = message.get('conversation') or message.get(
            'extendedTextMessage', {}
        ).get('text')
        if not text:
            return None

        remote_jid = key.get('remoteJid', '')
        # Extract phone number from JID (e.g. 1234567890@s.whatsapp.net)
        sender = remote_jid.split('@')[0] if '@' in remote_jid else remote_jid

        return {
            'sender': sender,
            'text': text,
            'chat_id': remote_jid,
        }

    async def create_instance(self):
        """Create the Evolution API instance.

        Returns
        -------
        dict or None
            Instance info including QR code, or None on failure.
        """
        if not self._session or self._session.closed:
            self._session = aiohttp.ClientSession()

        url = f"{self.evolution_url}/instance/create"
        payload = {
            'instanceName': self.instance_name,
            'qrcode': True,
        }
        try:
            async with self._session.post(
                url, json=payload, headers=self._headers()
            ) as resp:
                if resp.status in (200, 201):
                    return await resp.json()
                else:
                    body = await resp.text()
                    logger.warning(
                        "create_instance failed (status %s): %s",
                        resp.status, body,
                    )
                    return None
        except aiohttp.ClientError as e:
            logger.error("create_instance error: %s", e)
            return None

    async def get_qr_code(self):
        """Fetch QR code for WhatsApp pairing.

        Returns
        -------
        dict or None
            QR code data from Evolution API, or None on failure.
        """
        if not self._session or self._session.closed:
            self._session = aiohttp.ClientSession()

        url = (
            f"{self.evolution_url}/instance/connect/"
            f"{self.instance_name}"
        )
        try:
            async with self._session.get(
                url, headers=self._headers()
            ) as resp:
                if resp.status == 200:
                    return await resp.json()
                else:
                    body = await resp.text()
                    logger.warning(
                        "get_qr_code failed (status %s): %s",
                        resp.status, body,
                    )
                    return None
        except aiohttp.ClientError as e:
            logger.error("get_qr_code error: %s", e)
            return None
