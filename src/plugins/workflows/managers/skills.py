import json
import os
import re
import shutil
import tempfile
from pathlib import Path

from plugins.workflows.utils.acp import acp_agents, agent_of, scope_of
from utils import sql
from utils.filesystem import get_application_path
from utils.helpers import BaseManager


class SkillsManager(BaseManager):
    """
    Each skill belongs to one coding agent, named by its ``kind``:
    ``Claude`` for a global skill, ``PROJECT:<id>:Claude`` for a project
    skill. App-managed skills live in ``app_skills/<agent>/skills/<slug>/
    SKILL.md``, so slugs are unique per agent. The DB row tracks identity
    (name, kind, ordr, pinned, etc.); description and body are read and
    written directly to/from disk. ``read`` returns ``(description,
    body)`` parsed from the frontmatter; ``write`` reassembles the
    frontmatter from the same pair.

    ``sync_to_disk`` mirrors skills into the skills dir of their agent
    (``AcpAgent.skills_dir``, e.g. ``.claude/skills``) so terminal sessions
    see them too: global skills under the home dir, project skills under
    their project's working_dir.
    Skills flagged ``app_only`` in their config are never mirrored.
    ``mirrors.json`` records every mirror written, so stale ones can be
    removed without touching skill folders the app doesn't manage.
    """

    @property
    def ROOT(self):
        # Disposable (test/demo) DBs get their own dir, so a test run never
        # touches the real skill folders that a running instance watches.
        db_path = sql.get_db_path()
        if self._is_disposable_db():
            return Path(tempfile.gettempdir()) / f'agentpilot_{Path(db_path).stem}_skills'
        return Path(get_application_path()) / 'app_skills'

    @staticmethod
    def _is_disposable_db():
        return os.path.basename(sql.get_db_path()) != 'data.db'

    @property
    def MANIFEST_PATH(self):
        return self.ROOT / 'mirrors.json'

    def __init__(self, system):
        super().__init__(
            system,
            table_name='skills',
            folder_key='skills',
            load_columns=['name', 'config'],
            default_fields={'config': {}},
            add_item_options={'title': 'Add Skill', 'prompt': 'Enter a name for the skill:'},
            del_item_options={'title': 'Delete Skill', 'prompt': 'Are you sure you want to delete this skill?'},
        )
        if self._is_disposable_db():
            # The disposable DB is a fresh copy each run; match it with a
            # fresh dir so folders left by an earlier run aren't adopted.
            shutil.rmtree(self.ROOT, ignore_errors=True)
        self.ROOT.mkdir(parents=True, exist_ok=True)

    def load(self):
        super().load()
        self.sync_to_disk()

    def skills_dir(self, agent):
        return self.ROOT / agent / 'skills'

    def path_for(self, name, kind):
        slug = self._slug(name)
        return self.skills_dir(agent_of(kind)) / slug / 'SKILL.md' if slug else None

    def _project_dir(self, scope):
        return self.db_connector.get_scalar(
            "SELECT json_extract(config, '$.working_dir') FROM projects WHERE id = ?",
            (int(scope.split(':')[1]),)
        )

    def mirror_root_for(self, kind, config):
        """The dir a skill is mirrored to for terminal sessions, or None for
        app-only skills (never mirrored) and agents without a skills dir."""
        if config.get('app_only', False):
            return None
        agent_cls = acp_agents().get(agent_of(kind))
        if agent_cls is None or not agent_cls.skills_dir:
            return None
        scope = scope_of(kind)
        if scope:
            working_dir = self._project_dir(scope)
            return Path(working_dir) / agent_cls.skills_dir if working_dir else None
        # Global skills are for every terminal session, so they mirror to
        # the user-global skills dir rather than any single repo's.
        return Path.home() / agent_cls.skills_dir

    def _move_orphans(self, rows):
        """A row whose kind changed to another agent (e.g. dragged to its
        group) takes its folder along, if no row of the old agent owns it."""
        owned = {(agent_of(kind), self._slug(name)) for name, kind, _ in rows}
        for name, kind, _ in rows:
            slug = self._slug(name)
            target = self.skills_dir(agent_of(kind)) / slug
            if not slug or target.exists():
                continue
            for agent_dir in self.ROOT.iterdir():
                source = agent_dir / 'skills' / slug
                if source.is_dir() and (agent_dir.name, slug) not in owned:
                    target.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copytree(source, target)
                    shutil.rmtree(source)
                    break

    def sync_to_disk(self):
        """Refresh the terminal-facing mirrors to match the DB and the
        canonical folders. Only paths recorded in the manifest are ever
        deleted, so unmanaged skill folders are left alone. Mirrors of
        agents that aren't loaded are left as they are. Skipped for dummy
        (test/demo) DBs, which would otherwise clobber real mirrors."""
        rows = self.db_connector.get_results(
            "SELECT name, kind, config FROM skills"
        ) or []
        self._move_orphans(rows)
        if os.path.basename(sql.get_db_path()) != 'data.db':
            return
        agents = acp_agents()
        previous = {}
        if self.MANIFEST_PATH.exists():
            try:
                previous = json.loads(self.MANIFEST_PATH.read_text(encoding='utf-8'))
            except (OSError, json.JSONDecodeError):
                pass
        self._adopt_skills(agents, mirrors=set(previous.values()))

        desired = {key: path for key, path in previous.items()
                   if key.split('/')[0] not in agents}
        rows = self.db_connector.get_results(
            "SELECT name, kind, config FROM skills"
        ) or []
        for name, kind, config in rows:
            slug = self._slug(name)
            agent = agent_of(kind)
            if not slug or not (self.skills_dir(agent) / slug).exists():
                continue
            root = self.mirror_root_for(kind, json.loads(config) if config else {})
            if root is not None:
                desired[f'{agent}/{slug}'] = str(root / slug)

        for key, path in previous.items():
            if desired.get(key) != path and Path(path).exists():
                shutil.rmtree(path)
        for key, path in desired.items():
            agent, slug = key.split('/')
            mirror = Path(path)
            canonical = self.skills_dir(agent) / slug
            if not canonical.exists():
                continue
            if mirror.exists():
                m_md, c_md = mirror / 'SKILL.md', canonical / 'SKILL.md'
                if m_md.exists() and c_md.exists():
                    if m_md.read_bytes() == c_md.read_bytes():
                        continue  # already in sync — keeps watcher-triggered syncs from looping
                    # Newer-wins backflow: a terminal session may have edited
                    # the mirror since the last sync — adopt its content first.
                    if m_md.stat().st_mtime > c_md.stat().st_mtime:
                        shutil.rmtree(canonical)
                        shutil.copytree(mirror, canonical)
                shutil.rmtree(mirror)
            mirror.parent.mkdir(parents=True, exist_ok=True)
            shutil.copytree(canonical, mirror)

        self.MANIFEST_PATH.write_text(json.dumps(desired, indent=2), encoding='utf-8')

    def external_roots(self, agents=None):
        """``(kind, dir)`` of every agent's global and project skills dirs."""
        agents = acp_agents() if agents is None else agents
        projects = self.db_connector.get_results(
            "SELECT id, json_extract(config, '$.working_dir') FROM projects"
        ) or []
        roots = []
        for agent, agent_cls in agents.items():
            if not agent_cls.skills_dir:
                continue
            roots.append((agent, Path.home() / agent_cls.skills_dir))
            roots += [
                (f'PROJECT:{project_id}:{agent}', Path(working_dir) / agent_cls.skills_dir)
                for project_id, working_dir in projects if working_dir
            ]
        return roots

    def _adopt_skills(self, agents, mirrors):
        """Skill folders found in an agent's global or project skills dir
        that the app doesn't manage yet (e.g. hand-written by a terminal
        session) are adopted — a DB row of that agent and scope plus a
        canonical copy — so they show up in the Skills page. The app's own
        *mirrors* aren't, e.g. the mirror of a skill just deleted."""
        rows = self.db_connector.get_results(
            "SELECT name, kind FROM skills"
        ) or []
        known = {(agent_of(kind), self._slug(name)) for name, kind in rows}
        for kind, skills_dir in self.external_roots(agents):
            if not skills_dir.is_dir():
                continue
            agent = agent_of(kind)
            for d in sorted(skills_dir.iterdir()):
                slug = d.name
                if (not d.is_dir() or not (d / 'SKILL.md').exists()
                        or (agent, slug) in known or str(d) in mirrors):
                    continue
                shutil.copytree(d, self.skills_dir(agent) / slug)
                self.db_connector.execute(
                    "INSERT INTO skills (name, kind) VALUES (?, ?)",
                    (slug, kind)
                )
                known.add((agent, slug))

    def read(self, name, kind):
        path = self.path_for(name, kind)
        if path is None or not path.exists():
            return '', ''
        try:
            return self._parse(path.read_text(encoding='utf-8'))
        except OSError:
            return '', ''

    def write(self, name, kind, description, body):
        path = self.path_for(name, kind)
        if path is None:
            return
        path.parent.mkdir(parents=True, exist_ok=True)
        slug = self._slug(name)
        path.write_text(self._format(slug, description, body), encoding='utf-8')

    def list_files(self):
        """``(agent, slug)`` of every canonical skill folder."""
        return [
            (agent_dir.name, d.name)
            for agent_dir in self.ROOT.iterdir() if agent_dir.is_dir()
            for d in self.skills_dir(agent_dir.name).glob('*')
            if d.is_dir() and (d / 'SKILL.md').exists()
        ]

    def exists(self, name, kind, exclude_id=None):
        """Whether the skill's agent already has a skill of that slug."""
        slug = self._slug(name)
        agent = agent_of(kind)
        rows = self.db_connector.get_results(
            "SELECT id, name, kind FROM skills"
        ) or []
        return (self.skills_dir(agent) / slug).exists() or any(
            row_id != exclude_id and self._slug(n) == slug and agent_of(k) == agent
            for row_id, n, k in rows
        )

    def transfer(self, item_id, agent, move):
        """Copy or move a skill to *agent*, keeping its scope."""
        name, kind, config = self.db_connector.get_results(
            "SELECT name, kind, config FROM skills WHERE id = ?", (item_id,), return_type='tuple'
        )
        scope = scope_of(kind)
        new_kind = f'{scope}:{agent}' if scope else agent
        source = self.path_for(name, kind).parent
        target = self.path_for(name, new_kind).parent
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copytree(source, target)
        if move:
            shutil.rmtree(source)
            self.db_connector.execute(
                "UPDATE skills SET kind = ? WHERE id = ?", (new_kind, item_id)
            )
        else:
            self.db_connector.execute(
                "INSERT INTO skills (name, kind, config) VALUES (?, ?, ?)",
                (name, new_kind, config)
            )
        self.sync_to_disk()

    def delete(self, key, where_field='id'):
        row = self.db_connector.get_results(
            f"SELECT name, kind FROM `{self.table_name}` WHERE `{where_field}` = ?", (key,),
            return_type='tuple'
        )
        super().delete(key, where_field=where_field)
        if row:
            path = self.path_for(*row)
            if path and path.parent.exists():
                shutil.rmtree(path.parent)
            self.sync_to_disk()

    def add(self, name, **kwargs):
        item_id = super().add(name, **kwargs)
        # A re-added baked item keeps its row's kind, not the given one.
        kind = self.db_connector.get_scalar("SELECT kind FROM skills WHERE id = ?", (item_id,))
        path = self.path_for(name, kind) if agent_of(kind) else None
        if path is not None and not path.exists():
            self.write(name, kind, '', '')
        self.sync_to_disk()
        return item_id

    @staticmethod
    def _format(slug, description, body):
        description = (description or '').replace('\n', ' ').strip()
        body = (body or '').rstrip()
        return (
            "---\n"
            f"name: {slug}\n"
            f"description: {description}\n"
            "---\n\n"
            f"{body}\n"
        )

    @staticmethod
    def _parse(text):
        if not text.startswith('---\n'):
            return '', text
        end = text.find('\n---\n', 4)
        if end == -1:
            return '', text
        header, body = text[4:end], text[end + 5:].lstrip('\n')
        description = ''
        for line in header.splitlines():
            if line.startswith('description:'):
                description = line[len('description:'):].strip()
                break
        return description, body

    @staticmethod
    def _slug(name):
        lowered = (name or '').lower().strip()
        lowered = re.sub(r'[\s_]+', '-', lowered)
        lowered = re.sub(r'[^a-z0-9-]', '', lowered)
        lowered = re.sub(r'-+', '-', lowered).strip('-')
        return lowered
