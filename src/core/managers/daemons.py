
import asyncio
import inspect
import logging
from types import MappingProxyType
from typing import Any, Dict, Mapping, Protocol, Type

logger = logging.getLogger(__name__)

class DaemonManager:
    def __init__(self, system):
        self._system = system

        self._daemon_classes = {}
        self._instances = {}
        self._tasks = {}

    def load(self) -> None:
        """Discover available daemon classes from the `Daemons` directory."""
        self._daemon_classes.clear()

        for name, daemon_cls in self._system.modules.get_modules_in_folder(
            "Daemons", ("name", "class")
        ):
            self._daemon_classes[name] = daemon_cls
            logger.debug("Registered daemon %s -> %s", name, daemon_cls)

    @property
    def available_daemons(self):  #  -> Mapping[DaemonName, DaemonType]:
        """Read-only view of all discovered daemon classes."""
        return MappingProxyType(self._daemon_classes)

    @property
    def running_daemons(self):  #  -> Mapping[DaemonName, Daemon]:
        """Read-only view of currently running daemons."""
        return MappingProxyType(self._instances)


    def start_daemon(self, daemon_name):  # : DaemonName) -> bool:
        """
        Instantiate and start a daemon by name.

        Returns:
            True if the daemon was started, False if it was unknown
            or already running.
        """
        if daemon_name in self._tasks:
            logger.debug("Daemon %s is already running", daemon_name)
            return False

        daemon_cls = self._daemon_classes.get(daemon_name)
        if daemon_cls is None:
            logger.warning("Unknown daemon %s", daemon_name)
            return False

        daemon = daemon_cls(self._system)
        self._instances[daemon_name] = daemon

        task = asyncio.create_task(
            self._run_daemon(daemon_name, daemon),
            name=f"daemon:{daemon_name}",
        )
        self._tasks[daemon_name] = task

        return True

    async def _run_daemon(self, daemon_name, daemon):  # : DaemonName, daemon: Daemon) -> None:
        """
        Internal wrapper around `daemon.start()` with logging & cleanup.

        Ensures we always remove the daemon from bookkeeping when it finishes.
        """
        logger.info("Starting daemon: %s", daemon_name)
        try:
            await daemon.start()
        except asyncio.CancelledError:
            logger.info("Daemon %s cancelled", daemon_name)
            raise
        except Exception:
            logger.exception("Daemon %s crashed", daemon_name)
            raise
        finally:
            self._instances.pop(daemon_name, None)
            self._tasks.pop(daemon_name, None)
            logger.info("Daemon %s stopped", daemon_name)

    def stop_daemon(self, daemon_name):  # : DaemonName) -> bool:
        """
        Signal a running daemon to stop.

        Returns:
            True if the daemon was running and stop signal was sent,
            False otherwise.
        """
        daemon = self._instances.get(daemon_name)
        if daemon is None:
            logger.debug("Daemon %s is not running", daemon_name)
            return False

        try:
            result = daemon.stop()
            # Allow daemons to implement async stop if they want
            if inspect.isawaitable(result):
                asyncio.create_task(result)  # fire-and-forget async stop
        except Exception:
            logger.exception("Error while stopping daemon %s", daemon_name)

        logger.info("Stop signal sent to daemon %s", daemon_name)
        return True

    async def restart_daemon(self, daemon_name, timeout=5.0):  # : DaemonName) -> bool:
        """
        Restart a daemon: stop it, wait for its task to finish (cancelling
        it after `timeout` seconds), then start a fresh instance.

        Returns:
            True if start succeeded, False otherwise.
        """
        task = self._tasks.get(daemon_name)
        self.stop_daemon(daemon_name)
        if task is not None:
            done, _ = await asyncio.wait({task}, timeout=timeout)
            if not done:
                logger.warning(
                    "Daemon %s didn't stop within %ss, cancelling",
                    daemon_name, timeout,
                )
                task.cancel()
                await asyncio.wait({task})
        return self.start_daemon(daemon_name)

    def start_all_daemons(self):  #  -> None:
        """Start all discovered daemons."""
        for name in self._daemon_classes:
            self.start_daemon(name)

    def stop_all_daemons(self) -> None:
        """Stop all currently running daemons."""
        for name in list(self._instances):
            self.stop_daemon(name)

    def cancel_all_daemons(self) -> None:
        """Cancel every running daemon task, interrupting any pending await."""
        for task in list(self._tasks.values()):
            task.cancel()
