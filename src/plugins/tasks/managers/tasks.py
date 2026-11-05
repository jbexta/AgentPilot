import asyncio
import json
import re
from datetime import datetime, timezone
from itertools import islice

from dateutil.rrule import rrulestr

from plugins.workflows.utils.runs import get_run_manager
from plugins.workflows.utils.workflows import get_entity_workflow_config
from utils import sql
from utils.helpers import BaseManager, llm_tool, set_module_type

STATUSES = ('TODO', 'RUNNING', 'AWAITING_APPROVAL', 'DONE', 'FAILED', 'RECURRING', 'SCHEDULED')
AGENT_STATUSES = ('TODO', 'DONE', 'FAILED')
ACTIVE_STATUSES = ('RUNNING', 'AWAITING_APPROVAL')
DEFAULT_TASK_TEMPLATE = (
    '{{ task }}\n\n'
    'When you have finished, call '
    "tasks_set_status(id={{ task_id }}, status='DONE', note=<summary of what you did>). "
    "If you can't complete it, call tasks_set_status with status='FAILED' and the reason."
)


def is_repeating(rrule_str):
    """Whether the rrule has more than one occurrence."""
    if not rrule_str:
        return False
    try:
        rule = rrulestr(rrule_str)
    except (ValueError, TypeError):
        return False
    return len(list(islice(rule, 2))) > 1


@set_module_type(module_type='Managers')
class TaskManager(BaseManager):
    """Tasks: something to do, described by a text (config key `task`, as
    `description` is the workflow's own) and run by the task's workflow,
    optionally on a schedule. Each run is a context with kind
    `TASK:<id>`; the status of non-recurring tasks follows their runs."""

    def __init__(self, system):
        super().__init__(
            system,
            table_name='tasks',
            folder_key='tasks_scheduled',
            load_columns=['uuid', 'config'],
            default_fields={
                'kind': 'SCHEDULED',
                'status': 'TODO',
                'config': {},
            },
            config_is_workflow=True,
        )
        self._active_runs = {}  # context_id: task_id
        self.sync_recurring_statuses()
        self.fail_interrupted()
        get_run_manager().changed.connect(self.on_runs_changed)

    def sync_recurring_statuses(self):
        """Give tasks with a repeating schedule the `RECURRING` status."""
        rows = sql.get_results("SELECT id, status, COALESCE(json_extract(config, '$.rrule'), '') FROM tasks")
        for task_id, status, rrule in rows:
            repeating = is_repeating(rrule)
            if repeating != (status == 'RECURRING'):
                sql.execute("UPDATE tasks SET status = ? WHERE id = ?", ('RECURRING' if repeating else 'TODO', task_id))

    def fail_interrupted(self):
        """Fail tasks whose run was cut short by the app closing."""
        task_ids = sql.get_results(
            "SELECT id FROM tasks WHERE status IN ('RUNNING', 'AWAITING_APPROVAL')",
            return_type='list',
        )
        for task_id in task_ids:
            self.set_item_status(task_id, 'FAILED', 'Interrupted by app shutdown')

    def add(self, name, task='', **kwargs):
        """Tasks added without a workflow get the default task entity's,
        linked to it."""
        if not kwargs.get('config'):
            entity_val = self.system.config.get('system.default_task_entity', '')
            kwargs['config'] = get_entity_workflow_config(entity_val)
        if task:
            kwargs['config'] = {**kwargs['config'], 'task': task}
        return super().add(name, **kwargs)

    def delete(self, key, where_field='id'):
        """Delete a task with all its sub-tasks and their chats, stopping
        any of their runs."""
        task_ids = sql.get_results("""
            WITH RECURSIVE sub(id) AS (
                SELECT ?
                UNION ALL
                SELECT t.id FROM tasks t JOIN sub ON t.parent_id = sub.id
            )
            SELECT id FROM sub""", (key,), return_type='list')
        kinds = tuple(f'TASK:{task_id}' for task_id in task_ids)
        context_ids = sql.get_results(f"""
            WITH RECURSIVE tree(id) AS (
                SELECT id FROM contexts WHERE kind IN ({','.join('?' * len(kinds))})
                UNION ALL
                SELECT c.id FROM contexts c JOIN tree ON c.parent_id = tree.id
            )
            SELECT id FROM tree""", kinds, return_type='list')
        for context_id in context_ids:
            get_run_manager().stop(context_id)
        for table, column, ids in (('contexts_messages', 'context_id', context_ids), ('contexts', 'id', context_ids), ('tasks', 'id', task_ids)):
            if ids:
                sql.execute(f"DELETE FROM {table} WHERE {column} IN ({','.join('?' * len(ids))})", tuple(ids))
        self.load()
        self.reload_daemon()
        self.signals.changed.emit()

    def reload_daemon(self):
        daemon = self.system.daemons.running_daemons.get('tasks')
        if daemon:
            asyncio.ensure_future(daemon.load())

    def get_status(self, task_id):
        return sql.get_scalar("SELECT status FROM tasks WHERE id = ?", (task_id,))

    def append_note(self, task_id, text):
        """Add a timestamped line to the task's description."""
        config = sql.get_scalar("SELECT config FROM tasks WHERE id = ?", (task_id,), load_json=True) or {}
        stamp = datetime.now().strftime('%Y-%m-%d %H:%M')
        description = config.get('task', '').rstrip()
        config['task'] = f'{description}\n\n[{stamp}] {text}'.lstrip()
        sql.execute("UPDATE tasks SET config = ? WHERE id = ?", (json.dumps(config), task_id))

    def set_item_status(self, task_id, status, note=''):
        if status not in STATUSES:
            raise ValueError(f"Status must be one of {', '.join(STATUSES)}")
        sql.execute("UPDATE tasks SET status = ? WHERE id = ?", (status, task_id))
        if note:
            self.append_note(task_id, f'{status}: {note}')
        self.signals.changed.emit()

    def set_schedule(self, task_id, rrule_str, time_expression, duration=None):
        """Save a task's schedule; a repeating one makes it `RECURRING`,
        a one-off one `SCHEDULED` and no schedule `TODO`."""
        config = sql.get_scalar("SELECT config FROM tasks WHERE id = ?", (task_id,), load_json=True)
        config.update(rrule=rrule_str, time_expression=time_expression)
        if duration is not None:
            config['duration'] = duration
        if is_repeating(rrule_str):
            status = 'RECURRING'
        else:
            status = 'SCHEDULED' if rrule_str else 'TODO'
        sql.execute("UPDATE tasks SET config = ?, status = ? WHERE id = ?", (json.dumps(config), status, task_id))
        self.load()
        self.reload_daemon()
        self.signals.changed.emit()

    async def apply_time_expression(self, task_id, time_expression):
        """Convert a human time expression to an rrule and save it as the
        task's schedule.

        Uses the ``expression_to_time`` and ``time_to_expression`` blocks to
        translate the free-form expression.

        Parameters
        ----------
        task_id : int
        time_expression : str

        Returns
        -------
        tuple[str, str]
            (rrule_str, clean_time_expression)
        """
        te = (time_expression or '').strip()
        if te == '':
            rrule_str, clean_te = '', ''
        else:
            blocks = self.system.blocks
            raw = await blocks.compute_block_async(
                'expression_to_time', {'expression': te}
            )
            match = re.search(r'<answer>(.*?)</answer>', raw, re.DOTALL)
            rrule_str = (match.group(1) if match else raw).strip()

            raw = await blocks.compute_block_async(
                'time_to_expression', {'time': rrule_str}
            )
            match = re.search(r'<answer>(.*?)</answer>', raw, re.DOTALL)
            clean_te = (match.group(1) if match else raw).strip()

            inline_start = re.search(r'DTSTART=([^;\s]+);?', rrule_str)
            if inline_start:
                rule = rrule_str.replace(inline_start.group(0), '')
                rrule_str = f"DTSTART:{inline_start.group(1)}\n{rule.strip(';')}"
            elif 'DTSTART' not in rrule_str:
                now = datetime.now(timezone.utc)
                rrule_str = (
                    f"DTSTART:{now.strftime('%Y%m%dT%H%M%SZ')}\n{rrule_str}"
                )

        self.set_schedule(task_id, rrule_str, clean_te)
        return rrule_str, clean_te

    def get_item_dict(self, task_id):
        row = sql.get_results(
            "SELECT id, name, status, config, parent_id FROM tasks WHERE id = ?",
            (task_id,),
        )
        if not row:
            raise ValueError(f'No task with id {task_id}')
        item_id, name, status, config, parent_id = row[0]
        config = json.loads(config)
        sub_tasks = sql.get_results(
            "SELECT id, name, status FROM tasks WHERE parent_id = ? ORDER BY id",
            (task_id,),
        )
        return {
            'id': item_id,
            'name': name,
            'status': status,
            'description': config.get('task', ''),
            'when': config.get('time_expression', ''),
            'parent_id': parent_id,
            'sub_tasks': [dict(zip(('id', 'name', 'status'), sub)) for sub in sub_tasks],
        }

    @llm_tool(
        name='list',
        description='List tasks as JSON',
        params={
            'search': 'Only tasks whose name contains this text',
            'status': 'Only tasks with this status',
        },
    )
    def list_items(self, search: str = '', status: str = ''):
        where, params = '1 = 1', ()
        if search:
            where += ' AND name LIKE ?'
            params += (f'%{search}%',)
        if status:
            where += ' AND status = ?'
            params += (status,)
        rows = sql.get_results(f"""
            SELECT id, name, status,
                COALESCE(json_extract(config, '$.time_expression'), ''),
                parent_id
            FROM tasks
            WHERE {where}
            ORDER BY id""", params)
        keys = ('id', 'name', 'status', 'when', 'parent_id')
        return json.dumps([dict(zip(keys, row)) for row in rows])

    @llm_tool(
        name='get',
        description='Get a task with its description and sub-tasks as JSON',
        params={'id': 'Id of the task'},
    )
    def get_item(self, id: int):
        return json.dumps(self.get_item_dict(id))

    @llm_tool(
        name='add',
        description='Add a task, or a sub-task under parent_id. Returns its id',
        params={
            'name': 'Name of the task',
            'description': 'The task text: what to do, in enough detail to work on it',
            'time_expression': 'When it runs, e.g. "every weekday at 9am" '
                               'or "tomorrow at 3pm". Empty for no schedule',
            'parent_id': 'Id of the task to add it under, as a sub-task',
        },
    )
    async def add_item(self, name: str, description: str, time_expression: str = '', parent_id: int = None):
        if not description.strip():
            raise ValueError('description is required, write what the task is')
        kwargs = {}
        if parent_id is not None:
            self.get_item_dict(parent_id)
            folder_id, kind = sql.get_results("SELECT folder_id, kind FROM tasks WHERE id = ?", (parent_id,))[0]
            kwargs = {'folder_id': folder_id, 'kind': kind}
        task_id = self.add(name, parent_id=parent_id, **kwargs)
        if task_id is None:
            raise ValueError(f'Could not add {name!r}')
        await self.update_item(task_id, description=description, time_expression=time_expression or None)
        return json.dumps({'id': task_id})

    @llm_tool(
        name='update',
        description='Update a task\'s name, description or schedule',
        params={
            'id': 'Id of the task',
            'name': 'New name',
            'description': 'New description',
            'time_expression': 'New schedule, an empty string removes it',
        },
    )
    async def update_item(self, id: int, name: str = None, description: str = None, time_expression: str = None):
        self.get_item_dict(id)
        if name:
            sql.execute("UPDATE tasks SET name = ? WHERE id = ?", (name, id))
        if description is not None:
            sql.execute(
                "UPDATE tasks SET config = json_set(config, '$.task', ?) WHERE id = ?",
                (description, id),
            )
        if time_expression is not None:
            await self.apply_time_expression(id, time_expression)
        self.load()
        self.signals.changed.emit()

    @llm_tool(
        name='set_status',
        description='Set the status of a task: TODO, DONE or FAILED',
        params={
            'id': 'Id of the task',
            'status': 'TODO, DONE or FAILED',
            'note': 'Why, e.g. a summary of the work done or the reason it failed',
        },
    )
    def set_status(self, id: int, status: str, note: str = ''):
        if status not in AGENT_STATUSES:
            raise ValueError(f"status must be one of {', '.join(AGENT_STATUSES)}")
        if self.get_item_dict(id)['status'] == 'RECURRING':
            raise ValueError('Recurring tasks have no status to set, report the outcome in your reply')
        self.set_item_status(id, status, note)

    def context_id(self, task_id):
        """The task's latest chat, or None."""
        return sql.get_scalar(
            "SELECT id FROM contexts WHERE kind = ? AND parent_id IS NULL ORDER BY id DESC LIMIT 1",
            (f'TASK:{task_id}',),
        )

    def prepare_context(self, task_id, new=False):
        """Point the task's latest chat at the task's current workflow, or
        create a chat when `new` or when it has none. Returns
        (context_id, continuing)."""
        config, name = sql.get_results("SELECT config, name FROM tasks WHERE id = ?", (task_id,), return_type='tuple')
        context_id = None if new else self.context_id(task_id)
        if context_id is not None:
            sql.execute("UPDATE contexts SET config = ?, name = ? WHERE id = ?", (config, name, context_id))
            return context_id, True
        context_id = sql.execute(
            "INSERT INTO contexts (kind, config, name) VALUES (?, ?, ?)",
            (f'TASK:{task_id}', config, name),
        )
        return context_id, False

    @staticmethod
    def first_user_member_id(workflow):
        """The id of the workflow's first member if it's a user member, the
        member whose message is the task. Otherwise None."""
        first = next(iter(workflow.members.values()), None)
        if first is not None and first.config.get('_TYPE', 'agent') == 'user':
            return first.member_id
        return None

    async def run_message(self, task_id, continuing=False):
        """The user message starting a run: the task's id, the task text
        rendered with the `Task template` setting, and how to add
        sub-tasks."""
        item = self.get_item_dict(task_id)
        lines = [
            'Continue working on this task.' if continuing else 'Work on this task.',
            '',
            f"Task #{item['id']}: {item['name']}",
        ]
        template = self.system.config.get('system.task_template', DEFAULT_TASK_TEMPLATE)
        task_text = await self.system.blocks.format_string(
            template,
            additional_blocks={'task': item['description'], 'task_id': str(item['id'])},
        )
        if task_text.strip():
            lines += ['', task_text]
        open_sub_tasks = [sub for sub in item['sub_tasks'] if sub['status'] != 'DONE']
        if open_sub_tasks:
            lines += ['', 'Open sub-tasks:']
            lines += [f"- #{sub['id']} {sub['name']} ({sub['status']})" for sub in open_sub_tasks]
        if item['status'] != 'RECURRING':
            lines += [
                '',
                'To break the work down, create sub-tasks with '
                f"tasks_add(name=<name>, description=<what to do>, parent_id={item['id']}).",
            ]
        return '\n'.join(lines)

    async def run_scheduled(self, task_id):
        """Run a task on its schedule: a recurring task in a new chat, a
        one-off task continuing its latest chat. A workflow starting with a
        user member gets the task as that member's message."""
        from plugins.workflows.members.workflow import Workflow
        recurring = self.get_status(task_id) == 'RECURRING'
        context_id, continuing = self.prepare_context(task_id, new=recurring)
        workflow = Workflow(main=self.system._main_gui, context_id=context_id, kind=f'TASK:{task_id}')
        user_member_id = self.first_user_member_id(workflow)
        if user_member_id is not None:
            workflow.save_message('user', await self.run_message(task_id, continuing), member_id=user_member_id)
        await get_run_manager().start(workflow, notify=not recurring)
        messages = workflow.message_history.messages
        return messages[-1].content if messages else ''

    def task_id_for_context(self, context_id):
        kind = sql.get_scalar("SELECT kind FROM contexts WHERE id = ?", (context_id,)) or ''
        prefix, _, task_id = kind.partition(':')
        return int(task_id) if prefix == 'TASK' and task_id.isdigit() else None

    def on_runs_changed(self):
        """Keep non-recurring task statuses in step with their runs, however
        the run was started (Run, the schedule or a reply in the chat)."""
        runs = get_run_manager()
        running = {}
        for context_id in runs.runs:
            task_id = self._active_runs.get(context_id) or self.task_id_for_context(context_id)
            if task_id is not None:
                running[context_id] = task_id

        for context_id, task_id in running.items():
            status = self.get_status(task_id)
            if status in (None, 'RECURRING'):
                continue
            if context_id not in self._active_runs and status not in ACTIVE_STATUSES:
                self.set_item_status(task_id, 'RUNNING')
                status = 'RUNNING'
            awaiting = runs.is_awaiting_confirm(context_id)
            if awaiting and status == 'RUNNING':
                self.set_item_status(task_id, 'AWAITING_APPROVAL')
            elif not awaiting and status == 'AWAITING_APPROVAL':
                self.set_item_status(task_id, 'RUNNING')

        for context_id, task_id in self._active_runs.items():
            if context_id in running or self.get_status(task_id) in (None, 'RECURRING'):
                continue
            error = runs.errors.get(context_id)
            if error:
                self.set_item_status(task_id, 'FAILED', error)
            elif self.get_status(task_id) in ACTIVE_STATUSES:
                self.set_item_status(task_id, 'TODO')  # the agent didn't finish it

        self._active_runs = running
