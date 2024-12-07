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
        self.module_names = {}
        self.module_metadatas = {}
        self.loaded_modules = {}
        self.loaded_module_hashes = {}
        self.module_folders = {}

    def load(self, import_modules=True):
        modules_table = sql.get_results("""
            SELECT
                m.id,
                m.name,
                m.config,
                m.metadata,
				f.name
            FROM modules m
			LEFT JOIN folders f
				ON m.folder_id = f.id""")
        for module_id, name, config, metadata, folder in modules_table:
            config = json.loads(config)
            self.modules[module_id] = config
            self.module_names[module_id] = name
            self.module_metadatas[module_id] = json.loads(metadata)
            self.module_folders[module_id] = folder

            if module_id not in self.loaded_modules and import_modules:
                self.load_module(module_id)

    def load_module(self, module_id):  # , module_data):
        module_name = self.module_names[module_id]
        module_config = self.modules[module_id]

        try:
            module_hash = self.module_metadatas[module_id].get('hash')
            rechecked_hash = hashlib.sha1(json.dumps(module_config).encode()).hexdigest()
            if module_hash != rechecked_hash:
                raise ValueError(f"Module has been modified externally")
            code = module_config['data']

            with tempfile.NamedTemporaryFile(mode='w+', delete=False, suffix='.py') as temp_file:
                temp_file.write(code)
                temp_file_path = temp_file.name

            spec = importlib.util.spec_from_file_location(module_name, temp_file_path)
            module = importlib.util.module_from_spec(spec)
            sys.modules[module_name] = module
            spec.loader.exec_module(module)

            os.unlink(temp_file_path)

            module_hash = self.module_metadatas[module_id].get('hash')
            self.loaded_modules[module_id] = module
            self.loaded_module_hashes[module_id] = module_hash

            return module
        except Exception as e:
            print(f"Error importing `{module_name}`: {e}")
            return e
