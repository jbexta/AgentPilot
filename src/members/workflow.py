import asyncio
import json

from src.members.user import User, UserSettings
from src.utils import sql
from src.members.base import Member
from src.utils.messages import MessageHistory
from src.members.agent import Agent

import sqlite3
from abc import abstractmethod
from functools import partial

from PySide6.QtCore import QPointF, QRectF
from PySide6.QtGui import Qt, QPen, QColor, QBrush, QPixmap, QPainter, QPainterPath, QCursor, QRadialGradient
from PySide6.QtWidgets import QWidget, QGraphicsScene, QGraphicsEllipseItem, QGraphicsItem, QGraphicsView, \
    QMessageBox, QGraphicsPathItem, QStackedLayout, QMenu, QInputDialog, QApplication, QTextEdit

from src.gui.config import ConfigWidget, CVBoxLayout, CHBoxLayout

from src.gui.widgets import IconButton, ToggleButton, find_main_widget, ListDialog, BaseTreeWidget
from src.members.agent import AgentSettings
from src.utils.helpers import path_to_pixmap, display_messagebox


loop = asyncio.new_event_loop()
asyncio.set_event_loop(loop)


# Helper function to load behavior module dynamically todo - move to utils
def load_behaviour_module(group_key):
    from src.utils.plugin import all_plugins
    try:
        # Dynamically import the context behavior plugin based on group_key
        return all_plugins['Workflow'].get(group_key)
    except ImportError as e:
        # No module found for this group_key
        return None


def get_common_group_key(members):
    """Get all distinct group_keys and if there's only one, return it, otherwise return empty key"""
    group_keys = set(getattr(member, 'group_key', '') for member in members.values())
    if len(group_keys) == 1:
        return next(iter(group_keys))
    return ''


class Workflow(Member):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.parent_workflow = kwargs.get('workflow', None)
        self.system = self.main.system
        self.member_type = 'workflow'

        self.loop = asyncio.get_event_loop()
        self.responding = False
        self.stop_requested = False

        self.id = kwargs.get('context_id', None)
        self.chat_name = ''
        self.chat_title = ''
        self.leaf_id = self.id
        self.context_path = {self.id: None}
        self.members = {}

        self.behaviour = None
        self.message_history = MessageHistory(self)

        self.config = kwargs.get('config', {})

        if self.id is not None:
            config_str = sql.get_scalar("SELECT config FROM contexts WHERE id = ?", (self.id,))
            self.config = json.loads(config_str)

        # if agent_id is not None:  todo
        #     context_id = sql.get_scalar("""
        #         SELECT context_id AS id
        #         FROM contexts_members
        #         WHERE agent_id = ?
        #           AND context_id IN (
        #             SELECT context_id
        #             FROM contexts_members
        #             GROUP BY context_id
        #             HAVING COUNT(agent_id) = 1
        #           ) AND del = 0
        #         ORDER BY context_id DESC
        #         LIMIT 1""", (agent_id,))
        #     self.id = context_id

        self.load()

    def load(self):
        self.load_members()
        self.message_history.load()
        self.chat_title = sql.get_scalar("SELECT summary FROM contexts WHERE id = ?", (self.id,))

    def load_members(self):
        from src.utils.plugin import get_plugin_agent_class
        # Get members and inputs from the loaded json config
        if self.config.get('_TYPE', 'agent') == 'workflow':  # 'members' in self.config:  # todo remove?
            members = self.config['members']
        else:  # is a single agent, this allows single agent to be in workflow config for simplicity, but ?
            members = [{'config': self.config, 'agent_id': None}]
        inputs = self.config.get('inputs', [])

        members = sorted(members, key=lambda x: x.get('loc_x', 50))  # 50 to avoid order issue with new architecture

        self.members = {}
        iterable = iter(members)
        while len(members) > 0:
            try:
                member_dict = next(iterable)
            except StopIteration:  # todo temp make nicer
                iterable = iter(members)
                continue

            member_id = member_dict['id']
            entity_id = member_dict['agent_id']
            member_config = member_dict['config']
            loc_x = member_dict.get('loc_x', 50)
            loc_y = member_dict.get('loc_y', 0)
            member_input_ids = [
                input_info['input_member_id']
                for input_info in inputs if input_info['member_id'] == member_id
            ]

            # Order based on the inputs
            if len(member_input_ids) > 0:
                if not all((inp_id in self.members) for inp_id in member_input_ids):
                    continue

            deleted = member_dict.get('del', False)
            if deleted == 1:
                continue

            member_type = member_dict.get('config', {}).get('_TYPE', 'agent')
            # Instantiate the member
            kwargs = dict(main=self.main,
                          agent_id=entity_id,
                          member_id=member_id,
                          config=member_config,
                          workflow=self,
                          loc_x=loc_x,
                          loc_y=loc_y,
                          inputs=member_input_ids)
            # member_instance =
            if member_type == 'agent':
                use_plugin = member_config.get('info.use_plugin', None)
                agent_class = get_plugin_agent_class(use_plugin, kwargs)
                if agent_class is not None:
                    member_instance = agent_class
                else:
                    member_instance = Agent(**kwargs)

                member_instance.load_agent()  # Load the agent (can't be in the __init__ to make it overridable)
            elif member_type == 'workflow':
                member_instance = Workflow(**kwargs)
                # raise NotImplementedError("Nested workflows not implemented")
            elif member_type == 'user':  # main=None, workflow=None, member_id=None, config=None, inputs=None):
                member_instance = User(**kwargs)
            else:
                raise NotImplementedError(f"Member type '{member_type}' not implemented")

            self.members[member_id] = member_instance
            members.remove(member_dict)
            iterable = iter(members)
            continue

        counted_members = [m for m in self.members.values() if m.config.get('_TYPE', 'agent') == 'agent']
        if len(counted_members) == 1:
            self.chat_name = next(iter(counted_members)).config.get('info.name', 'Assistant')
        else:
            self.chat_name = f'{len(counted_members)} members'  # todo - also count nested workflow members

        self.update_behaviour()

    def update_behaviour(self):
        """Update the behaviour of the context based on the common key"""
        common_group_key = get_common_group_key(self.members)
        behaviour_module = load_behaviour_module(common_group_key)
        self.behaviour = behaviour_module(self) if behaviour_module else WorkflowBehaviour(self)

    def run_member(self):
        """The entry response method for the member."""
        self.behaviour.start()

    def save_message(self, role, content, member_id=None, log_obj=None):
        """Saves a message to the database and returns the message_id"""
        if role == 'output':
            content = 'The code executed without any output' if content.strip() == '' else content

        if content == '':
            return None

        # Set last_output for members, so they can be used by other members
        member = self.members.get(member_id, None)
        if member is not None:  # and role == 'assistant':
            member.last_output = content

        return self.message_history.add(role, content, member_id=member_id, log_obj=log_obj)

    def deactivate_all_branches_with_msg(self, msg_id):
        print("CALLED deactivate_all_branches_with_msg: ", msg_id)
        sql.execute("""
            UPDATE contexts
            SET active = 0
            WHERE branch_msg_id = (
                SELECT branch_msg_id
                FROM contexts
                WHERE id = (
                    SELECT context_id
                    FROM contexts_messages
                    WHERE id = ?
                )
            );""", (msg_id,))

    def activate_branch_with_msg(self, msg_id):
        print("CALLED activate_branch_with_msg: ", msg_id)
        sql.execute("""
            UPDATE contexts
            SET active = 1
            WHERE id = (
                SELECT context_id
                FROM contexts_messages
                WHERE id = ?
            );""", (msg_id,))


class WorkflowBehaviour:
    def __init__(self, workflow):
        self.workflow = workflow

    def start(self):
        for member in self.workflow.members.values():
            member.response_task = self.workflow.loop.create_task(self.run_member(member))

        self.workflow.responding = True
        try:
            t = asyncio.gather(*[m.response_task for m in self.workflow.members.values()])
            self.workflow.loop.run_until_complete(t)
        except asyncio.CancelledError:
            pass  # task was cancelled, so we ignore the exception
        except Exception as e:
            # self.main.finished_signal.emit()
            raise e

    def stop(self):
        self.workflow.stop_requested = True
        for member in self.workflow.members.values():
            if member.response_task is not None:
                member.response_task.cancel()

    async def run_member(self, member):
        try:
            # todo - throw exception for circular references
            if member.inputs:
                await asyncio.gather(*[self.workflow.members[m_id].response_task
                                       for m_id in member.inputs
                                       if m_id in self.workflow.members])

            await member.run_member()
        except asyncio.CancelledError:
            pass  # task was cancelled, so we ignore the exception


class WorkflowSettings(ConfigWidget):
    def __init__(self, parent, **kwargs):
        super().__init__(parent)
        self.main = find_main_widget(self)
        self.compact_mode = kwargs.get('compact_mode', False)  # For use in agent page

        self.members_in_view = {}  # id: member
        self.lines = {}  # (member_id, inp_member_id): line

        self.new_line = None
        self.new_agent = None

        self.layout = CVBoxLayout(self)
        self.workflow_buttons = WorkflowButtonsWidget(parent=self)
        # self.workflow_buttons.btn_add.clicked.connect(self.add_item)
        # self.workflow_buttons.btn_del.clicked.connect(self.delete_item)

        self.scene = QGraphicsScene(self)
        self.scene.setSceneRect(0, 0, 625, 200)

        self.view = CustomGraphicsView(self.scene, self)

        self.view.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.view.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.view.setFixedSize(625, 200)

        self.compact_mode_back_button = self.CompactModeBackButton(parent=self)
        self.member_config_widget = DynamicMemberConfigWidget(parent=self)
        self.member_config_widget.hide()

        self.layout.addWidget(self.workflow_buttons)
        h_container = QWidget()
        h_layout = CHBoxLayout(h_container)
        h_layout.addWidget(self.view)

        if not self.compact_mode:
            self.member_list = MemberList(self)
            # self.member_list.setFixedWidth(125)
            h_layout.addWidget(self.member_list)
            self.member_list.tree_members.itemSelectionChanged.connect(self.on_member_list_selection_changed)
            self.member_list.hide()
        # else:
        # h_layout.addStretch(1)

        self.scene.selectionChanged.connect(self.on_selection_changed)

        self.layout.addWidget(h_container)
        self.layout.addWidget(self.compact_mode_back_button)
        self.layout.addWidget(self.member_config_widget)
        self.layout.addStretch(1)

    class CompactModeBackButton(QWidget):
        def __init__(self, parent):
            super().__init__(parent)
            self.parent = parent
            self.layout = CHBoxLayout(self)
            self.btn_back = IconButton(
                parent=self,
                icon_path=':/resources/icon-back.png',
                tooltip='Back',
                size=18,
                text='Back to workflow'
            )
            self.btn_back.clicked.connect(self.on_clicked)

            self.layout.addWidget(self.btn_back)
            self.layout.addStretch(1)
            self.hide()

        def on_clicked(self):
            self.parent.select_ids([])  # deselect all
            self.parent.view.show()
            self.parent.workflow_buttons.show()
            self.hide()

    def load_config(self, json_config=None):
        if isinstance(json_config, str):
            json_config = json.loads(json_config)
        if '_TYPE' not in json_config:  # todo maybe change
            json_config = json.dumps({
                '_TYPE': 'workflow',
                'members': [
                    {'id': 1, 'agent_id': None, 'loc_x': -10, 'loc_y': 64, 'config': {'_TYPE': 'user'}, 'del': 0},
                    {'id': 2, 'agent_id': 0, 'loc_x': 37, 'loc_y': 30, 'config': json_config, 'del': 0}
                ],
                'inputs': [],
            })
        super().load_config(json_config)

    def get_config(self):
        config = {
            '_TYPE': 'workflow',
            'members': [],
            'inputs': [],
        }
        for member_id, member in self.members_in_view.items():
            config['members'].append({
                'id': member_id,
                'agent_id': None,  # member.agent_id, todo
                'loc_x': int(member.x()),
                'loc_y': int(member.y()),
                'config': member.member_config,
            })

        for line_key, line in self.lines.items():
            member_id, input_member_id = line_key

            config['inputs'].append({
                'member_id': member_id,
                'input_member_id': input_member_id,
                'type': line.input_type,
            })

        return config

    @abstractmethod
    def save_config(self):
        pass

    def update_member(self, update_list):
        for member_id, attribute, value in update_list:
            member = self.members_in_view.get(member_id)
            if not member:
                return
            setattr(member, attribute, value)
        self.save_config()

    def load(self, temp_exclude_conf_widget=False):
        # focused_widget = QApplication.focusWidget()
        # cursor_pos = None  # if focused_widget is textedit, get cursor position
        # if isinstance(focused_widget, QTextEdit):
        #     cursor_pos = focused_widget.textCursor().position()
        # # pass
        # if not temp_exclude_conf_widget:
        self.load_members()
        self.load_inputs()
        # if not temp_exclude_conf_widget:
        self.member_config_widget.load()

        if hasattr(self, 'member_list'):
            self.member_list.load()

        # if focused_widget:  # todo, temporary fix for focus issue
        #     focused_widget.setFocus()
        # #     if cursor_pos is not None:
        # #         focused_widget.textCursor().setPosition(cursor_pos)

    def load_members(self):
        sel_member_ids = [x.id for x in self.scene.selectedItems() if isinstance(x, DraggableMember)]
        # Clear any existing members from the scene
        for m_id, member in self.members_in_view.items():
            self.scene.removeItem(member)
        self.members_in_view = {}

        members_data = self.config.get('members', [])

        # Iterate over the parsed 'members' data and add them to the scene
        for member_info in members_data:
            id = member_info['id']
            agent_id = member_info.get('agent_id')
            member_config = member_info.get('config')
            loc_x = member_info.get('loc_x')
            loc_y = member_info.get('loc_y')

            member = DraggableMember(self, id, loc_x, loc_y, member_config)  # member_inp_str, member_type_str,
            self.scene.addItem(member)
            self.members_in_view[id] = member

        # count members but minus one for the user member
        member_count = len(self.members_in_view)
        if any(m.member_type == 'user' for m in self.members_in_view.values()):
            member_count -= 1

        if member_count == 1:
            # Select the member so that it's config is shown, then hide the workflow panel until more members are added
            other_member_ids = [k for k, m in self.members_in_view.items() if m.member_type != 'user']
            self.select_ids([other_member_ids[0]])
            self.view.hide()
        else:
            # Show the workflow panel in case it was hidden
            self.view.show()
            # Select the members that were selected before, patch for deselecting members todo
            # if not self.compact_mode:
            self.select_ids(sel_member_ids)

    def load_inputs(self):
        for _, line in self.lines.items():
            self.scene.removeItem(line)
        self.lines = {}

        inputs_data = self.config.get('inputs', [])
        for input_dict in inputs_data:
            member_id = input_dict['member_id']
            input_member_id = input_dict['input_member_id']
            input_type = input_dict['type']

            input_member = self.members_in_view.get(input_member_id)
            member = self.members_in_view.get(member_id)

            if input_member is None:  # todo temp
                return
            line = ConnectionLine(self, input_member, member, input_type)
            self.scene.addItem(line)
            self.lines[(member_id, input_member_id)] = line

    def select_ids(self, ids):
        for item in self.scene.selectedItems():
            item.setSelected(False)

        for _id in ids:
            if _id in self.members_in_view:
                self.members_in_view[_id].setSelected(True)

    def on_selection_changed(self):
        selected_agents = [x for x in self.scene.selectedItems() if isinstance(x, DraggableMember)]
        selected_lines = [x for x in self.scene.selectedItems() if isinstance(x, ConnectionLine)]

        # is_only_agent = len(self.members_in_view) == 1

        # with block_signals(self.group_topbar): # todo
        if len(selected_agents) == 1:
            member = selected_agents[0]
            self.member_config_widget.display_config_for_member(member)
            self.member_config_widget.show()
            # # self.load_agent_settings(selected_agents[0].id)
            # if self.compact_mode:
            #     self.view.hide()
            #     # if not is_only_agent:
            #     #     self.compact_mode_back_button.show()
            #     # # self.compact_mode_back_button.show()
            #     # # self.workflow_buttons.hide()
        else:
            self.member_config_widget.hide()

    def on_member_list_selection_changed(self):
        selected_member_ids = [self.member_list.tree_members.get_selected_item_id()]
        self.select_ids(selected_member_ids)

    def add_insertable_entity(self, item):
        self.view.show()
        mouse_scene_point = self.view.mapToScene(self.view.mapFromGlobal(QCursor.pos()))
        item = item.data(Qt.UserRole)
        entity_id = item['id']
        entity_avatar = item['avatar'].split('//##//##//')
        entity_config = json.loads(item['config'])
        self.new_agent = InsertableMember(self, entity_id, entity_avatar, entity_config, mouse_scene_point)
        self.scene.addItem(self.new_agent)
        self.view.setFocus()

    def add_entity(self):
        member_id = max(self.members_in_view.keys()) + 1 if len(self.members_in_view) else 1
        entity_config = self.new_agent.config
        loc_x, loc_y = self.new_agent.x(), self.new_agent.y()
        member = DraggableMember(self, member_id, loc_x, loc_y, entity_config)  # member_inp_str, member_type_str,
        self.scene.addItem(member)
        self.members_in_view[member_id] = member

        self.scene.removeItem(self.new_agent)
        self.new_agent = None

        self.save_config()
        if not self.compact_mode:
            self.parent.load()

    def add_input(self, member_id):
        input_member_id = self.new_line.input_member_id

        if member_id == input_member_id:
            return
        if (member_id, input_member_id) in self.lines:
            return
        cr_check = self.check_for_circular_references(member_id, [input_member_id])
        if cr_check:
            display_messagebox(
                icon=QMessageBox.Warning,
                title='Warning',
                text='Circular reference detected',
                buttons=QMessageBox.Ok,
            )
            return

        input_member = self.members_in_view[input_member_id]
        member = self.members_in_view[member_id]

        if input_member is None:  # todo temp
            return
        line = ConnectionLine(input_member, member, input_type=0)
        self.scene.addItem(line)
        self.lines[(member_id, input_member_id)] = line

        self.scene.removeItem(self.new_line)
        self.new_line = None

        self.save_config()
        if not self.compact_mode:
            self.parent.load()

    # recursive function to check for circular references
    def check_for_circular_references(self, member_id, input_member_ids):
        # member = self.members_in_view[member_id]
        connected_input_members = [g[1] for g in self.lines.keys() if g[0] in input_member_ids]
        if member_id in connected_input_members:
            return True
        if len(connected_input_members) == 0:
            return False
        return self.check_for_circular_references(member_id, connected_input_members)


class WorkflowButtonsWidget(QWidget):
    def __init__(self, parent):
        super().__init__(parent=parent)
        self.parent = parent
        self.layout = CHBoxLayout(self)

        # add 10px margin to the left
        self.layout.addSpacing(15)

        self.btn_add = IconButton(
            parent=self,
            icon_path=':/resources/icon-new.png',
            tooltip='Add',
            size=18,
        )
        self.btn_save_as = IconButton(
            parent=self,
            icon_path=':/resources/icon-save.png',
            tooltip='Save As',
            size=18,
        )
        self.btn_config = ToggleButton(
            parent=self,
            icon_path=':/resources/icon-settings-off.png',
            tooltip='Workflow Settings',
            size=18,
        )
        self.btn_clear_chat = IconButton(
            parent=self,
            icon_path=':/resources/icon-clear.png',
            tooltip='Clear Chat',
            size=18,
        )

        self.btn_member_list = ToggleButton(
            parent=self,
            icon_path=':/resources/icon-agent-group.png',
            tooltip='Open flow',
            size=18,
        )

        self.btn_add.clicked.connect(self.show_context_menu)
        self.btn_save_as.clicked.connect(self.save_as)
        self.btn_clear_chat.clicked.connect(self.clear_chat)
        self.btn_member_list.clicked.connect(self.toggle_member_list)

        self.layout.addWidget(self.btn_add)
        self.layout.addWidget(self.btn_save_as)
        self.layout.addWidget(self.btn_config)
        self.layout.addWidget(self.btn_clear_chat)

        self.layout.addStretch(1)
        self.layout.addWidget(self.btn_member_list)

        if parent.compact_mode:
            self.btn_save_as.hide()
            self.btn_clear_chat.hide()
            self.btn_member_list.hide()

        # self.layout.addWidget(self.btn_del)

        # if getattr(parent, 'folder_key', False):
        #     self.btn_new_folder = IconButton(
        #         parent=self,
        #         icon_path=':/resources/icon-new-folder.png',
        #         tooltip='New Folder',
        #         size=18,
        #     )
        #     self.layout.addWidget(self.btn_new_folder)
        #
        # if getattr(parent, 'filterable', False):
        #     self.btn_filter = ToggleButton(
        #         parent=self,
        #         icon_path=':/resources/icon-filter.png',
        #         icon_path_checked=':/resources/icon-filter-filled.png',
        #         tooltip='Filter',
        #         size=18,
        #     )
        #     self.layout.addWidget(self.btn_filter)
        #
        # if getattr(parent, 'searchable', False):
        #     self.btn_search = ToggleButton(
        #         parent=self,
        #         icon_path=':/resources/icon-search.png',
        #         icon_path_checked=':/resources/icon-search-filled.png',
        #         tooltip='Search',
        #         size=18,
        #     )
        #     self.layout.addWidget(self.btn_search)

        # self.layout.addStretch(1)

        # self.btn_clear = QPushButton('Clear', self)
        # # self.btn_clear.clicked.connect(self.clear_chat)
        # self.btn_clear.setFixedWidth(75)
        # self.layout.addWidget(self.btn_clear)

    def save_as(self):
        workflow_config = self.parent.get_config()
        text, ok = QInputDialog.getText(self, 'Entity Name', 'Enter a name for the new entity')

        if not ok:
            return False

        try:
            sql.execute("""
                INSERT INTO entities (name, kind, config)
                VALUES (?, ?, ?)
            """, (text, 'AGENT', json.dumps(workflow_config),))

            display_messagebox(
                icon=QMessageBox.Information,
                title='Success',
                text='Entity saved',
            )
        except sqlite3.IntegrityError as e:
            display_messagebox(
                icon=QMessageBox.Warning,
                title='Error',
                text='Name already exists',
            )
            return

    def show_context_menu(self):
        menu = QMenu(self)

        add_agent = menu.addAction('Agent')
        add_user = menu.addAction('User')
        add_tool = menu.addAction('Tool')

        add_agent.triggered.connect(partial(self.choose_member, "AGENT"))
        add_user.triggered.connect(partial(self.choose_member, "USER"))
        add_tool.triggered.connect(partial(self.choose_member, "TOOL"))

        menu.exec_(QCursor.pos())

    def choose_member(self, list_type):
        # if list_type == 'agents':
        #     callback = self.parent.insertAgent
        #     # multiselect = False
        # else:
        #     callback = self.parent.insertTool
        #     # multiselect = True

        # callback with partial of list_type

        list_dialog = ListDialog(
            parent=self,
            title="Add Member",
            list_type=list_type,
            callback=self.parent.add_insertable_entity,
            # multiselect=multiselect
        )
        list_dialog.open()

    def clear_chat(self):
        retval = display_messagebox(
            icon=QMessageBox.Warning,
            text="Are you sure you want to permanently clear the chat messages? This should only be used when testing a workflow. To keep your data start a new context.",
            title="Clear Chat",
            buttons=QMessageBox.Ok | QMessageBox.Cancel,
        )
        if retval != QMessageBox.Ok:
            return

        workflow = self.parent.main.page_chat.workflow

        sql.execute("""
            WITH RECURSIVE delete_contexts(id) AS (
                SELECT id FROM contexts WHERE id = ?
                UNION ALL
                SELECT contexts.id FROM contexts
                JOIN delete_contexts ON contexts.parent_id = delete_contexts.id
            )
            DELETE FROM contexts WHERE id IN delete_contexts AND id != ?;
        """, (workflow.id, workflow.id,))
        sql.execute("""
            WITH RECURSIVE delete_contexts(id) AS (
                SELECT id FROM contexts WHERE id = ?
                UNION ALL
                SELECT contexts.id FROM contexts
                JOIN delete_contexts ON contexts.parent_id = delete_contexts.id
            )
            DELETE FROM contexts_messages WHERE context_id IN delete_contexts;
        """, (workflow.id,))
        sql.execute("""
        DELETE FROM contexts_messages WHERE context_id = ?""",
        (workflow.id,))

        # page_chat = self.parent.parent.parent
        # page_chat.workflow = Workflow(main=page_chat.main)
        # self.parent.parent.parent.load()
        self.parent.main.page_chat.load()

    def toggle_member_list(self):
        is_visible = self.parent.member_list.isVisible()
        new_visibility = self.btn_member_list.isChecked()
        # if is_visible == new_visibility:
        #     return  # precaution
        #
        # new_scene_width = 400 if new_visibility else 550
        # self.parent.view.setFixedWidth(new_scene_width)
        self.parent.member_list.setVisible(new_visibility)



class CustomGraphicsView(QGraphicsView):
    def __init__(self, scene, parent):
        super(CustomGraphicsView, self).__init__(scene, parent)
        self.setMouseTracking(True)
        self.setRenderHint(QPainter.Antialiasing)
        self.parent = parent

        self._is_panning = False
        self._mouse_press_pos = None

        # Enable ScrollBars.
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        # self.setDragMode(QGraphicsView.ScrollHandDrag)  # Optional

    def mouse_is_over_member(self):
        # mouse_scene_position = self.mapToScene(self.mapFromGlobal(QCursor.pos()))
        # for member_id, member in self.parent.members_in_view.items():
        #     if member.contains(mouse_scene_position):
        #         return True
        # return False
        mouse_scene_position = self.mapToScene(self.mapFromGlobal(QCursor.pos()))
        for member_id, member in self.parent.members_in_view.items():
            # We need to map the scene position to the member's local coordinates
            member_local_pos = member.mapFromScene(mouse_scene_position)
            if member.contains(member_local_pos):
                return True
        return False

    def mousePressEvent(self, event):
        # todo
        if self.parent.new_agent:
            self.parent.add_entity()
            return

        # Check if the mouse is over a member and want to drag it, and not activate panning
        if self.mouse_is_over_member():
            self._is_panning = False
        else:
            # Otherwise, continue with the original behavior
            if event.button() == Qt.LeftButton:
                self._mouse_press_pos = event.pos()
                self._is_panning = True

        # if event.button() == Qt.LeftButton and not self.mouse_is_over_member():
        #     self._mouse_press_pos = event.pos()
        #     self._is_panning = True
        #     # self.setCursor(Qt.ClosedHandCursor)

        mouse_scene_position = self.mapToScene(event.pos())
        for member_id, member in self.parent.members_in_view.items():
            if isinstance(member, DraggableMember):
                if self.parent.new_line:
                    input_point_pos = member.input_point.scenePos()
                    # if within 20px
                    if (mouse_scene_position - input_point_pos).manhattanLength() <= 20:
                        self.parent.add_input(member_id)
                        return
                else:
                    output_point_pos = member.output_point.scenePos()
                    output_point_pos.setX(output_point_pos.x() + 8)
                    # if within 20px
                    if (mouse_scene_position - output_point_pos).manhattanLength() <= 20:
                        self.parent.new_line = ConnectionLine(self.parent, member)
                        self.parent.scene.addItem(self.parent.new_line)
                        return

        # If click anywhere else, cancel the new line
        if self.parent.new_line:
            self.scene().removeItem(self.parent.new_line)
            self.parent.new_line = None

        super(CustomGraphicsView, self).mousePressEvent(event)

    # def mouseReleaseEvent(self, event):
    #     if event.button() == Qt.LeftButton:
    #         self._is_panning = False
    #         # self.setCursor(Qt.ArrowCursor)

    def mouseMoveEvent(self, event):
        # if self._is_panning:
        #     # Delta
        #     delta = event.pos() - self._mouse_press_pos
        #     self._mouse_press_pos = event.pos()
        #
        #     # Scroll by delta
        #     self.horizontalScrollBar().setValue(self.horizontalScrollBar().value() - delta.x())
        #     self.verticalScrollBar().setValue(self.verticalScrollBar().value() - delta.y())
        #     return

        update = False
        mouse_point = self.mapToScene(event.pos())
        if self.parent.new_line:
            self.parent.new_line.updateEndPoint(mouse_point)
            update = True
        if self.parent.new_agent:
            self.parent.new_agent.setCentredPos(mouse_point)
            update = True

        if update:
            if self.scene():
                self.scene().update()
            self.update()

        super(CustomGraphicsView, self).mouseMoveEvent(event)

    def cancel_new_line(self):
        # Remove the temporary line from the scene and delete it
        self.scene().removeItem(self.parent.new_line)
        self.parent.new_line = None
        self.update()

    def cancel_new_entity(self):
        # Remove the new entity from the scene and delete it
        self.scene().removeItem(self.parent.new_agent)
        self.parent.new_agent = None
        self.update()

    def delete_selected_items(self):
        del_member_ids = set()
        del_inputs = set()
        all_del_objects = []
        all_del_objects_old_brushes = []
        all_del_objects_old_pens = []

        for selected_item in self.parent.scene.selectedItems():
            all_del_objects.append(selected_item)

            if isinstance(selected_item, DraggableMember):
                del_member_ids.add(selected_item.id)

                # Loop through all lines to find the ones connected to the selected agent
                for key, line in self.parent.lines.items():
                    member_id, input_member_id = key
                    if member_id == selected_item.id or input_member_id == selected_item.id:
                        del_inputs.add((member_id, input_member_id))
                        all_del_objects.append(line)

            elif isinstance(selected_item, ConnectionLine):
                del_inputs.add((selected_item.member_id, selected_item.input_member_id))

                # # Loop through all members to find the one connected to the selected line
                # for member_id, member in self.parent.members_in_view.items():
                #     if member_id in (selected_item.member_id, selected_item.input_member_id):
                #         del_member_ids.add(member_id)
                #         all_del_objects.append(member)

        del_count = len(del_member_ids) + len(del_inputs)
        if del_count == 0:
            return

        # fill all objects with a red tint at 30% opacity, overlaying the current item image
        for item in all_del_objects:
            old_brush = item.brush()
            all_del_objects_old_brushes.append(old_brush)
            # modify old brush and add a 30% opacity red fill
            old_pixmap = old_brush.texture()
            new_pixmap = old_pixmap.copy()
            painter = QPainter(new_pixmap)
            painter.setCompositionMode(QPainter.CompositionMode_SourceAtop)

            painter.fillRect(new_pixmap.rect(),
                             QColor(255, 0, 0, 126))
            painter.end()
            new_brush = QBrush(new_pixmap)
            item.setBrush(new_brush)

            old_pen = item.pen()
            all_del_objects_old_pens.append(old_pen)
            new_pen = QPen(QColor(255, 0, 0, 255),
                           old_pen.width())
            item.setPen(new_pen)

        self.parent.scene.update()

        # ask for confirmation
        retval = display_messagebox(
            icon=QMessageBox.Warning,
            text="Are you sure you want to delete the selected items?",
            title="Delete Items",
            buttons=QMessageBox.Ok | QMessageBox.Cancel,
        )
        if retval == QMessageBox.Ok:
            for obj in all_del_objects:
                self.parent.scene.removeItem(obj)

            for member_id in del_member_ids:
                self.parent.members_in_view.pop(member_id)
            for line_key in del_inputs:
                self.parent.lines.pop(line_key)

            self.parent.save_config()
            if not self.parent.compact_mode:
                self.parent.parent.load()
        else:
            for item in all_del_objects:
                item.setBrush(all_del_objects_old_brushes.pop(0))
                item.setPen(all_del_objects_old_pens.pop(0))

    def keyPressEvent(self, event):
        if event.key() == Qt.Key_Escape:  # todo - refactor
            if self.parent.new_line:
                self.cancel_new_line()
            if self.parent.new_agent:
                self.cancel_new_entity()

        elif event.key() == Qt.Key_Delete:
            if self.parent.new_line:
                self.cancel_new_line()
                return
            if self.parent.new_agent:
                self.cancel_new_entity()
                return

            self.delete_selected_items()
        else:
            super(CustomGraphicsView, self).keyPressEvent(event)


# class FixedUserBubble(QGraphicsEllipseItem):
#     def __init__(self, parent):
#         super(FixedUserBubble, self).__init__(0, 0, 50, 50)
#         from src.gui.style import TEXT_COLOR
#         self.id = 0
#         self.parent = parent
#
#         self.setPos(-42, 75)
#
#         # set border color
#         self.setPen(QPen(QColor(TEXT_COLOR), 1))
#
#         pixmap = colorize_pixmap(QPixmap(":/resources/icon-user.png"))
#         self.setBrush(QBrush(pixmap.scaled(50, 50, Qt.KeepAspectRatio, Qt.SmoothTransformation)))
#
#         self.output_point = ConnectionPoint(self, False)
#         self.output_point.setPos(self.rect().width() - 4, self.rect().height() / 2)
#
#         self.setAcceptHoverEvents(True)
#
#     def hoverMoveEvent(self, event):
#         # Check if the mouse is within 20 pixels of the output point
#         if self.output_point.contains(event.pos() - self.output_point.pos()):
#             self.output_point.setHighlighted(True)
#         else:
#             self.output_point.setHighlighted(False)
#         super(FixedUserBubble, self).hoverMoveEvent(event)
#
#     def hoverLeaveEvent(self, event):
#         self.output_point.setHighlighted(False)
#         super(FixedUserBubble, self).hoverLeaveEvent(event)


class InsertableMember(QGraphicsEllipseItem):
    def __init__(self, parent, agent_id, icon, config, pos):
        super(InsertableMember, self).__init__(0, 0, 50, 50)
        from src.gui.style import TEXT_COLOR
        self.parent = parent
        self.id = agent_id
        self.config = config
        member_type = config.get('_TYPE', 'agent')
        def_avatar = None
        pen = QPen(QColor(TEXT_COLOR), 1)

        if member_type == 'workflow':
            pen = None
        elif member_type == 'user':
            def_avatar = ':/resources/icon-user.png'
        elif member_type == 'tool':
            def_avatar = ':/resources/icon-tool.png'
            pen = None

        if pen:
            # set border color
            self.setPen(pen)
        if isinstance(icon, QPixmap):
            pixmap = icon
        else:
            pixmap = path_to_pixmap(icon, diameter=50, def_avatar=def_avatar)
        self.setBrush(QBrush(pixmap.scaled(50, 50)))
        self.setCentredPos(pos)

    def setCentredPos(self, pos):
        self.setPos(pos.x() - self.rect().width() / 2, pos.y() - self.rect().height() / 2)


class DraggableMember(QGraphicsEllipseItem):
    def __init__(self, parent, member_id, loc_x, loc_y, member_config):
        super(DraggableMember, self).__init__(0, 0, 50, 50)
        from src.gui.style import TEXT_COLOR

        self.parent = parent
        self.id = member_id
        self.member_type = member_config.get('_TYPE', 'agent')
        self.member_config = member_config
        def_avatar = None
        avatars = ''

        pen = QPen(QColor(TEXT_COLOR), 1)

        if self.member_type == 'agent':
            avatars = member_config.get('info.avatar_path', '')
        elif self.member_type == 'workflow':
            pen = None
            avatars = [member['config'].get('info.avatar_path', '') for member in member_config.get('members', [])]
        elif self.member_type == 'user':
            def_avatar = ':/resources/icon-user.png'
        elif self.member_type == 'tool':
            def_avatar = ':/resources/icon-tool.png'
            pen = None

        # # member_type = member_config.get('_TYPE', 'agent')
        # elif self.member_type == 'workflow':
        #     pass
        # elif self.member_type == 'user':
        #     def_avatar = ':/resources/icon-user.png'
        # elif self.member_type == 'tool':
        #     def_avatar = ':/resources/icon-tool.png'
        # else:
        #     def_avatar = None
        if pen:
            # set border color
            self.setPen(QPen(QColor(TEXT_COLOR), 1))

        # if member_type_str:
        #     member_inp_str = '0' if member_inp_str == 'NULL' else member_inp_str  # todo dirty
        # self.member_inputs = dict(
        #     zip([int(x) for x in member_inp_str.split(',')],
        #         member_type_str.split(','))) if member_type_str else {}

        self.setPos(loc_x, loc_y)

        # # agent_config = json.loads(agent_config)
        # # member_type = member_config.get('_TYPE', 'agent')
        # elif self.member_type == 'workflow':
        # else:
        hide_responses = member_config.get('group.hide_responses', False)
        opacity = 0.2 if hide_responses else 1
        diameter = 50
        pixmap = path_to_pixmap(avatars, opacity=opacity, diameter=diameter, def_avatar=def_avatar)

        self.setBrush(QBrush(pixmap.scaled(diameter, diameter)))

        self.setFlag(QGraphicsItem.ItemIsMovable)
        self.setFlag(QGraphicsItem.ItemIsSelectable)

        self.input_point = ConnectionPoint(self, True)
        self.output_point = ConnectionPoint(self, False)
        self.input_point.setPos(0, self.rect().height() / 2)
        self.output_point.setPos(self.rect().width() - 4, self.rect().height() / 2)

        self.setAcceptHoverEvents(True)

        # Create the highlight background item
        self.highlight_background = self.HighlightBackground(self)
        self.highlight_background.setPos(self.rect().width()/2, self.rect().height()/2)
        self.highlight_background.hide()  # Initially hidden

        # self.highlight_states = {
        #     'responding': '#0bde2b',
        #     'waiting': '#f7f7f7',
        # }

    def toggle_highlight(self, enable, color=None):
        """Toggles the visual highlight on or off."""
        if enable:
            self.highlight_background.use_color = color
            self.highlight_background.show()
        else:
            self.highlight_background.hide()

    def mouseReleaseEvent(self, event):
        super(DraggableMember, self).mouseReleaseEvent(event)
        new_loc_x = self.x()
        new_loc_y = self.y()
        # current_members_info = self.parent.config.get('members', [])
        # current_loc_x =
        self.parent.update_member([
            (self.id, 'loc_x', new_loc_x),
            (self.id, 'loc_y', new_loc_y)
        ])

    def mouseMoveEvent(self, event):
        if self.output_point.contains(event.pos() - self.output_point.pos()):
            return

        if self.parent.new_line:
            return

        # if mouse not inside scene, return
        cursor = event.scenePos()
        if not self.parent.view.rect().contains(cursor.toPoint()):
            return

        super(DraggableMember, self).mouseMoveEvent(event)
        for line in self.parent.lines.values():
            line.updatePosition()

    def hoverMoveEvent(self, event):
        # Check if the mouse is within 20 pixels of the output point
        if self.output_point.contains(event.pos() - self.output_point.pos()):
            self.output_point.setHighlighted(True)
        else:
            self.output_point.setHighlighted(False)
        super(DraggableMember, self).hoverMoveEvent(event)

    def hoverLeaveEvent(self, event):
        self.output_point.setHighlighted(False)
        super(DraggableMember, self).hoverLeaveEvent(event)

    class HighlightBackground(QGraphicsItem):
        def __init__(self, parent=None):
            super().__init__(parent)
            self.outer_diameter = 100  # Diameter including the gradient
            self.inner_diameter = 50  # Diameter of the hole, same as the DraggableMember's ellipse
            self.use_color = None  # Uses text color when none

        def boundingRect(self):
            return QRectF(-self.outer_diameter / 2, -self.outer_diameter / 2, self.outer_diameter, self.outer_diameter)

        def paint(self, painter, option, widget=None):
            from src.gui.style import TEXT_COLOR
            gradient = QRadialGradient(QPointF(0, 0), self.outer_diameter / 2)
            # text_color_ = QColor(TEXT_COLOR)
            color = self.use_color or QColor(TEXT_COLOR)

            gradient.setColorAt(0, color)  # Inner color of gradient
            gradient.setColorAt(1, QColor(255, 255, 0, 0))  # Outer color of gradient

            # Create a path for the outer ellipse (gradient)
            outer_path = QPainterPath()
            outer_path.addEllipse(-self.outer_diameter / 2, -self.outer_diameter / 2, self.outer_diameter,
                                  self.outer_diameter)

            # Create a path for the inner hole
            inner_path = QPainterPath()
            inner_path.addEllipse(-self.inner_diameter / 2, -self.inner_diameter / 2, self.inner_diameter,
                                  self.inner_diameter)

            # Subtract the inner hole from the outer path
            final_path = QPainterPath(outer_path)
            final_path = final_path.subtracted(inner_path)

            painter.setBrush(QBrush(gradient))
            painter.setPen(Qt.NoPen)  # No border
            painter.drawPath(final_path)


# class TemporaryConnectionLine(QGraphicsPathItem):
#     def __init__(self, parent, agent):
#         super(TemporaryConnectionLine, self).__init__()
#         from src.gui.style import TEXT_COLOR
#         self.parent = parent
#         self.input_member_id = agent.id
#         self.output_point = agent.output_point
#         self.setPen(QPen(QColor(TEXT_COLOR), 2, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin))
#         self.temp_end_point = self.output_point.scenePos()
#         self.updatePath()
#
#     def updatePath(self):
#         output_pos = self.output_point.scenePos()
#         end_pos = self.temp_end_point
#         x_distance = (end_pos - output_pos).x()  # Assuming horizontal distance matters
#         y_distance = abs((end_pos - output_pos).y())  # Assuming horizontal distance matters
#
#         # Set control points offsets to be a fraction of the horizontal distance
#         fraction = 0.61  # Adjust the fraction as needed (e.g., 0.2 for 20%)
#         offset = x_distance * fraction
#         if offset < 0:
#             offset *= 3
#             offset = min(offset, -40)
#         else:
#             offset = max(offset, 40)
#             offset = min(offset, y_distance)
#         offset = abs(offset)  # max(abs(offset), 10)
#
#         path = QPainterPath(output_pos)
#         ctrl_point1 = output_pos + QPointF(offset, 0)
#         ctrl_point2 = end_pos - QPointF(offset, 0)
#         path.cubicTo(ctrl_point1, ctrl_point2, end_pos)
#         self.setPath(path)
#
#     def updateEndPoint(self, end_point):
#         self.temp_end_point = end_point
#         self.updatePath()
#
#     def attach_to_member(self, member_id):
#         self.parent.add_input(self.input_member_id, member_id)


class ConnectionLine(QGraphicsPathItem):
    def __init__(self, parent, input_member, member=None, input_type=0):  # key, start_point, end_point=None, input_type=0):
        super(ConnectionLine, self).__init__()
        from src.gui.style import TEXT_COLOR
        self.parent = parent
        self.input_member_id = input_member.id
        self.member_id = member.id if member else None
        self.start_point = input_member.output_point
        self.end_point = member.input_point if member else None
        self.input_type = int(input_type)

        self.setAcceptHoverEvents(True)
        self.setFlag(QGraphicsItem.ItemIsSelectable)
        self.color = QColor(TEXT_COLOR)

        self.updatePath()

        self.setPen(QPen(self.color, 2, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin))
        self.setZValue(-1)

    def paint(self, painter, option, widget):
        line_width = 4 if self.isSelected() else 2
        current_pen = self.pen()
        current_pen.setWidth(line_width)
        # set to a dashed line if input type is 1
        if self.input_type == 1:
            current_pen.setStyle(Qt.DashLine)
        painter.setPen(current_pen)
        painter.drawPath(self.path())

    def updateEndPoint(self, end_point):
        self.end_point = end_point
        self.updatePath()

    def updatePosition(self):
        self.updatePath()
        self.scene().update(self.scene().sceneRect())

    def updatePath(self):
        if self.end_point is None:
            return
        start_point = self.start_point.scenePos() if isinstance(self.start_point, ConnectionPoint) else self.start_point
        end_point = self.end_point.scenePos() if isinstance(self.end_point, ConnectionPoint) else self.end_point

        x_distance = (end_point - start_point).x()
        y_distance = abs((end_point - start_point).y())

        # Set control points offsets to be a fraction of the horizontal distance
        fraction = 0.61  # Adjust the fraction as needed (e.g., 0.2 for 20%)
        offset = x_distance * fraction
        if offset < 0:
            offset *= 3
            offset = min(offset, -40)
        else:
            offset = max(offset, 40)
            offset = min(offset, y_distance)
        offset = abs(offset)  # max(abs(offset), 10)

        path = QPainterPath(start_point)
        ctrl_point1 = start_point + QPointF(offset, 0)
        ctrl_point2 = end_point - QPointF(offset, 0)
        path.cubicTo(ctrl_point1, ctrl_point2, end_point)
        self.setPath(path)

    # def attach_to_member(self, member_id):
    #     self.parent.add_input(self.input_member_id, member_id)

    # def updatePath(self):
    #     path = QPainterPath(self.start_point.scenePos())
    #     ctrl_point1 = self.start_point.scenePos() + QPointF(50, 0)
    #     ctrl_point2 = self.end_point.scenePos() - QPointF(50, 0)
    #     path.cubicTo(ctrl_point1, ctrl_point2, self.end_point.scenePos())
    #     self.setPath(path)


class ConnectionPoint(QGraphicsEllipseItem):
    def __init__(self, parent, is_input):
        radius = 2
        super(ConnectionPoint, self).__init__(0, 0, 2 * radius, 2 * radius, parent)
        self.is_input = is_input
        self.setBrush(QBrush(Qt.darkGray if is_input else Qt.darkRed))
        self.connections = []

    def setHighlighted(self, highlighted):
        if highlighted:
            self.setBrush(QBrush(Qt.red))
        else:
            self.setBrush(QBrush(Qt.black))

    def contains(self, point):
        distance = (point - self.rect().center()).manhattanLength()
        return distance <= 12


# class TemporaryConnectionLine(QGraphicsPathItem):
#     def __init__(self, parent, agent):
#         super(TemporaryConnectionLine, self).__init__()
#         self.parent = parent
#         self.input_member_id = agent.id
#         self.output_point = agent.output_point
#         self.setPen(QPen(QColor(TEXT_COLOR), 2, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin))
#         self.temp_end_point = self.output_point.scenePos()
#         self.updatePath()
#
#     def updatePath(self):
#         path = QPainterPath(self.output_point.scenePos())
#         ctrl_point1 = self.output_point.scenePos() + QPointF(50, 0)
#         ctrl_point2 = self.temp_end_point - QPointF(50, 0)
#         path.cubicTo(ctrl_point1, ctrl_point2, self.temp_end_point)
#         self.setPath(path)
#
#     def updateEndPoint(self, end_point):
#         self.temp_end_point = end_point
#         self.updatePath()
#
#     def attach_to_member(self, member_id):
#         self.parent.add_input(self.input_member_id, member_id)


class MemberList(QWidget):
    """This widget displays a list of members in the chat."""
    def __init__(self, parent):
        super().__init__(parent)
        self.parent = parent

        self.layout = CVBoxLayout(self)

        self.tree_members = BaseTreeWidget(self, row_height=15)
        self.schema = [
            {
                'text': 'Members',
                'type': str,
                'width': 150,
                'image_key': 'avatar',
            },
            {
                'key': 'id',
                'text': '',
                'type': int,
                'visible': False,
            },
            {
                'key': 'avatar',
                'text': '',
                'type': str,
                'visible': False,
            },
        ]
        self.tree_members.build_columns_from_schema(self.schema)
        # self.tree_members.setColumnCount(1)
        # self.tree_members.setHeaderLabels(['Members'])
        self.tree_members.setFixedWidth(150)

        # self.member_list.setFixedHeight(150)
        # self.member_list.setSpacing(5)
        # self.member_list.itemDoubleClicked.connect(self.on_member_double_clicked)
        self.layout.addWidget(self.tree_members)

        # self.member_list.setContextMenuPolicy(Qt.CustomContextMenu)
        # self.member_list.customContextMenuRequested.connect(self.on_context_menu)

    def load(self):
        def_avatars = {
            'User': ':/resources/icon-user.png',
            'Agent': ':/resources/icon-agent-solid.png',
            'Tool': ':/resources/icon-tool.png',
        }
        def_names = {
            'User': 'You',
            'Agent': 'Assistant',
            'Tool': 'Tool',
        }

        data = [
            [
                m.config.get('info.name') or def_names.get(m.__class__.__name__, ''),
                m_id,
                m.config.get('info.avatar_path') or def_avatars.get(m.__class__.__name__, ''),
            ]
            for m_id, m in self.parent.parent.workflow.members.items()
        ]  # todo - clean this mess
        self.tree_members.load(
            data=data,
            folders_data=[],
            schema=self.schema,
            readonly=True,
        )


class DynamicMemberConfigWidget(QWidget):
    def __init__(self, parent):
        super().__init__()
        self.parent = parent
        self.stacked_layout = QStackedLayout()

        self.current_member_id = None
        self.agent_config = self.AgentMemberSettings(parent)
        self.user_config = self.UserMemberSettings(parent)
        self.workflow_config = None  # self.WorkflowMemberSettings(parent)
        # self.human_config = HumanConfig()

        self.stacked_layout.addWidget(self.agent_config)
        self.stacked_layout.addWidget(self.user_config)
        # self.stacked_layout.addWidget(self.workflow_config)
        # # self.stacked_layout.addWidget(self.workflow_config)
        # # self.stacked_layout.addWidget(self.human_config)
        # # self.stacked_layout.setCurrentWidget(self.agent_config)

        self.setLayout(self.stacked_layout)

    def load(self, temp_only_config=False):
        if self.current_member_id is None:
            return
        if self.current_member_id not in self.parent.members_in_view:
            self.current_member_id = None  # todo
            return
        member = self.parent.members_in_view[self.current_member_id]
        self.display_config_for_member(member, temp_only_config)

    def display_config_for_member(self, member, temp_only_config=False):
        # Logic to switch between configurations based on member type
        self.current_member_id = member.id
        member_type = member.member_type
        member_config = member.member_config

        if member_type == "agent":
            self.stacked_layout.setCurrentWidget(self.agent_config)
            self.agent_config.member_id = member.id
            self.agent_config.load_config(member_config)
            if not temp_only_config:
                self.agent_config.load()
        elif member_type == "user":
            self.stacked_layout.setCurrentWidget(self.user_config)
            self.user_config.member_id = member.id
            self.user_config.load_config(member_config)
            if not temp_only_config:
                self.user_config.load()
        else:
            if self.workflow_config is None:
                self.workflow_config = self.WorkflowMemberSettings(self.parent)
                self.stacked_layout.addWidget(self.workflow_config)
            self.stacked_layout.setCurrentWidget(self.workflow_config)
            self.workflow_config.member_id = member.id
            self.workflow_config.load_config(member_config)
            if not temp_only_config:
                self.workflow_config.load()

    class AgentMemberSettings(AgentSettings):
        def __init__(self, parent):
            super().__init__(parent)
            self.member_id = None

        def update_config(self):
            self.save_config()

        def save_config(self):
            conf = self.get_config()
            self.parent.members_in_view[self.member_id].member_config = conf
            self.parent.save_config()

    class UserMemberSettings(UserSettings):
        def __init__(self, parent):
            super().__init__(parent)
            self.member_id = None

        def update_config(self):
            self.save_config()

        def save_config(self):
            conf = self.get_config()
            self.parent.members_in_view[self.member_id].member_config = conf
            self.parent.save_config()

    class WorkflowMemberSettings(WorkflowSettings):
        def __init__(self, parent):
            super().__init__(parent)

        def load(self):
            pass

        def update_config(self):
            pass

        def save_config(self):
            pass


# Welcome to the tutorial! Here, we will walk you through a number of key concepts in Agent Pilot,
# starting with the basics and then moving on to more advanced features.

# -- BASICS --
# Agent pilot can be used as a user interface for over N llm providers and M models.
# Let's start by adding our API keys in the settings.
# Click on the settings icon at the top of the sidebar, then click on the API's tab.
# Here, you'll see a list of all the APIs that are currently available, with a field to enter its API key.
# Selecting an API will list all the models available from it.
# And selecting a model will list all the parameters available for that model.
# Agent pilot uses litellm for llm api calls, the model name `here` is sent with the API call,
# prefixed with `litellm_prefix` here, if supplied.
# Once you've added your API key, head back to the chat page by clicking the chat icon here.
# When on the chat page, it's icon will change to a + button, clicking this will create a new chat with the same config
# To open the config for the chat, click this area at the top.
# Here you can change the config for the assistant, go to the `Chat` tab and set its LLM model here.
# Try chatting with the assistant
# You can go back to previous messages and edit them, when we edit this message and resubmit, a branch is created
# You can cycle between these branches with these buttons
# To start a new chat, click this `+` button.
# The history of all your chats is saved in the Chats page here.
# Clicking on a chat will open it back up so that you can continue or refer back to it.
# You can quickly cycle between chats by using these navigation buttons
# Let's say you like this assistant configuration, you've set an LLM and a system prompt,
# but you want a different assistant for a different purpose, you can click here to save the assistant
# Type a name, and your agent will be saved in the entities page, go there by clicking here
# Selecting an agent will open its config, this is not tied to any chat, this config will be the
# default config for when the agent is used in a workflow. Unless this `+` button is clicked,
# in which case the config will be copied from this workflow.
# Start a new chat with an agent by double clicking on it.

# -- MULTI AGENT --
# Now that's the basics out of the way, lets go over how multi agent workflows work.
# In the chat page, open the workflow config.
# Click the new button, you'll be prompted to select an Agent, User or Tool,
# Click on Agent and select one from the list, then drop it anywhere on the workflow
# This is a basic group chat with you and 2 other agents
# An important thing to note is that the order of response flows from left to right,
# so in this workflow, after you send a message, this agent will always respond first, followed by this agent.
# That is, unless an input is placed from this agent to this one, in this case,
# because the input of this one flows into this, this agent will respond first.
# Click on the member list button here to show the list of members, in the order they will respond.
# You should almost always have a user member at the beginning, this represents you.
# There can be multiple user members, so you can add your input at any point within a workflow

# Let's go over the context window of each agent, if the agent has no predefined inputs,
# then it can see all other agent messages, even the ones after it from previous turns
# But if an agent has inputs set like this one, then that agent will only see messages from the agents
# flowing into it.
# In this case this agent will output a response based on the direct output of this agent.
# The LLM will see this agents response in the form of a `user` LLM message.
# If an agent has multiple inputs, you can decide how to handle this in the agent config `group` tab
# You can use the output of an agent in the context window of another, using its output placeholder
# wrapped in curly braces, like this.

# -- TOOLS --
# Now that you know how to setup multi agent workflows, let's go over tools.
# Tools are a way to add custom functionality to your agents, that the LLM can decide to call.
# Go to the settings page, and go to Tools
# Here you can see a list of tools, you can create a new tool by clicking the `+` button
# Give it a name, and a description, these are used by the LLM to help decide when to call it.
# In this method dropdown, you can select the method the LLM will use to call the tool.
# This can be a function call or Prompt based.
# To use function calling you have to use an LLM that supports it,
# For prompt based you can use any LLM, but it may not be as reliable.
# In this Code tab, you can write the code for the tool,
# depending on which type is selected in this dropdown, the code will be treated differently.
# The Native option wraps the code in a predefined function that's integrated into agent pilot.
# this function can be a generator, meaning ActionResponses can be 'yielded' aswell as 'returned',
# allowing the tool logic to continue sequentially from where it left off, after each user message.
# In the Parameters tab, you can define the parameters of the tool,
# These can be used from within the code using their names.
# Tools can be used by agents by adding them to their config, in the tools tab here.
# You can also use tools independently in a workflow by adding a tool member like this.
# Then you can use its output from another agents context using its name wrapped in curly braces.



# -- FILES --
# Files
# You can attach files to the chat, click here to upload a file, you can upload multiple files at once.

#  to get you comfortable with the interface.
#
# 1. We will then introduce the concept of branching, which allows you to explore different conversation paths.
# 2. Next, we will delve into chat settings. Here, you will learn how to customize your chat environment.
# 3. You will learn about the new button, which allows you to create new chat instances.
# 4. We will then add two more agents to the chat to demonstrate multi-agent interactions.
# 5. The loc_x order will be explained. This is crucial for understanding the flow of the conversation.
# 6. Next, we will introduce context windows, which give you a snapshot of the conversation at any given point.
# 7. We will then add an input in the opposite direction to demonstrate bidirectional communication.
# 8. We will explain the significance of order and context in the chat environment.
# 9. You will learn how to manage multiple inputs and outputs in the conversation.
# 10. The concept of output placeholders will be introduced.
# 11. You will learn how to save a conversation as an entity for future reference.
# 12. We will show you the agent list where all the agents in the conversation are listed.
# 13. We will open a workflow entity to demonstrate how it can be manipulated.
# 14. You will learn how to incorporate a workflow entity into your workflow.
# 15. We will delve into the settings of the chat environment.
# 16. We will explain agent configuration, including chat, preload, group, files and tools.
# 17. We will open the settings to show you how they can be customized.
# 18. The concept of blocks will be introduced.
# 19. Sandboxes will be explained. These are environments where you can test your conversations.
# 20. You will learn about the tools available for managing your chat environment.
# 21. Finally, we will explain the display and role display settings.
#
# We hope this tutorial helps you understand and utilize the chat environment to its full extent!
#
# Start with basic llm chat
#
# Show branching
#
# Show chats
#
# Show chat settings and explain
#
# Explain new button
#
# Add 2 other agents
#
# Explain loc_x order
#
# Explain context windows
#
# Add an input opposite dir
#
# Explain order & context
#
# Explain multiple inputs/outputs
#
# Explain output placeholders
#
# Save as entity
#
# Show agent list
#
# Open workflow entity
#
# Add workflow entity into workflow
#
# Show settings
#
# Explain agent config
#
#   Chat, preload, group
#
#   Files
#
#   Tools
#
# Open settings
#
# Explain blocks
#
# Explain sandboxes
#
# Explain tools
#
# Explain display and role display