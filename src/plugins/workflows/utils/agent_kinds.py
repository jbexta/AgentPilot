from PySide6.QtCore import Qt
from PySide6.QtWidgets import QMessageBox

from gui.widgets.config_db_tree import ConfigDBTree
from plugins.workflows.utils.acp import acp_agents, agent_of, scope_of
from utils.helpers import display_message


class AgentKindTree:
    """Mixin for a ``ConfigDBTree`` of agent items, whose manager has
    ``exists(name, kind, exclude_id)`` and ``transfer(item_id, agent,
    move)``. Unscoped trees show a group per agent, even when empty. New
    items go to the selected agent, and items can be copied or moved to
    another agent from the context menu."""

    def load(self, *args, **kwargs):
        super().load(*args, **kwargs)
        if not self.kind:
            for agent in acp_agents():
                self.tree._get_or_create_kind_folder(agent, agent)

    def _row_for(self, item_id):
        """``(name, kind)`` of an item."""
        return self.db_connector.get_results(
            f"SELECT name, kind FROM `{self.table_name}` WHERE id = ?",
            (item_id,), return_type='tuple'
        )

    def selected_kind(self):
        """The kind of the selected item or agent group, else the first
        agent's, in this tree's scope. None without agents."""
        agents = list(acp_agents())
        if not agents:
            return None
        item = self.tree.currentItem()
        kind = None
        if item is not None:
            if isinstance(item.data(0, Qt.UserRole), dict):
                kind = self._row_for(self.get_selected_item_id())[1]
            else:
                kind = item.data(1, Qt.UserRole)
        if kind and agent_of(kind) in agents:
            return kind
        scope = self.kind() if callable(self.kind) else (self.kind or '')
        return f'{scope}:{agents[0]}' if scope else agents[0]

    def add_item(self, *, parent_id=None):
        if parent_id is not None:
            return ConfigDBTree.add_item(self, parent_id=parent_id)
        values = self.get_new_item_values()
        if values is None:
            return
        kind = self.selected_kind()
        if kind is None:
            display_message(message='Enable a coding agent plugin first.', icon=QMessageBox.Warning)
            return
        if self.manager.exists(values['name'], kind):
            display_message(
                message=f'{agent_of(kind)} already has one with that name.',
                icon=QMessageBox.Warning,
            )
            return
        self._editing_manager = True
        try:
            item_id = self.manager.add(values['name'], kind=kind)
        finally:
            self._editing_manager = False
        self.load(select_id=item_id)

    def on_context_menu(self, menu):
        item = self.tree.currentItem()
        if item is None or not isinstance(item.data(0, Qt.UserRole), dict):
            return
        current = agent_of(self._row_for(self.get_selected_item_id())[1])
        others = [a for a in acp_agents() if a != current]
        if not others:
            return
        menu.addSeparator()
        for title, move in (('Copy to', False), ('Move to', True)):
            submenu = menu.addMenu(title)
            for agent in others:
                submenu.addAction(agent).triggered.connect(
                    lambda _=False, a=agent, m=move: self.transfer_item(a, m))

    def transfer_item(self, agent, move):
        item_id = self.get_selected_item_id()
        name, kind = self._row_for(item_id)
        scope = scope_of(kind)
        if self.manager.exists(name, f'{scope}:{agent}' if scope else agent):
            display_message(
                message=f'{agent} already has one named {name}.',
                icon=QMessageBox.Warning,
            )
            return
        self.manager.transfer(item_id, agent, move)
        self.load(select_id=item_id)
