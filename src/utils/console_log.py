import faulthandler
import os
import sys
from collections import deque

from PySide6.QtCore import qInstallMessageHandler

from utils.filesystem import get_application_path

_chunks = deque(maxlen=50000)


class Tee:
    """Mirrors writes to a stream into the log file and in-memory log."""
    def __init__(self, stream, log_file):
        self.stream = stream
        self.log_file = log_file

    def write(self, data):
        _chunks.append(data)
        try:
            self.log_file.write(data)
        except OSError:  # shared folders (e.g. vboxsf) can reject writes
            pass
        # Windowed executables have no console, so the stream can be None
        return self.stream.write(data) if self.stream else len(data)

    def flush(self):
        try:
            self.log_file.flush()
        except OSError:
            pass
        if self.stream:
            self.stream.flush()

    def __getattr__(self, name):
        return getattr(self.stream or self.log_file, name)


def start():
    log_path = os.path.join(get_application_path(), 'run.log')
    log_file = open(log_path, 'w', buffering=1, encoding='utf-8')
    sys.stdout = Tee(sys.stdout, log_file)
    sys.stderr = Tee(sys.stderr, log_file)
    # faulthandler.enable(log_file)
    # Test runs: run.log is overwritten by the next launch, so send crash
    # dumps to the real stderr, which run_tests.sh tees to run_tests.log.
    if os.environ.get('AP_RUN_TESTS') and sys.__stderr__:
        faulthandler.enable(sys.__stderr__)
    else:
        faulthandler.enable(log_file)
    qInstallMessageHandler(lambda mode, context, msg: print(msg, file=sys.stderr))


def tail(lines):
    return '\n'.join(''.join(_chunks).splitlines()[-lines:])
