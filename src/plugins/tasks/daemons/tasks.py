import asyncio
import json
import re
import uuid
from typing import Optional, Dict, Set
from itertools import islice
from datetime import datetime, timezone

from PySide6.QtCore import QObject, Signal, Slot
from PySide6.QtWidgets import QMessageBox
from dateutil.rrule import rrulestr

from utils import sql
from utils.helpers import receive_workflow, display_message
from utils.sql import define_table

define_table('tasks')


class TasksDaemon:
    def __init__(self, system):
        self.system = system
        self.task_names = {}
        self.task_configs = {}
        self.scheduled_tasks: Dict[str, asyncio.Task] = {}
        self._running_task_ids: Set[str] = set()
        self._running = False
        self._task_group: Optional[asyncio.TaskGroup] = None

    async def start(self):
        """Start the daemon - load tasks and schedule them"""
        self._running = True
        async with asyncio.TaskGroup() as tg:
            self._task_group = tg
            await self.load()
            # Keep daemon running
            while self._running:
                await asyncio.sleep(1)

    def stop(self):
        """Stop the daemon and cancel all scheduled tasks"""
        self._running = False
        for task_id, task in self.scheduled_tasks.items():
            if not task.done():
                task.cancel()
        self.scheduled_tasks.clear()

    async def load(self):
        self.task_names = sql.get_results("""
            SELECT
                uuid,
                name
            FROM tasks
            WHERE kind = 'SCHEDULED'""", return_type='dict')

        self.task_configs = sql.get_results("""
            SELECT
                uuid,
                config
            FROM tasks
            WHERE kind = 'SCHEDULED'""", return_type='dict')
        self.task_configs = {k: json.loads(v) for k, v in self.task_configs.items()}

        await self.schedule_upcoming_tasks()

    async def schedule_upcoming_tasks(self):
        print('schedule_upcoming_tasks')
        now = datetime.now(timezone.utc)

        for task_id, config in self.task_configs.items():
            rrule_str = config.get('rrule', None)
            if not rrule_str or rrule_str == '':
                continue

            if task_id in self._running_task_ids:
                continue

            # Strip <answer> tags if present (AI block output artifact)
            match = re.search(r'<answer>(.*?)</answer>', rrule_str, re.DOTALL)
            if match:
                rrule_str = match.group(1).strip()

            try:
                rule = rrulestr(rrule_str)
            except Exception as e:
                print(f"Error parsing rrule for task {task_id}: {e}")
                continue

            next_occurrence = next(rule.xafter(now, inc=False, count=1), None)
            if not next_occurrence:
                continue

            # Cancel existing task if it exists
            if task_id in self.scheduled_tasks:
                if not self.scheduled_tasks[task_id].done():
                    self.scheduled_tasks[task_id].cancel()

            delay = max((next_occurrence - now).total_seconds(), 0)
            task = asyncio.create_task(self.run_task_with_delay(task_id, delay))
            self.scheduled_tasks[task_id] = task

            print(f'All tasks scheduled: {list(self.scheduled_tasks.keys())}')

    async def run_task_with_delay(self, task_uuid, delay):
        try:
            await asyncio.sleep(delay)
            if not self._running:
                return
            self._running_task_ids.add(task_uuid)
            try:
                result = await self.run_task_async(task_uuid)
            finally:
                self._running_task_ids.discard(task_uuid)
            await self.on_task_finished(task_uuid, result)
        except asyncio.CancelledError:
            self._running_task_ids.discard(task_uuid)
            return
        except Exception as e:
            self._running_task_ids.discard(task_uuid)
            await self.on_task_error(str(e))

    async def on_task_finished(self, task_uuid, result):
        print(f'Task {task_uuid} completed with result: {result}')
        await self.schedule_upcoming_tasks()

    async def on_task_error(self, error):
        print(f'Task error: {error}')
        display_message(
            message=f'Task error: {error}',
            icon=QMessageBox.Warning,
        )

    async def receive_task(self, task_uuid, params=None):
        wf_config = self.task_configs[task_uuid]
        task_name = self.task_names.get(task_uuid, 'Untitled task')
        async for key, chunk in receive_workflow(wf_config, kind='TASK', params=params, chat_title=task_name, main=self.system._main_gui):
            yield key, chunk

    async def run_task_async(self, task_uuid, params=None):
        response = ''
        async for key, chunk in self.receive_task(task_uuid, params=params):
            response += chunk
        return response


    def list_tasks_per_day(self):
        date_occurrences = {}
        now = datetime.now(timezone.utc)

        for task_id, config in self.task_configs.items():
            rrule_str = config.get('rrule', None)
            if not rrule_str or rrule_str == '':
                continue

            # Strip <answer> tags if present (AI block output artifact)
            match = re.search(r'<answer>(.*?)</answer>', rrule_str, re.DOTALL)
            if match:
                rrule_str = match.group(1).strip()

            try:
                rule = rrulestr(rrule_str)
            except Exception as e:
                print(f"Error parsing rrule for task {task_id}: {e}")
                continue

            try:
                max_occurrences = 10000
                half_count = max_occurrences // 2

                before = list(islice(rule.between(rule._dtstart, now, inc=True) or [], half_count))
                after = list(rule.xafter(dt=now, inc=False, count=half_count + max_occurrences % 2))

                before.reverse()
                occurrences = before + after
                for occ in occurrences:
                    date = occ.date()
                    if date not in date_occurrences:
                        date_occurrences[date] = set()
                    date_occurrences[date].add(task_id)

            except Exception as e:
                print(f"Error generating occurrences for task {task_id}: {e}")
                continue

        return dict(sorted(date_occurrences.items()))