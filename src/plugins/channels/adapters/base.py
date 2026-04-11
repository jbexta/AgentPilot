"""Base Channel Adapter.

Defines the abstract interface that all channel adapters must implement.
Each adapter handles communication with a specific messaging platform.
"""

from abc import ABC, abstractmethod
from typing import Optional


class BaseChannelAdapter(ABC):
    """Abstract base class for channel adapters.

    Parameters
    ----------
    channel_uuid : str
        Unique identifier for the channel this adapter serves.
    config : dict
        Channel configuration dictionary.
    """

    def __init__(self, channel_uuid, config):
        self.channel_uuid = channel_uuid
        self.config = config

    @abstractmethod
    async def start(self):
        """Start the adapter (register webhooks, etc.)."""

    @abstractmethod
    async def stop(self):
        """Stop the adapter and clean up resources."""

    @abstractmethod
    async def send_message(self, chat_id, text):
        """Send a text message to the specified chat.

        Parameters
        ----------
        chat_id : str
            Platform-specific chat identifier.
        text : str
            Message text to send.
        """

    @abstractmethod
    def normalize_message(self, payload):
        """Normalize a raw incoming message payload.

        Parameters
        ----------
        payload : dict
            Raw webhook payload from the platform.

        Returns
        -------
        dict or None
            Normalized dict with keys: sender, text, chat_id.
            Returns None if the payload should be ignored.
        """
