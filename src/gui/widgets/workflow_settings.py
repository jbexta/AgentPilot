
import json
import math
import sqlite3
import uuid
from functools import partial
from typing import Optional, Dict, Tuple, List, Any

from typing_extensions import override

from src.gui.widgets.input_settings import InputSettings
from src.utils import sql

from PySide6.QtCore import QPointF, QRectF, QPoint, Signal, QSize
from PySide6.QtGui import Qt, QPen, QColor, QBrush, QPainter, QPainterPath, QCursor, QRadialGradient, \
    QPainterPathStroker, QLinearGradient, QAction, QFont, QWheelEvent
from PySide6.QtWidgets import *

from src.gui.widgets.config_widget import ConfigWidget
from src.gui.widgets.config_fields import ConfigFields
from src.gui.widgets.config_json_tree import ConfigJsonTree
from src.gui.widgets.config_joined import ConfigJoined

from src.gui.util import IconButton, ToggleIconButton, IconButtonCollection, TreeDialog, CVBoxLayout, CHBoxLayout, \
    BaseTreeWidget, find_main_widget, clear_layout, safe_single_shot, get_selected_pages, set_selected_pages, \
    find_attribute, get_member_settings_class
from src.utils.helpers import path_to_pixmap, display_message_box, get_avatar_paths_from_config, \
    get_member_name_from_config, block_signals, display_message, apply_alpha_to_hex, \
    set_module_type, merge_config_into_workflow_config, merge_multiple_into_workflow_config


class HeaderFields(ConfigFields):
    def __init__(self, parent):
        super().__init__(parent=parent)
        self.setFixedHeight(50)
        is_member_header = self.parent.__class__.__name__ == 'MemberConfigWidget'
        # if is_member_header:
        self.schema = [
            {
                'text': 'Avatar',
                'key': 'avatar_path',
                'type': 'image',
                'diameter': 30 if is_member_header else 40,
                'circular': False,
                'border': False,
                'visibility_predicate': self.should_show,
                'default': '',
                'label_position': None,
                'row_key': 0,
            },
            {
                'text': 'Name',
                'type': str,
                'default': 'Unnamede',
                'stretch_x': True,
                'text_size': 14,
                # 'text_alignment': Qt.AlignCenter,
                'visibility_predicate': self.should_show,
                'label_position': None,
                'transparent': True,
                'row_key': 0,
            },
            # {
            #     'text': '',
            #     'key': 'toggle_description',
            #     'type': 'button_toggle',
            #     # 'checkable': True,
            #     'default': False,
            #     'icon_path': ':/resources/icon-description.png',
            #     'tooltip': 'Toggle description',
            #     'label_position': None,
            #     'row_key': 0,
            # },
        ]
        self.build_schema()

    def should_show(self, _):  # todo clean weird mechanism
        is_member_header = self.parent.__class__.__name__ == 'MemberConfigWidget'
        if is_member_header:
            is_view_visible = self.parent.parent.view.isVisible()
            show = is_view_visible

        else:
            is_chat_workflow = self.parent.__class__.__name__ == 'ChatWorkflowSettings'
            if not is_chat_workflow:
                show = True
            else:
                is_view_visible = self.parent.view.isVisible()
                show = is_view_visible
        self.setVisible(show)
        return show

    # def should_show(self, _):
    #     parent_class_name = self.parent.__class__.__name__
    #     # if parent_class_name == 'ChatWorkflowSettings':
    #     #     show = self.parent.view.isVisible()
    #     if parent_class_name == 'MemberConfigWidget':
    #         show = True
    #     elif parent_class_name == 'ChatWorkflowSettings':
    #         show = self.parent.view.isVisible()
    #     else:
    #         show = True  # Default to True for other parent classes
    #
    #     self.setVisible(show)
    #     return show



@set_module_type('Widgets')
class WorkflowSettings(ConfigWidget):
    def __init__(self, parent, **kwargs):
        super().__init__(parent=parent)
        self.compact_mode: bool = kwargs.get('compact_mode', False)  # For use in agent page
        self.compact_mode_editing: bool = False

        self.setSizePolicy(QSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding))

        self.members_in_view: Dict[str, DraggableMember] = {}
        self.inputs_in_view: Dict[Tuple[str, str], ConnectionLine] = {}  # (source_member_id, target_member_id): line
        # self.boxes_in_view: List[List[RoundedRectWidget]] = []

        self.new_lines: Optional[List[InsertableLine]] = None
        self.new_agents: Optional[List[Tuple[QPointF, DraggableMember]]] = None  # InsertableMember]]] = None
        self.adding_line: Optional[ConnectionLine] = None
        self.del_pairs: Optional[Any] = None

        self.autorun: bool = True

        self.layout = CVBoxLayout(self)

        self.header_widget = HeaderFields(self)
        self.workflow_buttons = self.WorkflowButtons(parent=self)

        self.scene = QGraphicsScene(self)
        self.scene.setSceneRect(0, 0, 2000, 2000)

        self.view = self.CustomGraphicsView(self.scene, self)

        self.compact_mode_back_button = self.CompactModeBackButton(parent=self)
        self.member_config_widget = MemberConfigWidget(parent=self)
        self.member_config_widget.hide()  # 32

        h_layout = CHBoxLayout()
        h_layout.addWidget(self.view)

        enable_member_list = self.linked_workflow() is not None
        if enable_member_list:
            self.member_list = self.MemberList(parent=self)
            h_layout.addWidget(self.member_list)
            self.member_list.hide()

        self.workflow_options = self.WorkflowOptions(parent=self)
        self.workflow_options.build_schema()

        self.workflow_description = self.WorkflowDescription(parent=self)
        self.workflow_description.build_schema()

        self.workflow_params = self.WorkflowParams(parent=self)
        self.workflow_params.build_schema()

        # self.workflow_extras = None  # not added here

        self.scene.selectionChanged.connect(self.on_selection_changed)

        self.workflow_panel = QWidget()
        panel_layout = CVBoxLayout(self.workflow_panel)
        panel_layout.addWidget(self.compact_mode_back_button)
        panel_layout.addWidget(self.header_widget)
        panel_layout.addWidget(self.workflow_params)
        panel_layout.addWidget(self.workflow_description)
        panel_layout.addWidget(self.workflow_options)
        panel_layout.addWidget(self.workflow_buttons)
        panel_layout.addLayout(h_layout)

        self.splitter = QSplitter(Qt.Vertical)
        self.splitter.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.splitter.setChildrenCollapsible(False)

        self.splitter.addWidget(self.workflow_panel)
        self.splitter.addWidget(self.member_config_widget)
        self.layout.addWidget(self.splitter)

    @override
    def load_config(self, json_config=None):
        if json_config is None:
            json_config = {}
        if isinstance(json_config, str):
            json_config = json.loads(json_config)
        # if json_config.get('_TYPE', 'agent') != 'workflow':
        json_config = merge_config_into_workflow_config(json_config)

        json_wf_options = json_config.get('options', {})
        json_wf_params = json_config.get('params', [])
        wf_desc = json_config.get('description', '')
        self.header_widget.load_config(json_config)
        self.workflow_options.load_config(json_wf_options)
        self.workflow_params.load_config({'data': json_wf_params})  # !55! #
        self.workflow_description.load_config({'description': wf_desc})
        super().load_config(json_config)

    @override
    def get_config(self):
        workflow_opts = self.workflow_options.get_config()
        workflow_opts['autorun'] = self.workflow_buttons.autorun
        workflow_opts['show_hidden_bubbles'] = self.workflow_buttons.show_hidden_bubbles
        workflow_opts['show_nested_bubbles'] = self.workflow_buttons.show_nested_bubbles
        # workflow_config['mini_view'] = self.view.mini_view

        workflow_params = self.workflow_params.get_config()

        workflow_desc = self.workflow_description.get_config().get('description', '')
        workflow_header = self.header_widget.get_config()

        config = {
            '_TYPE': 'workflow',
            'name': workflow_header.get('name', 'Workflow'),
            'avatar_path': workflow_header.get('avatar_path', None),
            'description': workflow_desc,
            'members': [],
            'inputs': [],
            'options': workflow_opts,
            'params': workflow_params.get('data', []),
        }

        for member_id, member in self.members_in_view.items():
            # # add _TYPE to member_config
            member.member_config['_TYPE'] = member.member_type
            proxy_size = member.member_proxy.size()

            config['members'].append({
                'id': member_id,
                'linked_id': member.linked_id,
                'loc_x': int(member.x()),
                'loc_y': int(member.y()),
                'width': max(proxy_size.width(), 450),
                'height': max(proxy_size.height(), 350),
                'config': member.member_config,
            })

        for line_key, line in self.inputs_in_view.items():
            source_member_id, target_member_id = line_key

            config['inputs'].append({
                'source_member_id': source_member_id,
                'target_member_id': target_member_id,
                'config': line.config,
            })

        return config

    @override
    def update_config(self):
        # iterate members and ensure all loc_x and loc_y are > 0
        for member in self.members_in_view.values():
            if member.x() < 0 or member.y() < 0:
                member.setPos(max(member.x(), 0), max(member.y(), 0))

        super().update_config()

        # self.load_async_groups()
        for m in self.members_in_view.values():
            m.update_visuals()  # refresh_avatar()
        self.refresh_member_highlights()
        if hasattr(self, 'member_list'):
            self.member_list.load()

    @override
    def load(self):
        self.setUpdatesEnabled(False)
        sel_member_ids = [x.id for x in self.scene.selectedItems()
                          if isinstance(x, DraggableMember)]
        self.load_members()
        self.load_inputs()
        # self.load_async_groups()
        self.member_config_widget.load()
        self.header_widget.load()
        self.workflow_params.load()
        self.workflow_options.load()
        self.workflow_buttons.load()

        if hasattr(self, 'member_list'):
            self.member_list.load()

        if self.can_simplify_view():
            self.toggle_view(False)
            # Select the member so that it's config is shown, then hide the workflow panel until more members are added
            other_member_ids = [k for k, m in self.members_in_view.items() if not m.member_config.get('_TYPE', 'agent') == 'user']

            if other_member_ids:
                self.select_ids([other_member_ids[0]])
        else:
            # Show the workflow panel in case it was hidden
            self.toggle_view(True)  # .view.show()
            # # Select the members that were selected before, patch for deselecting members todo
            if not self.compact_mode:
                self.select_ids(sel_member_ids)

        self.refresh_member_highlights()
        from src.system import manager
        view_type = manager.config.get('display.workflow_view', 'Mini')
        self.view.mini_view = view_type == 'Mini'
        self.view.refresh_mini_view()
        self.setUpdatesEnabled(True)

    def load_members(self):
        # return
        # Clear any existing members from the scene
        for m_id, member in self.members_in_view.items():
            self.scene.removeItem(member)
            # member.deleteLater()
        self.members_in_view = {}

        # return
        members_data = self.config.get('members', [])
        # Iterate over the parsed 'members' data and add them to the scene
        for member_info in members_data:
            _id = member_info['id']
            # agent_id = member_info.get('agent_id')
            linked_id = member_info.get('linked_id', None)
            member_config = member_info.get('config')
            loc_x = member_info.get('loc_x')
            loc_y = member_info.get('loc_y')
            width = member_info.get('width', None)
            height = member_info.get('height', None)

            member = DraggableMember(self, _id, linked_id, loc_x, loc_y, width, height, member_config)
            self.scene.addItem(member)
            self.members_in_view[_id] = member

        self.view.fit_to_all()

    # def load_async_groups(self):
    #     # print('WorkflowSettings.load_async_groups()')
    #     # Clear any existing members from the scene
    #     for box in self.boxes_in_view:
    #         self.scene.removeItem(box)
    #         box.deleteLater()
    #     self.boxes_in_view = []
    #
    #     last_member_id = None
    #     last_member_pos = None
    #     last_loc_x = -100
    #     current_box_member_positions = []
    #     current_box_member_ids = []
    #
    #     members = self.members_in_view.values()
    #     members = sorted(members, key=lambda m: m.x())
    #
    #     for member in members:
    #         loc_x = member.x()
    #         loc_y = member.y()
    #         pos = QPointF(loc_x, loc_y)
    #
    #         from src.system import manager
    #         member_type = member.member_config.get('_TYPE', 'agent')
    #         member_class = manager.modules.get_module_class('Members', module_name=member_type)
    #         if not member_class:
    #             display_message(self,
    #                 message=f"Member module '{member_type}' not found.",
    #                 icon=QMessageBox.Warning,
    #             )
    #             continue
    #
    #         if member_class.allow_async:
    #             if abs(loc_x - last_loc_x) < 10:
    #                 current_box_member_positions += [last_member_pos, pos]
    #                 current_box_member_ids += [last_member_id, member.id]
    #             else:
    #                 if current_box_member_positions:
    #                     box = RoundedRectWidget(self, points=current_box_member_positions, member_ids=current_box_member_ids)
    #                     self.scene.addItem(box)
    #                     self.boxes_in_view.append(box)
    #                     current_box_member_positions = []
    #                     current_box_member_ids = []
    #
    #             last_loc_x = loc_x
    #             last_member_pos = pos
    #             last_member_id = member.id
    #
    #     # Handle the last group after finishing the loop
    #     if current_box_member_positions:
    #         box = RoundedRectWidget(self, points=current_box_member_positions, member_ids=current_box_member_ids)
    #         self.scene.addItem(box)
    #         self.boxes_in_view.append(box)
    #
    #     del_boxes = []
    #     for box in self.boxes_in_view:
    #         for member_id in box.member_ids:
    #             fnd = self.walk_inputs_recursive(member_id, box.member_ids)
    #             if fnd:
    #                 del_boxes.append(box)
    #                 break
    #
    #     for box in del_boxes:
    #         self.scene.removeItem(box)
    #         self.boxes_in_view.remove(box)

    def load_inputs(self):
        for _, line in self.inputs_in_view.items():
            self.scene.removeItem(line)
            # line.deleteLater()
        self.inputs_in_view = {}

        inputs_data = self.config.get('inputs', [])
        for input_dict in inputs_data:
            source_member_id = input_dict['source_member_id']
            target_member_id = input_dict['target_member_id']
            input_config = input_dict.get('config', {})

            source_member = self.members_in_view.get(source_member_id)
            target_member = self.members_in_view.get(target_member_id)
            if source_member is None or target_member is None:
                return

            line = ConnectionLine(self, source_member, target_member, input_config)
            self.scene.addItem(line)
            self.inputs_in_view[(source_member_id, target_member_id)] = line

    def walk_inputs_recursive(self, member_id, search_list) -> bool:  #!asyncrecdupe!# todo dupe
        found = False
        member_inputs = [k[0] for k, v in self.inputs_in_view.items() if k[1] == member_id and v.config.get('looper', False) is False]
        for inp in member_inputs:
            if inp in search_list:
                return True
            found = found or self.walk_inputs_recursive(inp, search_list)
        return found

    def update_member(self, update_list, save=False):
        for member_id, attribute, value in update_list:
            member = self.members_in_view.get(member_id)
            if not member:
                return
            setattr(member, attribute, value)

        if save:
            self.update_config()

    def linked_workflow(self):
        return getattr(self.parent, 'workflow', None)

    def count_other_members(self, exclude_initial_user=True):
        # count members but minus one for the user member
        member_count = len(self.members_in_view)
        if exclude_initial_user and any(m.member_type == 'user' for m in self.members_in_view.values()):
            member_count -= 1
        return member_count

    def can_simplify_view(self):  # !wfdiff! #
        member_count = len(self.members_in_view)
        input_count = len(self.inputs_in_view)
        if input_count > 0:
            return False
        if member_count == 1:
            member_config = next(iter(self.members_in_view.values())).member_config
            types_to_simplify = ['text_block', 'code_block', 'prompt_block', 'voice_model', 'image_model']
            if member_config.get('_TYPE', 'agent') in types_to_simplify:
                return True
        elif member_count == 2:
            members = list(self.members_in_view.values())
            members.sort(key=lambda x: x.x())
            first_member = members[0]
            second_member = members[1]
            inputs_count = len(self.inputs_in_view)
            if (first_member.member_type == 'user'
            and second_member.member_type == 'agent'
            and inputs_count == 0):
                return True
        return False

    def toggle_view(self, visible):
        self.view.setVisible(visible)
        safe_single_shot(10, lambda: self.splitter.setSizes([300 if visible else 22, 0 if visible else 1000]))
        self.splitter.setHandleWidth(0 if not visible else 3)

        # if visible:
        #     self.view.fit_to_all()
        #     # self.reposition_view()

    def reposition_view(self):
        return
        min_scroll_x = self.view.horizontalScrollBar().minimum()
        min_scroll_y = self.view.verticalScrollBar().minimum()
        self.view.horizontalScrollBar().setValue(min_scroll_x)
        self.view.verticalScrollBar().setValue(min_scroll_y)

    def set_edit_mode(self, state):
        if not self.compact_mode:
            return

        self.view.temp_block_move_flag = True

        # deselect all members first, to avoid layout issue - only if multiple other members
        if not self.can_simplify_view() and state is False:
            self.select_ids([])

        # deselecting id's will trigger on_selection_changed, which will hide the member_config_widget
        # and below, when we set the tree to visible, the window resizes to fit the tree
        # so after the member_config_widget is hidden, we need to update geometry
        self.updateGeometry()  # todo check if still needed on all os

        self.compact_mode_editing = state

        if hasattr(self.parent.parent, 'view'):
            self.parent.parent.toggle_view(not state)

        else:
            tree_container = find_attribute(self.parent, 'tree_container', None)
            tree_container.setVisible(not state)

        self.compact_mode_back_button.setVisible(state)

    def select_ids(self, ids, send_signal=True):
        with block_signals(self.scene):
            for item in self.scene.selectedItems():
                item.setSelected(False)

            for _id in ids:  # todo clean
                if _id in self.members_in_view:
                    self.members_in_view[_id].setSelected(True)
        if send_signal:
            self.on_selection_changed()

    def on_selection_changed(self):
        selected_objects = self.scene.selectedItems()
        selected_agents = [x for x in selected_objects if isinstance(x, DraggableMember)]
        selected_lines = [x for x in selected_objects if isinstance(x, ConnectionLine)]

        can_simplify = self.can_simplify_view()
        if self.compact_mode and not can_simplify and len(selected_objects) > 0 and not self.compact_mode_editing:
            self.set_edit_mode(True)

        if len(selected_objects) == 1 and (self.view.mini_view or not self.view.isVisible()):
            if len(selected_agents) == 1:
                member = selected_agents[0]
                self.member_config_widget.display_member(member)
                if hasattr(self.member_config_widget.config_widget, 'reposition_view'):
                    self.member_config_widget.config_widget.reposition_view()

            elif len(selected_lines) == 1:
                line = selected_lines[0]
                self.member_config_widget.show_input(line)

        else:
            # is_vis = self.member_config_widget.isVisible()
            self.member_config_widget.hide()  # 32

        self.workflow_buttons.load()

        if hasattr(self, 'member_list'):
            self.member_list.refresh_selected()

    def add_insertable_entity(self, item, del_pairs=None):
        if self.compact_mode:
            self.set_edit_mode(True)
        if self.new_agents:
            return

        all_items = []  # list of tuple(pos, config)
        if isinstance(item, QTreeWidgetItem):
            item_config = json.loads(item.data(0, Qt.UserRole).get('config', '{}'))
            all_items = [(QPointF(0, 0), item_config)]
        elif isinstance(item, dict):
            all_items = [(QPointF(0, 0), item)]
        elif isinstance(item, list):
            all_items = item

        self.toggle_view(True)
        mouse_point = self.view.mapToScene(self.view.mapFromGlobal(QCursor.pos()))
        linked_id = None  # todo

        self.new_agents = [
            (
                pos,
                DraggableMember(
                    self,
                    None,
                    linked_id,
                    (mouse_point + pos).x(),
                    (mouse_point + pos).y(),
                    None, None,
                    config,
                ),
            ) for pos, config in all_items
        ]
        self.del_pairs = del_pairs or []
        # set all graphicsitem in del_pairs to half opacity
        for item in self.del_pairs:
            if isinstance(item, QGraphicsItem):
                item.setOpacity(0.5)
            elif isinstance(item, QTreeWidgetItem):
                item.setBackground(0, QBrush(QColor(200, 200, 200)))

        for pos, entity in self.new_agents:
            self.scene.addItem(entity)

        self.view.setFocus()

    def add_insertable_input(self, item, member_bundle):
        if self.compact_mode:
            self.set_edit_mode(True)
        if self.new_lines:
            return

        if not isinstance(item, list):
            return

        all_inputs = item  # list of tuple()

        self.toggle_view(True)

        self.new_lines = [] if len(all_inputs) > 0 else None
        for inp in all_inputs:
            source_member_index, member_index, config = inp
            self.new_lines.append(
                InsertableLine(
                    self,
                    member_bundle=member_bundle,
                    source_member_index=source_member_index,
                    member_index=member_index,
                    config=config,
                )
            )

        for line in self.new_lines:
            self.scene.addItem(line)

        self.view.setFocus()

    def next_available_member_id(self) -> str:
        # if any not int keys
        if any(not k.isdigit() for k in self.members_in_view.keys()):
            raise NotImplementedError()
        member_ids = [int(k) for k in self.members_in_view.keys()] + [0]
        return str(max(member_ids) + 1)

    def add_entity(self):
        start_member_id = int(self.next_available_member_id())

        member_index_id_map = {}
        for i, enitity_tup in enumerate(self.new_agents):
            entity_id = str(start_member_id + i)
            pos, entity = enitity_tup
            entity_config = entity.member_config
            linked_id = entity.linked_id
            loc_x, loc_y = entity.x(), entity.y()

            member = DraggableMember(self, entity_id, linked_id, loc_x, loc_y, None, None, entity_config)
            self.scene.addItem(member)
            self.members_in_view[entity_id] = member
            member_index_id_map[i] = entity_id

        for new_line in self.new_lines or []:
            source_member_id = member_index_id_map[new_line.source_member_index]
            target_member_id = member_index_id_map[new_line.target_member_index]
            source_member = self.members_in_view[source_member_id]
            target_member = self.members_in_view[target_member_id]

            line = ConnectionLine(self, source_member, target_member, new_line.config)
            self.scene.addItem(line)
            self.inputs_in_view[(source_member_id, target_member_id)] = line

        for item in self.del_pairs or []:
            # remove items from workflow
            if isinstance(item, DraggableMember):
                member_id = item.id
                self.members_in_view.pop(member_id, None)
            elif isinstance(item, ConnectionLine):
                line_key = (item.source_member_id, item.target_member_id)
                self.inputs_in_view.pop(line_key, None)
            self.scene.removeItem(item)

        self.cancel_new_line()
        self.cancel_new_entity()

        self.update_config()
        if hasattr(self.parent, 'top_bar'):
            self.parent.load()
        pass

    def add_input(self, target_member_id):
        if not self.adding_line:
            return

        source_member_id = self.adding_line.source_member_id

        if target_member_id == source_member_id:
            return
        if (source_member_id, target_member_id) in self.inputs_in_view:
            return
        cr_check = self.check_for_circular_references(target_member_id, [source_member_id])
        is_looper = self.adding_line.config.get('looper', False)
        if cr_check and not is_looper:
            display_message(self,
                message='Circular reference detected',
                icon=QMessageBox.Warning,
            )
            return

        source_member = self.members_in_view[source_member_id]
        target_member = self.members_in_view[target_member_id]

        config = {'looper': is_looper}
        allows_messages = [  # todo
            'user',
            'agent'
        ]

        if target_member.member_config.get('_TYPE', 'agent') == 'workflow':
            first_member = next(iter(sorted(target_member.member_config['members'], key=lambda x: x['loc_x'])), None)
            if first_member:
                first_member_is_user = first_member['config'].get('_TYPE', 'agent') == 'user'
                if first_member_is_user:
                    allows_messages.append('workflow')

        if target_member.member_config.get('_TYPE', 'agent') in allows_messages:
            config['mappings.data'] = [{'source': 'Output', 'target': 'Message'}]
        line = ConnectionLine(self, source_member, target_member, config)
        self.scene.addItem(line)
        self.inputs_in_view[(source_member_id, target_member_id)] = line

        self.scene.removeItem(self.adding_line)
        self.adding_line = None
        self.update_config()

    def cancel_new_line(self):
        # Remove the temporary line from the scene and delete it
        if self.new_lines:
            for new_line in self.new_lines:
                self.view.scene().removeItem(new_line)
            self.new_lines = None

        if self.adding_line:
            self.view.scene().removeItem(self.adding_line)
            self.adding_line = None

        self.view.update()

    def cancel_new_entity(self):
        # Remove the new entity from the scene and delete it
        if self.new_agents:
            for pos, entity in self.new_agents:
                self.view.scene().removeItem(entity)
        if self.del_pairs:
            for item in self.del_pairs:
                if isinstance(item, QGraphicsItem):
                    item.setOpacity(1.0)

        self.new_agents = None
        self.del_pairs = None
        self.view.update()

        can_simplify_view = self.can_simplify_view()
        if can_simplify_view:
            self.toggle_view(False)  # .view.hide()  # !68! # 31
            # Select the member so that it's config is shown, then hide the workflow panel until more members are added
            other_member_ids = [k for k, m in self.members_in_view.items() if not m.member_config.get('_TYPE', 'agent') == 'user']  # .member_type != 'user']
            if other_member_ids:
                self.select_ids([other_member_ids[0]])

    def check_for_circular_references(self, target_member_id, input_member_ids):
        """Recursive function to check for circular references"""
        connected_input_members = [line_key[0] for line_key, line in self.inputs_in_view.items()
                                   if line_key[1] in input_member_ids
                                   and line.config.get('looper', False) is False]
        if target_member_id in connected_input_members:
            return True
        if len(connected_input_members) == 0:
            return False
        return self.check_for_circular_references(target_member_id, connected_input_members)

    def refresh_member_highlights(self):
        # return  # todo
        if self.compact_mode or not self.linked_workflow():
            return
        for member in self.members_in_view.values():
            member.highlight_background.hide()

        workflow = self.linked_workflow()
        next_expected_member = workflow.next_expected_member()
        if not next_expected_member:
            return

        if next_expected_member:
            nem_id = next_expected_member.member_id
            nem = self.members_in_view.get(nem_id)
            if nem:
                nem.highlight_background.show()

    def goto_member(self, full_member_id):
        member_ids = full_member_id.split('.')
        # deselect all members and lines
        self.scene.clearSelection()
        # click each member in the path
        widget = self
        for member_id in member_ids:
            member = widget.members_in_view.get(member_id)
            if member is None:
                return
            member.setSelected(True)
            widget = widget.member_config_widget.config_widget
            if not widget:
                return

    class CustomGraphicsView(QGraphicsView):
        coordinatesChanged = Signal(QPoint)

        def __init__(self, scene, parent):
            super().__init__(scene, parent)
            self.parent = parent
            self.mini_view = True

            self._is_panning = False
            self._mouse_press_pos = None
            self._mouse_press_scroll_x_val = None
            self._mouse_press_scroll_y_val = None

            self.temp_block_move_flag = False

            self.setMinimumHeight(200)
            self.setHorizontalScrollBarPolicy(Qt.ScrollBarAsNeeded)
            self.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
            self.setRenderHint(QPainter.Antialiasing)

            self.setTransformationAnchor(QGraphicsView.ViewportAnchor.AnchorUnderMouse)
            self.setResizeAnchor(QGraphicsView.ViewportAnchor.AnchorUnderMouse)

            from src.gui.style import TEXT_COLOR
            from src.utils.helpers import apply_alpha_to_hex
            self.setBackgroundBrush(QBrush(QColor(apply_alpha_to_hex(TEXT_COLOR, 0.05))))
            self.setFrameShape(QFrame.Shape.NoFrame)

        def toggle_mini_view(self):
            self.mini_view = not self.mini_view
            self.refresh_mini_view()

        def fit_to_all(self):
            if not self.parent.members_in_view:
                return

            all_items_rect = QRectF()
            for member in self.parent.members_in_view.values():
                if all_items_rect.isNull():
                    all_items_rect = member.sceneBoundingRect()
                else:
                    all_items_rect = all_items_rect.united(member.sceneBoundingRect())

            if not all_items_rect.isNull():
                # Add some padding around the bounding rect
                padding = 50
                all_items_rect.adjust(-padding, -padding, padding, padding)
                self.fitInView(all_items_rect, Qt.KeepAspectRatio)

        def refresh_mini_view(self):
            drag_mode = QGraphicsView.RubberBandDrag if self.mini_view else QGraphicsView.NoDrag
            self.setDragMode(drag_mode)
            for item in self.scene().items():
                if isinstance(item, DraggableMember):
                    item.update_visuals()
            for line in self.parent.inputs_in_view.values():
                line.updatePosition()
            self.update()

        def wheelEvent(self, event: QWheelEvent):
            if self.mini_view:
                super().wheelEvent(event)
            else:
                zoom_factor = 1.03
                if event.angleDelta().y() < 0:
                    zoom_factor = 1.0 / zoom_factor
                self.scale(zoom_factor, zoom_factor)

        def contextMenuEvent(self, event):
            menu = QMenu(self)

            selected_items = self.parent.scene.selectedItems()
            if selected_items:
                # menu.addAction("Cut")
                menu.addAction("Copy")
            menu.addAction("Paste")

            if selected_items:
                menu.addAction("Delete")

            if len(selected_items) > 1:
                menu.addSeparator()
                menu.addAction("Group")
            elif len(selected_items) == 1:
                selected_item = selected_items[0]
                if isinstance(selected_item, DraggableMember) and selected_item.member_type == 'workflow':
                    menu.addSeparator()
                    menu.addAction("Explode")

            # Show the menu and get the chosen action
            chosen_action = menu.exec(event.globalPos())

            if chosen_action:
                if chosen_action.text() == "Copy":
                    self.parent.workflow_buttons.copy_selected_items()
                elif chosen_action.text() == "Delete":
                    self.parent.workflow_buttons.delete_selected_items()
                elif chosen_action.text() == "Paste":
                    self.parent.workflow_buttons.paste_items()
                elif chosen_action.text() == "Group":
                    self.parent.workflow_buttons.group_selected_items()
                elif chosen_action.text() == "Explode":
                    self.parent.workflow_buttons.explode_selected_item()

        # def mouse_is_over_member(self):
        #     mouse_scene_position = self.mapToScene(self.mapFromGlobal(QCursor.pos()))
        #     for member_id, member in self.parent.members_in_view.items():
        #         # We need to map the scene position to the member's local coordinates
        #         member_local_pos = member.mapFromScene(mouse_scene_position)
        #         if member.contains(member_local_pos):
        #             return True
        #     return False

        def mouseReleaseEvent(self, event):
            self._is_panning = False
            self._mouse_press_pos = None
            self._mouse_press_scroll_x_val = None
            self._mouse_press_scroll_y_val = None

            # Reset drag mode if it was temporarily changed for rubber banding in non-mini view.
            if not self.mini_view and self.dragMode() == QGraphicsView.RubberBandDrag:
                self.setDragMode(QGraphicsView.NoDrag)

            super().mouseReleaseEvent(event)
            main = find_main_widget(self)
            if main:
                main.mouseReleaseEvent(event)

        def mousePressEvent(self, event):
            self.temp_block_move_flag = False

            if self.parent.new_agents:
                self.parent.add_entity()
                return

            # --- Custom Interaction Overrides ---

            # Override 1: Non-mini view, Ctrl+Click -> Start Rubber Band Drag
            if not self.mini_view and event.button() == Qt.LeftButton and event.modifiers() == Qt.ControlModifier:
                self.setDragMode(QGraphicsView.RubberBandDrag)
                super().mousePressEvent(event)
                return

            # Override 2: Mini view, Ctrl+Click -> Prepare for Panning
            if self.mini_view and event.button() == Qt.LeftButton and event.modifiers() == Qt.ControlModifier:
                # Set up for panning, which will occur in mouseMoveEvent.
                # This consumes the event, preventing the base class from starting a rubber band drag.
                self._is_panning = True
                self._mouse_press_pos = event.pos()
                self._mouse_press_scroll_x_val = self.horizontalScrollBar().value()
                self._mouse_press_scroll_y_val = self.verticalScrollBar().value()
                event.accept()
                return

            # --- Default/Fallback Behavior ---

            # Let the event propagate to items or start a default drag (e.g., rubber band in mini_view)
            super().mousePressEvent(event)

            # If an item was clicked or a drag was started by the superclass, the event is accepted.
            if event.isAccepted():
                return

            # If we're here, a background click occurred that wasn't handled yet.
            # This is primarily for 'NoDrag' mode (the default for non-mini view).

            # Manually clear selection on background click in NoDrag mode.
            if self.dragMode() == QGraphicsView.NoDrag:
                self.scene().clearSelection()

            # Panning is the default action for a background click in non-mini view.
            if not self.mini_view and event.button() == Qt.LeftButton:
                self._is_panning = True
                self._mouse_press_pos = event.pos()
                self._mouse_press_scroll_x_val = self.horizontalScrollBar().value()
                self._mouse_press_scroll_y_val = self.verticalScrollBar().value()
                event.accept()
                return

            self._is_panning = False

            # If no item handled it, check for connection creation.
            mouse_scene_position = self.mapToScene(event.pos())
            for member_id, member in self.parent.members_in_view.items():
                if isinstance(member, DraggableMember):
                    member_width = member.boundingRect().width()
                    input_rad = int(member_width / 2.5)
                    if self.parent.adding_line:
                        input_point_pos = member.input_point.scenePos()
                        if (mouse_scene_position - input_point_pos).manhattanLength() <= 20:
                            self.parent.add_input(member_id)
                            return
                    else:
                        output_point_pos = member.output_point.scenePos()
                        output_point_pos.setX(output_point_pos.x() + 2)
                        x_diff_is_pos = (mouse_scene_position.x() - output_point_pos.x()) > 0
                        if x_diff_is_pos:
                            input_rad = 20
                        if (mouse_scene_position - output_point_pos).manhattanLength() <= input_rad:
                            self.parent.adding_line = ConnectionLine(self.parent, member)
                            self.parent.scene.addItem(self.parent.adding_line)
                            return

            self.parent.cancel_new_line()
        # def mousePressEvent(self, event):
        #     self.temp_block_move_flag = False
        #
        #     if self.parent.new_agents:
        #         self.parent.add_entity()
        #         return
        #
        #     # Let the event propagate to the items in the scene first.
        #     # This will handle item selection.
        #     super().mousePressEvent(event)
        #
        #     # If an item was clicked, it would have accepted the event.
        #     if event.isAccepted():
        #         return
        #
        #     # If no item was clicked, it's a click on the background.
        #     # In 'NoDrag' mode, QGraphicsView doesn't clear selection on background click,
        #     # so we need to do it manually.
        #     if self.dragMode() == QGraphicsView.NoDrag:
        #         self.scene().clearSelection()
        #
        #     # Now, handle panning.
        #     panning_triggered = False
        #     if event.button() == Qt.LeftButton:
        #         is_over_item = self.itemAt(event.pos()) is not None
        #         if not self.mini_view and not is_over_item:
        #             panning_triggered = True
        #         elif self.mini_view and event.modifiers() == Qt.ControlModifier:
        #             panning_triggered = True
        #
        #     if panning_triggered:
        #         self._is_panning = True
        #         self._mouse_press_pos = event.pos()
        #         self._mouse_press_scroll_x_val = self.horizontalScrollBar().value()
        #         self._mouse_press_scroll_y_val = self.verticalScrollBar().value()
        #         event.accept()
        #         return
        #
        #     self._is_panning = False
        #
        #     # If no item handled it, check for connection creation.
        #     mouse_scene_position = self.mapToScene(event.pos())
        #     for member_id, member in self.parent.members_in_view.items():
        #         if isinstance(member, DraggableMember):
        #             member_width = member.boundingRect().width()
        #             input_rad = int(member_width / 2.5)
        #             if self.parent.adding_line:
        #                 input_point_pos = member.input_point.scenePos()
        #                 if (mouse_scene_position - input_point_pos).manhattanLength() <= 20:
        #                     self.parent.add_input(member_id)
        #                     return
        #             else:
        #                 output_point_pos = member.output_point.scenePos()
        #                 output_point_pos.setX(output_point_pos.x() + 2)
        #                 x_diff_is_pos = (mouse_scene_position.x() - output_point_pos.x()) > 0
        #                 if x_diff_is_pos:
        #                     input_rad = 20
        #                 if (mouse_scene_position - output_point_pos).manhattanLength() <= input_rad:
        #                     self.parent.adding_line = ConnectionLine(self.parent, member)
        #                     self.parent.scene.addItem(self.parent.adding_line)
        #                     return
        #
        #     self.parent.cancel_new_line()

        def mouseMoveEvent(self, event):
            update = False
            mouse_point = self.mapToScene(event.pos())
            if self.parent.adding_line:
                self.parent.adding_line.updateEndPoint(mouse_point)
                update = True
            if self.parent.new_agents:
                for pos, entity in self.parent.new_agents:
                    entity.setCentredPos(mouse_point + pos)
                update = True
            if self.parent.new_lines:
                for new_line in self.parent.new_lines:
                    new_line.updatePath()
                update = True

            if update:
                if self.scene():
                    self.scene().update()
                self.update()

            if self._is_panning:
                delta = event.pos() - self._mouse_press_pos
                self.horizontalScrollBar().setValue(self._mouse_press_scroll_x_val - delta.x())
                self.verticalScrollBar().setValue(self._mouse_press_scroll_y_val - delta.y())
                event.accept()
                return

            super().mouseMoveEvent(event)

        def keyPressEvent(self, event):
            if event.key() == Qt.Key_Escape:
                if self.parent.new_lines or self.parent.adding_line:
                    self.parent.cancel_new_line()
                if self.parent.new_agents:
                    self.parent.cancel_new_entity()
                event.accept()

            elif event.key() == Qt.Key_Delete:
                if self.parent.new_lines or self.parent.adding_line:
                    self.parent.cancel_new_line()
                    event.accept()
                    return
                if self.parent.new_agents:
                    self.parent.cancel_new_entity()
                    event.accept()
                    return

                self.parent.workflow_buttons.delete_selected_items()
                event.accept()
            elif event.modifiers() == Qt.ControlModifier:
                if event.key() == Qt.Key_C:
                    self.parent.workflow_buttons.copy_selected_items()
                    event.accept()
                elif event.key() == Qt.Key_V:
                    self.parent.workflow_buttons.paste_items()
                    event.accept()
            else:
                super().keyPressEvent(event)

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

    class WorkflowButtons(IconButtonCollection):
        def __init__(self, parent):
            super().__init__(parent=parent)
            self.layout.addSpacing(15)

            self.autorun = True
            self.show_hidden_bubbles = False
            self.show_nested_bubbles = False

            self.btn_add = IconButton(
                parent=self,
                icon_path=':/resources/icon-new.png',
                target=self.show_add_context_menu,
                tooltip='Add',
                size=self.icon_size,
            )

            self.btn_save_as = IconButton(
                parent=self,
                icon_path=':/resources/icon-save.png',
                target=self.show_save_context_menu,
                tooltip='Save As',
                size=self.icon_size,
            )

            # self.btn_link = ToggleIconButton(
            #     parent=self,
            #     icon_path=':/resources/icon-unlink.png',
            #     icon_path_checked=':/resources/icon-link.png',
            #     target=self.toggle_link,  # partial(self.toggle_attribute, 'autorun'),
            #     tooltip="Link member to it's source",
            #     tooltip_checked="Unlink member from it's source",
            #     opacity=0.3,
            #     opacity_when_checked=1.0,
            #     size=self.icon_size,
            # )

            self.btn_clear_chat = IconButton(
                parent=self,
                icon_path=':/resources/icon-clear.png',
                target=self.clear_chat,
                tooltip='Clear Chat',
                size=self.icon_size,
            )

            self.btn_copy = IconButton(
                parent=self,
                icon_path=':/resources/icon-copy.png',
                target=self.copy_selected_items,
                tooltip='Copy',
                size=self.icon_size,
            )

            self.btn_paste = IconButton(
                parent=self,
                icon_path=':/resources/icon-paste.png',
                target=self.paste_items,
                tooltip='Paste',
                size=self.icon_size,
            )

            self.btn_delete = IconButton(
                parent=self,
                icon_path=':/resources/close.png',
                target=self.delete_selected_items,
                icon_size_percent=0.6,
                tooltip='Delete',
                size=self.icon_size,
            )

            self.btn_group = IconButton(
                parent=self,
                icon_path=':/resources/icon-screenshot.png',
                target=self.group_selected_items,
                tooltip='Group selected items',
                size=self.icon_size,
            )

            self.btn_explode = IconButton(
                parent=self,
                icon_path=':/resources/icon-screenshot.png',
                target=self.explode_selected_item,
                tooltip='Explode workflow',
                size=self.icon_size,
            )

            self.layout.addWidget(self.btn_add)
            self.layout.addWidget(self.btn_save_as)
            self.layout.addWidget(self.btn_clear_chat)

            # separator
            self.layout.addSpacing(5)

            self.layout.addWidget(self.btn_copy)
            self.layout.addWidget(self.btn_paste)
            self.layout.addWidget(self.btn_delete)
            self.layout.addWidget(self.btn_group)
            self.layout.addWidget(self.btn_explode)

            # self.layout.addWidget(self.btn_link)

            self.layout.addStretch(1)

            self.btn_disable_autorun = ToggleIconButton(
                parent=self,
                icon_path=':/resources/icon-run-solid.png',
                icon_path_checked=':/resources/icon-run.png',
                target=partial(self.toggle_attribute, 'autorun'),
                tooltip='Disable autorun',
                tooltip_checked='Enable autorun',
                size=self.icon_size,
            )

            self.btn_member_list = ToggleIconButton(
                parent=self,
                icon_path=':/resources/icon-agent-solid.png',
                target=self.toggle_member_list,
                tooltip='View member list',
                icon_size_percent=0.9,
                size=self.icon_size,
            )

            self.btn_view = ToggleIconButton(
                parent=self,
                icon_path=':/resources/icon-eye.png',
                target=self.btn_view_clicked,
                size=self.icon_size,
            )

            self.btn_workflow_params = ToggleIconButton(
                parent=self,
                icon_path=':/resources/icon-parameter.png',
                target=self.toggle_workflow_params,
                tooltip='Workflow params',
                size=self.icon_size,
            )

            self.btn_toggle_description = ToggleIconButton(
                parent=self,
                icon_path=':/resources/icon-description.png',
                target=self.toggle_description,
                tooltip='Description',
                size=self.icon_size,
            )

            self.btn_workflow_options = ToggleIconButton(
                parent=self,
                icon_path=':/resources/icon-settings-solid.png',
                target=self.toggle_workflow_options,
                tooltip='Workflow options',
                size=self.icon_size,
            )

            self.layout.addWidget(self.btn_disable_autorun)
            self.layout.addWidget(self.btn_member_list)
            self.layout.addWidget(self.btn_view)
            self.layout.addWidget(self.btn_workflow_params)
            self.layout.addWidget(self.btn_toggle_description)
            self.layout.addWidget(self.btn_workflow_options)

            self.workflow_is_linked = self.parent.linked_workflow() is not None

            self.btn_clear_chat.setVisible(self.workflow_is_linked)
            self.btn_view.setVisible(self.workflow_is_linked)
            self.btn_disable_autorun.setVisible(self.workflow_is_linked)
            self.btn_member_list.setVisible(self.workflow_is_linked)

        def load(self):
            with block_signals(self):
                workflow_settings = self.parent
                workflow_options = workflow_settings.config.get('config', {})
                self.autorun = workflow_options.get('autorun', True)
                self.show_hidden_bubbles = workflow_options.get('show_hidden_bubbles', False)
                self.show_nested_bubbles = workflow_options.get('show_nested_bubbles', False)

                is_multi_member = workflow_settings.count_other_members() > 1
                contains_workflow_member = any(m.member_type == 'workflow' for m in workflow_settings.members_in_view.values())
                self.btn_member_list.setVisible(is_multi_member and self.workflow_is_linked)
                self.btn_disable_autorun.setChecked(not self.autorun)
                self.btn_disable_autorun.setVisible(is_multi_member and self.workflow_is_linked)
                self.btn_view.setChecked(self.show_hidden_bubbles or self.show_nested_bubbles)
                self.btn_view.setVisible((is_multi_member or contains_workflow_member) and self.workflow_is_linked)

                any_is_agent = any(m.member_type == 'agent' for m in workflow_settings.members_in_view.values())
                is_chat_workflow = workflow_settings.__class__.__name__ == 'ChatWorkflowSettings'
                param_list = workflow_settings.workflow_params.config.get('data', [])
                has_params = len(param_list) > 0
                self.btn_save_as.setVisible(is_multi_member or is_chat_workflow)
                self.btn_workflow_params.setChecked(has_params)
                self.btn_workflow_params.setVisible(is_multi_member or not any_is_agent or has_params)
                self.btn_workflow_options.setVisible(is_multi_member or not any_is_agent)

                selected_items = workflow_settings.scene.selectedItems()
                selected_count = len(selected_items)
                first_selected_item = next(iter(selected_items), None)
                selected_single_workflow = (
                    selected_count == 1
                    and isinstance(first_selected_item, DraggableMember)
                    and first_selected_item.member_type == 'workflow'
                )
                # check_explode_button = selected_count == 1
                # if check_explode_button:
                #     selected_member = next(iter(workflow_settings.scene.selectedItems()))
                #     allow_explode = isinstance(selected_member, DraggableMember) and selected_member.member_type == 'workflow'
                #     self.btn_explode.setEnabled(allow_explode)
                # else:
                #     self.btn_explode.setEnabled(False)
                selected_is_linked = (
                    selected_count == 1
                    and isinstance(first_selected_item, DraggableMember)
                    and first_selected_item.linked_id is not None
                )
                # self.btn_link.setChecked(selected_is_linked)
                # self.btn_link.setVisible(selected_count == 1)

                compact_mode_editing = workflow_settings.compact_mode_editing
                show_edit_group = is_multi_member and (is_chat_workflow or compact_mode_editing)
                self.btn_copy.setVisible(show_edit_group)
                self.btn_paste.setVisible(show_edit_group)
                self.btn_delete.setVisible(show_edit_group)
                self.btn_group.setVisible(show_edit_group)
                self.btn_explode.setVisible(show_edit_group)
                if show_edit_group:
                    self.btn_copy.setEnabled(selected_count > 0)
                    self.btn_paste.setEnabled(self.has_copied_items())
                    self.btn_delete.setEnabled(selected_count > 0)
                    self.btn_group.setEnabled(selected_count >= 1 and not selected_single_workflow)
                    self.btn_explode.setEnabled(selected_single_workflow)
                self.toggle_workflow_params()

        def add_contxt_menu_header(self, menu, title):
            section = QAction(title, self)
            section.setEnabled(False)
            font = QFont()
            font.setPointSize(8)
            section.setFont(font)
            menu.addAction(section)

        def show_add_context_menu(self):  # todo populate dynamically
            from src.gui.style import TEXT_COLOR
            menu = QMenu(self)
            # style sheet for disabled menu items
            menu.setStyleSheet(f"""
                QMenu::item {{
                    color: {TEXT_COLOR};
                }}
                QMenu::item:disabled {{
                    color: {apply_alpha_to_hex(TEXT_COLOR, 0.5)};
                    padding-left: 10px;
                }}
            """)

            self.add_contxt_menu_header(menu, 'Conversation')
            add_agent = menu.addAction('Agent')  #!memberdiff!#
            add_user = menu.addAction('User')
            add_contact = menu.addAction('Contact')
            menu.addSeparator()
            self.add_contxt_menu_header(menu, 'Blocks')
            add_text = menu.addAction('Text')
            add_code = menu.addAction('Code')
            add_prompt = menu.addAction('Prompt')
            menu.addSeparator()
            self.add_contxt_menu_header(menu, 'Models')
            add_image_model = menu.addAction('Image')
            add_voice_model = menu.addAction('Voice')
            menu.addSeparator()
            self.add_contxt_menu_header(menu, 'Flow')
            add_node = menu.addAction('Node')
            add_iterate = menu.addAction('Iterate')
            menu.addSeparator()
            self.add_contxt_menu_header(menu, 'System')
            add_notif = menu.addAction('Notification')
            # add_tool = menu.addAction('Tool')
            add_agent.triggered.connect(partial(self.choose_member, "AGENT"))
            add_user.triggered.connect(partial(
                self.parent.add_insertable_entity,
                {"_TYPE": "user"}
            ))
            add_voice_model.triggered.connect(partial(
                self.parent.add_insertable_entity,
                {"_TYPE": "voice_model"}
            ))
            add_image_model.triggered.connect(partial(
                self.parent.add_insertable_entity,
                {"_TYPE": "image_model"}
            ))
            add_node.triggered.connect(partial(
                self.parent.add_insertable_entity,
                {"_TYPE": "node"}
            ))
            add_iterate.triggered.connect(partial(
                self.parent.add_insertable_entity,
                {"_TYPE": "iterate"}
            ))
            add_notif.triggered.connect(partial(
                self.parent.add_insertable_entity,
                {"_TYPE": "notif"}
            ))

            add_contact.triggered.connect(partial(self.choose_member, "CONTACT"))
            add_text.triggered.connect(partial(self.choose_member, "TEXT"))
            add_code.triggered.connect(partial(self.choose_member, "CODE"))
            add_prompt.triggered.connect(partial(self.choose_member, "PROMPT"))

            menu.exec_(QCursor.pos())

        def choose_member(self, list_type):
            self.parent.set_edit_mode(True)
            list_dialog = TreeDialog(
                parent=self,
                title="Add Member",
                list_type=list_type,
                callback=self.parent.add_insertable_entity,
                show_blank=True,
            )
            list_dialog.open()

        def show_save_context_menu(self):
            menu = QMenu(self)  # todo dynamically populate
            save_agent = menu.addAction('Save as Agent')  # !wfmemberdiff! #
            save_agent.triggered.connect(partial(self.save_as, 'AGENT'))
            save_block = menu.addAction('Save as Block')
            save_block.triggered.connect(partial(self.save_as, 'BLOCK'))
            save_tool = menu.addAction('Save as Tool')
            save_tool.triggered.connect(partial(self.save_as, 'TOOL'))
            menu.exec_(QCursor.pos())

        def save_as(self, save_type):
            new_name, ok = QInputDialog.getText(self, f"New {save_type.capitalize()}", f"Enter the name for the new {save_type.lower()}:")
            if not ok:
                return

            workflow_config = json.dumps(self.parent.get_config())
            try:
                if save_type == 'AGENT':  # !wfmemberdiff! #
                    sql.execute("""
                        INSERT INTO entities (name, kind, config)
                        VALUES (?, ?, ?)
                    """, (new_name, 'AGENT', workflow_config,))

                elif save_type == 'BLOCK':
                    sql.execute("""
                        INSERT INTO blocks (name, config)
                        VALUES (?, ?)
                    """, (new_name, workflow_config,))

                elif save_type == 'TOOL':
                    sql.execute("""
                        INSERT INTO tools (uuid, name, config)
                        VALUES (?, ?, ?)
                    """, (str(uuid.uuid4()), new_name, workflow_config,))

                display_message(self,
                    message='Entity saved',
                    icon=QMessageBox.Information,
                )
            except sqlite3.IntegrityError as e:
                display_message(self,
                    message='Name already exists',
                    icon=QMessageBox.Warning,
                )

        def clear_chat(self):
            retval = display_message_box(
                icon=QMessageBox.Warning,
                text="Are you sure you want to permanently clear the chat messages?\nThis should only be used when testing a workflow.\nTo keep your data start a new chat.",
                title="Clear Chat",
                buttons=QMessageBox.Ok | QMessageBox.Cancel,
            )
            if retval != QMessageBox.Ok:
                return

            workflow = self.parent.linked_workflow()
            if not workflow:
                return

            sql.execute("""
                WITH RECURSIVE delete_contexts(id) AS (
                    SELECT id FROM contexts WHERE id = ?
                    UNION ALL
                    SELECT contexts.id FROM contexts
                    JOIN delete_contexts ON contexts.parent_id = delete_contexts.id
                )
                DELETE FROM contexts_messages WHERE context_id IN delete_contexts;
            """, (workflow.context_id,))
            sql.execute("""
            DELETE FROM contexts_messages WHERE context_id = ?""",
                        (workflow.context_id,))
            sql.execute("""
                WITH RECURSIVE delete_contexts(id) AS (
                    SELECT id FROM contexts WHERE id = ?
                    UNION ALL
                    SELECT contexts.id FROM contexts
                    JOIN delete_contexts ON contexts.parent_id = delete_contexts.id
                )
                DELETE FROM contexts WHERE id IN delete_contexts AND id != ?;
            """, (workflow.context_id, workflow.context_id,))

            if hasattr(self.parent.parent, 'main'):
                self.parent.parent.main.page_chat.load()

        def get_member_configs(self):
            scene = self.parent.view.scene()
            member_configs = []  # list of tuple(pos, config_dict)
            member_inputs = []  # list of tuple(member_index, input_member_index, config_dict)
            member_id_indexes = {}  # dict of member_id: index
            for selected_member in scene.selectedItems():
                if isinstance(selected_member, DraggableMember):
                    item_position = selected_member.pos()
                    member_configs.append(
                        (
                            item_position, selected_member.member_config
                        )
                    )
                    member_id_indexes[selected_member.id] = len(member_configs) - 1

            for selected_line in scene.selectedItems():
                if isinstance(selected_line, ConnectionLine):
                    if selected_line.target_member_id not in member_id_indexes or selected_line.source_member_id not in member_id_indexes:
                        continue
                    member_inputs.append(
                        (
                            member_id_indexes[selected_line.source_member_id],
                            member_id_indexes[selected_line.target_member_id],
                            selected_line.config,
                        )
                    )
            if len(member_configs) == 0:
                return
            center_x = sum([pos.x() for pos, _ in member_configs]) / len(member_configs)
            center_y = sum([pos.y() for pos, _ in member_configs]) / len(member_configs)
            center = QPointF(center_x, center_y)
            member_configs = [(pos - center, config) for pos, config in member_configs]
            return member_configs, member_inputs

        def toggle_link(self):
            selected_member = next(iter(self.parent.view.scene().selectedItems()), None)
            if not selected_member or not isinstance(selected_member, DraggableMember):
                return
            if selected_member.linked_id is not None:
                selected_member.linked_id = None
            else:
                selected_member.linked_id = "TODO"

            self.parent.update_config()
            self.load()

        def copy_selected_items(self):
            member_configs, member_inputs = self.get_member_configs()

            relative_members = [(f'{pos.x()},{pos.y()}', config) for pos, config in member_configs]
            member_bundle = (relative_members, member_inputs)
            # add to clipboard
            clipboard = QApplication.clipboard()
            copied_data = 'WORKFLOW_MEMBERS:' + json.dumps(member_bundle)
            clipboard.setText(copied_data)
            self.load()

        def paste_items(self):
            try:
                clipboard = QApplication.clipboard()
                copied_data = clipboard.text()
                start_text = 'WORKFLOW_MEMBERS:'
                if copied_data.startswith(start_text):
                    copied_data = copied_data[len(start_text):]

                member_bundle = json.loads(copied_data)
                member_configs = member_bundle[0]
                member_inputs = member_bundle[1]
                if not isinstance(member_configs, list) or not isinstance(member_inputs, list):
                    return

                member_configs = [(QPointF(*map(float, pos.split(','))), config) for pos, config in member_configs]

                self.parent.add_insertable_entity(member_configs)
                self.parent.add_insertable_input(member_inputs, member_bundle=member_bundle)

            except Exception as e:
                display_message(self.parent,
                    message=f"Error pasting items: {str(e)}",
                    icon=QMessageBox.Warning,
                )

        def has_copied_items(self):
            try:
                clipboard = QApplication.clipboard()
                copied_data = clipboard.text()
                start_text = 'WORKFLOW_MEMBERS:'
                return copied_data.startswith(start_text)

            except Exception as e:
                return False

        def explode_selected_item(self):
            scene = self.parent.view.scene()
            selected_items = scene.selectedItems()
            if len(selected_items) != 1:
                return
            explode_item = selected_items[0]
            if not isinstance(explode_item, DraggableMember) or explode_item.member_type != 'workflow':
                return

            members = explode_item.member_config.get('members', [])
            if not members:
                return
            # add as insertable entities
            member_configs = []
            member_inputs = []
            min_x = min(member.get('loc_x', 0) for member in members)
            min_y = min(member.get('loc_y', 0) for member in members)
            for member in members:
                member_config = member.get('config', {})
                if not member_config:
                    continue
                pos = QPointF(
                    max(member.get('loc_x', 0) - min_x, 0),
                    max(member.get('loc_y', 0) - min_y, 0)
                )
                member_configs.append((pos, member_config))
                inputs = member.get('inputs', [])
                for input in inputs:
                    source_member_id = input.get('source_member_id')
                    target_member_id = input.get('target_member_id')
                    if source_member_id and target_member_id:
                        member_inputs.append((source_member_id, target_member_id, input))

            del_pairs = scene.selectedItems()
            self.parent.add_insertable_entity(member_configs, del_pairs=del_pairs)

        def group_selected_items(self):
            member_configs, member_inputs = self.get_member_configs()
            group_member_config = merge_multiple_into_workflow_config(member_configs, member_inputs)
            scene = self.parent.view.scene()
            del_pairs = scene.selectedItems()
            self.parent.add_insertable_entity(group_member_config, del_pairs=del_pairs)
            # self.parent.add_insertable_input(member_inputs, member_bundle=member_bundle)

        def delete_selected_items(self):
            del_member_ids = set()
            del_inputs = set()
            all_del_objects = []

            workflow_settings = self.parent
            scene = workflow_settings.view.scene()
            selected_items = scene.selectedItems()

            if not selected_items:
                return

            for selected_item in selected_items:
                all_del_objects.append(selected_item)

                if isinstance(selected_item, DraggableMember):
                    del_member_ids.add(selected_item.id)
                    # Find connected lines to also mark for deletion
                    for key, line in workflow_settings.inputs_in_view.items():
                        if selected_item.id in key:
                            del_inputs.add(key)
                            if line not in all_del_objects:
                                all_del_objects.append(line)

                elif isinstance(selected_item, ConnectionLine):
                    del_inputs.add((selected_item.source_member_id, selected_item.target_member_id))

            # Remove duplicates from all_del_objects
            all_del_objects = list(dict.fromkeys(all_del_objects))

            del_count = len(del_member_ids) + len(del_inputs)
            if del_count == 0:
                return

            all_del_objects_old_brushes = [item.brush() for item in all_del_objects]
            all_del_objects_old_pens = [item.pen() for item in all_del_objects]

            # Apply a red tint to all items marked for deletion
            for item in all_del_objects:
                # Tint the outline
                old_pen = item.pen()
                new_pen = QPen(QColor(255, 0, 0, 255), old_pen.width())
                item.setPen(new_pen)

                # Tint the fill for members
                if isinstance(item, DraggableMember):
                    old_brush = item.brush()
                    texture = old_brush.texture()
                    if not texture.isNull():
                        new_pixmap = texture.copy()
                        painter = QPainter(new_pixmap)
                        painter.setCompositionMode(QPainter.CompositionMode_SourceAtop)
                        painter.fillRect(new_pixmap.rect(), QColor(255, 0, 0, 126))
                        painter.end()
                        item.setBrush(QBrush(new_pixmap))
                    else:  # For solid colors
                        item.setBrush(QBrush(QColor(255, 0, 0, 126)))

            scene.update()

            retval = display_message_box(
                icon=QMessageBox.Warning,
                text="Are you sure you want to delete the selected items?",
                title="Delete Items",
                buttons=QMessageBox.Ok | QMessageBox.Cancel,
            )

            if retval != QMessageBox.Ok:
                # Restore original appearance if cancelled
                for i, item in enumerate(all_del_objects):
                    item.setBrush(all_del_objects_old_brushes[i])
                    item.setPen(all_del_objects_old_pens[i])
                scene.update()
                return

            # Proceed with deletion
            for obj in all_del_objects:
                scene.removeItem(obj)

            for member_id in del_member_ids:
                workflow_settings.members_in_view.pop(member_id, None)
            for line_key in del_inputs:
                workflow_settings.inputs_in_view.pop(line_key, None)

            workflow_settings.update_config()
            if hasattr(workflow_settings.parent, 'top_bar'):
                workflow_settings.parent.load()

        def toggle_member_list(self):
            is_checked = self.btn_member_list.isChecked()
            self.parent.member_list.setVisible(is_checked)

        def toggle_workflow_params(self):
            self.show_toggle_widget(self.btn_workflow_params)

        def toggle_description(self):
            self.show_toggle_widget(self.btn_toggle_description)

        def toggle_workflow_options(self):
            self.show_toggle_widget(self.btn_workflow_options)

        def show_toggle_widget(self, toggle_btn):
            all_toggle_widgets = {
                self.btn_workflow_params: self.parent.workflow_params,
                self.btn_workflow_options: self.parent.workflow_options,
                self.btn_toggle_description: self.parent.workflow_description,
            }

            is_now_checked = toggle_btn.isChecked()

            # Show/hide the widget associated with the clicked button
            all_toggle_widgets[toggle_btn].setVisible(is_now_checked)

            # Ensure all other toggleable widgets are hidden and their buttons unchecked
            for btn, widget in all_toggle_widgets.items():
                if btn is not toggle_btn and btn.isChecked():
                    btn.setChecked(False)
                    widget.setVisible(False)

        def btn_view_clicked(self):
            menu = QMenu(self)
            show_hidden = menu.addAction('Show hidden bubbles')
            show_nested = menu.addAction('Show nested bubbles')
            menu.addSeparator()
            mini_view = menu.addAction('Mini view')

            show_hidden.setCheckable(True)
            show_nested.setCheckable(True)
            mini_view.setCheckable(True)

            show_hidden.setChecked(self.show_hidden_bubbles)
            show_nested.setChecked(self.show_nested_bubbles)
            mini_view.setChecked(self.parent.view.mini_view)

            show_hidden.triggered.connect(partial(self.toggle_attribute, 'show_hidden_bubbles'))
            show_nested.triggered.connect(partial(self.toggle_attribute, 'show_nested_bubbles'))
            mini_view.triggered.connect(partial(self.parent.view.toggle_mini_view))

            self.btn_view.setChecked(self.show_hidden_bubbles or self.show_nested_bubbles)

            menu.exec_(QCursor.pos() - QPoint(menu.sizeHint().width(), 0))

        def toggle_attribute(self, attr):
            new_state = not getattr(self, attr)
            setattr(self, attr, new_state)

            self.parent.update_config()
            self.btn_view.setChecked(self.show_hidden_bubbles or self.show_nested_bubbles)
            if self.parent.linked_workflow():
                self.parent.parent.load()

    class MemberList(QWidget):
        """This widget displays a list of members in the chat."""
        def __init__(self, parent):
            super().__init__(parent)
            self.parent = parent
            self.block_flag = False  # todo clean

            self.layout = CVBoxLayout(self)
            self.layout.setContentsMargins(0, 5, 0, 0)

            self.tree_members = BaseTreeWidget(self)
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
            self.tree_members.itemSelectionChanged.connect(self.on_selection_changed)
            self.tree_members.build_columns_from_schema(self.schema)
            self.tree_members.setFixedWidth(150)
            self.layout.addWidget(self.tree_members)
            self.layout.addStretch(1)

        def load(self):
            selected_ids = self.tree_members.get_selected_item_ids()
            data = [
                [
                    get_member_name_from_config(m.config),
                    m.member_id,
                    get_avatar_paths_from_config(m.config, merge_multiple=True),
                ]
                for m in self.parent.linked_workflow().members.values()
            ]
            self.tree_members.load(
                data=data,
                folders_data=[],
                schema=self.schema,
                readonly=True,
                silent_select_id=selected_ids,
            )
            # set height to fit all items & header
            height = self.tree_members.sizeHintForRow(0) * (len(data) + 1)
            self.tree_members.setFixedHeight(height)

        def on_selection_changed(self):
            # push selection to view
            all_selected_ids = self.tree_members.get_selected_item_ids()
            self.block_flag = True
            self.parent.select_ids(all_selected_ids, send_signal=False)
            self.block_flag = False

        def refresh_selected(self):
            # get selection from view
            if self.block_flag:
                return
            selected_objects = self.parent.scene.selectedItems()
            selected_members = [x for x in selected_objects if isinstance(x, DraggableMember)]
            selected_member_ids = [m.id for m in selected_members]
            with block_signals(self.tree_members):
                self.tree_members.select_items_by_id(selected_member_ids)

    class WorkflowDescription(ConfigFields):
        def __init__(self, parent):
            super().__init__(
                parent=parent,
                schema=[
                    {
                        'text': 'Description',
                        'type': str,
                        'default': '',
                        'num_lines': 10,
                        'stretch_x': True,
                        'stretch_y': True,
                        'placeholder_text': 'Description',
                        'gen_block_folder_name': 'todo',
                        'label_position': None,
                    },
                ]
            )
            self.hide()

    class WorkflowParams(ConfigJsonTree):
        def __init__(self, parent):
            super().__init__(
                parent=parent,
                schema=[
                    {
                        'text': 'Name',
                        'type': str,
                        'width': 120,
                        'default': '< Enter a parameter name >',
                    },
                    {
                        'text': 'Description',
                        'type': str,
                        'stretch': True,
                        'default': '',
                    },
                    {
                        'text': 'Type',
                        'type': ('String', 'Int', 'Float', 'Bool',),
                        'width': 100,
                        'on_edit_reload': True,
                        'default': 'String',
                    },
                    {
                        'text': 'Req',
                        'type': bool,
                        'default': True,
                    },
                ],
                add_item_options={'title': 'NA', 'prompt': 'NA'},
                del_item_options={'title': 'NA', 'prompt': 'NA'}
            )
            self.hide()

    class WorkflowOptions(ConfigJoined):
        def __init__(self, parent):
            super().__init__(
                parent=parent,
                layout_type='vertical',
                widgets=[
                    self.WorkflowFields(self),
                ],
            )
            self.hide()

        class WorkflowFields(ConfigFields):
            def __init__(self, parent):
                super().__init__(
                    parent=parent,
                    schema = [
                        {
                            'text': 'Filter role',
                            'type': 'combo',
                            'table_name': 'roles',
                            'width': 90,
                            'tooltip': 'Filter the output to a specific role. This is only used for the final member.',
                            'default': 'All',
                            'row_key': 0,
                        },
                        {
                            'text': 'Member options',
                            'type': 'popup_button',
                            'use_namespace': 'group',
                            'member_type': 'agent',
                            'label_position': None,
                            'default': '',
                            'row_key': 0,
                        },
                    ]
                )


class MemberConfigWidget(ConfigWidget):
    def __init__(self, parent):
        super().__init__(parent=parent)
        self.layout = CVBoxLayout(self)  # QStackedLayout(self)
        self.config_widget = None
        self.member_header_widget = HeaderFields(self)
        self.layout.addWidget(self.member_header_widget)

    def get_config(self):
        if not self.config_widget:
            return {}
        header_config = self.member_header_widget.get_config()
        config = self.config_widget.get_config()
        return header_config | config

    def update_config(self):
        self.save_config()

    def save_config(self):
        if not self.config_widget:
            return
        config = self.get_config()

        # is_mini_view_member = isinstance(self.parent, WorkflowSettings)
        # if is_mini_view_member:
        #     # self.parent.member_config = config
        self.parent.members_in_view[self.config_widget.member_id].member_config = config
        # else:
        #     self.parent.parent.member_config = config

        self.parent.update_config()

    # def save_config(self):
    #     if not self.config_widget:
    #         return
    #     config = self.config_widget.get_config()
    #     # self.workflow_settings.members_in_view[self.parent.id].member_config = config
    #     self.parent.member_config = config
    #     self.parent.update_config()

    def display_member(self, member):
        clear_layout(self.layout, skip_count=1)
        member_type = member.member_type
        member_config = member.member_config

        # return
        member_settings_class = get_member_settings_class(member_type)
        if not member_settings_class:
            return

        kwargs = {}
        if member_settings_class == WorkflowSettings:
            kwargs = {'compact_mode': True}

        page_map = None
        is_same = isinstance(self.config_widget, member_settings_class)
        if is_same:
            page_map = get_selected_pages(self.config_widget)

        self.config_widget = member_settings_class(self, **kwargs)
        self.config_widget.member_id = member.id
        self.rebuild_member(config=member_config)

        if page_map:
            set_selected_pages(self.config_widget, page_map)

    def show_input(self, line):
        source_member_id, target_member_id = line.source_member_id, line.target_member_id
        self.config_widget = InputSettings(self.parent)
        self.config_widget.input_key = (source_member_id, target_member_id)
        self.rebuild_member(config=line.config)

    def rebuild_member(self, config):
        clear_layout(self.layout, skip_count=1)
        member_type = config.get('_TYPE', 'agent')

        self.member_header_widget.setVisible(member_type != 'workflow')
        if member_type != 'workflow':
            from src.system import manager
            member_class = manager.modules.get_module_class('Members', module_name=member_type)
            if member_class:
                default_avatar = getattr(member_class, 'default_avatar', '')
                self.member_header_widget.schema[0]['default'] = default_avatar
                self.member_header_widget.build_schema()

            self.member_header_widget.load_config(config)
            self.member_header_widget.load()

        self.config_widget.load_config(config)
        self.config_widget.build_schema()
        self.config_widget.load()
        self.layout.addWidget(self.config_widget)
        self.show()
        # if hasattr(self.config_widget, 'reposition_view'):
        #     self.config_widget.reposition_view()


class DraggableMember(QGraphicsObject):
    (NoHandle, Top, Bottom, Left, Right, TopLeft, TopRight, BottomLeft, BottomRight) = range(9)

    def __init__(
            self,
            workflow_settings,
            member_id: str,
            linked_id: str,
            loc_x: int,
            loc_y: int,
            width: Optional[int],
            height: Optional[int],
            member_config: Dict[str, Any]
    ):
        super().__init__()

        self.workflow_settings = workflow_settings
        self.id = member_id
        self.linked_id = linked_id
        self.member_type = member_config.get('_TYPE', 'agent')
        self.member_config = member_config

        # --- State for resizing logic ---
        self.is_resizing = False
        self.current_resize_handle = self.NoHandle
        self.resize_handle_size = 10.0
        self.minimum_size = QSize(150, 100)
        self.original_geometry = QRectF()
        self.original_mouse_pos = QPointF()
        # ---

        self.member_ellipse = self.MemberEllipse(self, diameter=50 if self.member_type != 'node' else 20)
        self.member_proxy = self.MemberProxy(self)

        # Apply initial size for proxy
        if width and height:
            scale = self.member_proxy.scale()
            self.member_proxy.resize(width / scale, height / scale)

        # --- Setup Item Flags and Position ---
        self.setPos(loc_x, loc_y)
        self.setFlag(QGraphicsItem.ItemIsMovable)
        self.setFlag(QGraphicsItem.ItemIsSelectable)
        self.setAcceptHoverEvents(True)

        # --- Child Items ---
        self.input_point = ConnectionPoint(self, True)
        self.output_point = ConnectionPoint(self, False)
        self.highlight_background = self.HighlightBackground(self)
        self.highlight_background.updatePosition()
        self.highlight_background.hide()

        # --- Finalize ---
        self.update_visuals()

    def geometry(self) -> QRectF:
        """
        Returns the item's geometry (its bounding rectangle translated by its position)
        in scene coordinates.
        """
        return self.boundingRect().translated(self.pos())

    class MemberEllipse(QGraphicsEllipseItem):
        def __init__(self, parent, diameter):
            super().__init__(0, 0, diameter, diameter, parent=parent)
            from src.gui.style import TEXT_COLOR
            self.setPen(QPen(QColor(TEXT_COLOR), 1) if parent.member_type in ['user', 'agent'] else Qt.NoPen)
            # self.setBrush(QBrush(QColor(TEXT_COLOR)))
            self.setAcceptHoverEvents(True)

    # class MemberProxy(QGraphicsProxyWidget):
    #     def __init__(self, parent):
    #         super().__init__(parent=parent)
    #         self.parent = parent
    #         self.workflow_settings = parent.workflow_settings
    #         self.setScale(0.5)
    #         self.config_widget = None
    #         # self.member_settings_class = MemberConfigWidget
    #
    #     def show(self):
    #         if self.config_widget is None:
    #             self.config_widget = MemberConfigWidget(parent=self)
    #             self.config_widget.display_member(self.parent)
    #             # self.config_widget.build_schema()
    #             # self.config_widget.load_config(self.parent.member_config)
    #             # self.config_widget.load()
    #             self.setWidget(self.config_widget)
    #         super().show()
    #     #     # self.config_widget = MemberConfigWidget(parent=self)
    #     #     # self.config_widget.display_member(self.parent)
    #     # def show(self):
    #     #     self.config_widget = get_member_settings_class(self.parent.member_type)(parent=self)
    #     #     # self.config_widget.build_schema()
    #     #     # self.config_widget.load_config(self.parent.member_config)
    #     #     # self.config_widget.load()
    #     #     # self.setWidget(self.config_widget)
    #
    # #     def update_config(self):
    # #         self.save_config()
    # #
    # #     def save_config(self):
    # #         if not self.config_widget:
    # #             return
    # #         config = self.config_widget.get_config()
    # #         # self.workflow_settings.members_in_view[self.parent.id].member_config = config
    # #         self.parent.member_config = config
    # #         self.workflow_settings.update_config()
    #
    class MemberProxy(QGraphicsProxyWidget):
        def __init__(self, parent):
            super().__init__(parent=parent)
            self.parent = parent
            self.workflow_settings = parent.workflow_settings
            self.setScale(0.5)
            self.container_widget = None
            self.config_widget = None
            self.member_header_widget = HeaderFields(self)
            self.member_settings_class = get_member_settings_class(parent.member_type)

        def show(self):
            if self.member_settings_class and self.container_widget is None: #  and self.config_widget is None:
                self.config_widget = self.member_settings_class(parent=self)
                self.config_widget.build_schema()
                self.config_widget.load_config(self.parent.member_config)
                self.config_widget.load()
                self.container_widget = QWidget()
                container_layout = CVBoxLayout(self.container_widget)
                container_layout.addWidget(self.member_header_widget)
                container_layout.addWidget(self.config_widget)
                self.setWidget(self.container_widget)  #self.config_widget)
            super().show()

        def update_config(self):
            self.save_config()

        def save_config(self):
            if not self.config_widget:
                return
            config = self.config_widget.get_config()
            # self.workflow_settings.members_in_view[self.parent.id].member_config = config
            self.parent.member_config = config
            self.workflow_settings.update_config()

    def boundingRect(self):
        if self.workflow_settings.view.mini_view or not self.member_proxy.widget():
            return self.member_ellipse.boundingRect()
        else:
            pr = self.member_proxy.boundingRect()
            scale = self.member_proxy.scale()
            padding = self.resize_handle_size
            return QRectF(pr.topLeft(), QSize(pr.width() * scale, pr.height() * scale)).adjusted(-padding, -padding,
                                                                                                 padding, padding)

    def paint(self, painter, option, widget=None):
        from src.gui.style import TEXT_COLOR
        if option.state & QStyle.State_Selected:
            painter.setPen(QPen(QColor(TEXT_COLOR), 1, Qt.DashLine))
            painter.setBrush(Qt.NoBrush)  # Avoid filling the rect
            painter.drawRect(self.boundingRect())

    def brush(self):
        return self.member_ellipse.brush()

    def pen(self):
        return self.member_ellipse.pen()

    def setBrush(self, brush):
        self.member_ellipse.setBrush(brush)

    def setPen(self, pen):
        self.member_ellipse.setPen(pen)

    def setCentredPos(self, pos):
        self.setPos(pos.x() - self.boundingRect().width() / 2, pos.y() - self.boundingRect().height() / 2)

    def update_visuals(self):
        self.prepareGeometryChange()
        is_mini = self.workflow_settings.view.mini_view

        has_proxy = self.member_proxy.member_settings_class is not None
        self.member_ellipse.setVisible(is_mini or not has_proxy)
        if has_proxy:
            self.member_proxy.setVisible(not is_mini)
            if not is_mini:
                self.member_proxy.show()

        if is_mini or not has_proxy:
            rect = self.member_ellipse.rect()
        else:
            proxy_br = self.member_proxy.boundingRect()
            rect = self.member_proxy.mapToParent(proxy_br).boundingRect()

        self.input_point.setPos(rect.left(), rect.center().y() - self.input_point.boundingRect().height() / 2)
        self.output_point.setPos(rect.right() - self.output_point.boundingRect().width(),
                                 rect.center().y() - self.output_point.boundingRect().height() / 2)
        self.refresh_avatar()
        self.highlight_background.updatePosition()

    def refresh_avatar(self):
        from src.gui.style import TEXT_COLOR
        if self.member_type == 'node':
            self.member_ellipse.setBrush(QBrush(QColor(TEXT_COLOR)))
            return

        hide_bubbles = self.member_config.get('group.hide_bubbles', False)
        in_del_pairs = self in (self.workflow_settings.del_pairs or [])
        opacity = 0.2 if (hide_bubbles or in_del_pairs) else 1
        avatar_paths = get_avatar_paths_from_config(self.member_config)

        diameter = self.member_ellipse.rect().width()
        pixmap = path_to_pixmap(avatar_paths, opacity=opacity, diameter=diameter)

        if pixmap:
            self.member_ellipse.setBrush(QBrush(pixmap.scaled(diameter, diameter)))

    def get_handle_at(self, pos: QPointF):
        # Map the proxy's bounding rect to the parent (this DraggableMember)
        # to get a rect in local coordinates that accounts for the proxy's scale.
        proxy_br = self.member_proxy.boundingRect()
        rect = self.member_proxy.mapToParent(proxy_br).boundingRect()
        handle_size = self.resize_handle_size

        on_top = abs(pos.y() - rect.top()) < handle_size
        on_bottom = abs(pos.y() - rect.bottom()) < handle_size
        on_left = abs(pos.x() - rect.left()) < handle_size
        on_right = abs(pos.x() - rect.right()) < handle_size

        if on_top and on_left: return self.TopLeft
        if on_top and on_right: return self.TopRight
        if on_bottom and on_left: return self.BottomLeft
        if on_bottom and on_right: return self.BottomRight
        if on_top: return self.Top
        if on_bottom: return self.Bottom
        if on_left: return self.Left
        if on_right: return self.Right
        return self.NoHandle

    def set_cursor_for_handle(self, handle):
        if handle in (self.TopLeft, self.BottomRight):
            self.setCursor(Qt.SizeFDiagCursor)
        elif handle in (self.TopRight, self.BottomLeft):
            self.setCursor(Qt.SizeBDiagCursor)
        elif handle in (self.Top, self.Bottom):
            self.setCursor(Qt.SizeVerCursor)
        elif handle in (self.Left, self.Right):
            self.setCursor(Qt.SizeHorCursor)
        else:
            self.setCursor(Qt.ArrowCursor)

    def mousePressEvent(self, event: QGraphicsSceneMouseEvent):
        handle = self.get_handle_at(event.pos())
        if handle != self.NoHandle and self.isSelected() and not self.workflow_settings.view.mini_view:
            self.is_resizing = True
            self.current_resize_handle = handle
            self.original_geometry = self.geometry()
            self.original_mouse_pos = event.scenePos()
            self.setFlag(QGraphicsItem.ItemIsMovable, False)
            event.accept()
        else:
            super().mousePressEvent(event)

    def mouseMoveEvent(self, event: QGraphicsSceneMouseEvent):
        for line in self.workflow_settings.inputs_in_view.values():
            if line.source_member_id == self.id or line.target_member_id == self.id:
                line.updatePosition()

        if self.is_resizing:
            delta = event.scenePos() - self.original_mouse_pos
            new_geom = QRectF(self.original_geometry)
            handle = self.current_resize_handle

            # Adjust geometry based on handle, preserving the opposite edge
            if handle in (self.Left, self.TopLeft, self.BottomLeft):
                new_geom.setLeft(self.original_geometry.left() + delta.x())
            if handle in (self.Right, self.TopRight, self.BottomRight):
                new_geom.setRight(self.original_geometry.right() + delta.x())
            if handle in (self.Top, self.TopLeft, self.TopRight):
                new_geom.setTop(self.original_geometry.top() + delta.y())
            if handle in (self.Bottom, self.BottomLeft, self.BottomRight):
                new_geom.setBottom(self.original_geometry.bottom() + delta.y())

            # Enforce minimum size, anchoring the correct edge
            min_width = self.minimum_size.width()
            if new_geom.width() < min_width:
                if handle in (self.Left, self.TopLeft, self.BottomLeft):
                    new_geom.setLeft(new_geom.right() - min_width)
                else:
                    new_geom.setRight(new_geom.left() + min_width)

            min_height = self.minimum_size.height()
            if new_geom.height() < min_height:
                if handle in (self.Top, self.TopLeft, self.TopRight):
                    new_geom.setTop(new_geom.bottom() - min_height)
                else:
                    new_geom.setBottom(new_geom.top() + min_height)

            self.prepareGeometryChange()
            self.setPos(new_geom.topLeft())
            self.member_proxy.resize(new_geom.size() / self.member_proxy.scale())

            self.update_visuals()
            event.accept()
        else:
            super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event: QGraphicsSceneMouseEvent):
        if self.is_resizing:
            self.is_resizing = False
            self.current_resize_handle = self.NoHandle
            self.setFlag(QGraphicsItem.ItemIsMovable, True)
            self.save_pos()
            event.accept()
        else:
            super().mouseReleaseEvent(event)
            self.save_pos()

    def save_pos(self):
        new_loc_x = max(0, int(self.x()))
        new_loc_y = max(0, int(self.y()))

        current_size = self.member_proxy.size() * self.member_proxy.scale()

        members = self.workflow_settings.config.get('members', [])
        member = next((m for m in members if m['id'] == self.id), None)

        if member:
            pos_changed = new_loc_x != member.get('loc_x') or new_loc_y != member.get('loc_y')
            size_changed = not math.isclose(current_size.width(), member.get('width', 0)) or \
                           not math.isclose(current_size.height(), member.get('height', 0))
            if not pos_changed and not size_changed:
                return

        self.workflow_settings.update_config()

    def hoverMoveEvent(self, event: QGraphicsSceneHoverEvent):
        if self.is_resizing or not self.isSelected() or self.workflow_settings.view.mini_view:
            self.setCursor(Qt.ArrowCursor)
            super().hoverMoveEvent(event)
            return

        handle = self.get_handle_at(event.pos())
        self.set_cursor_for_handle(handle)
        super().hoverMoveEvent(event)

    def hoverLeaveEvent(self, event: QGraphicsSceneHoverEvent):
        self.setCursor(Qt.ArrowCursor)
        super().hoverLeaveEvent(event)

    class HighlightBackground(QGraphicsItem):
        def __init__(self, parent):
            super().__init__(parent)
            self.member_ellipse = parent.member_ellipse
            self.member_proxy = parent.member_proxy
            self.padding = 15

        def boundingRect(self):
            is_mini = not self.member_proxy.isVisible()
            if is_mini:
                outer_diameter = self.member_ellipse.rect().width() * 1.6
                return QRectF(-outer_diameter / 2, -outer_diameter / 2, outer_diameter, outer_diameter)
            else:
                proxy_rect = self.member_proxy.boundingRect()
                scale = self.member_proxy.scale()
                scaled_width = proxy_rect.width() * scale
                scaled_height = proxy_rect.height() * scale
                outer_width = scaled_width + 2 * self.padding
                outer_height = scaled_height + 2 * self.padding
                return QRectF(-outer_width / 2, -outer_height / 2, outer_width, outer_height)

        def paint(self, painter, option, widget=None):
            from src.gui.style import TEXT_COLOR
            color = QColor(TEXT_COLOR)
            painter.setPen(Qt.NoPen)

            is_mini = not self.member_proxy.isVisible()
            if is_mini:
                outer_diameter = self.member_ellipse.rect().width() * 1.6
                inner_diameter = self.member_ellipse.rect().width()

                gradient = QRadialGradient(QPointF(0, 0), outer_diameter / 2)
                color.setAlpha(155)
                gradient.setColorAt(0, color)
                gradient.setColorAt(1, QColor(0, 0, 0, 0))

                outer_path = QPainterPath()
                outer_path.addEllipse(QPointF(0, 0), outer_diameter / 2, outer_diameter / 2)
                inner_path = QPainterPath()
                inner_path.addEllipse(QPointF(0, 0), inner_diameter / 2, inner_diameter / 2)

                final_path = outer_path.subtracted(inner_path)
                painter.setBrush(QBrush(gradient))
                painter.drawPath(final_path)
            else:
                # Full view: Implement glow effect for member proxy with edge and corner gradients
                proxy_rect = self.member_proxy.boundingRect()
                scale = self.member_proxy.scale()
                color = QColor(apply_alpha_to_hex(TEXT_COLOR, 0.3))  # Use a lighter color for the glow effect
                # Calculate scaled dimensions of the proxy
                scaled_width = proxy_rect.width() * scale
                scaled_height = proxy_rect.height() * scale
                # outer_width = scaled_width + 2 * self.padding
                # outer_height = scaled_height + 2 * self.padding
                # rounding = 10.0  # Corner rounding radius
                # Define inner rectangle coordinates (centered at (0, 0))
                left = -scaled_width / 2
                right = scaled_width / 2
                top = -scaled_height / 2
                bottom = scaled_height / 2

                # **Edge Gradients**
                # Top edge
                top_gradient = QLinearGradient(QPointF(left, top), QPointF(left, top - self.padding))
                top_gradient.setColorAt(0, color)  # Start at edge with highlight
                top_gradient.setColorAt(1, QColor(0, 0, 0, 0))  # Fade outward to transparent
                painter.setBrush(top_gradient)
                painter.drawRect(QRectF(left, top - self.padding, scaled_width, self.padding))
                # Bottom edge
                bottom_gradient = QLinearGradient(QPointF(left, bottom), QPointF(left, bottom + self.padding))
                bottom_gradient.setColorAt(0, color)
                bottom_gradient.setColorAt(1, QColor(0, 0, 0, 0))
                painter.setBrush(bottom_gradient)
                painter.drawRect(QRectF(left, bottom, scaled_width, self.padding))
                # Left edge
                left_gradient = QLinearGradient(QPointF(left, top), QPointF(left - self.padding, top))
                left_gradient.setColorAt(0, color)
                left_gradient.setColorAt(1, QColor(0, 0, 0, 0))
                painter.setBrush(left_gradient)
                painter.drawRect(QRectF(left - self.padding, top, self.padding, scaled_height))
                # Right edge
                right_gradient = QLinearGradient(QPointF(right, top), QPointF(right + self.padding, top))
                right_gradient.setColorAt(0, color)
                right_gradient.setColorAt(1, QColor(0, 0, 0, 0))
                painter.setBrush(right_gradient)
                painter.drawRect(QRectF(right, top, self.padding, scaled_height))
                # **Corner Gradients**
                # Top-left corner
                tl_gradient = QRadialGradient(QPointF(left, top), self.padding)
                tl_gradient.setColorAt(0, color)
                tl_gradient.setColorAt(1, QColor(0, 0, 0, 0))
                painter.setBrush(tl_gradient)
                painter.drawPie(QRectF(left - self.padding, top - self.padding,
                                    self.padding * 2, self.padding * 2), 90 * 16, 90 * 16)
                # Top-right corner
                tr_gradient = QRadialGradient(QPointF(right, top), self.padding)
                tr_gradient.setColorAt(0, color)
                tr_gradient.setColorAt(1, QColor(0, 0, 0, 0))
                painter.setBrush(tr_gradient)
                painter.drawPie(QRectF(right - self.padding, top - self.padding,
                                    self.padding * 2, self.padding * 2), 0 * 16, 90 * 16)
                # Bottom-left corner
                bl_gradient = QRadialGradient(QPointF(left, bottom), self.padding)
                bl_gradient.setColorAt(0, color)
                bl_gradient.setColorAt(1, QColor(0, 0, 0, 0))
                painter.setBrush(bl_gradient)
                painter.drawPie(QRectF(left - self.padding, bottom - self.padding,
                                    self.padding * 2, self.padding * 2), 180 * 16, 90 * 16)
                # Bottom-right corner
                br_gradient = QRadialGradient(QPointF(right, bottom), self.padding)
                br_gradient.setColorAt(0, color)
                br_gradient.setColorAt(1, QColor(0, 0, 0, 0))
                painter.setBrush(br_gradient)
                painter.drawPie(QRectF(right - self.padding, bottom - self.padding,
                                    self.padding * 2, self.padding * 2), 270 * 16, 90 * 16)

        def updatePosition(self):
            is_mini = not self.member_proxy.isVisible()
            if is_mini:
                diameter = self.member_ellipse.rect().width()
                center = QPointF(diameter / 2, diameter / 2)
            else:
                proxy_rect = self.member_proxy.boundingRect()
                scale = self.member_proxy.scale()
                visual_width = proxy_rect.width() * scale
                visual_height = proxy_rect.height() * scale
                center = QPointF(visual_width / 2, visual_height / 2)
            self.setPos(center)


class BaseLine(QGraphicsPathItem):
    """A base class for lines to remove duplicated path calculation logic."""

    def __init__(self, parent, config=None):
        super().__init__()
        from src.gui.style import TEXT_COLOR
        self.parent = parent
        self.selection_path = None
        self.looper_midpoint = None
        self.config: Dict[str, Any] = config if config else {}

        self.setAcceptHoverEvents(True)
        self.color = QColor(TEXT_COLOR)
        self.setPen(QPen(self.color, 2, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin))
        self.setZValue(-1)

    def updatePosition(self):
        self.updatePath()
        if self.scene():
            self.scene().update(self.scene().sceneRect())

    def _calculate_path(self, start_point, end_point):
        """Calculates and returns the QPainterPath for the line."""
        start_point += QPointF(2, 2)
        end_point += QPointF(2, 2)
        is_looper = self.config.get('looper', False)
        path = QPainterPath(start_point)

        if is_looper:
            line_is_under = start_point.y() >= end_point.y()
            extender_side = 'left' if (line_is_under and start_point.y() > end_point.y()) or (
                        not line_is_under and start_point.y() < end_point.y()) else 'right'
            y_diff = abs(start_point.y() - end_point.y())
            if not line_is_under:
                y_diff = -y_diff

            x_rad, y_rad = 25, 25 if line_is_under else -25

            # Right-side curve
            cp1 = QPointF(start_point.x() + x_rad, start_point.y())
            cp2 = QPointF(start_point.x() + x_rad, start_point.y() + y_rad)
            path.cubicTo(cp1, cp2, QPointF(start_point.x() + x_rad, start_point.y() + y_rad))
            if extender_side == 'right':
                path.lineTo(QPointF(start_point.x() + x_rad, start_point.y() + y_rad + y_diff))
            var = y_diff if extender_side == 'right' else 0
            cp3 = QPointF(start_point.x() + x_rad, start_point.y() + y_rad + var + y_rad)
            cp4 = QPointF(start_point.x(), start_point.y() + y_rad + var + y_rad)
            path.cubicTo(cp3, cp4, QPointF(start_point.x(), start_point.y() + y_rad + var + y_rad))

            # Horizontal line with triangle
            x_diff = max(50, start_point.x() - end_point.x())
            line_y = start_point.y() + y_rad + var + y_rad
            mid_point = QPointF(start_point.x() - (x_diff / 2), line_y)
            self.looper_midpoint = mid_point

            side_length, gap = 15.0, 4.0
            triangle_height = (side_length * math.sqrt(3)) / 2
            p_base_top = QPointF(mid_point.x(), mid_point.y() - side_length / 2.0)
            p_base_bottom = QPointF(mid_point.x(), mid_point.y() + side_length / 2.0)
            p_apex_left = QPointF(mid_point.x() - triangle_height, mid_point.y())
            line1_end = QPointF(mid_point.x() + gap / 2.0, line_y)
            line2_start = QPointF(p_apex_left.x() - gap / 2.0, line_y)
            final_line_end = QPointF(start_point.x() - x_diff, line_y)

            path.lineTo(line1_end)
            path.moveTo(p_base_top)
            path.lineTo(p_apex_left)
            path.lineTo(p_base_bottom)
            path.closeSubpath()
            path.moveTo(line2_start)
            path.lineTo(final_line_end)

            # Left-side curve
            line_to = QPointF(start_point.x() - x_diff - x_rad, start_point.y() + y_rad + var)
            cp5 = QPointF(start_point.x() - x_diff - x_rad, start_point.y() + y_rad + var + y_rad)
            path.cubicTo(cp5, line_to, line_to)
            if extender_side == 'left':
                line_to.setY(line_to.y() - y_diff)
            else:
                line_to.setY(line_to.y() + y_diff)
            path.lineTo(line_to)
            diag_pt_top_right = QPointF(line_to.x() + x_rad, line_to.y() - y_rad)
            cp7 = QPointF(diag_pt_top_right.x() - x_rad, diag_pt_top_right.y() + y_rad)
            cp8 = QPointF(diag_pt_top_right.x() - x_rad, diag_pt_top_right.y())
            path.cubicTo(cp7, cp8, diag_pt_top_right)

            path.lineTo(end_point)
        else:
            x_distance = (end_point - start_point).x()
            y_distance = abs((end_point - start_point).y())
            fraction = 0.61
            offset = x_distance * fraction
            offset = min(offset, -40) if offset < 0 else min(max(offset, 40), y_distance)
            offset = abs(offset)
            path.cubicTo(start_point + QPointF(offset, 0), end_point - QPointF(offset, 0), end_point)
            self.looper_midpoint = None

        return path

    def updateSelectionPath(self):
        stroker = QPainterPathStroker()
        stroker.setWidth(20)
        self.selection_path = stroker.createStroke(self.path())

    def shape(self):
        return self.selection_path if self.selection_path else super().shape()


class InsertableLine(BaseLine):
    def __init__(self, parent, member_bundle, source_member_index, member_index, config=None):
        super().__init__(parent, config)
        self.member_bundle = member_bundle.copy()
        self.source_member_index = source_member_index
        self.target_member_index = member_index
        self.updatePath()

    def paint(self, painter, option, widget):
        line_width = 4 if self.isSelected() else 2
        current_pen = self.pen()
        current_pen.setWidth(line_width)

        has_no_mappings = len(self.config.get('mappings.data', [])) == 0
        if self.config.get('conditional', False):
            current_pen.setStyle(Qt.DashLine)
        if has_no_mappings:
            color = current_pen.color()
            color.setAlphaF(0.5)
            current_pen.setColor(color)

        painter.setPen(current_pen)
        painter.drawPath(self.path())

    def updatePath(self):
        start_point = self.parent.new_agents[self.source_member_index][1].output_point.scenePos()
        end_point = self.parent.new_agents[self.target_member_index][1].input_point.scenePos()
        path = self._calculate_path(start_point, end_point)
        self.setPath(path)
        self.updateSelectionPath()


class ConnectionLine(BaseLine):
    def __init__(self, parent, source_member, target_member=None, config=None):
        super().__init__(parent, config)
        self.setFlag(QGraphicsItem.ItemIsSelectable)
        self.source_member_id = source_member.id
        self.target_member_id = target_member.id if target_member else None
        self.start_point = source_member.output_point
        self.end_point = target_member.input_point if target_member else None
        self.updatePath()

    def paint(self, painter, option, widget):
        line_width = 4 if self.isSelected() else 2
        current_pen = self.pen()
        current_pen.setWidth(line_width)

        mappings_data = self.config.get('mappings.data', [])
        is_conditional = self.config.get('conditional', False)
        if is_conditional:
            current_pen.setStyle(Qt.DashLine)

        if not mappings_data:
            faded_color = current_pen.color()
            faded_color.setAlphaF(0.31)
            current_pen.setColor(faded_color)
            painter.setPen(current_pen)
            painter.drawPath(self.path())
        else:
            from src.gui.style import TEXT_COLOR, PARAM_COLOR, STRUCTURE_COLOR
            color_codes = {"Output": QColor(TEXT_COLOR), "Message": QColor(TEXT_COLOR), "Param": QColor(PARAM_COLOR),
                           "Structure": QColor(STRUCTURE_COLOR)}

            gradient = QLinearGradient(self.path().pointAtPercent(0), self.path().pointAtPercent(1))
            source_colors = list(
                dict.fromkeys([color_codes.get(m['source'], QColor(TEXT_COLOR)) for m in mappings_data]))
            target_colors = list(
                dict.fromkeys([color_codes.get(m['target'], QColor(TEXT_COLOR)) for m in mappings_data]))

            num_dashes = int(self.path().length() / 10)
            if len(source_colors) > 1 and len(target_colors) == 1:
                for i in range(num_dashes):
                    gradient.setColorAt(i / num_dashes, source_colors[i % len(source_colors)])
                    gradient.setColorAt((i + 1) / num_dashes,
                                        self.blend_colors(source_colors[i % len(source_colors)], target_colors[0], 0.5))
            elif len(source_colors) > 1 or len(target_colors) > 1:
                for i in range(num_dashes):
                    gradient.setColorAt(i / num_dashes, source_colors[i % len(source_colors)])
                    gradient.setColorAt((i + 1) / num_dashes, target_colors[i % len(target_colors)])
            else:
                gradient.setColorAt(0, source_colors[0] if source_colors else QColor(TEXT_COLOR))
                gradient.setColorAt(1, target_colors[0] if target_colors else QColor(TEXT_COLOR))

            current_pen.setBrush(gradient)
            painter.setPen(current_pen)
            painter.drawPath(self.path())

    @staticmethod
    def blend_colors(color1, color2, ratio):
        r = int(color1.red() * (1 - ratio) + color2.red() * ratio)
        g = int(color1.green() * (1 - ratio) + color2.green() * ratio)
        b = int(color1.blue() * (1 - ratio) + color2.blue() * ratio)
        return QColor(r, g, b)

    def updateEndPoint(self, end_point_pos):
        closest_member = None
        min_dist = float('inf')
        for member in self.parent.members_in_view.values():
            if member.id == self.source_member_id:
                continue
            dist = (member.input_point.scenePos() - end_point_pos).manhattanLength()
            if dist < min_dist:
                min_dist = dist
                closest_member = member

        if min_dist < 20 and closest_member:
            self.end_point = closest_member.input_point.scenePos()
            self.config['looper'] = self.parent.check_for_circular_references(closest_member.id,
                                                                              [self.source_member_id])
        else:
            self.end_point = end_point_pos
            self.config['looper'] = False
        self.updatePath()

    def updatePath(self):
        if self.end_point is None:
            return
        start_pos = self.start_point.scenePos() if isinstance(self.start_point, QGraphicsItem) else self.start_point
        end_pos = self.end_point.scenePos() if isinstance(self.end_point, QGraphicsItem) else self.end_point
        path = self._calculate_path(start_pos, end_pos)
        self.setPath(path)
        self.updateSelectionPath()


class ConnectionPoint(QGraphicsEllipseItem):
    def __init__(self, parent, is_input):
        super().__init__(0, 0, 4, 4, parent)
        self.is_input = is_input
        self.setBrush(QBrush(Qt.darkGray))
        self.connections = []

    def setHighlighted(self, highlighted):
        if highlighted:
            self.setBrush(QBrush(Qt.red))
        else:
            self.setBrush(QBrush(Qt.darkGray))

    def contains(self, point):
        distance = (point - self.rect().center()).manhattanLength()
        return distance <= 12


# class RoundedRectWidget(QGraphicsWidget):
#     def __init__(self, parent, points, member_ids, rounding_radius=25):
#         super().__init__()
#         self.parent = parent
#         self.member_ids = member_ids
#
#         self.rounding_radius = rounding_radius
#         self.setZValue(-2)
#
#         # points is a list of QPointF points, all must be within the bounds
#         lowest_x = min([point.x() for point in points])
#         lowest_y = min([point.y() for point in points])
#         btm_left = QPointF(lowest_x, lowest_y)
#
#         highest_x = max([point.x() for point in points])
#         highest_y = max([point.y() for point in points])
#         top_right = QPointF(highest_x, highest_y)
#
#         # Calculate width and height from l_bound and u_bound
#         width = abs(btm_left.x() - top_right.x()) + 50
#         height = abs(btm_left.y() - top_right.y()) + 50
#
#         # Set size policy and preferred size
#         self.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)
#         self.setPreferredSize(width, height)
#
#         # Set the position based on the l_bound
#         self.setPos(btm_left)
#
#     def boundingRect(self):
#         return QRectF(0, 0, self.preferredWidth(), self.preferredHeight())
#
#     def paint(self, painter, option, widget):
#         from src.gui.style import TEXT_COLOR
#         rect = self.boundingRect()
#         painter.setRenderHint(QPainter.Antialiasing)
#
#         # Set brush with 20% opacity color
#         color = QColor(TEXT_COLOR)
#         color.setAlpha(50)
#         painter.setBrush(QBrush(color))
#
#         painter.setPen(Qt.NoPen)
#         painter.drawRoundedRect(rect, self.rounding_radius, self.rounding_radius)
