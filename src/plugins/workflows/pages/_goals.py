import json

import qasync
from PySide6.QtGui import Qt
from PySide6.QtWidgets import QSplitter, QPushButton, QWidget, QMessageBox

from gui.gui_utils.layouts import CVBoxLayout, CHBoxLayout
from gui.widgets.config_db_tree import ConfigDBTree
from gui.widgets.config_fields import ConfigFields
from gui.widgets.config_widget import ConfigWidget
from plugins.workflows.widgets.chat_widget import ChattableWorkflowWidget
from utils import sql
from utils.helpers import display_message


CLAUDE_CODE_TOOLS = {
    'bash': True, 'read': True, 'write': True, 'edit': True,
    'glob': True, 'grep': True, 'webfetch': False, 'websearch': False,
}


def build_goal_workflow_config(working_dir):
    """Build a workflow config (user + Claude Code member) for a goal's chat.

    Parameters
    ----------
    working_dir : str
        Directory Claude Code runs in for this goal.

    Returns
    -------
    dict
        A ``contexts.config`` value producing a runnable Claude Code chat.
    """
    claude_code = {
        '_TYPE': 'claude_code',
        'name': 'Claude Code',
        'builtin_tools': CLAUDE_CODE_TOOLS,
        'working_dir': working_dir or '',
    }
    return {
        '_TYPE': 'workflow',
        'inputs': [],
        'members': [
            {'id': '1', 'loc_x': 20, 'loc_y': 64,
             'config': {'_TYPE': 'user', 'name': 'You'}},
            {'id': '2', 'loc_x': 100, 'loc_y': 80, 'config': claude_code},
        ],
    }


def link_context_to_goal(context_id, name):
    """Create or update a goal row linked to ``context_id``.

    Called when a user issues ``/goal <name>`` in a Claude Code chat so the
    chat shows up on the Goals page. If a goal already points at this context
    its name is updated to the latest ``/goal`` text; otherwise a new row is
    inserted. Returns the goal id.
    """
    name = (name or '').strip() or 'Untitled goal'
    goal_id = sql.get_scalar(
        "SELECT id FROM goals WHERE context_id = ?", (context_id,))
    if goal_id:
        sql.execute("UPDATE goals SET name = ? WHERE id = ?", (name, goal_id))
        return goal_id
    sql.execute(
        "INSERT INTO goals (name, context_id) VALUES (?, ?)",
        (name, context_id))
    return sql.get_scalar(
        "SELECT id FROM goals WHERE context_id = ?", (context_id,))


class Page_Goals_Settings(ConfigDBTree):
    display_name = 'Goals'
    icon_path = ':/resources/icon-goals.png'
    page_type = 'any'  # either 'settings', 'main', or 'any' (pinnable)

    def __init__(self, parent):
        super().__init__(
            parent=parent,
            table_name='goals',
            query="""
                SELECT
                    name,
                    id,
                    folder_id
                FROM goals
                ORDER BY pinned DESC, ordr, name COLLATE NOCASE""",
            schema=[
                {
                    'text': 'Goals',
                    'key': 'name',
                    'type': str,
                    'stretch': True,
                },
                {
                    'text': 'id',
                    'key': 'id',
                    'type': int,
                    'visible': False,
                },
            ],
            add_item_options={'title': 'New goal',
                              'prompt': 'Enter a name for the goal:'},
            del_item_options={'title': 'Delete goal',
                              'prompt': 'Are you sure you want to delete this goal?'},
            folder_key='goals',
            readonly=False,
            layout_type='horizontal',
            tree_header_hidden=True,
            config_widget=self.Goal_Config_Widget(parent=self),
            searchable=True,
            default_item_icon=':/resources/icon-todo.png',
        )
        self.splitter.setSizes([300, 1000])

    class Goal_Config_Widget(ConfigWidget):
        """Goal fields + Run button + embedded Claude Code chat.

        ``fields`` and ``chat`` are kept as plain attributes (not a ``widgets``
        list, not named ``config_widget``) so the base ``ConfigWidget`` config
        aggregation only ever sees the fields — the chat persists itself to
        the ``contexts`` table independently.
        """

        def __init__(self, parent):
            super().__init__(parent=parent)
            self.propagate_config = True
            self.layout = CVBoxLayout(self)

            self.fields = self.Goal_Fields(parent=self)
            self.chat = self.Goal_Chat(parent=self)

            self.run_button = QPushButton('Run goal')
            self.run_button.setFixedHeight(28)
            self.run_button.clicked.connect(self.run_goal)
            run_bar = CHBoxLayout()
            run_bar.addWidget(self.run_button)
            run_bar.addStretch(1)

            top_widget = QWidget()
            top_layout = CVBoxLayout(top_widget)
            top_layout.addWidget(self.fields)
            top_layout.addLayout(run_bar)

            self.splitter = QSplitter(Qt.Vertical)
            self.splitter.setChildrenCollapsible(False)
            self.splitter.addWidget(top_widget)
            self.splitter.addWidget(self.chat)
            self.splitter.setSizes([220, 600])
            self.layout.addWidget(self.splitter)

        def build_schema(self):
            self.fields.build_schema()

        def load_config(self, json_config=None):
            self.fields.load_config(json_config)

        def get_config(self):
            return self.fields.get_config()

        def load(self):
            self.fields.load()
            goal_id = self.parent.get_selected_item_id()
            if not goal_id:
                return
            working_dir = self.fields.get_config().get('working_dir', '')
            self.chat.load_goal(goal_id, working_dir)

        @qasync.asyncSlot()
        async def run_goal(self):
            goal_id = self.parent.get_selected_item_id()
            if not goal_id:
                return
            config = self.fields.get_config()
            description = (config.get('description') or '').strip()
            if not description:
                display_message(
                    message='Add a description for this goal first.',
                    icon=QMessageBox.Information,
                )
                return
            self.chat.load_goal(goal_id, config.get('working_dir') or '')
            await self.chat.workflow.send_message(
                description, role='goal', as_member_id='1')

        class Goal_Fields(ConfigFields):
            def __init__(self, parent):
                super().__init__(parent=parent)
                self.label_width = 120
                self.schema = [
                    {
                        'text': 'Description',
                        'key': 'description',
                        'type': str,
                        'num_lines': 5,
                        'label_position': 'top',
                        'stretch_x': True,
                        'default': '',
                    },
                    {
                        'text': 'Working directory',
                        'key': 'working_dir',
                        'type': 'file_picker',
                        'mode': 'directory',
                        'stretch_x': True,
                        'default': '',
                    },
                    {
                        'text': 'Status',
                        'key': 'status',
                        'type': ('Not Started', 'In Progress', 'Completed'),
                        'default': 'Not Started',
                    },
                ]

        class Goal_Chat(ChattableWorkflowWidget):
            def __init__(self, parent):
                super().__init__(parent=parent, collapsible=True)

            def load_goal(self, goal_id, working_dir):
                """Load (creating if needed) the goal's Claude Code chat."""
                context_id = sql.get_scalar(
                    "SELECT context_id FROM goals WHERE id = ?", (goal_id,))
                if not context_id:
                    sql.execute(
                        "INSERT INTO contexts (kind, config) VALUES ('CHAT', ?)",
                        (json.dumps(build_goal_workflow_config(working_dir)),))
                    context_id = sql.get_scalar("SELECT MAX(id) FROM contexts")
                    sql.execute("UPDATE goals SET context_id = ? WHERE id = ?",
                                (context_id, goal_id))
                else:
                    self._apply_working_dir(context_id, working_dir)

                if not self.workflow or self.workflow.context_id != context_id:
                    self.goto_context(context_id)

            def _apply_working_dir(self, context_id, working_dir):
                """Keep the Claude Code member's cwd in sync with the goal."""
                config = sql.get_scalar(
                    "SELECT config FROM contexts WHERE id = ?",
                    (context_id,), load_json=True)
                if not isinstance(config, dict):
                    return
                changed = False
                for member in config.get('members', []):
                    member_config = member.get('config', {})
                    if member_config.get('_TYPE') != 'claude_code':
                        continue
                    if member_config.get('working_dir', '') != (working_dir or ''):
                        member_config['working_dir'] = working_dir or ''
                        changed = True
                if changed:
                    sql.execute("UPDATE contexts SET config = ? WHERE id = ?",
                                (json.dumps(config), context_id))