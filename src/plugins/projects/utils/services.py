"""Runs the processes a Website project's stack needs.

The stack module decides what to run; this just supervises it. Services
stop when another project is opened, when the user stops them, and when
the app quits, so nothing is left listening on a port afterwards.
"""

import json
from functools import partial

from PySide6.QtCore import QObject, QProcess, QProcessEnvironment, Signal
from PySide6.QtWidgets import QApplication

from plugins.projects.utils.tls_proxy import serve_https


class ServiceRunner(QObject):
    output = Signal(str)

    def __init__(self):
        super().__init__()
        self._procs = {}
        self._key = None
        self._proxy = None

    def running(self):
        return bool(self._procs)

    async def start(self, services, working_dir, force=False, proxy=None):
        """Run *services* in *working_dir*, replacing anything running.

        Repeated calls for the same project do nothing, so saving a field
        never restarts a healthy process. *force* overrides that.
        *proxy* is a ``(port, target_port)`` pair to serve over HTTPS.
        """
        key = (working_dir, json.dumps(services, sort_keys=True), proxy)
        if key == self._key and not force:
            return
        self.stop()
        self._key = key

        if proxy:
            try:
                self._proxy = await serve_https(*proxy)
            except OSError as e:
                self.output.emit(f'[https] {e}')
                return
            self.output.emit(f'[https] port {proxy[0]} -> {proxy[1]}')

        for service in services:
            name = service.get('name', '')
            command = service.get('command', '')
            if not command:
                continue

            proc = QProcess(self)
            proc.setWorkingDirectory(working_dir)
            proc.setProcessChannelMode(QProcess.MergedChannels)
            proc.readyReadStandardOutput.connect(
                partial(self._read_output, name, proc)
            )
            proc.errorOccurred.connect(partial(self._report_error, name))

            env = service.get('env', {})
            if env:
                process_env = QProcessEnvironment.systemEnvironment()
                for env_key, value in env.items():
                    process_env.insert(env_key, value)
                proc.setProcessEnvironment(process_env)

            self.output.emit(f'[{name}] $ {command}')
            proc.startCommand(command)
            self._procs[name] = proc

    def stop(self):
        if self._proxy:
            self._proxy.close()
            self._proxy = None
            self.output.emit('[https] stopped')
        for name, proc in self._procs.items():
            # Stop reporting errors first, or terminate() reports a crash.
            proc.errorOccurred.disconnect()
            proc.terminate()
            if not proc.waitForFinished(1000):
                proc.kill()
            self.output.emit(f'[{name}] stopped')
        self._procs.clear()

    def _read_output(self, name, proc):
        text = bytes(proc.readAllStandardOutput()).decode(errors='replace')
        for line in text.splitlines():
            self.output.emit(f'[{name}] {line}')

    def _report_error(self, name, error):
        self.output.emit(f'[{name}] {error.name}')


runner = ServiceRunner()

_app = QApplication.instance()
if _app:
    _app.aboutToQuit.connect(runner.stop)
