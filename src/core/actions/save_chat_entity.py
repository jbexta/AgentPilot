from core.actions.base import UndoableAction
from utils.helpers import set_module_type


@set_module_type('Actions')
class SaveChatEntityAction(UndoableAction):
    """Groups the writes made when saving a chattable entity — the live context row
    plus its linked source entity row (block/agent/tool) — into a single undo step."""
    label = 'Save chattable entity'

    def merge_with(self, prev_data):
        from core.actions.config_save import MERGE_WINDOW_SECS
        prev_saves = prev_data.get('saves', [])
        saves = self.data.get('saves', [])

        def targets(entries):
            return [(e['type'], e['data'].get('table'), e['data'].get('item_id'), e['data'].get('key_field'))
                    for e in entries]
        if not saves or targets(prev_saves) != targets(saves):
            return False
        prev_ts = max((e['data'].get('ts', 0) for e in prev_saves), default=0)
        new_ts = max((e['data'].get('ts', 0) for e in saves), default=0)
        if new_ts - prev_ts >= MERGE_WINDOW_SECS:
            return False
        for prev_entry, entry in zip(prev_saves, saves):
            entry['data']['before'] = prev_entry['data']['before']
        return True

    def undo(self):
        self._replay('undo', reverse=True)

    def redo(self):
        self._replay('redo', reverse=False)

    def _replay(self, method_name, reverse):
        from core.actions import base as undo_history
        entries = self.data.get('saves', [])
        for entry in (reversed(entries) if reverse else entries):
            action_class = undo_history.get_action_class(entry['type'])
            if action_class:
                getattr(action_class(**entry['data']), method_name)()
