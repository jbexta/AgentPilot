import asyncio
import json

from src.gui.windows.workspace import WorkspaceWindow
from src.members.tool import Tool
from src.members.user import User, UserSettings
from src.utils import sql
from src.members.base import Member
from src.utils.messages import MessageHistory
from src.members.agent import Agent

import sqlite3
from abc import abstractmethod
from functools import partial

from PySide6.QtCore import QPointF, QRectF
from PySide6.QtGui import Qt, QPen, QColor, QBrush, QPainter, QPainterPath, QCursor, QRadialGradient
from PySide6.QtWidgets import QWidget, QGraphicsScene, QGraphicsEllipseItem, QGraphicsItem, QGraphicsView, \
    QMessageBox, QGraphicsPathItem, QStackedLayout, QMenu, QInputDialog, QGraphicsWidget, \
    QSizePolicy, QApplication

from src.gui.config import ConfigWidget, CVBoxLayout, CHBoxLayout, ConfigFields, ConfigPlugin, IconButtonCollection, \
    ConfigTool

from src.gui.widgets import IconButton, ToggleButton, find_main_widget, ListDialog, BaseTreeWidget
from src.utils.helpers import path_to_pixmap, display_messagebox, get_avatar_paths_from_config, \
    merge_config_into_workflow_config

loop = asyncio.new_event_loop()
asyncio.set_event_loop(loop)


# Helper function to load behavior module dynamically todo - move to utils
def load_behaviour_module(group_key):
    from src.system.plugins import ALL_PLUGINS
    try:
        # Dynamically import the context behavior plugin based on group_key
        return ALL_PLUGINS['Workflow'].get(group_key)
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
        self._parent_workflow = kwargs.get('workflow', None)
        self.system = self.main.system
        self.member_type = 'workflow'

        self.loop = asyncio.get_event_loop()
        self.responding = False
        self.stop_requested = False

        self.members = {}  # id: member
        self.boxes = []  # list of lists of member ids

        self.autorun = True
        self.behaviour = None

        self.config = kwargs.get('config', {})

        # Load base workflow
        if not self._parent_workflow:
            self._id = kwargs.get('context_id', None)
            self._chat_name = ''
            self._chat_title = ''
            self._leaf_id = self.id
            self._message_history = MessageHistory(self)

        self.load()

        # else:
        #     # Load nested workflow
        #     self.update_behaviour()

    @property
    def id(self):
        return self.get_from_root('_id')

    @property
    def chat_name(self):
        return self.get_from_root('_chat_name')

    @property
    def chat_title(self):
        return self.get_from_root('_chat_title')

    @property
    def leaf_id(self):
        return self.get_from_root('_leaf_id')

    @property
    def message_history(self):
        return self.get_from_root('_message_history')

    @id.setter
    def id(self, value):
        self._id = value

    @chat_name.setter
    def chat_name(self, value):
        self._chat_name = value

    @chat_title.setter
    def chat_title(self, value):
        self._chat_title = value

    @leaf_id.setter
    def leaf_id(self, value):
        self._leaf_id = value

    @message_history.setter
    def message_history(self, value):
        self._message_history = value

    def get_from_root(self, attr_name):
        if hasattr(self, attr_name):
            return getattr(self, attr_name, None)
        return self._parent_workflow.get_from_root(attr_name)
        # parent = self._parent_workflow
        # while parent:
        #     if parent._parent_workflow is None:
        #         break
        #     parent = parent._parent_workflow
        # return getattr(parent, attr_name, None)

    def load(self):
        if not self._parent_workflow:
            # Load base workflow
            if self.id is not None:
                config_str = sql.get_scalar("SELECT config FROM contexts WHERE id = ?", (self.id,))
                if config_str is None:
                    raise Exception("43723")  # todo clean
                self.config = json.loads(config_str) or {}

        workflow_config = self.config.get('config', {})
        self.autorun = workflow_config.get('autorun', True)
        self.load_members()

        if not self._parent_workflow:
            # Load base workflow
            self.message_history.load()
            self.chat_title = sql.get_scalar("SELECT name FROM contexts WHERE id = ?", (self.id,))

    def load_members(self):
        from src.system.plugins import get_plugin_class
        # Get members and inputs from the loaded json config
        if self.config.get('_TYPE', 'agent') == 'workflow':
            members = self.config['members']
        else:  # is a single entity, this allows single entity to be in workflow config for simplicity
            wf_config = merge_config_into_workflow_config(self.config)
            members = wf_config.get('members', [])
        inputs = self.config.get('inputs', [])

        last_member_id = None
        last_loc_x = -100
        current_box_member_ids = set()

        members = sorted(members, key=lambda x: x['loc_x'])

        self.members = {}
        self.boxes = []
        iterable = iter(members)
        while len(members) > 0:
            try:
                member_dict = next(iterable)
            except StopIteration:  # todo temp make nicer
                iterable = iter(members)
                continue

            # if member_dict.get('del', False):
            #     continue

            member_id = member_dict['id']
            entity_id = member_dict['agent_id']
            member_config = member_dict['config']
            loc_x = member_dict.get('loc_x', 50)
            loc_y = member_dict.get('loc_y', 0)
            # pos = QPointF(loc_x, loc_y)
            member_input_ids = [
                input_info['input_member_id']
                for input_info in inputs if input_info['member_id'] == member_id
            ]

            # Order based on the inputs
            if len(member_input_ids) > 0:
                if not all((inp_id in self.members) for inp_id in member_input_ids):
                    continue

            # Instantiate the member
            member_type = member_dict.get('config', {}).get('_TYPE', 'agent')
            kwargs = dict(main=self.main,
                          workflow=self,
                          member_id=member_id,
                          config=member_config,
                          agent_id=entity_id,
                          loc_x=loc_x,
                          loc_y=loc_y,
                          inputs=member_input_ids)
            if member_type == 'agent':
                use_plugin = member_config.get('info.use_plugin', None)
                member = get_plugin_class('Agent', use_plugin, kwargs) or Agent(**kwargs)
            elif member_type == 'workflow':
                member = Workflow(**kwargs)
            elif member_type == 'user':
                member = User(**kwargs)
            elif member_type == 'tool':
                member = Tool(**kwargs)
            else:
                raise NotImplementedError(f"Member type '{member_type}' not implemented")

            member.load()

            if abs(loc_x - last_loc_x) < 10:  # Assuming they are close enough to be considered in the same group
                if last_member_id is not None:
                    current_box_member_ids |= {last_member_id}
                current_box_member_ids |= {member_id}

            else:
                if current_box_member_ids:
                    self.boxes.append(current_box_member_ids)
                    current_box_member_ids = set()

            last_loc_x = loc_x
            last_member_id = member_id

            self.members[member_id] = member
            members.remove(member_dict)
            iterable = iter(members)

        if current_box_member_ids:
            self.boxes.append(current_box_member_ids)

        counted_members = self.get_members()
        if len(counted_members) == 1:
            self.chat_name = next(iter(counted_members)).config.get('info.name', 'Assistant')
        else:
            self.chat_name = f'{len(counted_members)} members'

        self.update_behaviour()

    def get_members(self, incl_types=('agent', 'workflow')):
        matched_members = [m for m in self.members.values() if m.config.get('_TYPE', 'agent') in incl_types]
        return matched_members

    def count_members(self, incl_types=('agent', 'workflow')):
        extra_user_count = max(len(self.get_members(incl_types=('user',))) - 1, 0)
        matched_members = self.get_members(incl_types=incl_types)
        return len(matched_members) + extra_user_count

    def next_expected_member(self, _id=False):
        """Returns the next member where turn output is None"""
        next_member = next((member for member in self.members.values()
                     if member.turn_output is None),
                    None)
        if _id:
            return next_member.member_id if next_member else None

        return next_member

    def get_member_async_group(self, member_id):
        for box in self.boxes:
            if member_id in box:
                return box
        return None

    def get_member_config(self, member_id):
        member = self.members.get(member_id)
        return member.config if member else {}

    def update_behaviour(self):
        """Update the behaviour of the context based on the common key"""
        common_group_key = get_common_group_key(self.members)
        behaviour_module = load_behaviour_module(common_group_key)
        self.behaviour = behaviour_module(self) if behaviour_module else WorkflowBehaviour(self)

    async def run_member(self):
        """The entry response method for the member."""
        await self.behaviour.start()

    def save_message(self, role, content, member_id=1, log_obj=None):
        """Saves a message to the database and returns the message_id"""
        if role == 'output':
            content = 'The code executed without any output' if content.strip() == '' else content

        if content == '':
            return None

        new_run = None not in [member.turn_output for member in self.members.values()]
        if new_run:
            self.message_history.alt_turn_state = 1 - self.message_history.alt_turn_state

        return self.message_history.add(role, content, member_id=member_id, log_obj=log_obj)
        # ^ calls message_history.load_messages after

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
        self.tasks = []

    async def start(self, from_member_id=None):
        # tasks = []
        found_source = False  # todo clean this
        pause_on = ('user', 'contact')
        processed_members = set()

        def create_async_group_task(member_ids):
            """ Helper function to create and return a coroutine that runs all members in the member_async_group """
            async def run_group():
                group_tasks = []
                for member_id in member_ids:
                    if member_id not in processed_members:
                        m = self.workflow.members[member_id]
                        sub_task = asyncio.create_task(m.run_member())
                        group_tasks.append(sub_task)
                        processed_members.add(member_id)
                await asyncio.gather(*group_tasks)

            return run_group

        self.workflow.responding = True
        try:
            for member in self.workflow.members.values():
                if member.member_id == from_member_id or from_member_id is None:
                    found_source = True
                if not found_source:
                    continue
                if member.member_id in processed_members:
                    continue

                member_async_group = self.workflow.get_member_async_group(member.member_id)
                if member_async_group:
                    # Create a single coroutine to handle the entire member async group
                    run_method = create_async_group_task(member_async_group)
                    await run_method()

                else:
                    # Run individual member
                    member.response_task = asyncio.create_task(member.run_member())  # self.run_member(member) # self.workflow.loop.create_task()
                    processed_members.add(member.member_id)
                    await asyncio.gather(*[member.response_task])

                # tasks.append(member.response_task)

                if not self.workflow.autorun:
                    break
                if member.config.get('_TYPE', 'agent') in pause_on and member.member_id != from_member_id:
                    break
        except asyncio.CancelledError:
            pass  # task was cancelled, so we ignore the exception
        except Exception as e:
            # self.main.finished_signal.emit()
            raise e
        finally:
            self.workflow.responding = False

    def stop(self):
        self.workflow.stop_requested = True
        for member in self.workflow.members.values():
            if member.response_task is not None:
                member.response_task.cancel()


class WorkflowSettings(ConfigWidget):
    def __init__(self, parent, **kwargs):
        super().__init__(parent)
        self.main = find_main_widget(self)
        self.compact_mode = kwargs.get('compact_mode', False)  # For use in agent page
        self.compact_mode_editing = False

        self.members_in_view = {}  # id: member
        self.lines = {}  # (member_id, inp_member_id): line
        self.boxes_in_view = {}  # list of lists of member ids

        self.new_line = None
        self.new_agent = None

        self.autorun = True

        self.layout = CVBoxLayout(self)
        self.workflow_buttons = WorkflowButtons(parent=self)

        self.scene = QGraphicsScene(self)
        self.scene.setSceneRect(0, 0, 625, 200)

        self.view = CustomGraphicsView(self.scene, self)

        self.view.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.view.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        # self.view.setFixedSize(625, 200) #!!#

        self.compact_mode_back_button = self.CompactModeBackButton(parent=self)
        self.member_config_widget = DynamicMemberConfigWidget(parent=self)
        self.member_config_widget.hide()

        h_container = QWidget()
        h_layout = CHBoxLayout(h_container)
        h_layout.addWidget(self.view)

        if not self.compact_mode:
            self.member_list = MemberList(parent=self)
            h_layout.addWidget(self.member_list)
            self.member_list.tree_members.itemSelectionChanged.connect(self.on_member_list_selection_changed)
            self.member_list.hide()

        self.workflow_config = WorkflowConfig(parent=self)
        h_layout.addWidget(self.workflow_config)
        self.workflow_config.hide()

        self.scene.selectionChanged.connect(self.on_selection_changed)

        self.layout.addWidget(self.compact_mode_back_button)
        self.layout.addWidget(self.workflow_buttons)
        self.layout.addWidget(h_container)
        self.layout.addWidget(self.member_config_widget)
        self.layout.addStretch(1)

    class CompactModeBackButton(QWidget):
        def __init__(self, parent):
            super().__init__(parent)
            self.parent = parent
            self.layout = CHBoxLayout(self)
            self.btn_back = IconButton(
                parent=self,
                icon_path=':/resources/icon-cross.png',
                tooltip='Back',
                size=22,
                text='Close edit mode',
            )
            self.btn_back.clicked.connect(partial(self.parent.set_edit_mode, False))

            self.layout.addWidget(self.btn_back)
            self.layout.addStretch(1)
            self.hide()

    def set_edit_mode(self, state):
        if not self.compact_mode:
            return

        self.compact_mode_editing = state
        if hasattr(self.parent, 'tree_config'):
            self.parent.tree_config.tree.setVisible(not state)
            self.parent.tree_config.tree_buttons.setVisible(not state)
        elif hasattr(self.parent, 'view'):
            self.parent.view.setVisible(not state)
            self.parent.member_config_widget.updateGeometry()
            # self.setFixedHeight(200 if state else 400)
        self.compact_mode_back_button.setVisible(state)

        if state is False:
            self.select_ids([])

    def load_config(self, json_config=None):
        if isinstance(json_config, str):
            json_config = json.loads(json_config)
        if json_config.get('_TYPE', 'agent') != 'workflow':  # todo maybe change
            json_config = json.dumps({
                '_TYPE': 'workflow',
                'members': [
                    {'id': 1, 'agent_id': None, 'loc_x': -10, 'loc_y': 64, 'config': {'_TYPE': 'user'}, 'del': 0},
                    {'id': 2, 'agent_id': 0, 'loc_x': 37, 'loc_y': 30, 'config': json_config, 'del': 0}
                ],
                'inputs': [],
            })
        super().load_config(json_config)
        self.workflow_config.load_config(json_config)

    def get_config(self):
        user_members = [m for m in self.members_in_view.values() if m.member_type == 'user']
        agent_members = [m for m in self.members_in_view.values() if m.member_type in ('agent', 'workflow')]
        if len(user_members) == 1 and len(agent_members) == 1:
            return agent_members[0].member_config

        workflow_config = self.workflow_config.get_config()
        workflow_config['autorun'] = not self.workflow_buttons.btn_disable_autorun.isChecked()
        config = {
            '_TYPE': 'workflow',
            'members': [],
            'inputs': [],
            'config': workflow_config,
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
                'config': line.config,
            })

        return config

    @abstractmethod
    def save_config(self):
        pass

    def update_member(self, update_list, save=False):
        for member_id, attribute, value in update_list:
            member = self.members_in_view.get(member_id)
            if not member:
                return
            setattr(member, attribute, value)

        if save:
            self.save_config()

    def load(self):
        self.load_members()
        self.load_inputs()
        self.load_async_groups()
        self.member_config_widget.load()
        self.workflow_buttons.load()
        self.workflow_config.load()

        if hasattr(self, 'member_list'):
            self.member_list.load()

        if not self.compact_mode:
            self.refresh_member_highlights()

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
            # agent_id = member_info.get('agent_id')
            member_config = member_info.get('config')
            loc_x = member_info.get('loc_x')
            loc_y = member_info.get('loc_y')

            member = DraggableMember(self, id, loc_x, loc_y, member_config)
            self.scene.addItem(member)
            self.members_in_view[id] = member

        # count members but minus one for the user member
        member_count = self.count_other_members()

        if member_count == 1:  # and not self.compact_mode:
            # Select the member so that it's config is shown, then hide the workflow panel until more members are added
            other_member_ids = [k for k, m in self.members_in_view.items() if m.id != 1]  # .member_type != 'user']

            if other_member_ids:
                self.select_ids([other_member_ids[0]])
            self.view.hide()
            # if self.workflow_buttons.
        else:
            # Show the workflow panel in case it was hidden
            self.view.show()
            # # Select the members that were selected before, patch for deselecting members todo
            if not self.compact_mode:
                self.select_ids(sel_member_ids)

    def load_async_groups(self):
        # Clear any existing members from the scene
        for box in self.boxes_in_view:
            self.scene.removeItem(box)
        self.boxes_in_view = []

        last_member_pos = None
        last_loc_x = -100
        current_box_member_positions = []

        members = self.members_in_view.values()
        members = sorted(members, key=lambda m: m.x())

        for member in members:
            loc_x = member.x()
            loc_y = member.y()
            pos = QPointF(loc_x, loc_y)

            if abs(loc_x - last_loc_x) < 10:
                current_box_member_positions += [last_member_pos, pos]
            else:
                if current_box_member_positions:
                    box = RoundedRectWidget(self, points=current_box_member_positions)
                    self.scene.addItem(box)
                    self.boxes_in_view.append(box)
                    current_box_member_positions = []

            last_loc_x = loc_x
            last_member_pos = pos

        # Handle the last group after finishing the loop
        if current_box_member_positions:
            box = RoundedRectWidget(self, points=current_box_member_positions)
            self.scene.addItem(box)
            self.boxes_in_view.append(box)

    def count_other_members(self):
        # count members but minus one for the user member
        member_count = len(self.members_in_view)
        if any(m.member_type == 'user' for m in self.members_in_view.values()):
            member_count -= 1
        return member_count

    def load_inputs(self):
        for _, line in self.lines.items():
            self.scene.removeItem(line)
        self.lines = {}

        inputs_data = self.config.get('inputs', [])
        for input_dict in inputs_data:
            member_id = input_dict['member_id']
            input_member_id = input_dict['input_member_id']
            input_config = input_dict.get('config', {})

            input_member = self.members_in_view.get(input_member_id)
            member = self.members_in_view.get(member_id)

            if input_member is None:  # todo temp
                return
            line = ConnectionLine(self, input_member, member, input_config)
            self.scene.addItem(line)
            self.lines[(member_id, input_member_id)] = line

    def select_ids(self, ids):
        for item in self.scene.selectedItems():
            item.setSelected(False)

        for _id in ids:
            if _id in self.members_in_view:
                self.members_in_view[_id].setSelected(True)

    def on_selection_changed(self):
        selected_objects = self.scene.selectedItems()
        selected_agents = [x for x in selected_objects if isinstance(x, DraggableMember)]
        selected_lines = [x for x in selected_objects if isinstance(x, ConnectionLine)]

        # with block_signals(self.group_topbar): # todo
        if len(selected_objects) == 1:
            if len(selected_agents) == 1:
                member = selected_agents[0]
                self.member_config_widget.display_config_for_member(member)
                self.member_config_widget.show()
            elif len(selected_lines) == 1:
                line = selected_lines[0]
                self.member_config_widget.display_config_for_input(line)
                self.member_config_widget.show()

        else:
            self.member_config_widget.hide()

        member_count = self.count_other_members()
        if self.compact_mode and member_count != 1 and len(selected_objects) > 0:
            self.set_edit_mode(True)

    def on_member_list_selection_changed(self):
        selected_member_ids = [self.member_list.tree_members.get_selected_item_id()]
        self.select_ids(selected_member_ids)

    def add_insertable_entity(self, item):
        self.view.show()
        mouse_scene_point = self.view.mapToScene(self.view.mapFromGlobal(QCursor.pos()))
        item = item.data(Qt.UserRole)
        entity_id = item['id']
        entity_avatar = (item['avatar'] or '').split('//##//##//')
        entity_config = json.loads(item['config'])
        self.new_agent = InsertableMember(self, entity_id, entity_avatar, entity_config, mouse_scene_point)
        self.scene.addItem(self.new_agent)
        self.view.setFocus()

    def add_entity(self):
        member_id = max(self.members_in_view.keys()) + 1 if len(self.members_in_view) else 1
        entity_config = self.new_agent.config
        loc_x, loc_y = self.new_agent.x(), self.new_agent.y()
        member = DraggableMember(self, member_id, loc_x, loc_y, entity_config)
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
        line = ConnectionLine(self, input_member, member, {'input_type': 'Message'})
        self.scene.addItem(line)
        self.lines[(member_id, input_member_id)] = line

        self.scene.removeItem(self.new_line)
        self.new_line = None

        self.save_config()
        if not self.compact_mode:
            self.parent.load()

    def check_for_circular_references(self, member_id, input_member_ids):
        """ Recursive function to check for circular references"""
        connected_input_members = [g[1] for g in self.lines.keys() if g[0] in input_member_ids]
        if member_id in connected_input_members:
            return True
        if len(connected_input_members) == 0:
            return False
        return self.check_for_circular_references(member_id, connected_input_members)

    def refresh_member_highlights(self):
        if self.compact_mode:
            return
        for member in self.members_in_view.values():
            member.highlight_background.hide()

        next_expected_member = self.parent.workflow.next_expected_member()
        if not next_expected_member:
            return

        next_expected_member_id = next_expected_member.member_id
        if next_expected_member_id in self.members_in_view:
            self.members_in_view[next_expected_member_id].highlight_background.show()


class WorkflowButtons(IconButtonCollection):
    def __init__(self, parent):
        super().__init__(parent=parent)
        self.layout.addSpacing(15)

        self.btn_add = IconButton(
            parent=self,
            icon_path=':/resources/icon-new.png',
            tooltip='Add',
            size=self.icon_size,
        )
        self.btn_save_as = IconButton(
            parent=self,
            icon_path=':/resources/icon-save.png',
            tooltip='Save As',
            size=self.icon_size,
        )
        self.btn_clear_chat = IconButton(
            parent=self,
            icon_path=':/resources/icon-clear.png',
            tooltip='Clear Chat',
            size=self.icon_size,
        )
        # self.btn_pull = IconButton(
        #     parent=self,
        #     icon_path=':/resources/icon-pull.png',
        #     tooltip='Set member config to agent default',
        #     size=self.icon_size,
        # )
        # self.btn_push = IconButton(
        #     parent=self,
        #     icon_path=':/resources/icon-push.png',
        #     tooltip='Set all member configs to agent default',
        #     size=self.icon_size,
        # )
        self.btn_toggle_hidden_messages = ToggleButton(
            parent=self,
            icon_path=':/resources/icon-eye-cross.png',
            icon_path_checked=':/resources/icon-eye.png',
            tooltip='Show hidden agent messages',
            tooltip_when_checked='Hide hidden agent messages',
            size=self.icon_size,
        )

        self.layout.addWidget(self.btn_add)
        self.layout.addWidget(self.btn_save_as)
        # self.layout.addWidget(self.btn_pull)
        # self.layout.addWidget(self.btn_push)
        self.layout.addWidget(self.btn_clear_chat)
        self.layout.addWidget(self.btn_toggle_hidden_messages)

        self.layout.addStretch(1)

        self.btn_disable_autorun = ToggleButton(
            parent=self,
            icon_path=':/resources/icon-run-solid.png',
            icon_path_checked=':/resources/icon-run.png',
            tooltip='Disable autorun',
            tooltip_when_checked='Enable autorun',
            size=self.icon_size,
        )
        self.btn_member_list = ToggleButton(
            parent=self,
            icon_path=':/resources/icon-agent-solid.png',
            tooltip='View member list',
            icon_size_percent=0.9,
            size=self.icon_size,
        )
        self.btn_workflow_config = ToggleButton(
            parent=self,
            icon_path=':/resources/icon-settings-solid.png',
            tooltip='Workflow config',
            size=self.icon_size,
        )
        # self.btn_workspace = IconButton(
        #     parent=self,
        #     icon_path=':/resources/icon-workspace.png',
        #     tooltip='Open workspace',
        #     size=18,
        # )
        self.layout.addWidget(self.btn_disable_autorun)
        self.layout.addWidget(self.btn_member_list)
        self.layout.addWidget(self.btn_workflow_config)
        # self.layout.addWidget(self.btn_workspace)

        self.btn_add.clicked.connect(self.show_context_menu)
        self.btn_save_as.clicked.connect(self.save_as)
        self.btn_clear_chat.clicked.connect(self.clear_chat)
        self.btn_toggle_hidden_messages.clicked.connect(self.toggle_hidden_messages)
        self.btn_disable_autorun.clicked.connect(self.parent.save_config)
        self.btn_workflow_config.clicked.connect(self.toggle_workflow_config)

        if parent.compact_mode:
            self.btn_save_as.hide()
            self.btn_clear_chat.hide()
            # self.btn_pull.hide()
            self.btn_member_list.hide()
            # self.btn_workspace.hide()
            self.btn_toggle_hidden_messages.hide()
            self.btn_disable_autorun.hide()
            self.btn_workflow_config.hide()
        else:
            # self.btn_push.hide()
            self.btn_member_list.clicked.connect(self.toggle_member_list)
            # self.btn_workspace.clicked.connect(self.open_workspace)

    def load(self):
        workflow_config = self.parent.config.get('config', {})
        autorun = workflow_config.get('autorun', True)
        self.btn_disable_autorun.setChecked(not autorun)

        is_multi_member = self.parent.count_other_members() > 1

        self.btn_workflow_config.setVisible(is_multi_member)
        if not is_multi_member:
            self.parent.workflow_config.setVisible(False)

        if not self.parent.compact_mode:
            self.btn_disable_autorun.setVisible(is_multi_member)
            self.btn_member_list.setVisible(is_multi_member)
            # if self.
            if not is_multi_member:
                if self.btn_member_list.isChecked():
                    self.btn_member_list.click()
                if self.btn_workflow_config.isChecked():
                    self.btn_workflow_config.click()

    def open_workspace(self):
        page_chat = self.parent.main.page_chat
        if page_chat.workspace_window is None:  # Check if the secondary window is not already open
            page_chat.workspace_window = WorkspaceWindow(page_chat)
            page_chat.workspace_window.setAttribute(
                Qt.WA_DeleteOnClose)  # Ensure the secondary window is deleted when closed
            page_chat.workspace_window.destroyed.connect(self.on_secondary_window_closed)  # Handle window close event
            page_chat.workspace_window.show()
        else:
            page_chat.workspace_window.raise_()
            page_chat.workspace_window.activateWindow()

    def on_secondary_window_closed(self):
        page_chat = self.parent.main.page_chat
        page_chat.workspace_window = None  # Reset the reference when the secondary window is closed

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
        self.parent.set_edit_mode(True)
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
            text="Are you sure you want to permanently clear the chat messages?\nThis should only be used when testing a workflow.\nTo keep your data start a new chat.",
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

        self.parent.main.page_chat.load()

    def toggle_member_list(self):
        if self.btn_workflow_config.isChecked():
            self.btn_workflow_config.setChecked(False)
            self.parent.workflow_config.setVisible(False)
        is_checked = self.btn_member_list.isChecked()
        self.parent.member_list.setVisible(is_checked)

    def toggle_workflow_config(self):
        if self.btn_member_list.isChecked():
            self.btn_member_list.setChecked(False)
            self.parent.member_list.setVisible(False)
        is_checked = self.btn_workflow_config.isChecked()
        self.parent.workflow_config.setVisible(is_checked)

    def toggle_hidden_messages(self):
        state = self.btn_toggle_hidden_messages.isChecked()
        self.parent.main.page_chat.toggle_hidden_messages(state)


class MemberList(QWidget):
    """This widget displays a list of members in the chat."""
    def __init__(self, parent):
        super().__init__(parent)
        self.parent = parent

        self.layout = CVBoxLayout(self)
        self.layout.setContentsMargins(0, 5, 0, 0)

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
        self.tree_members.setFixedWidth(150)
        self.layout.addWidget(self.tree_members)
        self.layout.addStretch(1)

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
        # set height to fit all items & header
        height = self.tree_members.sizeHintForRow(0) * (len(data) + 1)
        self.tree_members.setFixedHeight(height)


class WorkflowConfig(ConfigPlugin):
    def __init__(self, parent):
        super().__init__(
            parent,
            plugin_type='WorkflowConfig',
            plugin_json_key='behavior',
            plugin_label_text='Behavior:',
            none_text='Native'
        )
        self.setFixedWidth(175)
        self.default_class = self.Native_WorkflowConfig

    class Native_WorkflowConfig(ConfigFields):
        def __init__(self, parent):
            super().__init__(parent=parent)
            self.parent = parent
            self.schema = []

    def load_config(self, json_config=None):
        if json_config is not None:
            if isinstance(json_config, str):
                json_config = json.loads(json_config)
            self.config = json_config if json_config else {}
            # self.load()
        else:
            parent_config = getattr(self.parent, 'config', {})

            if self.conf_namespace is None:
                self.config = parent_config
            else:
                self.config = {k: v for k, v in parent_config.items() if k.startswith(f'{self.conf_namespace}.')}

        self.config = self.config.get('config', {})
        if self.config_widget:
            self.config_widget.load_config()


class DynamicMemberConfigWidget(ConfigWidget):
    def __init__(self, parent):
        super().__init__(parent=parent)
        from src.system.plugins import get_plugin_agent_settings
        self.parent = parent
        self.stacked_layout = QStackedLayout(self)
        self.setFixedHeight(200)

        self.agent_config = get_plugin_agent_settings(None)(parent)
        self.user_config = self.UserMemberSettings(parent)
        self.workflow_config = None  # self.WorkflowMemberSettings(parent)
        self.tool_config = self.ToolMemberSettings(parent)
        self.input_config = self.InputSettings(parent)

        self.agent_config.build_schema()

        self.stacked_layout.addWidget(self.agent_config)
        self.stacked_layout.addWidget(self.user_config)
        self.stacked_layout.addWidget(self.tool_config)
        self.stacked_layout.addWidget(self.input_config)

        # self.stacked_layout.currentChanged.connect(self.on_widget_changed)

    def load(self, temp_only_config=False):
        pass

    def display_config_for_member(self, member, temp_only_config=False):
        from src.system.plugins import get_plugin_agent_settings
        # Logic to switch between configurations based on member type
        member_type = member.member_type
        member_config = member.member_config

        if member_type == "agent":
            agent_plugin = member_config.get('info.use_plugin', '')
            if agent_plugin == '':
                agent_plugin = None

            current_plugin = getattr(self.agent_config, '_plugin_name', '')
            is_different = agent_plugin != current_plugin

            if is_different:
                old_widget = self.agent_config
                agent_settings_class = get_plugin_agent_settings(agent_plugin)
                self.agent_config = agent_settings_class(self.parent)
                self.agent_config.build_schema()

                self.stacked_layout.addWidget(self.agent_config)
                self.stacked_layout.setCurrentWidget(self.agent_config)

                self.stacked_layout.removeWidget(old_widget)
                old_widget.deleteLater()

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
        elif member_type == "workflow":
            if self.workflow_config is None:
                self.workflow_config = self.WorkflowMemberSettings(self.parent)
                self.stacked_layout.addWidget(self.workflow_config)
            self.stacked_layout.setCurrentWidget(self.workflow_config)
            self.workflow_config.member_id = member.id
            self.workflow_config.load_config(member_config)
            if not temp_only_config:
                self.workflow_config.load()
        elif member_type == "tool":
            self.stacked_layout.setCurrentWidget(self.tool_config)
            self.tool_config.member_id = member.id
            self.tool_config.load_config(member_config)
            if not temp_only_config:
                self.tool_config.load()

        self.refresh_geometry()

    def display_config_for_input(self, line):  # member_id, input_member_id):
        member_id, input_member_id = line.member_id, line.input_member_id
        # self.current_input_key = (member_id, input_member_id)
        self.stacked_layout.setCurrentWidget(self.input_config)
        self.input_config.input_key = (member_id, input_member_id)
        self.input_config.load_config(line.config)
        self.input_config.load()

        self.refresh_geometry()

    def refresh_geometry(self):
        widget = self.stacked_layout.currentWidget()
        if widget:
            # Adjust the stacked layout's size to match the current widget
            size = widget.sizeHint()
            self.setFixedHeight(size.height())

    class UserMemberSettings(UserSettings):
        def __init__(self, parent):
            super().__init__(parent)
            self.build_schema()

        def update_config(self):
            self.save_config()

        def save_config(self):
            conf = self.get_config()
            self.parent.members_in_view[self.member_id].member_config = conf
            self.parent.save_config()

    class WorkflowMemberSettings(WorkflowSettings):
        def __init__(self, parent):
            super().__init__(parent, compact_mode=True)

        def update_config(self):
            self.save_config()

        def save_config(self):
            conf = self.get_config()
            self.parent.members_in_view[self.member_id].member_config = conf
            self.parent.save_config()

    class ToolMemberSettings(ConfigTool):
        def __init__(self, parent):
            super().__init__(parent)
            # self.build_schema()

        def update_config(self):
            pass
            # self.save_config()

        def save_config(self):
            pass
            # conf = self.get_config()
            # self.parent.members_in_view[self.member_id].member_config = conf
            # self.parent.save_config()

    class InputSettings(ConfigFields):
        def __init__(self, parent):
            super().__init__(parent)
            self.input_key = None
            self.schema = [
                {
                    'text': 'Input Type',
                    'type': ('Message', 'Context'),
                    'default': 'Message',
                },
            ]
            self.build_schema()

        def save_config(self):
            conf = self.get_config()
            self.parent.lines[self.input_key].config = conf
            self.parent.save_config()


class CustomGraphicsView(QGraphicsView):
    def __init__(self, scene, parent):
        super(CustomGraphicsView, self).__init__(scene, parent)
        self.setMouseTracking(True)
        self.setRenderHint(QPainter.Antialiasing)
        self.parent = parent

        self._is_panning = False
        self._mouse_press_pos = None

        self.setHorizontalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)

    # def contextMenuEvent(self, event):
    #
    #     menu = QMenu(self)
    #
    #     selected_items = self.parent.scene.selectedItems()
    #     if selected_items:
    #         # menu.addAction("Cut")
    #         menu.addAction("Copy")
    #     menu.addAction("Paste")
    #
    #     if selected_items:
    #         menu.addAction("Delete")
    #
    #     # Show the menu and get the chosen action
    #     chosen_action = menu.exec(event.globalPos())
    #
    #     if chosen_action:
    #         if chosen_action.text() == "Copy":
    #
    #         if chosen_action.text() == "Delete":
    #             self.delete_selected_items()
    #
    #     # if chosen_action == delete_action:
    #     #     for item in selected_items:
    #     #         self.scene.removeItem(item)
    #     # elif chosen_action:
    #     #     # Handle other actions
    #     #     print(f"Action: {chosen_action.text()} for {len(selected_items)} items")
    #
    # def copy_selected_items(self):
    #     member_configs = []
    #     for selected_item in self.scene().selectedItems():
    #         if isinstance(selected_item, DraggableMember):
    #             member_configs.append(selected_item.member_config)
    #     # add to clipboard
    #     clipboard = QApplication.clipboard()
    #     clipboard.setText(json.dumps(member_configs))
    #
    # def paste_items(self):
    #     clipboard = QApplication.clipboard()
    #     try:
    #         member_configs = json.loads(clipboard.text())
    #         if not isinstance(member_configs, list):
    #             return
    #         if not all(isinstance(x, dict) for x in member_configs):
    #             return
    #         for member_config in member_configs:
    #             self.parent.add_entity(member_config)
    #     except Exception as e:
    #         return

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

        member_count = self.parent.count_other_members()  # todo merge duplicate code
        if member_count == 1:  # and not self.compact_mode:
            # Select the member so that it's config is shown, then hide the workflow panel until more members are added
            other_member_ids = [k for k, m in self.parent.members_in_view.items() if m.id != 1]  # .member_type != 'user']
            if other_member_ids:
                self.parent.select_ids([other_member_ids[0]])
            self.parent.view.hide()

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
        if retval != QMessageBox.Ok:
            for item in all_del_objects:
                item.setBrush(all_del_objects_old_brushes.pop(0))
                item.setPen(all_del_objects_old_pens.pop(0))
            return

        for obj in all_del_objects:
            self.parent.scene.removeItem(obj)

        for member_id in del_member_ids:
            self.parent.members_in_view.pop(member_id)
        for line_key in del_inputs:
            self.parent.lines.pop(line_key)

        self.parent.save_config()
        if not self.parent.compact_mode:
            self.parent.parent.load()

    def mouse_is_over_member(self):
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

        if event.button() == Qt.RightButton:
            # Get the item at the clicked position
            item = self.itemAt(event.pos())
            if item:
                if not item.isSelected():
                    # Clear previous selection
                    for selected_item in self.scene().selectedItems():
                        selected_item.setSelected(False)
                    # Select the clicked item
                    item.setSelected(True)
            else:
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

    def mouseMoveEvent(self, event):
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

    def keyPressEvent(self, event):
        if event.key() == Qt.Key_Escape:
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


class InsertableMember(QGraphicsEllipseItem):
    def __init__(self, parent, agent_id, icon, config, pos):
        super(InsertableMember, self).__init__(0, 0, 50, 50)
        from src.gui.style import TEXT_COLOR

        self.parent = parent
        self.id = agent_id
        member_type = config.get('_TYPE', 'agent')
        self.config = config

        pen = QPen(QColor(TEXT_COLOR), 1)

        type_avatars = {
            'user': ':/resources/icon-user.png',
            'agent': ':/resources/icon-agent-solid.png',
            'tool': ':/resources/icon-tool.png',
        }

        if member_type in ['workflow', 'tool']:
            pen = None
        self.setPen(pen if pen else Qt.NoPen)

        diameter = 50
        pixmap = path_to_pixmap(icon, diameter=diameter, def_avatar=type_avatars.get(member_type, ''))

        self.setBrush(QBrush(pixmap.scaled(diameter, diameter)))
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

        pen = QPen(QColor(TEXT_COLOR), 1)

        if self.member_type in ['workflow', 'tool']:
            pen = None

        self.setPen(pen if pen else Qt.NoPen)

        self.setPos(loc_x, loc_y)

        self.refresh_avatar()

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

    def refresh_avatar(self):
        hide_bubbles = self.member_config.get('group.hide_bubbles', False)
        opacity = 0.2 if hide_bubbles else 1
        avatar_paths = get_avatar_paths_from_config(self.member_config)

        diameter = 50
        pixmap = path_to_pixmap(avatar_paths, opacity=opacity, diameter=diameter)  # , def_avatar=def_avatar)

        self.setBrush(QBrush(pixmap.scaled(diameter, diameter)))

    def toggle_highlight(self, enable, color=None):
        """Toggles the visual highlight on or off."""
        if enable:
            self.highlight_background.use_color = color
            self.highlight_background.show()
        else:
            self.highlight_background.hide()

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
        self.parent.load_async_groups()

        self.parent.refresh_member_highlights()

    def mouseReleaseEvent(self, event):
        super(DraggableMember, self).mouseReleaseEvent(event)
        new_loc_x = self.x()
        new_loc_y = self.y()
        self.parent.update_member([
            (self.id, 'loc_x', new_loc_x),
            (self.id, 'loc_y', new_loc_y)
        ])
        self.parent.save_config()

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
            self.outer_diameter = 80  # Diameter including the gradient
            self.inner_diameter = 50  # Diameter of the hole, same as the DraggableMember's ellipse
            self.use_color = None  # Uses text color when none

        def boundingRect(self):
            return QRectF(-self.outer_diameter / 2, -self.outer_diameter / 2, self.outer_diameter, self.outer_diameter)

        def paint(self, painter, option, widget=None):
            from src.gui.style import TEXT_COLOR
            gradient = QRadialGradient(QPointF(0, 0), self.outer_diameter / 2)
            # text_color_ = QColor(TEXT_COLOR)
            color = self.use_color or QColor(TEXT_COLOR)
            color.setAlpha(155)
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


class ConnectionLine(QGraphicsPathItem):
    def __init__(self, parent, input_member, member=None, config=None):  # input_type=0):  # key, start_point, end_point=None, input_type=0):
        super(ConnectionLine, self).__init__()
        from src.gui.style import TEXT_COLOR
        self.parent = parent
        self.input_member_id = input_member.id
        self.member_id = member.id if member else None
        self.start_point = input_member.output_point
        self.end_point = member.input_point if member else None

        self.config = config if config else {}
        # self.input_type = self.config.get('input_type', 'Message')

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
        input_type = self.config.get('input_type', 'Message')
        # set to a dashed line if input type is 1
        if input_type == 'Message':
            current_pen.setStyle(Qt.SolidLine)
        elif input_type == 'Context':
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


class RoundedRectWidget(QGraphicsWidget):
    def __init__(self, parent, points, rounding_radius=25):
        super().__init__()
        self.parent = parent
        self.rounding_radius = rounding_radius
        self.setZValue(-2)

        # points is a list of QPointF points, all must be within the bounds
        lowest_x = min([point.x() for point in points])
        lowest_y = min([point.y() for point in points])
        btm_left = QPointF(lowest_x, lowest_y)

        highest_x = max([point.x() for point in points])
        highest_y = max([point.y() for point in points])
        top_right = QPointF(highest_x, highest_y)

        # Calculate width and height from l_bound and u_bound
        width = abs(btm_left.x() - top_right.x()) + 50
        height = abs(btm_left.y() - top_right.y()) + 50

        # Set size policy and preferred size
        self.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)
        self.setPreferredSize(width, height)

        # Set the position based on the l_bound
        self.setPos(btm_left)

    def boundingRect(self):
        return QRectF(0, 0, self.preferredWidth(), self.preferredHeight())

    def paint(self, painter, option, widget):
        from src.gui.style import TEXT_COLOR
        rect = self.boundingRect()
        painter.setRenderHint(QPainter.Antialiasing)

        # Set brush with 20% opacity color
        color = QColor(TEXT_COLOR)
        color.setAlpha(50)
        painter.setBrush(QBrush(color))

        painter.setPen(Qt.NoPen)
        painter.drawRoundedRect(rect, self.rounding_radius, self.rounding_radius)


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
# By selecting an input, you can set which type of input to use,
# Message will send the output to the agent as user role,
# so it's like the agent is having a conversation with this agent
# A context input will not send as a message,
# but allows the agent output to be used in the context window of the next agents.
# You can do this using its output placeholder defined here,
# and use it in the system message of this agent using curly braces like this.
# Agents that are aligned vertically will run asynchronously, indicated by this highlighted bar.
#
# Lets use all of this in practice to create a simple mixture of agents workflow.
# These 2 agents can run asynchronously, and their only input is the user input.
# Set their models and output placeholders here.
# Add a new agent to use as the final agent, place it here and set its model.
# In the system message, we can use a prompt to combine the outputs of the previous agents,
# using their output placeholders, as defined here.
# Finally you can hide the bubbles for these agents by setting Hide bubbles to true here.
# Let's try chatting with this workflow.
# Those asynchronous agents should be working behind the scenes and the final agent should respond with a combined output.
# You can toggle the hidden bubbles by clicking this toggle icon here in the workflow settings.
# You can save the workflow as a single entity by clicking this save button, enter a name and click enter.
# Now any time you want to use this workflow just select it from the entities page.

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