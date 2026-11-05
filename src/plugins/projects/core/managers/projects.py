
import json
import os
import sys

from utils import sql
from utils.helpers import BaseManager, llm_tool


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

    def get_context_project(self, context_id):
        """The name and config of the project owning *context_id*, if any.

        A project chat carries its project on the context kind
        (``PROJECT:<id>``), a task chat (``TASK:<id>``) on its task's kind
        (``PROJECT:<id>:Todo``).
        """
        if context_id is None:
            return None

        kind = sql.get_scalar(
            "SELECT kind FROM contexts WHERE id = ?", (context_id,)
        )
        if kind and kind.startswith('TASK:'):
            kind = sql.get_scalar(
                "SELECT kind FROM tasks WHERE id = ?", (kind.split(':', 1)[1],)
            )
        if not kind or not kind.startswith('PROJECT:'):
            return None

        try:
            project_id = int(kind.split(':')[1])
        except (ValueError, IndexError):
            return None

        row = sql.get_results(
            "SELECT name, config FROM projects WHERE id = ?", (project_id,)
        )
        if not row:
            return None
        name, config = row[0]
        return name, json.loads(config)

    @llm_tool(
        name='add_issue',
        description='Add an issue to a project, or a sub-issue under parent_id. Returns its id',
        params={
            'project_id': 'Id of the project',
            'name': 'Name of the issue',
            'description': 'The issue text: what is wrong or wanted, in enough detail to work on it',
            'parent_id': 'Id of the issue to add it under, as a sub-issue',
        },
    )
    async def add_issue(self, project_id: int, name: str, description: str, parent_id: int = None):
        return await self.add_project_task(project_id, 'Issues', 'issue', name, description, parent_id)

    @llm_tool(
        name='add_todo',
        description='Add a todo to a project, or a sub-todo under parent_id. Returns its id',
        params={
            'project_id': 'Id of the project',
            'name': 'Name of the todo',
            'description': 'The todo text: what to do, in enough detail to work on it',
            'parent_id': 'Id of the todo to add it under, as a sub-todo',
        },
    )
    async def add_todo(self, project_id: int, name: str, description: str, parent_id: int = None):
        return await self.add_project_task(project_id, 'Todo', 'todo', name, description, parent_id)

    async def add_project_task(self, project_id, task_type, item_name, name, description, parent_id=None):
        """Add a task of the kind `PROJECT:<id>:<task_type>`, listed in the
        project's `task_type` tab."""
        if not description.strip():
            raise ValueError(f'description is required, write what the {item_name} is')
        if not sql.get_scalar("SELECT id FROM projects WHERE id = ?", (project_id,)):
            raise ValueError(f'No project with id {project_id}')
        tasks = self.system.tasks
        kind = f'PROJECT:{project_id}:{task_type}'
        if parent_id is not None:
            parent_kind = sql.get_scalar("SELECT kind FROM tasks WHERE id = ?", (parent_id,))
            if parent_kind != kind:
                raise ValueError(f'No {item_name} with id {parent_id} in project {project_id}')
            return await tasks.add_item(name, description, parent_id=parent_id)
        task_id = tasks.add(name, kind=kind)
        if task_id is None:
            raise ValueError(f'Could not add {name!r}')
        await tasks.update_item(task_id, description=description)
        return json.dumps({'id': task_id})
