from core.actions.base import UndoableAction
from utils.helpers import set_module_type

_last_path = None


def record_path_change(new_path):
    """Called from `ConfigWidget.update_page_map` whenever the current page path is recomputed."""
    global _last_path
    from core.actions import base as undo_history
    if new_path == _last_path:
        return
    if _last_path is not None:  # skip the initial path set on startup
        undo_history.record(NavigateAction(before=_last_path, after=new_path))
    _last_path = new_path


def set_last(path):
    global _last_path
    _last_path = path


@set_module_type('Actions')
class NavigateAction(UndoableAction):
    """Records a change of the current page path (pages, tabs, tree selections), so it can be restored on undo/redo."""
    label = 'Navigate'

    def undo(self):
        self._navigate(self.data.get('before'))

    def redo(self):
        self._navigate(self.data.get('after'))

    def _navigate(self, path):
        from gui import system
        from gui.gui_utils.helpers import set_selected_pages
        main = getattr(system.manager, '_main_gui', None)
        if main is None or path is None:
            return
        set_selected_pages(main.main_pages, path)
        set_last(path)  # deferred update_page_map calls then dedupe against this path
