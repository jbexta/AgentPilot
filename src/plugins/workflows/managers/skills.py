import re
import shutil
from pathlib import Path

from jinja2 import BaseLoader, DebugUndefined, Environment

from plugins.workflows.managers.blocks import BlockManager
from utils.filesystem import get_application_path


class SkillsManager(BlockManager):
    """
    Skills are templatable workflows (same storage shape as blocks) that are
    additionally mirrored to the project's ``.claude/skills/`` directory as
    Anthropic-style ``SKILL.md`` files. The rendered workflow output becomes
    the body of the markdown file, so Claude Code can load each skill as a
    static document while the AgentPilot user keeps editing it as a workflow.
    """

    def __init__(self, system):
        # Deliberately skip BlockManager.__init__ — it hardcodes
        # table_name='blocks'. We call BaseManager directly so we can point at
        # the skills table while inheriting all of BlockManager's template
        # machinery (receive_block, compute_block, format_string).
        super(BlockManager, self).__init__(
            system,
            table_name='skills',
            folder_key='skills',
            load_columns=['name', 'config'],
            default_fields={'config': {'_TYPE': 'text'}},
            add_item_options={'title': 'Add Skill', 'prompt': 'Enter a name for the skill:'},
            del_item_options={'title': 'Delete Skill', 'prompt': 'Are you sure you want to delete this skill?'},
            config_is_workflow=True,
        )
        self.jinja_env = Environment(
            loader=BaseLoader(),
            undefined=DebugUndefined,
            enable_async=True,
        )

    def sync_to_disk(self):
        """Write every skill to ``<repo>/.claude/skills/<slug>/SKILL.md``.

        Tries to render the workflow first (so jinja expansion is applied); if
        rendering fails — most commonly because ``compute_block`` uses
        ``asyncio.run`` and we're already inside a running event loop — falls
        back to concatenating the raw ``data`` fields of each member.

        Also prunes any ``<repo>/.claude/skills/<slug>/`` directory whose slug
        no longer matches a DB row. Pruning is strictly scoped to that
        directory so unrelated filesystem contents are never touched.
        """
        skills_root = Path(get_application_path()) / '.claude' / 'skills'
        skills_root.mkdir(parents=True, exist_ok=True)

        valid_slugs = set()
        for key, config in self.items():
            if not isinstance(config, dict):
                continue
            display_name = config.get('name', key)
            slug = self._slug(display_name)
            if not slug:
                continue
            valid_slugs.add(slug)

            description = (config.get('description') or '').strip()
            body = self._render_body(display_name, config)

            skill_dir = skills_root / slug
            skill_dir.mkdir(parents=True, exist_ok=True)
            (skill_dir / 'SKILL.md').write_text(
                self._format_skill_md(slug, description, body),
                encoding='utf-8',
            )

        for entry in skills_root.iterdir():
            if entry.is_dir() and entry.name not in valid_slugs:
                shutil.rmtree(entry)

    def _render_body(self, name, config):
        try:
            rendered = self.compute_block(name)
            if rendered:
                return rendered
        except Exception:
            pass
        return self._extract_raw_body(config)

    @staticmethod
    def _extract_raw_body(config):
        parts = []
        for member in config.get('members', []) or []:
            member_config = member.get('config') or {}
            data = member_config.get('data')
            if isinstance(data, str) and data.strip():
                parts.append(data)
        return '\n\n'.join(parts)

    @staticmethod
    def _format_skill_md(slug, description, body):
        description = description.replace('\n', ' ').strip()
        return (
            "---\n"
            f"name: {slug}\n"
            f"description: {description}\n"
            "---\n\n"
            f"{body.rstrip()}\n"
        )

    @staticmethod
    def _slug(name):
        lowered = (name or '').lower().strip()
        lowered = re.sub(r'[\s_]+', '-', lowered)
        lowered = re.sub(r'[^a-z0-9-]', '', lowered)
        lowered = re.sub(r'-+', '-', lowered).strip('-')
        return lowered
