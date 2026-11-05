import re
from pathlib import Path

from utils.helpers import BaseManager


class PlansManager(BaseManager):
    """
    Plans live as ``~/.claude/plans/<slug>.md`` files. The DB row tracks
    only identity (name, ordr, pinned, etc.); the body is read and written
    directly to/from disk by the page. No mirroring, no equality checks,
    no reconciliation cache.
    """

    PLANS_DIR = Path.home() / '.claude' / 'plans'

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

    def path_for(self, name):
        slug = self._slug(name)
        return self.PLANS_DIR / f'{slug}.md' if slug else None

    def read(self, name):
        path = self.path_for(name)
        if path is None or not path.exists():
            return ''
        try:
            return path.read_text(encoding='utf-8')
        except OSError:
            return ''

    def write(self, name, body):
        path = self.path_for(name)
        if path is None:
            return
        self.PLANS_DIR.mkdir(parents=True, exist_ok=True)
        text = body or ''
        if text and not text.endswith('\n'):
            text += '\n'
        path.write_text(text, encoding='utf-8')

    def list_files(self):
        if not self.PLANS_DIR.exists():
            return []
        return [p.stem for p in self.PLANS_DIR.glob('*.md') if p.stem]

    def delete(self, key, where_field='id'):
        name = self.db_connector.get_scalar(
            f"SELECT name FROM `{self.table_name}` WHERE `{where_field}` = ?", (key,)
        )
        super().delete(key, where_field=where_field)
        if name:
            path = self.path_for(name)
            if path is not None and path.exists():
                path.unlink()

    def add(self, name, **kwargs):
        item_id = super().add(name, **kwargs)
        path = self.path_for(name)
        if path is not None and not path.exists():
            self.PLANS_DIR.mkdir(parents=True, exist_ok=True)
            path.write_text('', encoding='utf-8')
        return item_id

    @staticmethod
    def _slug(name):
        lowered = (name or '').lower().strip()
        lowered = re.sub(r'[\s_]+', '-', lowered)
        lowered = re.sub(r'[^a-z0-9-]', '', lowered)
        lowered = re.sub(r'-+', '-', lowered).strip('-')
        return lowered
