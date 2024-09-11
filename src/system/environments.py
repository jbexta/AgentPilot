import json
import os

import src.plugins.openinterpreter.src
from src.utils import sql


OI_EXECUTOR = src.plugins.openinterpreter.src.interpreter


class EnvironmentManager:
    def __init__(self):
        self.environments = {}  # dict of name: Environment

    def load(self):
        from src.system.plugins import get_plugin_class
        data = sql.get_results("""
            SELECT
                name,
                config
            FROM sandboxes""", return_type='dict')
        for name, config in data.items():
            config = json.loads(config)  # todo clean
            if name not in self.environments:
                env_class = get_plugin_class('Sandbox', name, default_class=Environment)
                env_obj = env_class(config=config)
                self.environments[name] = env_obj
            else:
                self.environments[name].update(config)


class Environment:
    def __init__(self, config):
        self.config = config
        self.update(config)

    def run_code(self, lang, code, venv_path=None):
        OI_EXECUTOR.venv_path = venv_path
        oi_res = OI_EXECUTOR.computer.run(lang, code)
        output = next(r for r in oi_res if r['format'] == 'output').get('content', '')
        return output

    def update(self, config):
        self.config = config
        self.set_env_vars()

    def set_env_vars(self):
        env_vars = self.config.get('env_vars.data', '{}')  # todo clean nested json
        env_vars = json.loads(env_vars)
        for env_var in env_vars:
            ev_name, ev_value = env_var.get('env_var'), env_var.get('value')
            if ev_name == 'Variable name':
                continue
            os.environ[ev_name] = (ev_value or '')
