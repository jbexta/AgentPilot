from core.actions.base import UndoableAction
from utils.helpers import set_module_type

MERGE_WINDOW_SECS = 5.0


@set_module_type('Actions')
class ConfigSaveAction(UndoableAction):
    """Records a table item save (before/after value), recorded from `save_table_config`.
    Rapid consecutive saves of the same item (e.g. per-keystroke text edits) merge into one action."""
    label = 'Edit item'

    def merge_with(self, prev_data):
        same_target = all(prev_data.get(k) == self.data.get(k) for k in ('table', 'item_id', 'key_field'))
        if same_target and self.data.get('ts', 0) - prev_data.get('ts', 0) < MERGE_WINDOW_SECS:
            self.data['before'] = prev_data['before']
            return True
        return False

    def undo(self):
        self._apply(self.data.get('before'))

    def redo(self):
        self._apply(self.data.get('after'))

    def _apply(self, value):
        if value is None:
            return
        from gui.gui_utils.helpers import save_table_config
        save_table_config(self.data['table'], self.data['item_id'], value, key_field=self.data.get('key_field', 'config'))
        self._refresh()

    def _refresh(self):
        from PySide6.QtWidgets import QApplication
        for widget in QApplication.allWidgets():
            try:
                if (getattr(widget, 'table_name', None) == self.data['table']
                        and hasattr(widget, 'on_edited')
                        and widget.isVisible()):
                    widget.on_edited()  # refreshes the tree, but not the config widget
                    if (hasattr(widget, 'get_selected_item_id')
                            and widget.get_selected_item_id() == self.data['item_id']
                            and hasattr(widget, 'on_item_selected')):
                        widget.on_item_selected()  # reload the visible config widget from the DB
                    break
            except RuntimeError:  # widget's C++ object already deleted
                continue
