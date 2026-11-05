
import io
import json
import sys


class SafeIntegratedEnvironment:
    """Integrated execution environment with access to app internals."""

    def __init__(self, config):
        self.config = config

    def run_code(self, lang: str, code: str, venv_path=None) -> str:
        """Execute Python code in-process with access to system managers."""
        if lang.lower() != 'python':
            raise ValueError(f"Language '{lang}' is not supported. Only Python is supported.")

        from gui import system
        from utils import sql

        exec_globals = {
            '__builtins__': __builtins__,
            'system': system,
            'sql': sql,
            'json': json,
        }

        byte_code = compile(code, '<inline>', 'exec')

        old_stdout = sys.stdout
        sys.stdout = io.StringIO()

        try:
            exec(byte_code, exec_globals)
            output = sys.stdout.getvalue()
            return output
        finally:
            sys.stdout = old_stdout
