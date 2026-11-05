import os
import shutil

from plugins.projects.core.web_stacks.base import WebStack
from utils.helpers import set_module_type


@set_module_type(module_type='Web_stacks')
class PythonStack(WebStack):
    display_name = 'Python'
    priority = 30

    @classmethod
    def interpreter(cls, path):
        for venv in ('.venv', 'venv', 'env'):
            for binary in ('bin/python', 'Scripts/python.exe'):
                candidate = os.path.join(path, venv, binary)
                if os.path.isfile(candidate):
                    return f'"{candidate}"'
        return 'python3' if os.name != 'nt' else 'python'

    @classmethod
    def entry_point(cls, path):
        """The project's web entry point, as (kind, filename)."""
        if os.path.isfile(os.path.join(path, 'manage.py')):
            return 'django', 'manage.py'
        for name in ('app.py', 'main.py', 'server.py', 'wsgi.py'):
            full = os.path.join(path, name)
            if not os.path.isfile(full):
                continue
            with open(full, encoding='utf-8', errors='replace') as file:
                source = file.read()
            if 'FastAPI' in source:
                return 'fastapi', name
            if 'Flask' in source:
                return 'flask', name
        return '', ''

    @classmethod
    def detect(cls, path):
        return bool(cls.entry_point(path)[0])

    @classmethod
    def requirement(cls, path):
        interpreter = cls.interpreter(path).strip('"')
        if os.path.isfile(interpreter) or shutil.which(interpreter):
            return ''
        return f'{interpreter} is not installed.'

    @classmethod
    def services(cls, path, port):
        kind, filename = cls.entry_point(path)
        python = cls.interpreter(path)
        module = filename.removesuffix('.py')

        if kind == 'django':
            command = f'{python} manage.py runserver 127.0.0.1:{port}'
        elif kind == 'fastapi':
            command = (f'{python} -m uvicorn {module}:app '
                       f'--host 127.0.0.1 --port {port} --reload')
        elif kind == 'flask':
            command = (f'{python} -m flask --app {module} run '
                       f'--host 127.0.0.1 --port {port} --debug')
        else:
            return []

        return [{'name': 'python', 'command': command}]