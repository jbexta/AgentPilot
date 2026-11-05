import json
import os
import re
import shutil
import tempfile
from pathlib import Path

from utils import sql
from utils.filesystem import get_application_path
from utils.helpers import BaseManager


class SkillsManager(BaseManager):
    """
    All app-managed skills live in one fixed folder, ``app_skills/`` —
    shaped as a local Claude Code plugin (``.claude-plugin/plugin.json``
    plus one ``skills/<slug>/SKILL.md`` folder per skill) so in-app
    Claude Code sessions load it directly. The DB row tracks identity
    (name, kind, ordr, pinned, etc.); description and body are read and
    written directly to/from disk. ``read`` returns ``(description,
    body)`` parsed from the frontmatter; ``write`` reassembles the
    frontmatter from the same pair.

    ``sync_to_disk`` mirrors skills into ``.claude/skills`` dirs so
    terminal Claude Code sessions see them too: project-less skills into
    the user-global ``~/.claude/skills``, project skills into their
    project's working_dir.
    Skills flagged ``app_only`` in their config are never mirrored.
    ``mirrors.json`` records every mirror written, so stale ones can be
    removed without touching skill folders the app doesn't manage.
    """

    # PLUGIN_DIR = Path(get_application_path()) / 'app_skills'
    # SKILLS_DIR = PLUGIN_DIR / 'skills'
    # MANIFEST_PATH = PLUGIN_DIR / 'mirrors.json'

    @property
    def PLUGIN_DIR(self):
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
    def SKILLS_DIR(self):
        return self.PLUGIN_DIR / 'skills'

    @property
    def MANIFEST_PATH(self):
        return self.PLUGIN_DIR / 'mirrors.json'

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
            shutil.rmtree(self.PLUGIN_DIR, ignore_errors=True)
        self.SKILLS_DIR.mkdir(parents=True, exist_ok=True)
        plugin_json = self.PLUGIN_DIR / '.claude-plugin' / 'plugin.json'
        if not plugin_json.exists():
            plugin_json.parent.mkdir(parents=True, exist_ok=True)
            plugin_json.write_text(
                json.dumps({'name': 'agentpilot', 'version': '0.1.0'}),
                encoding='utf-8',
            )

    def load(self):
        super().load()
        self.sync_to_disk()

    def path_for(self, name):
        slug = self._slug(name)
        return self.SKILLS_DIR / slug / 'SKILL.md' if slug else None

    def mirror_root_for(self, name):
        """The ``.claude/skills`` dir a skill is mirrored to for terminal
        sessions, or None for app-only skills (never mirrored)."""
        row = self.db_connector.get_results(
            "SELECT kind, config FROM skills WHERE name = ?", (name,), return_type='tuple'
        )
        kind, config = row[:2] if row else ('', None)
        config = json.loads(config) if config else {}
        if config.get('app_only', False):
            return None
        if (kind or '').startswith('PROJECT:'):
            working_dir = self.db_connector.get_scalar(
                "SELECT json_extract(config, '$.working_dir') FROM projects WHERE id = ?",
                (int(kind.split(':')[1]),)
            )
            return Path(working_dir) / '.claude' / 'skills' if working_dir else None
        # Project-less skills are for every terminal session, so they mirror
        # to the user-global skills dir rather than any single repo's.
        return Path.home() / '.claude' / 'skills'

    def sync_to_disk(self):
        """Refresh the terminal-facing mirrors to match the DB and the
        canonical folders. Only paths recorded in the manifest are ever
        deleted, so unmanaged skill folders are left alone. Skipped for
        dummy (test/demo) DBs, which would otherwise clobber real mirrors."""
        if os.path.basename(sql.get_db_path()) != 'data.db':
            return
        self._adopt_project_skills()

        previous = {}
        if self.MANIFEST_PATH.exists():
            try:
                previous = json.loads(self.MANIFEST_PATH.read_text(encoding='utf-8'))
            except (OSError, json.JSONDecodeError):
                pass

        names = self.db_connector.get_results(
            "SELECT name FROM skills", return_type='list'
        ) or []
        desired = {}
        for name in names:
            slug = self._slug(name)
            if not slug or not (self.SKILLS_DIR / slug).exists():
                continue
            root = self.mirror_root_for(name)
            if root is not None:
                desired[slug] = str(root / slug)

        for slug, path in previous.items():
            if desired.get(slug) != path and Path(path).exists():
                shutil.rmtree(path)
        for slug, path in desired.items():
            mirror = Path(path)
            canonical = self.SKILLS_DIR / slug
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

    def _adopt_project_skills(self):
        """Skill folders found in ``~/.claude/skills`` or a project's
        ``.claude/skills`` that the app doesn't manage yet (e.g.
        hand-written by a terminal session) are adopted — a DB row
        (project-less or ``PROJECT:n`` respectively) plus a canonical
        copy — so they show up in the Skills page."""
        names = self.db_connector.get_results(
            "SELECT name FROM skills", return_type='list'
        ) or []
        known = {self._slug(n) for n in names}
        projects = self.db_connector.get_results(
            "SELECT id, json_extract(config, '$.working_dir') FROM projects"
        ) or []
        sources = [('', Path.home() / '.claude' / 'skills')]
        sources += [
            (f'PROJECT:{project_id}', Path(working_dir) / '.claude' / 'skills')
            for project_id, working_dir in projects if working_dir
        ]
        for kind, skills_dir in sources:
            if not skills_dir.is_dir():
                continue
            for d in sorted(skills_dir.iterdir()):
                slug = d.name
                if not d.is_dir() or not (d / 'SKILL.md').exists() or slug in known:
                    continue
                shutil.copytree(d, self.SKILLS_DIR / slug)
                self.db_connector.execute(
                    "INSERT INTO skills (name, kind) VALUES (?, ?)",
                    (slug, kind)
                )
                known.add(slug)

    def read(self, name):
        path = self.path_for(name)
        if path is None or not path.exists():
            return '', ''
        try:
            return self._parse(path.read_text(encoding='utf-8'))
        except OSError:
            return '', ''

    def write(self, name, description, body):
        path = self.path_for(name)
        if path is None:
            return
        path.parent.mkdir(parents=True, exist_ok=True)
        slug = self._slug(name)
        path.write_text(self._format(slug, description, body), encoding='utf-8')

    def list_files(self):
        if not self.SKILLS_DIR.exists():
            return []
        return [
            d.name for d in self.SKILLS_DIR.iterdir()
            if d.is_dir() and (d / 'SKILL.md').exists()
        ]

    def delete(self, key, where_field='id'):
        name = self.db_connector.get_scalar(
            f"SELECT name FROM `{self.table_name}` WHERE `{where_field}` = ?", (key,)
        )
        super().delete(key, where_field=where_field)
        if name:
            slug_dir = self.SKILLS_DIR / self._slug(name)
            if slug_dir.exists():
                shutil.rmtree(slug_dir)
            self.sync_to_disk()

    def add(self, name, **kwargs):
        item_id = super().add(name, **kwargs)
        path = self.path_for(name)
        if path is not None and not path.exists():
            self.write(name, '', '')
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
