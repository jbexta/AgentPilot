import json
import os
import shutil

from plugins.projects.core.web_stacks.base import WebStack
from utils.helpers import set_module_type


@set_module_type(module_type='Web_stacks')
class NodeStack(WebStack):
    display_name = 'Node'
    priority = 30

    @classmethod
    def scripts(cls, path):
        manifest = os.path.join(path, 'package.json')
        if not os.path.isfile(manifest):
            return {}
        with open(manifest, encoding='utf-8') as file:
            return json.load(file).get('scripts', {})

    @classmethod
    def detect(cls, path):
        return bool(cls.scripts(path))

    @classmethod
    def requirement(cls, path):
        if not shutil.which('npm'):
            return 'npm is not installed. Install Node.js.'
        if not cls.script(path):
            return 'package.json has no dev, start or serve script.'
        return ''

    @classmethod
    def script(cls, path):
        scripts = cls.scripts(path)
        return next(
            (name for name in ('dev', 'start', 'serve') if name in scripts),
            '',
        )

    @classmethod
    def services(cls, path, port):
        script = cls.script(path)
        if not script:
            return []
        return [{
            'name': 'node',
            'command': f'npm run {script}',
            # Most Node servers honour PORT; the ones that don't print the
            # port they picked, and the preview follows that instead.
            'env': {'PORT': str(port), 'BROWSER': 'none'},
        }]