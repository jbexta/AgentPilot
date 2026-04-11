"""Channels Daemon.

Runs a lightweight aiohttp webhook server, manages channel adapters,
performs whitelist checks, debounces rapid messages, resolves sessions,
applies routing rules, and dispatches messages to agents via
``receive_workflow``.
"""

import asyncio
import json
import logging
import time
from datetime import datetime
from typing import Dict, Optional

from aiohttp import web

from utils import sql
from utils.helpers import receive_workflow
from utils.sql import define_table

logger = logging.getLogger(__name__)

define_table('channels')

# Session tracking table (created once, idempotent)
sql.execute("""
    CREATE TABLE IF NOT EXISTS channel_sessions (
        id INTEGER PRIMARY KEY,
        channel_id TEXT NOT NULL,
        external_chat_id TEXT NOT NULL,
        context_id INTEGER,
        agent_id INTEGER,
        last_activity DATETIME,
        UNIQUE(channel_id, external_chat_id)
    )
""")


ADAPTER_CLASSES = {
    'whatsapp_evolution': (
        'plugins.channels.adapters.whatsapp_evolution',
        'WhatsAppEvolutionAdapter',
    ),
}


class ChannelsDaemon:
    """Webhook server daemon that bridges messaging channels to agents."""

    def __init__(self, system):
        self.system = system
        self.channel_configs: Dict[str, dict] = {}
        self.channel_names: Dict[str, str] = {}
        self.adapters: Dict[str, object] = {}
        self._running = False
        self._app: Optional[web.Application] = None
        self._runner: Optional[web.AppRunner] = None
        self._debounce: Dict[str, float] = {}
        self._debounce_tasks: Dict[str, asyncio.Task] = {}
        self._webhook_port = 8765

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    async def start(self):
        """Start the webhook server and load channels."""
        self._running = True

        self._app = web.Application()
        self._app.router.add_post(
            '/webhook/wa/{channel_uuid}', self._handle_webhook
        )

        self._runner = web.AppRunner(self._app)
        await self._runner.setup()

        await self.load()

        site = web.TCPSite(self._runner, '0.0.0.0', self._webhook_port)
        await site.start()
        logger.info(
            "Channels webhook server listening on port %s",
            self._webhook_port,
        )

        # Keep daemon alive
        while self._running:
            await asyncio.sleep(1)

    def stop(self):
        """Signal the daemon to shut down."""
        self._running = False
        for task in self._debounce_tasks.values():
            if not task.done():
                task.cancel()
        self._debounce_tasks.clear()

        asyncio.ensure_future(self._shutdown())

    async def _shutdown(self):
        """Stop adapters and the HTTP server."""
        for adapter in self.adapters.values():
            try:
                await adapter.stop()
            except Exception as e:
                logger.error("Error stopping adapter: %s", e)
        self.adapters.clear()

        if self._runner:
            await self._runner.cleanup()
            self._runner = None

    # ------------------------------------------------------------------
    # Config loading
    # ------------------------------------------------------------------

    async def load(self):
        """Reload channel configs from the database and restart adapters."""
        self.channel_names = sql.get_results(
            "SELECT uuid, name FROM channels", return_type='dict'
        )
        raw_configs = sql.get_results(
            "SELECT uuid, config FROM channels", return_type='dict'
        )
        self.channel_configs = {
            k: json.loads(v) for k, v in raw_configs.items()
        }

        # Determine webhook port from first enabled channel (or default)
        for cfg in self.channel_configs.values():
            if cfg.get('enabled', False):
                self._webhook_port = cfg.get('webhook_port', 8765)
                break

        # Stop old adapters
        for adapter in self.adapters.values():
            try:
                await adapter.stop()
            except Exception as e:
                logger.error("Error stopping adapter: %s", e)
        self.adapters.clear()

        # Start adapters for enabled channels
        for ch_uuid, cfg in self.channel_configs.items():
            if not cfg.get('enabled', False):
                continue
            await self._start_adapter(ch_uuid, cfg)

    async def _start_adapter(self, channel_uuid, config):
        """Instantiate and start an adapter for a channel."""
        channel_type = config.get('channel_type', '')
        if isinstance(channel_type, list):
            channel_type = channel_type[0] if channel_type else ''
        adapter_info = ADAPTER_CLASSES.get(channel_type)
        if not adapter_info:
            logger.warning(
                "Unknown channel_type '%s' for channel %s",
                channel_type, channel_uuid,
            )
            return

        module_path, class_name = adapter_info
        import importlib
        mod = importlib.import_module(module_path)
        adapter_cls = getattr(mod, class_name)

        webhook_base = f"http://localhost:{self._webhook_port}"
        adapter = adapter_cls(channel_uuid, config, webhook_base)

        try:
            await adapter.start()
            self.adapters[channel_uuid] = adapter
            logger.info("Adapter started for channel %s", channel_uuid)
        except Exception as e:
            logger.error(
                "Failed to start adapter for channel %s: %s",
                channel_uuid, e,
            )

    # ------------------------------------------------------------------
    # Webhook handler
    # ------------------------------------------------------------------

    async def _handle_webhook(self, request):
        """Handle incoming POST from a messaging platform."""
        channel_uuid = request.match_info['channel_uuid']
        if channel_uuid not in self.adapters:
            return web.Response(status=404, text='Channel not found')

        try:
            payload = await request.json()
        except Exception:
            return web.Response(status=400, text='Invalid JSON')

        adapter = self.adapters[channel_uuid]
        normalized = adapter.normalize_message(payload)
        if normalized is None:
            return web.Response(status=200, text='OK')

        asyncio.ensure_future(
            self.on_message_received(channel_uuid, normalized)
        )
        return web.Response(status=200, text='OK')

    # ------------------------------------------------------------------
    # Message processing
    # ------------------------------------------------------------------

    async def on_message_received(self, channel_uuid, msg):
        """Process an incoming normalized message.

        Parameters
        ----------
        channel_uuid : str
            UUID of the channel that received the message.
        msg : dict
            Normalized message with keys: sender, text, chat_id.
        """
        config = self.channel_configs.get(channel_uuid, {})

        # Whitelist check
        whitelist = config.get('whitelisted_numbers', [])
        if whitelist and msg['sender'] not in whitelist:
            logger.info(
                "Rejected message from non-whitelisted sender %s",
                msg['sender'],
            )
            return

        # Debounce
        debounce_ms = config.get('debounce_ms', 2000)
        debounce_key = f"{channel_uuid}:{msg['chat_id']}"
        now = time.monotonic()
        last = self._debounce.get(debounce_key, 0)
        if now - last < debounce_ms / 1000.0:
            # Cancel previous pending task and reschedule
            prev = self._debounce_tasks.pop(debounce_key, None)
            if prev and not prev.done():
                prev.cancel()

        self._debounce[debounce_key] = now

        delay = debounce_ms / 1000.0
        task = asyncio.create_task(
            self._debounced_dispatch(
                debounce_key, delay, channel_uuid, msg, config
            )
        )
        # Cancel any previously scheduled task for this key
        prev = self._debounce_tasks.pop(debounce_key, None)
        if prev and not prev.done():
            prev.cancel()
        self._debounce_tasks[debounce_key] = task

    async def _debounced_dispatch(
        self, debounce_key, delay, channel_uuid, msg, config
    ):
        """Wait for debounce period then dispatch the message."""
        try:
            await asyncio.sleep(delay)
        except asyncio.CancelledError:
            return

        self._debounce_tasks.pop(debounce_key, None)
        await self._dispatch_message(channel_uuid, msg, config)

    async def _dispatch_message(self, channel_uuid, msg, config):
        """Route and dispatch a message to the appropriate agent."""
        agent_id = self._resolve_agent(msg, config)

        if agent_id and agent_id > 0:
            # Routing rule matched — load agent from contexts table
            self._upsert_session(
                channel_uuid, msg['chat_id'], agent_id
            )
            agent_config = sql.get_scalar(
                "SELECT config FROM contexts WHERE id = ?",
                (agent_id,),
            )
            if not agent_config:
                logger.warning("Agent %s not found", agent_id)
                return
            agent_config = json.loads(agent_config)
        else:
            # No routing rule — use the channel's embedded workflow
            self._upsert_session(
                channel_uuid, msg['chat_id'], 0
            )
            agent_config = config

        # Inject the user message as a param
        params = {
            'user_msg': msg['text'],
            'channel_sender': msg['sender'],
            'channel_chat_id': msg['chat_id'],
        }

        channel_name = self.channel_names.get(channel_uuid, 'Channel')
        chat_title = f"{channel_name} - {msg['sender']}"

        # Run the workflow
        response = ''
        try:
            async for key, chunk in receive_workflow(
                agent_config,
                kind='CHANNEL',
                params=params,
                chat_title=chat_title,
                main=self.system._main_gui,
            ):
                response += chunk
        except Exception as e:
            logger.error("Workflow error for channel %s: %s", channel_uuid, e)
            response = "Sorry, an error occurred processing your message."

        # Send response back
        if response.strip():
            adapter = self.adapters.get(channel_uuid)
            if adapter:
                await adapter.send_message(msg['chat_id'], response.strip())

    def _resolve_agent(self, msg, config):
        """Apply routing rules to determine the target agent ID.

        Parameters
        ----------
        msg : dict
            Normalized message.
        config : dict
            Channel configuration.

        Returns
        -------
        int or None
            Agent ID to handle the message.
        """
        rules = config.get('routing_rules', [])
        text = msg.get('text', '')

        for rule in rules:
            match_type = rule.get('match_type', '')
            match_value = rule.get('match_value', '')
            agent_id = rule.get('agent_id')

            if not match_value or agent_id is None:
                continue

            if match_type == 'starts_with' and text.startswith(match_value):
                return agent_id
            elif match_type == 'contains' and match_value in text:
                return agent_id
            elif match_type == 'equals' and text == match_value:
                return agent_id
            elif match_type == 'regex':
                import re
                if re.search(match_value, text):
                    return agent_id

        return None

    def _upsert_session(self, channel_id, external_chat_id, agent_id):
        """Create or update a channel session record."""
        now = datetime.utcnow().isoformat()
        sql.execute("""
            INSERT INTO channel_sessions
                (channel_id, external_chat_id, agent_id, last_activity)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(channel_id, external_chat_id)
            DO UPDATE SET
                agent_id = excluded.agent_id,
                last_activity = excluded.last_activity
        """, (channel_id, external_chat_id, agent_id, now))
