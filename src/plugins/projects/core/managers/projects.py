
import json
import os
import sys

from utils import sql
from utils.helpers import BaseManager


class ProjectManager(BaseManager):
    def __init__(self, system):
        super().__init__(
            system,
            table_name='projects',
            folder_key='projects',
            load_columns=['name', 'config'],
            add_item_options={'title': 'New Project', 'prompt': 'Enter a name for the project:'},
            del_item_options={'title': 'Delete Project',
                              'prompt': 'Are you sure you want to delete this project?'},
        )

    def load(self):
        super().load()
        self.ensure_application_project()

    def ensure_application_project(self):
        """Create the Application project if it does not already exist.
        """
        from utils.filesystem import get_application_path

        exists = sql.get_scalar(
            "SELECT id FROM projects WHERE name = 'Application'"
        )
        if not exists:
            app_path = get_application_path()
            if getattr(sys, 'frozen', False):
                app_path = os.path.join(app_path, 'SOURCE')
            config = {
                '_PROJECT_TYPE': 'application',
                'working_dir': app_path,
            }
            sql.execute(
                "INSERT INTO projects (name, config) VALUES (?, ?)",
                ('Application', json.dumps(config)),
            )
            super().load()
