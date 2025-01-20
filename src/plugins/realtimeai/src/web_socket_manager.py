import json
import logging
import threading
import time
import uuid
import websocket  # pip install websocket-client
from realtime_ai.models.realtime_ai_options import RealtimeAIOptions

logger = logging.getLogger(__name__)


class WebSocketManager:
    """
    Synchronous WebSocket manager for handling connections and communication.
    """
    
    def __init__(self, options : RealtimeAIOptions, service_manager):
        self._options = options
        self._service_manager = service_manager

        if self._options.azure_openai_endpoint:
            request_id = uuid.uuid4()
            self._url = self._options.azure_openai_endpoint + f"?api-version={self._options.azure_openai_api_version}" + f"&deployment={self._options.model}"
            self._headers = {
                "x-ms-client-request-id": str(request_id),
                "api-key": self._options.api_key,
            }
        else:
            self._url = f"{self._options.url}?model={self._options.model}"
            self._headers = {
                "Authorization": f"Bearer {self._options.api_key}",
                "openai-beta": "realtime=v1",
            }

        self._ws = None
        self._receive_thread = None
        self._reconnect_delay = 5 # Time to wait before attempting to reconnect, in seconds
        self._is_reconnection = False

    def connect(self):
        """
        Establishes a WebSocket connection.
        """
        try:
            if self._ws and self._ws.sock and self._ws.sock.connected:
                logger.info("WebSocketManager: Already connected.")
                return
    
            logger.info(f"WebSocketManager: Connecting to {self._url}")
            self._ws = websocket.WebSocketApp(
                self._url,
                on_open=self._on_open,
                on_message=self._on_message,
                on_error=self._on_error,
                on_close=self._on_close,
                header=self._headers
            )

            self._receive_thread = threading.Thread(target=self._ws.run_forever)
            self._receive_thread.start()
            logger.info("WebSocketManager: WebSocket connection established.")
        except Exception as e:
            logger.error(f"WebSocketManager: Connection error: {e}")

    def disconnect(self):
        """
        Gracefully disconnects the WebSocket connection.
        """
        if self._ws:
            self._ws.close()
            if self._receive_thread:
                self._receive_thread.join()
            logger.info("WebSocketManager: WebSocket closed gracefully.")

    def send(self, message: dict):
        """
        Sends a message over the WebSocket.
        """
        if self._ws and self._ws.sock and self._ws.sock.connected:
            try:
                message_str = json.dumps(message)
                self._ws.send(message_str)
                logger.debug(f"WebSocketManager: Sent message: {message_str}")
            except Exception as e:
                logger.error(f"WebSocketManager: Send failed: {e}")

    def _on_open(self, ws):
        logger.info("WebSocketManager: WebSocket connection opened.")
        if self._is_reconnection:
            logger.info("WebSocketManager: Connection reopened (Reconnection).")
            self._service_manager.on_connected(reconnection=True)
            self._is_reconnection = False
        else:
            logger.info("WebSocketManager: Connection opened (Initial).")
            self._service_manager.on_connected()

        self._is_reconnection = False 

    def _on_message(self, ws, message):
        logger.debug(f"WebSocketManager: Received message: {message}")
        self._service_manager.on_message_received(message)

    def _on_error(self, ws, error):
        logger.error(f"WebSocketManager: WebSocket error: {error}")
        self._service_manager.on_error(error)

    def _on_close(self, ws, close_status_code, close_msg):
        logger.warning(f"WebSocketManager: WebSocket connection closed: {close_status_code} - {close_msg}")
        self._service_manager.on_disconnected(close_status_code, close_msg)

        # If the session ended due to maximum duration, attempt to reconnect
        if close_status_code == 1001 and "maximum duration of 15 minutes" in close_msg:
            logger.debug("WebSocketManager: Session ended due to maximum duration. Reconnecting...")
            if self._options.enable_auto_reconnect:
                self._schedule_reconnect()

    def _schedule_reconnect(self):
        logger.info("WebSocketManager: Scheduling reconnection...")
        time.sleep(self._reconnect_delay)
        self._is_reconnection = True
        self.connect()
