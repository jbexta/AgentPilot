import re
import shutil
from pathlib import Path

from plugins.workflows.utils.acp import acp_agents, agent_of, scope_of
from utils.filesystem import get_application_path
from utils.helpers import BaseManager


class PlansManager(BaseManager):
    """
    Each plan belongs to one coding agent, named by its ``kind``: ``Claude``
    for a global plan, ``PROJECT:<id>:Claude`` for a project plan. Plans
    live as ``<slug>.md`` files in their agent's plans dir — the one the
    agent itself writes plans to (``AcpAgent.plans_dir``, e.g.
    ``~/.claude/plans``), else ``app_plans/<agent>``. Slugs are unique per
    agent. The DB row tracks only identity (name, ordr, pinned, etc.); the
    body is read and written directly to/from disk by the page.
    """

    def __init__(self, system):
        super().__init__(
            system,
            table_name='plans',
            folder_key='plans',
            load_columns=['name', 'config'],
            default_fields={'config': {}},
            add_item_options={'title': 'Add Plan', 'prompt': 'Enter a name for the plan:'},
            del_item_options={'title': 'Delete Plan', 'prompt': 'Are you sure you want to delete this plan?'},
        )

    @staticmethod
    def plans_dir(agent):
        agent_cls = acp_agents().get(agent)
        if agent_cls and agent_cls.plans_dir:
            return Path.home() / agent_cls.plans_dir
        return Path(get_application_path()) / 'app_plans' / agent

    def path_for(self, name, kind):
        slug = self._slug(name)
        return self.plans_dir(agent_of(kind)) / f'{slug}.md' if slug else None

    def read(self, name, kind):
        path = self.path_for(name, kind)
        if path is None or not path.exists():
            return ''
        try:
            return path.read_text(encoding='utf-8')
        except OSError:
            return ''

    def write(self, name, kind, body):
        path = self.path_for(name, kind)
        if path is None:
            return
        path.parent.mkdir(parents=True, exist_ok=True)
        text = body or ''
        if text and not text.endswith('\n'):
            text += '\n'
        path.write_text(text, encoding='utf-8')

    def list_files(self):
        """``(agent, slug)`` of every plan file of the loaded agents."""
        return [
            (agent, p.stem)
            for agent in acp_agents()
            for p in self.plans_dir(agent).glob('*.md') if p.stem
        ]

    def move_orphans(self):
        """A row whose kind changed to another agent (e.g. dragged to its
        group) takes its file along, if no row of the old agent owns it."""
        rows = self.db_connector.get_results("SELECT name, kind FROM plans") or []
        owned = {(agent_of(kind), self._slug(name)) for name, kind in rows}
        for name, kind in rows:
            target = self.path_for(name, kind)
            if target is None or target.exists():
                continue
            for agent in acp_agents():
                source = self.plans_dir(agent) / target.name
                if source.exists() and (agent, target.stem) not in owned:
                    target.parent.mkdir(parents=True, exist_ok=True)
                    shutil.move(source, target)
                    break

    def exists(self, name, kind, exclude_id=None):
        """Whether the plan's agent already has a plan of that slug."""
        slug = self._slug(name)
        agent = agent_of(kind)
        rows = self.db_connector.get_results(
            "SELECT id, name, kind FROM plans"
        ) or []
        return (self.plans_dir(agent) / f'{slug}.md').exists() or any(
            row_id != exclude_id and self._slug(n) == slug and agent_of(k) == agent
            for row_id, n, k in rows
        )

    def transfer(self, item_id, agent, move):
        """Copy or move a plan to *agent*, keeping its scope. A copy starts
        without the plan's chat."""
        name, kind = self.db_connector.get_results(
            "SELECT name, kind FROM plans WHERE id = ?", (item_id,), return_type='tuple'
        )
        scope = scope_of(kind)
        new_kind = f'{scope}:{agent}' if scope else agent
        source = self.path_for(name, kind)
        target = self.path_for(name, new_kind)
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, target)
        if move:
            source.unlink()
            self.db_connector.execute(
                "UPDATE plans SET kind = ? WHERE id = ?", (new_kind, item_id)
            )
        else:
            self.db_connector.execute(
                "INSERT INTO plans (name, kind) VALUES (?, ?)", (name, new_kind)
            )

    def delete(self, key, where_field='id'):
        row = self.db_connector.get_results(
            f"SELECT name, kind FROM `{self.table_name}` WHERE `{where_field}` = ?", (key,),
            return_type='tuple'
        )
        super().delete(key, where_field=where_field)
        if row:
            path = self.path_for(*row)
            if path is not None and path.exists():
                path.unlink()

    def add(self, name, **kwargs):
        item_id = super().add(name, **kwargs)
        # A re-added baked item keeps its row's kind, not the given one.
        kind = self.db_connector.get_scalar("SELECT kind FROM plans WHERE id = ?", (item_id,))
        path = self.path_for(name, kind) if agent_of(kind) else None
        if path is not None and not path.exists():
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text('', encoding='utf-8')
        return item_id

    @staticmethod
    def _slug(name):
        lowered = (name or '').lower().strip()
        lowered = re.sub(r'[\s_]+', '-', lowered)
        lowered = re.sub(r'[^a-z0-9-]', '', lowered)
        lowered = re.sub(r'-+', '-', lowered).strip('-')
        return lowered
