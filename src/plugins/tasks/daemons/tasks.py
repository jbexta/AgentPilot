import asyncio
import json
import logging
import re
import uuid
from typing import Dict
from itertools import islice
from datetime import datetime, timezone

from PySide6.QtCore import QObject, Signal, Slot
from PySide6.QtWidgets import QMessageBox
from dateutil.rrule import rrulestr
from dateutil.tz import tzlocal

from utils import sql
from utils.helpers import display_message
from utils.sql import define_table

define_table('tasks')

logger = logging.getLogger(__name__)


class TasksDaemon:
    def __init__(self, system):
        self.system = system
        self.task_names = {}
        self.task_configs = {}
        # One long-running loop per task uuid. The loop owns its own
        # scheduling — each iteration sleeps until the next occurrence,
        # fires, then repeats. This avoids the cancel-and-reschedule race
        # that double-fired when an external load() interleaved with
        # on_task_finished.
        self._task_loops: Dict[str, asyncio.Task] = {}
        self._loop_rrules: Dict[str, str] = {}
        self._running = False

    async def start(self):
        """Start the daemon - load tasks and schedule them"""
        self._running = True
        await self.load()
        while self._running:
            await asyncio.sleep(1)

    def stop(self):
        """Stop the daemon and cancel all running task loops"""
        self._running = False
        for task in self._task_loops.values():
            if not task.done():
                task.cancel()
        self._task_loops.clear()
        self._loop_rrules.clear()

    async def load(self):
        self.task_names = sql.get_results("""
            SELECT
                uuid,
                name
            FROM tasks
            WHERE kind = 'SCHEDULED' OR kind LIKE 'PROJECT:%'""", return_type='dict')

        self.task_configs = sql.get_results("""
            SELECT
                uuid,
                config
            FROM tasks
            WHERE kind = 'SCHEDULED' OR kind LIKE 'PROJECT:%'""", return_type='dict')
        self.task_configs = {k: json.loads(v) for k, v in self.task_configs.items()}

        self._reconcile_loops()

    def _reconcile_loops(self):
        """Start/stop/restart per-task loops to match current configs.

        Only tasks whose rrule changed get cancelled and restarted; unchanged
        tasks keep their running loop untouched, which prevents load() from
        perturbing a task that's about to fire.
        """
        active_rrules = {}
        for task_id, config in self.task_configs.items():
            rrule_str = config.get('rrule') or ''
            if not rrule_str:
                continue
            match = re.search(r'<answer>(.*?)</answer>', rrule_str, re.DOTALL)
            if match:
                rrule_str = match.group(1).strip()
            active_rrules[task_id] = rrule_str

        # Stop loops for removed tasks or tasks whose rrule changed
        for task_id in list(self._task_loops.keys()):
            loop_task = self._task_loops[task_id]
            if task_id not in active_rrules:
                if not loop_task.done():
                    loop_task.cancel()
                del self._task_loops[task_id]
                self._loop_rrules.pop(task_id, None)
                continue
            if self._loop_rrules.get(task_id) != active_rrules[task_id]:
                if not loop_task.done():
                    loop_task.cancel()
                del self._task_loops[task_id]
                self._loop_rrules.pop(task_id, None)

        # Start loops for new or restarted tasks
        for task_id, rrule_str in active_rrules.items():
            if task_id in self._task_loops and not self._task_loops[task_id].done():
                continue
            self._task_loops[task_id] = asyncio.create_task(
                self._task_loop(task_id, rrule_str)
            )
            self._loop_rrules[task_id] = rrule_str

        logger.info('Active task loops: %s', list(self._task_loops))

    async def _task_loop(self, task_uuid, rrule_str):
        """Run a single task on its rrule schedule until cancelled."""
        try:
            rule = rrulestr(rrule_str)
        except Exception as e:
            logger.error("Error parsing rrule for task %s: %s", task_uuid, e)
            return
        if rule._dtstart.tzinfo is None:
            rule = rule.replace(dtstart=rule._dtstart.replace(tzinfo=tzlocal()))

        while self._running:
            now = datetime.now(timezone.utc)
            next_occurrence = next(rule.xafter(now, inc=False, count=1), None)
            if not next_occurrence:
                return
            try:
                # asyncio.sleep can wake up slightly before the target time
                # (observed ~40ms early). If we don't re-check, the next
                # xafter() call will return the SAME occurrence (because
                # now < next_occurrence still) and fire it again.
                while self._running:
                    remaining = (next_occurrence
                                 - datetime.now(timezone.utc)).total_seconds()
                    if remaining <= 0:
                        break
                    await asyncio.sleep(remaining)
            except asyncio.CancelledError:
                return
            if not self._running:
                return
            try:
                result = await self.run_task_async(task_uuid)
                logger.info('Task %s completed with result: %s', task_uuid, result)
            except asyncio.CancelledError:
                return
            except Exception as e:
                await self.on_task_error(str(e))

    async def on_task_error(self, error):
        logger.error('Task error: %s', error)
        display_message(
            message=f'Task error: {error}',
            icon=QMessageBox.Warning,
        )

    async def run_task_async(self, task_uuid):
        task_id = sql.get_scalar("SELECT id FROM tasks WHERE uuid = ?", (task_uuid,))
        return await self.system.tasks.run_scheduled(task_id)


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
                logger.error("Error parsing rrule for task %s: %s", task_id, e)
                continue
            if rule._dtstart.tzinfo is None:
                rule = rule.replace(dtstart=rule._dtstart.replace(tzinfo=tzlocal()))

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
                logger.error("Error generating occurrences for task %s: %s", task_id, e)
                continue

        return dict(sorted(date_occurrences.items()))