import shutil

from plugins.projects.core.web_stacks.base import WebStack
from utils.helpers import set_module_type


@set_module_type(module_type='Web_stacks')
class PhpStack(WebStack):
    display_name = 'PHP'
    priority = 40

    @classmethod
    def binary(cls):
        return shutil.which('php') or ''

    @classmethod
    def detect(cls, path):
        return cls.has_files(path, '*.php')

    @classmethod
    def requirement(cls, path):
        if cls.binary():
            return ''
        return 'PHP is not installed. Install PHP, XAMPP or WAMP.'

    @classmethod
    def url(cls, path, port):
        return cls.site_url(path, port)

    @classmethod
    def services(cls, path, port):
        return [{
            'name': 'php',
            'command': f'"{cls.binary() or "php"}" -S 127.0.0.1:{port} '
                       f'-t "{cls.web_root(path)}"',
        }]