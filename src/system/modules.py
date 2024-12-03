# import hashlib
import hashlib
import importlib
import json
import os
import sys
import tempfile

from src.utils import sql


class ModuleManager:
    def __init__(self, parent):
        self.parent = parent
        self.modules = {}
        self.module_metadatas = {}
        self.loaded_modules = {}

    def load(self):
        modules_table = sql.get_results("""
            SELECT
                name,
                config,
                metadata
            FROM modules""")  # , return_type='dict')
        for name, config, metadata in modules_table:
            # recheck_hash = hashlib.sha1(code.encode()).hexdigest()
            config = json.loads(config)
            self.modules[name] = config
            self.module_metadatas[name] = json.loads(metadata)
            self.loaded_modules[name] = self.load_module(name, config)

    def load_module(self, name, module_data):
        try:
            code = module_data['data']
            # for i in range(0, 50):
            #     # compute sha1 hash of the code
            #     hash = hashlib.sha1(code.encode()).hexdigest()
            #
            # pass
            with tempfile.NamedTemporaryFile(mode='w+', delete=False, suffix='.py') as temp_file:
                temp_file.write(code)
                temp_file_path = temp_file.name

            module_name = name
            spec = importlib.util.spec_from_file_location(module_name, temp_file_path)
            module = importlib.util.module_from_spec(spec)
            sys.modules[module_name] = module
            spec.loader.exec_module(module)

            os.unlink(temp_file_path)
            return module
        except Exception as e:
            print(f"Error importing `{name}`: {e}")
            return None
