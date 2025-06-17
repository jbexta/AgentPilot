
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
    merge_config_into_workflow_config, get_member_name_from_config, block_signals, display_message, apply_alpha_to_hex, \
    set_module_type, merge_multiple_into_workflow_config


@set_module_type('Widgets')
class WorkflowSettings(ConfigWidget):
    def __init__(self, parent, **kwargs):
        super().__init__(parent=parent)
        self.compact_mode: bool = kwargs.get('compact_mode', False)  # For use in agent page
        self.compact_mode_editing: bool = False

        self.setSizePolicy(QSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding))

        self.members_in_view: Dict[str, DraggableMember] = {}
        self.inputs_in_view: Dict[Tuple[str, str], ConnectionLine] = {}  # (source_member_id, target_member_id): line
        self.boxes_in_view: List[List[RoundedRectWidget]] = []

        self.new_lines: Optional[List[InsertableLine]] = None
        self.new_agents: Optional[List[Tuple[QPointF, DraggableMember]]] = None  # InsertableMember]]] = None
        self.adding_line: Optional[ConnectionLine] = None
        self.del_pairs: Optional[Any] = None

        self.autorun: bool = True

        self.layout = CVBoxLayout(self)
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

        self.workflow_config = self.WorkflowConfig(parent=self)
        self.workflow_config.build_schema()

        self.workflow_description = self.WorkflowDescription(parent=self)
        self.workflow_description.build_schema()

        self.workflow_params = self.WorkflowParams(parent=self)
        self.workflow_params.build_schema()

        # self.workflow_extras = None  # not added here

        self.scene.selectionChanged.connect(self.on_selection_changed)

        self.workflow_panel = QWidget()
        panel_layout = CVBoxLayout(self.workflow_panel)
        panel_layout.addWidget(self.compact_mode_back_button)
        panel_layout.addWidget(self.workflow_params)
        panel_layout.addWidget(self.workflow_description)
        panel_layout.addWidget(self.workflow_config)
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
        if json_config.get('_TYPE', 'agent') != 'workflow':
            json_config = merge_config_into_workflow_config(json_config)

        json_wf_config = json_config.get('config', {})
        json_wf_params = json_config.get('params', [])
        self.workflow_config.load_config(json_wf_config)
        self.workflow_params.load_config({'data': json_wf_params})  # !55! #
        super().load_config(json_config)

    @override
    def get_config(self):
        workflow_config = self.workflow_config.get_config()
        workflow_config['autorun'] = self.workflow_buttons.autorun
        workflow_config['show_hidden_bubbles'] = self.workflow_buttons.show_hidden_bubbles
        workflow_config['show_nested_bubbles'] = self.workflow_buttons.show_nested_bubbles
        # workflow_config['mini_view'] = self.view.mini_view

        workflow_params = self.workflow_params.get_config()

        config = {
            '_TYPE': 'workflow',
            'members': [],
            'inputs': [],
            'config': workflow_config,
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
                'width': proxy_size.width(),
                'height': proxy_size.height(),
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

        self.load_async_groups()
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
        self.load_async_groups()
        self.member_config_widget.load()
        self.workflow_params.load()
        self.workflow_config.load()
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

    def load_async_groups(self):
        # Clear any existing members from the scene
        for box in self.boxes_in_view:
            self.scene.removeItem(box)
        self.boxes_in_view = []

        last_member_id = None
        last_member_pos = None
        last_loc_x = -100
        current_box_member_positions = []
        current_box_member_ids = []

        members = self.members_in_view.values()
        members = sorted(members, key=lambda m: m.x())

        for member in members:
            loc_x = member.x()
            loc_y = member.y()
            pos = QPointF(loc_x, loc_y)

            from src.system import manager
            member_type = member.member_config.get('_TYPE', 'agent')
            member_class = manager.modules.get_module_class('Members', module_name=member_type)
            if not member_class:
                display_message(self,
                    message=f"Member module '{member_type}' not found.",
                    icon=QMessageBox.Warning,
                )
                continue

            if member_class.allow_async:
                if abs(loc_x - last_loc_x) < 10:
                    current_box_member_positions += [last_member_pos, pos]
                    current_box_member_ids += [last_member_id, member.id]
                else:
                    if current_box_member_positions:
                        box = RoundedRectWidget(self, points=current_box_member_positions, member_ids=current_box_member_ids)
                        self.scene.addItem(box)
                        self.boxes_in_view.append(box)
                        current_box_member_positions = []
                        current_box_member_ids = []

                last_loc_x = loc_x
                last_member_pos = pos
                last_member_id = member.id

        # Handle the last group after finishing the loop
        if current_box_member_positions:
            box = RoundedRectWidget(self, points=current_box_member_positions, member_ids=current_box_member_ids)
            self.scene.addItem(box)
            self.boxes_in_view.append(box)

        del_boxes = []
        for box in self.boxes_in_view:
            for member_id in box.member_ids:
                fnd = self.walk_inputs_recursive(member_id, box.member_ids)
                if fnd:
                    del_boxes.append(box)
                    break

        for box in del_boxes:
            self.scene.removeItem(box)
            self.boxes_in_view.remove(box)

    def load_inputs(self):
        for _, line in self.inputs_in_view.items():
            self.scene.removeItem(line)
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

        if visible:
            self.reposition_view()

    def reposition_view(self):
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

        # return  # todo

        if len(selected_objects) == 1:
            if len(selected_agents) == 1:
                member = selected_agents[0]
                self.member_config_widget.display_member(member)
                if hasattr(self.member_config_widget.config_widget, 'reposition_view'):
                    self.member_config_widget.config_widget.reposition_view()

            elif len(selected_lines) == 1:
                line = selected_lines[0]
                self.member_config_widget.show_input(line)

        else:
            is_vis = self.member_config_widget.isVisible()
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
            entity_config = entity.config
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
        return  # todo
        if self.compact_mode or not self.linked_workflow():
            return
        for member in self.members_in_view.values():
            member.highlight_background.hide()

        workflow = self.linked_workflow()
        next_expected_member = workflow.next_expected_member()
        if not next_expected_member:
            return

        # if next_expected_member:
        #     self.members_in_view[next_expected_member.member_id].highlight_background.show()

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
            widget = widget.member_config_widget.workflow_settings
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

            self.setDragMode(QGraphicsView.RubberBandDrag)

        def toggle_mini_view(self):
            self.mini_view = not self.mini_view
            self.refresh_mini_view()
        #     """Sets the mini view mode."""
        #     if state == self.mini_view:
        #         return
        #     self.mini_view = state
        #     self.refresh_mini_view()

        def refresh_mini_view(self):  # , state: bool):
            """Toggles the mini view mode."""
            # self.mini_view = not self.mini_view
            # print('Refresh mini view mode as: ', self.mini_view)
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
            # super().mouseReleaseEvent(event)
            # return  # todo

            self.setDragMode(QGraphicsView.RubberBandDrag)
            self._is_panning = False
            self._mouse_press_pos = None
            self._mouse_press_scroll_x_val = None
            self._mouse_press_scroll_y_val = None
            self.setCursor(Qt.ArrowCursor)
            super().mouseReleaseEvent(event)
            main = find_main_widget(self)
            if main:
                main.mouseReleaseEvent(event)

        def mousePressEvent(self, event):
            # super().mousePressEvent(event)
            # return  # todo

            self.temp_block_move_flag = False

            if self.parent.new_agents:
                self.parent.add_entity()
                return

            panning_triggered = False
            if event.button() == Qt.LeftButton:
                is_over_item = self.itemAt(event.pos()) is not None
                if not self.mini_view and not is_over_item:
                    panning_triggered = True
                elif self.mini_view and event.modifiers() == Qt.ControlModifier:
                    panning_triggered = True

            if panning_triggered:
                self.setDragMode(QGraphicsView.NoDrag)
                self.setCursor(Qt.ClosedHandCursor)
                self._is_panning = True
                self._mouse_press_pos = event.pos()
                self._mouse_press_scroll_x_val = self.horizontalScrollBar().value()
                self._mouse_press_scroll_y_val = self.verticalScrollBar().value()
                event.accept()
                return

            self.setDragMode(QGraphicsView.RubberBandDrag)
            self._is_panning = False

            # Let the event propagate to the items in the scene first.
            super().mousePressEvent(event)
            if event.isAccepted():
                return

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

        def mouseMoveEvent(self, event):
            # super().mouseMoveEvent(event)
            # return  # todo

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
            # super().keyPressEvent(event)
            # return  # todo

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

            self.btn_link = ToggleIconButton(
                parent=self,
                icon_path=':/resources/icon-unlink.png',
                icon_path_checked=':/resources/icon-link.png',
                target=self.toggle_link,  # partial(self.toggle_attribute, 'autorun'),
                tooltip="Link member to it's source",
                tooltip_checked="Unlink member from it's source",
                opacity=0.3,
                opacity_when_checked=1.0,
                size=self.icon_size,
            )

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

            self.layout.addWidget(self.btn_link)

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

            self.btn_workflow_config = ToggleIconButton(
                parent=self,
                icon_path=':/resources/icon-settings-solid.png',
                target=self.toggle_workflow_config,
                tooltip='Workflow config',
                size=self.icon_size,
            )

            self.layout.addWidget(self.btn_disable_autorun)
            self.layout.addWidget(self.btn_member_list)
            self.layout.addWidget(self.btn_view)
            self.layout.addWidget(self.btn_workflow_params)
            self.layout.addWidget(self.btn_toggle_description)
            self.layout.addWidget(self.btn_workflow_config)

            self.workflow_is_linked = self.parent.linked_workflow() is not None

            self.btn_clear_chat.setVisible(self.workflow_is_linked)
            self.btn_view.setVisible(self.workflow_is_linked)
            self.btn_disable_autorun.setVisible(self.workflow_is_linked)
            self.btn_member_list.setVisible(self.workflow_is_linked)

        def load(self):
            with block_signals(self):
                workflow_settings = self.parent
                workflow_config = workflow_settings.config.get('config', {})
                self.autorun = workflow_config.get('autorun', True)
                self.show_hidden_bubbles = workflow_config.get('show_hidden_bubbles', False)
                self.show_nested_bubbles = workflow_config.get('show_nested_bubbles', False)

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
                self.btn_workflow_config.setVisible(is_multi_member or not any_is_agent)

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
                self.btn_link.setChecked(selected_is_linked)
                self.btn_link.setVisible(selected_count == 1)

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
            all_del_objects_old_brushes = []
            all_del_objects_old_pens = []

            workflow_settings = self.parent
            scene = workflow_settings.view.scene()
            for selected_item in scene.selectedItems():
                all_del_objects.append(selected_item)

                if isinstance(selected_item, DraggableMember):
                    del_member_ids.add(selected_item.id)

                    # Loop through all lines to find the ones connected to the selected agent
                    for key, line in workflow_settings.inputs_in_view.items():
                        source_member_id, target_member_id = key
                        if target_member_id == selected_item.id or source_member_id == selected_item.id:
                            del_inputs.add((source_member_id, target_member_id))
                            all_del_objects.append(line)

                elif isinstance(selected_item, ConnectionLine):
                    del_inputs.add((selected_item.source_member_id, selected_item.target_member_id))

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

            scene.update()

            # ask for confirmation
            retval = display_message_box(
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
                scene.removeItem(obj)

            for member_id in del_member_ids:
                workflow_settings.members_in_view.pop(member_id)
            for line_key in del_inputs:
                workflow_settings.inputs_in_view.pop(line_key)

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

        def toggle_workflow_config(self):
            self.show_toggle_widget(self.btn_workflow_config)

        def show_toggle_widget(self, toggle_btn):
            all_toggle_widgets = {
                self.btn_workflow_params: self.parent.workflow_params,
                self.btn_workflow_config: self.parent.workflow_config,
                self.btn_toggle_description: self.parent.workflow_description,
            }
            for btn, widget in all_toggle_widgets.items():
                if btn.isChecked() and btn != toggle_btn:
                    btn.setChecked(False)
                    widget.setVisible(False)

            is_checked = not toggle_btn.isChecked()  # the not is a dirty hack todo
            toggle_btn.setChecked(not is_checked)
            all_toggle_widgets[toggle_btn].setVisible(not is_checked)

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

    class WorkflowConfig(ConfigJoined):
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

    def update_config(self):
        self.save_config()

    def save_config(self):
        config = self.config_widget.get_config()
        self.parent.members_in_view[self.config_widget.member_id].member_config = config
        self.parent.update_config()

    def display_member(self, member):
        clear_layout(self.layout)
        member_type = member.member_type
        member_config = member.member_config

        # return
        member_settings_class = get_member_settings_class(member_type)

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
        clear_layout(self.layout)
        self.config_widget.load_config(config)
        self.config_widget.build_schema()
        self.config_widget.load()
        self.layout.addWidget(self.config_widget)
        self.show()
        # if hasattr(self.config_widget, 'reposition_view'):
        #     self.config_widget.reposition_view()


# # # class InsertableMember(QGraphicsEllipseItem):
# # #     def __init__(self, parent, config, linked_id, pos):
# # #         self.member_type = config.get('_TYPE', 'agent')
# # #         self.member_config = config
# # #         diameter = 50 if self.member_type != 'node' else 20
# # #         super().__init__(0, 0, diameter, diameter)
# # #         from src.gui.style import TEXT_COLOR
# # #
# # #         self.parent = parent
# # #         member_type = config.get('_TYPE', 'agent')
# # #         self.config: Dict[str, Any] = config
# # #         self.linked_id = linked_id
# # #
# # #         self.input_point = ConnectionPoint(self, True)
# # #         self.output_point = ConnectionPoint(self, False)
# # #         # take into account the diameter of the points
# # #         self.input_point.setPos(0, self.rect().height() / 2 - 2)
# # #         self.output_point.setPos(self.rect().width() - 4, self.rect().height() / 2 - 2)
# # #
# # #         pen = QPen(QColor(TEXT_COLOR), 1)
# # #
# # #         if member_type not in ['user', 'agent']:
# # #             pen = None
# # #         self.setPen(pen if pen else Qt.NoPen)
# # #         self.refresh_avatar()
# # #
# # #         self.setCentredPos(pos)
# # #
# # #     def refresh_avatar(self):
# # #         from src.gui.style import TEXT_COLOR
# # #         if self.member_type == 'node':
# # #             self.setBrush(QBrush(QColor(TEXT_COLOR)))
# # #             return
# # #
# # #         hide_bubbles = self.config.get('group.hide_bubbles', False)
# # #         opacity = 0.2 if hide_bubbles else 1
# # #
# # #         avatar_paths = get_avatar_paths_from_config(self.config)
# # #
# # #         diameter = 50
# # #         pixmap = path_to_pixmap(avatar_paths, opacity=opacity, diameter=diameter)
# # #
# # #         if pixmap:
# # #             self.setBrush(QBrush(pixmap.scaled(diameter, diameter)))
# # #
# # #     def setCentredPos(self, pos):
# # #         self.setPos(pos.x() - self.rect().width() / 2, pos.y() - self.rect().height() / 2)
# #
# #
# class DraggableMember(QGraphicsObject):
#     def __init__(
#             self,
#             workflow_settings,
#             member_id: str,
#             linked_id: str,
#             loc_x: int,
#             loc_y: int,
#             width: Optional[int],
#             height: Optional[int],
#             member_config: Dict[str, Any]
#     ):
#         super().__init__()
#
#         self.workflow_settings = workflow_settings
#         self.id = member_id
#         self.linked_id = linked_id
#         self.member_type = member_config.get('_TYPE', 'agent')
#         self.member_config = member_config
#
#         self.member_ellipse = self.MemberEllipse(self, diameter=50 if self.member_type != 'node' else 20)
#         self.member_proxy = self.MemberProxy(self)
#
#         # Apply initial size for proxy
#         if width and height:
#             scale = self.member_proxy.scale()
#             self.member_proxy.resize(width / scale, height / scale)
#
#         # --- Setup Item Flags and Position ---
#         self.setPos(loc_x, loc_y)
#         self.setFlag(QGraphicsItem.ItemIsMovable)
#         self.setFlag(QGraphicsItem.ItemIsSelectable)
#
#         # --- Child Items ---
#         self.input_point = ConnectionPoint(self, True)
#         self.output_point = ConnectionPoint(self, False)
#         self.highlight_background = self.HighlightBackground(self)
#         self.highlight_background.hide()
#
#         # --- Finalize ---
#         self.update_visuals()
#
#     class MemberEllipse(QGraphicsEllipseItem):
#         def __init__(self, parent, diameter):
#             super().__init__(0, 0, diameter, diameter, parent=parent)
#             from src.gui.style import TEXT_COLOR
#             self.setPen(QPen(QColor(TEXT_COLOR), 1) if parent.member_type in ['user', 'agent'] else Qt.NoPen)
#             self.setBrush(QBrush(QColor(TEXT_COLOR)))
#             self.setAcceptHoverEvents(True)
#
#     class MemberProxy(QGraphicsProxyWidget):
#         def __init__(self, parent):
#             super().__init__(parent=parent)
#             self.setScale(0.5)
#             self.config_widget = None
#             self.member_settings_class = get_member_settings_class(parent.member_type)
#
#         def show(self):
#             if self.member_settings_class and self.config_widget is None:
#                 self.config_widget = self.member_settings_class(parent=self)
#                 self.config_widget.build_schema()
#                 self.setWidget(self.config_widget)
#             super().show()
#
#     def boundingRect(self):
#         if self.workflow_settings.view.mini_view or not self.member_proxy.widget():
#             return self.member_ellipse.boundingRect()
#         else:
#             pr = self.member_proxy.boundingRect()
#             scale = self.member_proxy.scale()
#             # Add padding for the resize handles
#             padding = self.resize_handle_size
#             return QRectF(pr.topLeft(), QSize(pr.width() * scale, pr.height() * scale)).adjusted(-padding, -padding, padding, padding)
#
#     def paint(self, painter, option, widget=None):  # Don't delete
#         pass
#
#     def setCentredPos(self, pos):
#         self.setPos(pos.x() - self.rect().width() / 2, pos.y() - self.rect().height() / 2)
#
#     def update_visuals(self):
#         self.prepareGeometryChange()
#         is_mini = self.workflow_settings.view.mini_view
#
#         has_proxy = self.member_proxy.member_settings_class is not None
#         self.member_ellipse.setVisible(is_mini or not has_proxy)
#         if has_proxy:
#             if is_mini:
#                 self.member_proxy.hide()
#             else:
#                 self.member_proxy.show()  # need to call show()
#         #     self.member_proxy.setVisible(not is_mini)
#         # # self.highlight_background.set_mode(is_mini)
#
#         if is_mini or not has_proxy:
#             rect = self.member_ellipse.rect()
#         else:
#             pr = self.member_proxy.boundingRect()
#             scale = self.member_proxy.scale()
#             rect = QRectF(pr.topLeft(), QSize(pr.width() * scale, pr.height() * scale))
#
#         self.input_point.setPos(rect.left(), rect.center().y() - self.input_point.boundingRect().height()/2)
#         self.output_point.setPos(rect.right() - self.output_point.boundingRect().width(), rect.center().y() - self.output_point.boundingRect().height()/2)
#
#         # self.highlight_background.setPos(center_x, center_y)
#
#     def refresh_avatar(self):
#         from src.gui.style import TEXT_COLOR
#         if self.member_type == 'node':
#             self.member_ellipse.setBrush(QBrush(QColor(TEXT_COLOR)))
#             return
#
#         hide_bubbles = self.member_config.get('group.hide_bubbles', False)
#         in_del_pairs = False if not self.workflow_settings.del_pairs else self in self.workflow_settings.del_pairs
#         opacity = 0.2 if (hide_bubbles or in_del_pairs) else 1
#         avatar_paths = get_avatar_paths_from_config(self.member_config)
#
#         diameter = self.member_ellipse.rect().width()
#         pixmap = path_to_pixmap(avatar_paths, opacity=opacity, diameter=diameter)
#
#         if pixmap:
#             self.member_ellipse.setBrush(QBrush(pixmap.scaled(diameter, diameter)))
#
#     # --- Resizing Logic ---
#     def get_handle_at(self, pos: QPointF):
#         """Identifies which resize handle is at a given position."""
#         rect = self.member_proxy.geometry()
#         handle_size = self.resize_handle_size
#
#         on_top = abs(pos.y() - rect.top()) < handle_size
#         on_bottom = abs(pos.y() - rect.bottom()) < handle_size
#         on_left = abs(pos.x() - rect.left()) < handle_size
#         on_right = abs(pos.x() - rect.right()) < handle_size
#
#         if on_top and on_left: return self.TopLeft
#         if on_top and on_right: return self.TopRight
#         if on_bottom and on_left: return self.BottomLeft
#         if on_bottom and on_right: return self.BottomRight
#         if on_top: return self.Top
#         if on_bottom: return self.Bottom
#         if on_left: return self.Left
#         if on_right: return self.Right
#         return self.NoHandle
#
#     def set_cursor_for_handle(self, handle):
#         """Sets the cursor shape based on the handle."""
#         if handle in (self.TopLeft, self.BottomRight):
#             self.setCursor(Qt.SizeFDiagCursor)
#         elif handle in (self.TopRight, self.BottomLeft):
#             self.setCursor(Qt.SizeBDiagCursor)
#         elif handle in (self.Top, self.Bottom):
#             self.setCursor(Qt.SizeVerCursor)
#         elif handle in (self.Left, self.Right):
#             self.setCursor(Qt.SizeHorCursor)
#         else:
#             self.setCursor(Qt.ArrowCursor)
#
#     def mousePressEvent(self, event: QGraphicsSceneMouseEvent):
#         handle = self.get_handle_at(event.pos())
#         if handle != self.NoHandle and self.isSelected() and not self.workflow_settings.view.mini_view:
#             self.is_resizing = True
#             self.current_resize_handle = handle
#             self.original_geometry = self.geometry()
#             self.original_mouse_pos = event.scenePos()
#             self.setFlag(QGraphicsItem.ItemIsMovable, False)
#             event.accept()
#         else:
#             super().mousePressEvent(event)
#
#     def mouseMoveEvent(self, event: QGraphicsSceneMouseEvent):
#         if self.is_resizing:
#             delta = event.scenePos() - self.original_mouse_pos
#             new_geom = QRectF(self.original_geometry)
#
#             if self.current_resize_handle == self.Top:
#                 new_geom.setTop(self.original_geometry.top() + delta.y())
#             elif self.current_resize_handle == self.Bottom:
#                 new_geom.setBottom(self.original_geometry.bottom() + delta.y())
#             elif self.current_resize_handle == self.Left:
#                 new_geom.setLeft(self.original_geometry.left() + delta.x())
#             elif self.current_resize_handle == self.Right:
#                 new_geom.setRight(self.original_geometry.right() + delta.x())
#             elif self.current_resize_handle == self.TopLeft:
#                 new_geom.setTopLeft(self.original_geometry.topLeft() + delta)
#             elif self.current_resize_handle == self.TopRight:
#                 new_geom.setTopRight(self.original_geometry.topRight() + delta)
#             elif self.current_resize_handle == self.BottomLeft:
#                 new_geom.setBottomLeft(self.original_geometry.bottomLeft() + delta)
#             elif self.current_resize_handle == self.BottomRight:
#                 new_geom.setBottomRight(self.original_geometry.bottomRight() + delta)
#
#             # Enforce minimum size
#             if new_geom.width() < self.minimum_size.width(): new_geom.setWidth(self.minimum_size.width())
#             if new_geom.height() < self.minimum_size.height(): new_geom.setHeight(self.minimum_size.height())
#
#             self.prepareGeometryChange()
#             self.setPos(new_geom.topLeft())
#
#             scale = self.member_proxy.scale()
#             self.member_proxy.resize(new_geom.width() / scale, new_geom.height() / scale)
#
#             self.update_visuals()
#             for line in self.workflow_settings.inputs_in_view.values():
#                 if line.source_member_id == self.id or line.target_member_id == self.id:
#                     line.updatePosition()
#             event.accept()
#         else:
#             super().mouseMoveEvent(event)
#
#     def mouseReleaseEvent(self, event: QGraphicsSceneMouseEvent):
#         if self.is_resizing:
#             self.is_resizing = False
#             self.current_resize_handle = self.NoHandle
#             self.setFlag(QGraphicsItem.ItemIsMovable, True)
#             self.save_pos()
#             event.accept()
#         else:
#             super().mouseReleaseEvent(event)
#             self.save_pos()
#
#     def save_pos(self):
#         new_loc_x = max(0, int(self.x()))
#         new_loc_y = max(0, int(self.y()))
#
#         pr = self.member_proxy.geometry()
#         scale = self.member_proxy.scale()
#         current_size = QSize(pr.width() * scale, pr.height() * scale)
#
#         members = self.workflow_settings.config.get('members', [])
#         member = next((m for m in members if m['id'] == self.id), None)
#
#         if member:
#             pos_changed = new_loc_x != member.get('loc_x') or new_loc_y != member.get('loc_y')
#             # Compare with a tolerance for floating point issues
#             size_changed = not math.isclose(current_size.width(), member.get('width', 0)) or \
#                            not math.isclose(current_size.height(), member.get('height', 0))
#             if not pos_changed and not size_changed:
#                 return
#
#         self.workflow_settings.update_config()
#
#     def hoverMoveEvent(self, event: QGraphicsSceneHoverEvent):
#         if self.is_resizing or not self.isSelected() or self.workflow_settings.view.mini_view:
#             self.setCursor(Qt.ArrowCursor)
#             super().hoverMoveEvent(event)
#             return
#
#         handle = self.get_handle_at(event.pos())
#         self.set_cursor_for_handle(handle)
#         super().hoverMoveEvent(event)
#
#     def hoverLeaveEvent(self, event: QGraphicsSceneHoverEvent):
#         self.setCursor(Qt.ArrowCursor)
#         super().hoverLeaveEvent(event)
#
#     class HighlightBackground(QGraphicsItem):
#         def __init__(self, parent):  #, use_color=None):
#             super().__init__(parent)
#             self.member_ellipse = parent.member_ellipse
#             self.member_proxy = parent.member_proxy
#             self.padding = 15  # Glow size in pixels
#
#         def boundingRect(self):
#             is_mini = not self.member_proxy.isVisible()
#             if is_mini:
#                 outer_diameter = self.member_ellipse.rect().width() * 1.6
#                 return QRectF(-outer_diameter / 2, -outer_diameter / 2, outer_diameter, outer_diameter)
#             else:
#                 proxy_rect = self.member_proxy.boundingRect()
#                 scale = self.member_proxy.scale()
#                 scaled_width = proxy_rect.width() * scale
#                 scaled_height = proxy_rect.height() * scale
#
#                 outer_width = scaled_width + 2 * self.padding
#                 outer_height = scaled_height + 2 * self.padding
#
#                 return QRectF(-outer_width / 2, -outer_height / 2, outer_width, outer_height)
#
#         def paint(self, painter, option, widget=None):
#             from src.gui.style import TEXT_COLOR
#             color = QColor(TEXT_COLOR)
#             painter.setPen(Qt.NoPen)
#
#             is_mini = not self.member_proxy.isVisible()
#             if is_mini:
#                 outer_diameter = self.member_ellipse.rect().width() * 1.6
#                 inner_diameter = self.member_ellipse.rect().width()
#
#                 gradient = QRadialGradient(QPointF(0, 0), outer_diameter / 2)
#                 color.setAlpha(155)
#                 gradient.setColorAt(0, color)
#                 gradient.setColorAt(1, QColor(0, 0, 0, 0))
#
#                 outer_path = QPainterPath()
#                 outer_path.addEllipse(QPointF(0, 0), outer_diameter / 2, outer_diameter / 2)
#                 inner_path = QPainterPath()
#                 inner_path.addEllipse(QPointF(0, 0), inner_diameter / 2, inner_diameter / 2)
#
#                 final_path = outer_path.subtracted(inner_path)
#                 painter.setBrush(QBrush(gradient))
#                 painter.drawPath(final_path)
#             else:
#                 proxy_rect = self.member_proxy.boundingRect()
#                 scale = self.member_proxy.scale()
#
#                 inner_w = proxy_rect.width() * scale
#                 inner_h = proxy_rect.height() * scale
#                 inner_rect = QRectF(-inner_w / 2, -inner_h / 2, inner_w, inner_h)
#
#                 outer_w = inner_w + 2 * self.padding
#                 outer_h = inner_h + 2 * self.padding
#                 outer_rect = QRectF(-outer_w / 2, -outer_h / 2, outer_w, outer_h)
#
#                 rounding = 10.0
#
#                 outer_path = QPainterPath()
#                 outer_path.addRoundedRect(outer_rect, rounding, rounding)
#                 inner_path = QPainterPath()
#                 inner_path.addRoundedRect(inner_rect, rounding, rounding)
#
#                 final_path = outer_path.subtracted(inner_path)
#                 color.setAlpha(80)  # Use a solid, semi-transparent glow for the rectangle
#                 painter.setBrush(color)
#                 painter.drawPath(final_path)
# # class DraggableMember(QGraphicsObject):
# #     def __init__(
# #             self,
# #             workflow_settings,
# #             member_id: str,
# #             linked_id: str,
# #             loc_x: int,
# #             loc_y: int,
# #             width: Optional[int],
# #             height: Optional[int],
# #             member_config: Dict[str, Any]
# #     ):
# #         super().__init__()
# #
# #         self.workflow_settings = workflow_settings
# #         self.id = member_id
# #         self.linked_id = linked_id
# #         self.member_type = member_config.get('_TYPE', 'agent')
# #         self.member_config = member_config
# #
# #         self.member_ellipse = self.MemberEllipse(self, diameter=50 if self.member_type != 'node' else 20)
# #         self.member_proxy = self.MemberProxy(self)
# #
# #         # Apply initial size for proxy
# #         if width and height:
# #             scale = self.member_proxy.scale()
# #             self.member_proxy.resize(width / scale, height / scale)
# #
# #         # --- Setup Item Flags and Position ---
# #         self.setPos(loc_x, loc_y)
# #         self.setFlag(QGraphicsItem.ItemIsMovable)
# #         self.setFlag(QGraphicsItem.ItemIsSelectable)
# #
# #         # --- Child Items ---
# #         self.input_point = ConnectionPoint(self, True)
# #         self.output_point = ConnectionPoint(self, False)
# #         self.highlight_background = self.HighlightBackground(self)
# #         self.highlight_background.hide()
# #
# #         # --- Finalize ---
# #         self.update_visuals()
# #
# #     class MemberEllipse(QGraphicsEllipseItem):
# #         def __init__(self, parent, diameter):
# #             super().__init__(0, 0, diameter, diameter, parent=parent)
# #             from src.gui.style import TEXT_COLOR
# #             self.setPen(QPen(QColor(TEXT_COLOR), 1) if parent.member_type in ['user', 'agent'] else Qt.NoPen)
# #             self.setBrush(QBrush(QColor(TEXT_COLOR)))
# #             self.setAcceptHoverEvents(True)
# #
# #     class MemberProxy(QGraphicsProxyWidget):
# #         (NoHandle, Top, Bottom, Left, Right, TopLeft, TopRight, BottomLeft, BottomRight) = range(9)
# #
# #         def __init__(self, parent: 'DraggableMember'):
# #             super().__init__(parent=parent)
# #             self.member_parent = parent
# #             self.setScale(0.5)
# #             self.config_widget = None
# #             self.member_settings_class = get_member_settings_class(parent.member_type)
# #
# #             # --- Resizing state logic moved here ---
# #             self.is_resizing = False
# #             self.current_resize_handle = self.NoHandle
# #             self.resize_handle_size = 10.0
# #             self.minimum_size = QSize(150, 100)
# #             self.original_geometry = QRectF()
# #             self.original_mouse_pos = QPointF()
# #
# #             self.setAcceptHoverEvents(True)
# #
# #         def show(self):
# #             if self.member_settings_class and self.config_widget is None:
# #                 self.config_widget = self.member_settings_class(parent=self)
# #                 self.config_widget.build_schema()
# #                 self.setWidget(self.config_widget)
# #             super().show()
# #
# #         def boundingRect(self):
# #             # The bounding rect should include padding for the resize handles
# #             padding = self.resize_handle_size if self.parentItem().isSelected() else 0
# #             return self.geometry().adjusted(-padding, -padding, padding, padding)
# #
# #         # --- Resizing logic methods moved here ---
# #         def get_handle_at(self, pos: QPointF):
# #             """Identifies which resize handle is at a given position."""
# #             rect = self.geometry()
# #             handle_size = self.resize_handle_size
# #
# #             on_top = abs(pos.y() - rect.top()) < handle_size
# #             on_bottom = abs(pos.y() - rect.bottom()) < handle_size
# #             on_left = abs(pos.x() - rect.left()) < handle_size
# #             on_right = abs(pos.x() - rect.right()) < handle_size
# #
# #             if on_top and on_left: return self.TopLeft
# #             if on_top and on_right: return self.TopRight
# #             if on_bottom and on_left: return self.BottomLeft
# #             if on_bottom and on_right: return self.BottomRight
# #             if on_top: return self.Top
# #             if on_bottom: return self.Bottom
# #             if on_left: return self.Left
# #             if on_right: return self.Right
# #             return self.NoHandle
# #
# #         def set_cursor_for_handle(self, handle):
# #             """Sets the cursor shape based on the handle."""
# #             if handle in (self.TopLeft, self.BottomRight):
# #                 self.setCursor(Qt.SizeFDiagCursor)
# #             elif handle in (self.TopRight, self.BottomLeft):
# #                 self.setCursor(Qt.SizeBDiagCursor)
# #             elif handle in (self.Top, self.Bottom):
# #                 self.setCursor(Qt.SizeVerCursor)
# #             elif handle in (self.Left, self.Right):
# #                 self.setCursor(Qt.SizeHorCursor)
# #             else:
# #                 self.setCursor(Qt.ArrowCursor)
# #
# #         def mousePressEvent(self, event: QGraphicsSceneMouseEvent):
# #             handle = self.get_handle_at(event.pos())
# #             is_mini = self.member_parent.workflow_settings.view.mini_view
# #             if handle != self.NoHandle and self.member_parent.isSelected() and not is_mini:
# #                 self.is_resizing = True
# #                 self.current_resize_handle = handle
# #                 self.original_geometry = self.member_parent.geometry()
# #                 self.original_mouse_pos = event.scenePos()
# #                 self.member_parent.setFlag(QGraphicsItem.ItemIsMovable, False)
# #                 event.accept()
# #             else:
# #                 # Pass the event to the parent DraggableMember to handle movement
# #                 super().mousePressEvent(event)
# #
# #         def mouseMoveEvent(self, event: QGraphicsSceneMouseEvent):
# #             if self.is_resizing:
# #                 delta = event.scenePos() - self.original_mouse_pos
# #                 new_geom = QRectF(self.original_geometry)
# #
# #                 # Adjust geometry based on the handle being dragged
# #                 if self.current_resize_handle in (self.Top, self.TopLeft, self.TopRight):
# #                     new_geom.setTop(self.original_geometry.top() + delta.y())
# #                 if self.current_resize_handle in (self.Bottom, self.BottomLeft, self.BottomRight):
# #                     new_geom.setBottom(self.original_geometry.bottom() + delta.y())
# #                 if self.current_resize_handle in (self.Left, self.TopLeft, self.BottomLeft):
# #                     new_geom.setLeft(self.original_geometry.left() + delta.x())
# #                 if self.current_resize_handle in (self.Right, self.TopRight, self.BottomRight):
# #                     new_geom.setRight(self.original_geometry.right() + delta.x())
# #
# #                 # Enforce minimum size
# #                 scaled_min_size = self.minimum_size / self.scale()
# #                 if new_geom.width() < scaled_min_size.width():
# #                     if self.current_resize_handle in (self.Left, self.TopLeft, self.BottomLeft):
# #                         new_geom.setLeft(new_geom.right() - scaled_min_size.width())
# #                     else:
# #                         new_geom.setWidth(scaled_min_size.width())
# #                 if new_geom.height() < scaled_min_size.height():
# #                     if self.current_resize_handle in (self.Top, self.TopLeft, self.TopRight):
# #                         new_geom.setTop(new_geom.bottom() - scaled_min_size.height())
# #                     else:
# #                         new_geom.setHeight(scaled_min_size.height())
# #
# #                 self.member_parent.prepareGeometryChange()
# #                 self.member_parent.setPos(new_geom.topLeft())
# #                 self.resize(new_geom.size() / self.scale())
# #
# #                 self.member_parent.update_visuals()
# #                 for line in self.member_parent.workflow_settings.inputs_in_view.values():
# #                     if line.source_member_id == self.member_parent.id or line.target_member_id == self.member_parent.id:
# #                         line.updatePosition()
# #                 event.accept()
# #             else:
# #                 super().mouseMoveEvent(event)
# #
# #         def mouseReleaseEvent(self, event: QGraphicsSceneMouseEvent):
# #             if self.is_resizing:
# #                 self.is_resizing = False
# #                 self.current_resize_handle = self.NoHandle
# #                 self.member_parent.setFlag(QGraphicsItem.ItemIsMovable, True)
# #                 self.member_parent.save_pos()
# #                 event.accept()
# #             else:
# #                 super().mouseReleaseEvent(event)
# #
# #         def hoverMoveEvent(self, event: QGraphicsSceneHoverEvent):
# #             is_mini = self.member_parent.workflow_settings.view.mini_view
# #             if self.is_resizing or not self.member_parent.isSelected() or is_mini:
# #                 self.setCursor(Qt.ArrowCursor)
# #             else:
# #                 handle = self.get_handle_at(event.pos())
# #                 self.set_cursor_for_handle(handle)
# #             super().hoverMoveEvent(event)
# #
# #         def hoverLeaveEvent(self, event: QGraphicsSceneHoverEvent):
# #             self.setCursor(Qt.ArrowCursor)
# #             super().hoverLeaveEvent(event)
# #
# #     def boundingRect(self):
# #         return self.childrenBoundingRect()
# #
# #     def paint(self, painter, option, widget=None):
# #         # Children are responsible for painting
# #         pass
# #
# #     def setCentredPos(self, pos):
# #         self.setPos(pos.x() - self.boundingRect().width() / 2, pos.y() - self.boundingRect().height() / 2)
# #
# #     def update_visuals(self):
# #         self.prepareGeometryChange()
# #         is_mini = self.workflow_settings.view.mini_view
# #
# #         has_proxy = self.member_proxy.member_settings_class is not None
# #         self.member_ellipse.setVisible(is_mini or not has_proxy)
# #         if has_proxy:
# #             if is_mini:
# #                 self.member_proxy.hide()
# #             else:
# #                 self.member_proxy.show()
# #
# #         if is_mini or not has_proxy:
# #             rect = self.member_ellipse.boundingRect()
# #         else:
# #             rect = self.member_proxy.geometry()
# #
# #         self.input_point.setPos(rect.left(), rect.center().y() - self.input_point.boundingRect().height() / 2)
# #         self.output_point.setPos(rect.right() - self.output_point.boundingRect().width(),
# #                                  rect.center().y() - self.output_point.boundingRect().height() / 2)
# #
# #     def refresh_avatar(self):
# #         from src.gui.style import TEXT_COLOR
# #         if self.member_type == 'node':
# #             self.member_ellipse.setBrush(QBrush(QColor(TEXT_COLOR)))
# #             return
# #
# #         hide_bubbles = self.member_config.get('group.hide_bubbles', False)
# #         in_del_pairs = False if not self.workflow_settings.del_pairs else self in self.workflow_settings.del_pairs
# #         opacity = 0.2 if (hide_bubbles or in_del_pairs) else 1
# #         avatar_paths = get_avatar_paths_from_config(self.member_config)
# #
# #         diameter = self.member_ellipse.rect().width()
# #         pixmap = path_to_pixmap(avatar_paths, opacity=opacity, diameter=diameter)
# #
# #         if pixmap:
# #             self.member_ellipse.setBrush(QBrush(pixmap.scaled(diameter, diameter)))
# #
# #     def mouseReleaseEvent(self, event: QGraphicsSceneMouseEvent):
# #         super().mouseReleaseEvent(event)
# #         self.save_pos()
# #
# #     def save_pos(self):
# #         new_loc_x = max(0, int(self.x()))
# #         new_loc_y = max(0, int(self.y()))
# #
# #         current_size = self.member_proxy.size() * self.member_proxy.scale()
# #
# #         members = self.workflow_settings.config.get('members', [])
# #         member = next((m for m in members if m['id'] == self.id), None)
# #
# #         if member:
# #             pos_changed = new_loc_x != member.get('loc_x') or new_loc_y != member.get('loc_y')
# #             size_changed = not math.isclose(current_size.width(), member.get('width', 0)) or \
# #                            not math.isclose(current_size.height(), member.get('height', 0))
# #             if not pos_changed and not size_changed:
# #                 return
# #
# #         self.workflow_settings.update_config()
# #
# #     class HighlightBackground(QGraphicsItem):
# #         def __init__(self, parent):
# #             super().__init__(parent)
# #             self.member_ellipse = parent.member_ellipse
# #             self.member_proxy = parent.member_proxy
# #             self.padding = 15  # Glow size in pixels
# #
# #         def boundingRect(self):
# #             is_mini = not self.member_proxy.isVisible()
# #             if is_mini:
# #                 outer_diameter = self.member_ellipse.rect().width() * 1.6
# #                 return QRectF(-outer_diameter / 2, -outer_diameter / 2, outer_diameter, outer_diameter)
# #             else:
# #                 proxy_rect = self.member_proxy.geometry()
# #                 outer_width = proxy_rect.width() + 2 * self.padding
# #                 outer_height = proxy_rect.height() + 2 * self.padding
# #
# #                 return QRectF(-outer_width / 2, -outer_height / 2, outer_width, outer_height)
# #
# #         def paint(self, painter, option, widget=None):
# #             from src.gui.style import TEXT_COLOR
# #             color = QColor(TEXT_COLOR)
# #             painter.setPen(Qt.NoPen)
# #
# #             is_mini = not self.member_proxy.isVisible()
# #             if is_mini:
# #                 outer_diameter = self.member_ellipse.rect().width() * 1.6
# #                 inner_diameter = self.member_ellipse.rect().width()
# #
# #                 gradient = QRadialGradient(QPointF(0, 0), outer_diameter / 2)
# #                 color.setAlpha(155)
# #                 gradient.setColorAt(0, color)
# #                 gradient.setColorAt(1, QColor(0, 0, 0, 0))
# #
# #                 outer_path = QPainterPath()
# #                 outer_path.addEllipse(QPointF(0, 0), outer_diameter / 2, outer_diameter / 2)
# #                 inner_path = QPainterPath()
# #                 inner_path.addEllipse(QPointF(0, 0), inner_diameter / 2, inner_diameter / 2)
# #
# #                 final_path = outer_path.subtracted(inner_path)
# #                 painter.setBrush(QBrush(gradient))
# #                 painter.drawPath(final_path)
# #             else:
# #                 proxy_rect = self.member_proxy.geometry()
# #
# #                 inner_rect = QRectF(-proxy_rect.width() / 2, -proxy_rect.height() / 2, proxy_rect.width(),
# #                                     proxy_rect.height())
# #
# #                 outer_w = proxy_rect.width() + 2 * self.padding
# #                 outer_h = proxy_rect.height() + 2 * self.padding
# #                 outer_rect = QRectF(-outer_w / 2, -outer_h / 2, outer_w, outer_h)
# #
# #                 rounding = 10.0
# #
# #                 outer_path = QPainterPath()
# #                 outer_path.addRoundedRect(outer_rect, rounding, rounding)
# #                 inner_path = QPainterPath()
# #                 inner_path.addRoundedRect(inner_rect, rounding, rounding)
# #
# #                 final_path = outer_path.subtracted(inner_path)
# #                 color.setAlpha(80)
# #                 painter.setBrush(color)
# #                 painter.drawPath(final_path)

# class DraggableMember(QGraphicsObject):
#     (NoHandle, Top, Bottom, Left, Right, TopLeft, TopRight, BottomLeft, BottomRight) = range(9)
#
#     def __init__(
#             self,
#             workflow_settings,
#             member_id: str,
#             linked_id: str,
#             loc_x: int,
#             loc_y: int,
#             width: Optional[int],  # FEATURE: Added width for resizing
#             height: Optional[int],
#             member_config: Dict[str, Any]
#     ):
#         super().__init__()
#
#         self.workflow_settings = workflow_settings
#         self.id = member_id
#         self.linked_id = linked_id
#         self.member_type = member_config.get('_TYPE', 'agent')
#         self.member_config = member_config
#         # self.use_color = None  # For highlight
#
#         # --- FEATURE: State for the new resizing logic ---
#         self.is_resizing = False
#         self.current_resize_handle = self.NoHandle
#         self.resize_handle_size = 10.0  # "Thickness" of the resize border
#         self.minimum_size = QSize(150, 100)  # Minimum scaled size
#         self.original_geometry = QRectF()
#         self.original_mouse_pos = QPointF()
#         # ---
#
#         self.member_ellipse = self.MemberEllipse(self, diameter=50 if self.member_type != 'node' else 20)
#         self.member_proxy = self.MemberProxy(self)
#
#         # FEATURE: Apply initial size for proxy
#         if width and height:
#             # Respect the scale of the proxy
#             scale = self.member_proxy.scale()
#             self.member_proxy.resize(width / scale, height / scale)
#
#         # else:
#         #     # Set a default size if none is provided in config
#         #     if self.member_proxy.widget():
#         #          self.member_proxy.resize(self.member_proxy.widget().sizeHint())
#
#         # --- Setup Item Flags and Position ---
#         self.setPos(loc_x, loc_y)
#         self.setFlag(QGraphicsItem.ItemIsMovable)
#         self.setFlag(QGraphicsItem.ItemIsSelectable)
#         self.setAcceptHoverEvents(True)
#
#         # --- Child Items ---
#         self.input_point = ConnectionPoint(self, True)
#         self.output_point = ConnectionPoint(self, False)
#         # # Pass both visual items to the highlight background todo
#         self.highlight_background = self.HighlightBackground(self)  # , self.ellipse_item, self.proxy_item)
#         self.highlight_background.hide()
#
#         # --- Finalize ---
#         # self.refresh_avatar()
#         self.update_visuals()
#
#     class MemberEllipse(QGraphicsEllipseItem):
#         def __init__(self, parent, diameter):
#             super().__init__(0, 0, diameter, diameter, parent=parent)
#             from src.gui.style import TEXT_COLOR
#             self.setPen(QPen(QColor(TEXT_COLOR), 1) if parent.member_type in ['user', 'agent'] else Qt.NoPen)
#             self.setBrush(QBrush(QColor(TEXT_COLOR)))
#             self.setAcceptHoverEvents(True)
#
#     class MemberProxy(QGraphicsProxyWidget):
#         def __init__(self, parent):
#             super().__init__(parent=parent)
#             self.setScale(0.5)
#             self.config_widget = None
#             self.member_settings_class = get_member_settings_class(parent.member_type)
#
#         def show(self):
#             if self.member_settings_class and self.config_widget is None:
#                 self.config_widget = self.member_settings_class(parent=self)
#                 self.config_widget.build_schema()
#                 self.setWidget(self.config_widget)
#             super().show()
#
#     def boundingRect(self):
#         if self.workflow_settings.view.mini_view or not self.member_proxy.widget():
#             return self.member_ellipse.boundingRect()
#         else:
#             pr = self.member_proxy.boundingRect()
#             scale = self.member_proxy.scale()
#             # Add padding for the resize handles
#             padding = self.resize_handle_size
#             return QRectF(pr.topLeft(), QSize(pr.width() * scale, pr.height() * scale)).adjusted(-padding, -padding,
#                                                                                                  padding, padding)
#
#     def paint(self, painter, option, widget=None):  # Don't delete
#         pass
#
#     def setCentredPos(self, pos):
#         self.setPos(pos.x() - self.rect().width() / 2, pos.y() - self.rect().height() / 2)
#
#     def update_visuals(self):
#         self.prepareGeometryChange()
#         is_mini = self.workflow_settings.view.mini_view
#
#         has_proxy = self.member_proxy.member_settings_class is not None
#         self.member_ellipse.setVisible(is_mini or not has_proxy)
#         if has_proxy:
#             if is_mini:
#                 self.member_proxy.hide()
#             else:
#                 self.member_proxy.show()  # need to call show()
#         #     self.member_proxy.setVisible(not is_mini)
#         # # self.highlight_background.set_mode(is_mini)
#
#         if is_mini or not has_proxy:
#             rect = self.member_ellipse.rect()
#         else:
#             pr = self.member_proxy.boundingRect()
#             scale = self.member_proxy.scale()
#             rect = QRectF(pr.topLeft(), QSize(pr.width() * scale, pr.height() * scale))
#
#         self.input_point.setPos(rect.left(), rect.center().y() - self.input_point.boundingRect().height() / 2)
#         self.output_point.setPos(rect.right() - self.output_point.boundingRect().width(),
#                                  rect.center().y() - self.output_point.boundingRect().height() / 2)
#
#         # self.highlight_background.setPos(center_x, center_y)
#
#     def refresh_avatar(self):
#         from src.gui.style import TEXT_COLOR
#         if self.member_type == 'node':
#             self.member_ellipse.setBrush(QBrush(QColor(TEXT_COLOR)))
#             return
#
#         hide_bubbles = self.member_config.get('group.hide_bubbles', False)
#         in_del_pairs = False if not self.workflow_settings.del_pairs else self in self.workflow_settings.del_pairs
#         opacity = 0.2 if (hide_bubbles or in_del_pairs) else 1
#         avatar_paths = get_avatar_paths_from_config(self.member_config)
#
#         diameter = self.member_ellipse.rect().width()
#         pixmap = path_to_pixmap(avatar_paths, opacity=opacity, diameter=diameter)
#
#         if pixmap:
#             self.member_ellipse.setBrush(QBrush(pixmap.scaled(diameter, diameter)))
#
#     # --- Resizing Logic ---
#     def get_handle_at(self, pos: QPointF):
#         """Identifies which resize handle is at a given position."""
#         rect = self.member_proxy.geometry()
#         handle_size = self.resize_handle_size
#
#         on_top = abs(pos.y() - rect.top()) < handle_size
#         on_bottom = abs(pos.y() - rect.bottom()) < handle_size
#         on_left = abs(pos.x() - rect.left()) < handle_size
#         on_right = abs(pos.x() - rect.right()) < handle_size
#
#         if on_top and on_left: return self.TopLeft
#         if on_top and on_right: return self.TopRight
#         if on_bottom and on_left: return self.BottomLeft
#         if on_bottom and on_right: return self.BottomRight
#         if on_top: return self.Top
#         if on_bottom: return self.Bottom
#         if on_left: return self.Left
#         if on_right: return self.Right
#         return self.NoHandle
#
#     def set_cursor_for_handle(self, handle):
#         """Sets the cursor shape based on the handle."""
#         if handle in (self.TopLeft, self.BottomRight):
#             self.setCursor(Qt.SizeFDiagCursor)
#         elif handle in (self.TopRight, self.BottomLeft):
#             self.setCursor(Qt.SizeBDiagCursor)
#         elif handle in (self.Top, self.Bottom):
#             self.setCursor(Qt.SizeVerCursor)
#         elif handle in (self.Left, self.Right):
#             self.setCursor(Qt.SizeHorCursor)
#         else:
#             self.setCursor(Qt.ArrowCursor)
#
#     def mousePressEvent(self, event: QGraphicsSceneMouseEvent):
#         handle = self.get_handle_at(event.pos())
#         if handle != self.NoHandle and self.isSelected() and not self.workflow_settings.view.mini_view:
#             self.is_resizing = True
#             self.current_resize_handle = handle
#             self.original_geometry = self.geometry()
#             self.original_mouse_pos = event.scenePos()
#             self.setFlag(QGraphicsItem.ItemIsMovable, False)
#             event.accept()
#         else:
#             super().mousePressEvent(event)
#
#     def mouseMoveEvent(self, event: QGraphicsSceneMouseEvent):
#         if self.is_resizing:
#             delta = event.scenePos() - self.original_mouse_pos
#             new_geom = QRectF(self.original_geometry)
#
#             if self.current_resize_handle == self.Top:
#                 new_geom.setTop(self.original_geometry.top() + delta.y())
#             elif self.current_resize_handle == self.Bottom:
#                 new_geom.setBottom(self.original_geometry.bottom() + delta.y())
#             elif self.current_resize_handle == self.Left:
#                 new_geom.setLeft(self.original_geometry.left() + delta.x())
#             elif self.current_resize_handle == self.Right:
#                 new_geom.setRight(self.original_geometry.right() + delta.x())
#             elif self.current_resize_handle == self.TopLeft:
#                 new_geom.setTopLeft(self.original_geometry.topLeft() + delta)
#             elif self.current_resize_handle == self.TopRight:
#                 new_geom.setTopRight(self.original_geometry.topRight() + delta)
#             elif self.current_resize_handle == self.BottomLeft:
#                 new_geom.setBottomLeft(self.original_geometry.bottomLeft() + delta)
#             elif self.current_resize_handle == self.BottomRight:
#                 new_geom.setBottomRight(self.original_geometry.bottomRight() + delta)
#
#             # Enforce minimum size
#             if new_geom.width() < self.minimum_size.width(): new_geom.setWidth(self.minimum_size.width())
#             if new_geom.height() < self.minimum_size.height(): new_geom.setHeight(self.minimum_size.height())
#
#             self.prepareGeometryChange()
#             self.setPos(new_geom.topLeft())
#
#             scale = self.member_proxy.scale()
#             self.member_proxy.resize(new_geom.width() / scale, new_geom.height() / scale)
#
#             self.update_visuals()
#             for line in self.workflow_settings.inputs_in_view.values():
#                 if line.source_member_id == self.id or line.target_member_id == self.id:
#                     line.updatePosition()
#             event.accept()
#         else:
#             super().mouseMoveEvent(event)
#
#     def mouseReleaseEvent(self, event: QGraphicsSceneMouseEvent):
#         if self.is_resizing:
#             self.is_resizing = False
#             self.current_resize_handle = self.NoHandle
#             self.setFlag(QGraphicsItem.ItemIsMovable, True)
#             self.save_pos()
#             event.accept()
#         else:
#             super().mouseReleaseEvent(event)
#             self.save_pos()
#
#     def save_pos(self):
#         new_loc_x = max(0, int(self.x()))
#         new_loc_y = max(0, int(self.y()))
#
#         pr = self.member_proxy.geometry()
#         scale = self.member_proxy.scale()
#         current_size = QSize(pr.width() * scale, pr.height() * scale)
#
#         members = self.workflow_settings.config.get('members', [])
#         member = next((m for m in members if m['id'] == self.id), None)
#
#         if member:
#             pos_changed = new_loc_x != member.get('loc_x') or new_loc_y != member.get('loc_y')
#             # Compare with a tolerance for floating point issues
#             size_changed = not math.isclose(current_size.width(), member.get('width', 0)) or \
#                            not math.isclose(current_size.height(), member.get('height', 0))
#             if not pos_changed and not size_changed:
#                 return
#
#         self.workflow_settings.update_config()
#
#     def hoverMoveEvent(self, event: QGraphicsSceneHoverEvent):
#         if self.is_resizing or not self.isSelected() or self.workflow_settings.view.mini_view:
#             self.setCursor(Qt.ArrowCursor)
#             super().hoverMoveEvent(event)
#             return
#
#         handle = self.get_handle_at(event.pos())
#         self.set_cursor_for_handle(handle)
#         super().hoverMoveEvent(event)
#
#     def hoverLeaveEvent(self, event: QGraphicsSceneHoverEvent):
#         self.setCursor(Qt.ArrowCursor)
#         super().hoverLeaveEvent(event)
#
#     class HighlightBackground(QGraphicsItem):
#         def __init__(self, parent):  # , use_color=None):
#             super().__init__(parent)
#             self.member_ellipse = parent.member_ellipse
#             self.member_proxy = parent.member_proxy
#             self.padding = 15  # Glow size in pixels
#
#         def boundingRect(self):
#             is_mini = not self.member_proxy.isVisible()
#             if is_mini:
#                 outer_diameter = self.member_ellipse.rect().width() * 1.6
#                 return QRectF(-outer_diameter / 2, -outer_diameter / 2, outer_diameter, outer_diameter)
#             else:
#                 proxy_rect = self.member_proxy.boundingRect()
#                 scale = self.member_proxy.scale()
#                 scaled_width = proxy_rect.width() * scale
#                 scaled_height = proxy_rect.height() * scale
#
#                 outer_width = scaled_width + 2 * self.padding
#                 outer_height = scaled_height + 2 * self.padding
#
#                 return QRectF(-outer_width / 2, -outer_height / 2, outer_width, outer_height)
#
#         def paint(self, painter, option, widget=None):
#             from src.gui.style import TEXT_COLOR
#             color = QColor(TEXT_COLOR)
#             painter.setPen(Qt.NoPen)
#
#             is_mini = not self.member_proxy.isVisible()
#             if is_mini:
#                 outer_diameter = self.member_ellipse.rect().width() * 1.6
#                 inner_diameter = self.member_ellipse.rect().width()
#
#                 gradient = QRadialGradient(QPointF(0, 0), outer_diameter / 2)
#                 color.setAlpha(155)
#                 gradient.setColorAt(0, color)
#                 gradient.setColorAt(1, QColor(0, 0, 0, 0))
#
#                 outer_path = QPainterPath()
#                 outer_path.addEllipse(QPointF(0, 0), outer_diameter / 2, outer_diameter / 2)
#                 inner_path = QPainterPath()
#                 inner_path.addEllipse(QPointF(0, 0), inner_diameter / 2, inner_diameter / 2)
#
#                 final_path = outer_path.subtracted(inner_path)
#                 painter.setBrush(QBrush(gradient))
#                 painter.drawPath(final_path)
#             else:
#                 proxy_rect = self.member_proxy.boundingRect()
#                 scale = self.member_proxy.scale()
#
#                 inner_w = proxy_rect.width() * scale
#                 inner_h = proxy_rect.height() * scale
#                 inner_rect = QRectF(-inner_w / 2, -inner_h / 2, inner_w, inner_h)
#
#                 outer_w = inner_w + 2 * self.padding
#                 outer_h = inner_h + 2 * self.padding
#                 outer_rect = QRectF(-outer_w / 2, -outer_h / 2, outer_w, outer_h)
#
#                 rounding = 10.0
#
#                 outer_path = QPainterPath()
#                 outer_path.addRoundedRect(outer_rect, rounding, rounding)
#                 inner_path = QPainterPath()
#                 inner_path.addRoundedRect(inner_rect, rounding, rounding)
#
#                 final_path = outer_path.subtracted(inner_path)
#                 color.setAlpha(80)  # Use a solid, semi-transparent glow for the rectangle
#                 painter.setBrush(color)
#                 painter.drawPath(final_path)
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
            self.setBrush(QBrush(QColor(TEXT_COLOR)))
            self.setAcceptHoverEvents(True)

    class MemberProxy(QGraphicsProxyWidget):
        def __init__(self, parent):
            super().__init__(parent=parent)
            self.setScale(0.5)
            self.config_widget = None
            self.member_settings_class = get_member_settings_class(parent.member_type)

        def show(self):
            if self.member_settings_class and self.config_widget is None:
                self.config_widget = self.member_settings_class(parent=self)
                self.config_widget.build_schema()
                self.setWidget(self.config_widget)
            super().show()

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
        pass

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
            # Get the scaled rect of the proxy in the parent's coordinates
            proxy_br = self.member_proxy.boundingRect()
            rect = self.member_proxy.mapToParent(proxy_br).boundingRect()

        self.input_point.setPos(rect.left(), rect.center().y() - self.input_point.boundingRect().height() / 2)
        self.output_point.setPos(rect.right() - self.output_point.boundingRect().width(),
                                 rect.center().y() - self.output_point.boundingRect().height() / 2)

    def refresh_avatar(self):
        from src.gui.style import TEXT_COLOR
        if self.member_type == 'node':
            self.member_ellipse.setBrush(QBrush(QColor(TEXT_COLOR)))
            return

        hide_bubbles = self.member_config.get('group.hide_bubbles', False)
        in_del_pairs = False if not self.workflow_settings.del_pairs else self in self.workflow_settings.del_pairs
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
            for line in self.workflow_settings.inputs_in_view.values():
                if line.source_member_id == self.id or line.target_member_id == self.id:
                    line.updatePosition()
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
                proxy_rect = self.member_proxy.boundingRect()
                scale = self.member_proxy.scale()

                inner_w = proxy_rect.width() * scale
                inner_h = proxy_rect.height() * scale
                inner_rect = QRectF(-inner_w / 2, -inner_h / 2, inner_w, inner_h)

                outer_w = inner_w + 2 * self.padding
                outer_h = inner_h + 2 * self.padding
                outer_rect = QRectF(-outer_w / 2, -outer_h / 2, outer_w, outer_h)

                rounding = 10.0

                outer_path = QPainterPath()
                outer_path.addRoundedRect(outer_rect, rounding, rounding)
                inner_path = QPainterPath()
                inner_path.addRoundedRect(inner_rect, rounding, rounding)

                final_path = outer_path.subtracted(inner_path)
                color.setAlpha(80)
                painter.setBrush(color)
                painter.drawPath(final_path)


class InsertableLine(QGraphicsPathItem):
    def __init__(self, parent, member_bundle, source_member_index, member_index, config=None):
        super().__init__()
        from src.gui.style import TEXT_COLOR
        self.parent = parent
        self.member_bundle = member_bundle.copy()

        self.source_member_index = source_member_index
        self.target_member_index = member_index

        self.start_point = self.parent.new_agents[self.source_member_index][1].output_point
        self.end_point = self.parent.new_agents[self.target_member_index][1].input_point

        self.selection_path = None
        self.looper_midpoint = None

        self.config: Dict[str, Any] = config if config else {}

        self.setAcceptHoverEvents(True)
        self.color = QColor(TEXT_COLOR)

        self.updatePath()

        self.setPen(QPen(self.color, 2, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin))
        self.setZValue(-1)

    def paint(self, painter, option, widget):
        line_width = 4 if self.isSelected() else 2
        current_pen = self.pen()
        current_pen.setWidth(line_width)
        has_no_mappings = len(self.config.get('mappings.data', [])) == 0
        is_conditional = self.config.get('conditional', False)
        if is_conditional:
            current_pen.setStyle(Qt.DashLine)

        if has_no_mappings:
            # Get the current color, set its alpha to 50%, and apply it
            color = current_pen.color()
            color.setAlphaF(0.5)
            current_pen.setColor(color)

        # painter.setBrush(QBrush(self.color))
        painter.setPen(current_pen)
        painter.drawPath(self.path())

    def updatePosition(self):
        self.updatePath()
        self.scene().update(self.scene().sceneRect())

    def updatePath(self):
        start_point = self.start_point.scenePos() if isinstance(self.start_point, ConnectionPoint) else self.start_point
        end_point = self.end_point.scenePos() if isinstance(self.end_point, ConnectionPoint) else self.end_point

        # start point += (2, 2)
        start_point += QPointF(2, 2)
        end_point += QPointF(2, 2)

        is_looper = self.config.get('looper', False)

        if is_looper:
            line_is_under = start_point.y() >= end_point.y()
            if (line_is_under and start_point.y() > end_point.y()) or (start_point.y() < end_point.y() and not line_is_under):
                extender_side = 'left'
            else:
                extender_side = 'right'
            y_diff = abs(start_point.y() - end_point.y())
            if not line_is_under:
                y_diff = -y_diff

            path = QPainterPath(start_point)

            x_rad = 25
            y_rad = 25 if line_is_under else -25

            # Draw half of the right side of the loop
            cp1 = QPointF(start_point.x() + x_rad, start_point.y())
            cp2 = QPointF(start_point.x() + x_rad, start_point.y() + y_rad)
            path.cubicTo(cp1, cp2, QPointF(start_point.x() + x_rad, start_point.y() + y_rad))

            if extender_side == 'right':
                # Draw a vertical line
                path.lineTo(QPointF(start_point.x() + x_rad, start_point.y() + y_rad + y_diff))

            # Draw the other half of the right hand side loop
            var = y_diff if extender_side == 'right' else 0
            cp3 = QPointF(start_point.x() + x_rad, start_point.y() + y_rad + var + y_rad)
            cp4 = QPointF(start_point.x(), start_point.y() + y_rad + var + y_rad)
            path.cubicTo(cp3, cp4, QPointF(start_point.x(), start_point.y() + y_rad + var + y_rad))

            # # Draw the horizontal line
            # x_diff = start_point.x() - end_point.x()
            # if x_diff < 50:
            #     x_diff = 50
            # path.lineTo(QPointF(start_point.x() - x_diff, start_point.y() + y_rad + var + y_rad))
            # self.looper_midpoint = QPointF(start_point.x() - (x_diff / 2), start_point.y() + y_rad + var + y_rad)

            # Draw the horizontal line with a gapped, left-pointing equilateral triangle
            x_diff = start_point.x() - end_point.x()
            if x_diff < 50:
                x_diff = 50

            # Define the y-coordinate and midpoint for the horizontal line
            line_y = start_point.y() + y_rad + var + y_rad
            mid_point = QPointF(start_point.x() - (x_diff / 2), line_y)
            self.looper_midpoint = mid_point

            # --- Define Triangle and Gap Geometry ---
            side_length = 15.0
            # Height of an equilateral triangle: (side * sqrt(3)) / 2
            triangle_height = (side_length * math.sqrt(3)) / 2
            half_side = side_length / 2.0
            gap = 4.0  # Gap space around the triangle
            half_gap = gap / 2.0

            # --- Calculate Coordinates for a Left-Pointing Triangle ---
            # The main line is drawn from right to left.

            # The triangle's base is now a vertical line at mid_point.x()
            # The apex points left along the horizontal line's y-axis.
            p_base_top = QPointF(mid_point.x(), mid_point.y() - half_side)
            p_base_bottom = QPointF(mid_point.x(), mid_point.y() + half_side)
            p_apex_left = QPointF(mid_point.x() - triangle_height, mid_point.y())

            # End of the first line segment (right of the triangle's base)
            line1_end = QPointF(mid_point.x() + half_gap, line_y)

            # Start of the second line segment (left of the triangle's apex)
            line2_start = QPointF(p_apex_left.x() - half_gap, line_y)

            # The final destination for the entire horizontal line
            final_line_end = QPointF(start_point.x() - x_diff, line_y)

            # --- Update the QPainterPath ---

            # 1. Draw the first line segment, stopping before the triangle
            path.lineTo(line1_end)

            # 2. Draw the equilateral triangle (now pointing left)
            path.moveTo(p_base_top)
            path.lineTo(p_apex_left)
            path.lineTo(p_base_bottom)
            path.closeSubpath()  # Draws the vertical base to close the shape

            # 3. Move painter to the start of the second line segment
            path.moveTo(line2_start)

            # 4. Draw the final line segment
            path.lineTo(final_line_end)


            # Draw half of the left side of the loop
            line_to = QPointF(start_point.x() - x_diff - x_rad, start_point.y() + y_rad + var)
            cp5 = QPointF(start_point.x() - x_diff - x_rad, start_point.y() + y_rad + var + y_rad)
            cp6 = line_to
            path.cubicTo(cp5, cp6, line_to)

            if extender_side == 'left':
                # Draw the vertical line up y_diff pixels
                line_to = QPointF(start_point.x() - x_diff - x_rad, start_point.y() + y_rad - y_diff)
                path.lineTo(line_to)
            else:
                # Draw the vertical line down y_diff pixels
                line_to = QPointF(start_point.x() - x_diff - x_rad, start_point.y() + y_rad + y_diff)
                path.lineTo(line_to)

            # Draw the other half of the left hand side loop
            # cp7 = QPointF(start_point.x() - x_diff - 25, start_point.y() + 25 - y_diff - 25)
            # cp8 = QPointF(start_point.x(), start_point.y() + 25 - y_diff - 25)
            diag_pt_top_right = QPointF(line_to.x() + x_rad, line_to.y() - y_rad)
            # diag_pt_top_right = line_to + QPointF(25, 25 * (-1 if line_is_under else 1))
            cp7 = QPointF(diag_pt_top_right.x() - x_rad, diag_pt_top_right.y() + y_rad)
            cp8 = QPointF(diag_pt_top_right.x() - x_rad, diag_pt_top_right.y())
            path.cubicTo(cp7, cp8, diag_pt_top_right)

            # Draw line to the end point
            path.lineTo(end_point)
        else:
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
            self.looper_midpoint = None

        self.setPath(path)
        self.updateSelectionPath()

    def updateSelectionPath(self):
        stroker = QPainterPathStroker()
        stroker.setWidth(20)
        self.selection_path = stroker.createStroke(self.path())

    def shape(self):
        if self.selection_path is None:
            return super().shape()
        return self.selection_path


class ConnectionLine(QGraphicsPathItem):  # todo dupe code above
    def __init__(self, parent, source_member, target_member=None, config=None):
        super().__init__()
        from src.gui.style import TEXT_COLOR
        self.parent = parent
        self.source_member_id = source_member.id
        self.target_member_id = target_member.id if target_member else None
        self.start_point = source_member.output_point
        self.end_point = target_member.input_point if target_member else None
        self.selection_path = None
        self.looper_midpoint = None

        self.config: Dict[str, Any] = config if config else {}

        self.setAcceptHoverEvents(True)
        self.setFlag(QGraphicsItem.ItemIsSelectable)
        self.color = QColor(TEXT_COLOR)

        self.updatePath()

        self.setPen(QPen(self.color, 2, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin))
        self.setZValue(-1)

    def paint(self, painter, option, widget):
        line_width = 4 if self.isSelected() else 2
        # painter.setBrush(QBrush(self.color))
        current_pen = self.pen()
        current_pen.setWidth(line_width)

        mappings_data = self.config.get('mappings.data', [])
        has_no_mappings = len(mappings_data) == 0
        is_conditional = self.config.get('conditional', False)
        if is_conditional:
            current_pen.setStyle(Qt.DashLine)

        if has_no_mappings:
            # current_pen.setStyle(Qt.DashLine)
            # painter.setPen(current_pen)
            # painter.drawPath(self.path())
            # Get the current color, set its alpha to 50%, and apply it
            faded_color = current_pen.color()
            faded_color.setAlphaF(0.31)
            current_pen.setColor(faded_color)
            painter.setPen(current_pen)
            painter.drawPath(self.path())

        else:
            from src.gui.style import TEXT_COLOR, PARAM_COLOR, STRUCTURE_COLOR
            color_codes = {
                "Output": QColor(TEXT_COLOR),
                "Message": QColor(TEXT_COLOR),
                "Param": QColor(PARAM_COLOR),
                "Structure": QColor(STRUCTURE_COLOR),
            }

            start_point = self.path().pointAtPercent(0)
            end_point = self.path().pointAtPercent(1)

            gradient = QLinearGradient(start_point, end_point)

            source_colors = []
            target_colors = []

            for mapping in mappings_data:
                source_color = color_codes.get(mapping['source'], QColor(TEXT_COLOR))
                target_color = color_codes.get(mapping['target'], QColor(TEXT_COLOR))
                if source_color not in source_colors:
                    source_colors.append(source_color)
                if target_color not in target_colors:
                    target_colors.append(target_color)

            dash_length = 10
            total_length = self.path().length()
            num_dashes = int(total_length / dash_length)

            if len(source_colors) > 1 and len(target_colors) == 1:
                # Multiple sources, single target
                target_color = target_colors[0]
                for i in range(num_dashes):
                    t1 = i / num_dashes
                    t2 = (i + 1) / num_dashes

                    source_color = source_colors[i % len(source_colors)]

                    gradient.setColorAt(t1, source_color)
                    gradient.setColorAt(t2, self.blend_colors(source_color, target_color, 0.5))

            elif len(source_colors) > 1 or len(target_colors) > 1:
                # Multiple sources and multiple targets, or single source and multiple targets
                for i in range(num_dashes):
                    t1 = i / num_dashes
                    t2 = (i + 1) / num_dashes

                    source_color = source_colors[i % len(source_colors)]
                    target_color = target_colors[i % len(target_colors)]

                    gradient.setColorAt(t1, source_color)
                    gradient.setColorAt(t2, target_color)
            else:
                # Simple gradient from single source to single target
                source_color = source_colors[0] if source_colors else QColor(255, 255, 255)
                target_color = target_colors[0] if target_colors else QColor(255, 255, 255)
                gradient.setColorAt(0, source_color)
                gradient.setColorAt(1, target_color)

            current_pen.setBrush(gradient)
            painter.setPen(current_pen)
            painter.drawPath(self.path())

        # # Draw the looper triangle
        # if self.looper_midpoint:
        #     painter.drawPolygon(QPolygonF(
        #         [self.looper_midpoint, self.looper_midpoint + QPointF(10, 5), self.looper_midpoint + QPointF(10, -5)]))

    @staticmethod
    def blend_colors(color1, color2, ratio):
        r = int(color1.red() * (1 - ratio) + color2.red() * ratio)
        g = int(color1.green() * (1 - ratio) + color2.green() * ratio)
        b = int(color1.blue() * (1 - ratio) + color2.blue() * ratio)
        return QColor(r, g, b)

    def updateEndPoint(self, end_point):
        # find the closest start point
        closest_member_id = None
        closest_start_point = None
        closest_distance = 1000
        for member_id, member in self.parent.members_in_view.items():
            if member_id == self.source_member_id:
                continue
            start_point = member.input_point.scenePos()
            distance = (start_point - end_point).manhattanLength()
            if distance < closest_distance:
                closest_distance = distance
                closest_start_point = start_point
                closest_member_id = member_id

        if closest_distance < 20:
            self.end_point = closest_start_point
            cr_check = self.parent.check_for_circular_references(closest_member_id, [self.source_member_id])
            self.config['looper'] = True if cr_check else False
        else:
            self.end_point = end_point
            self.config['looper'] = False
        self.updatePath()

    def updatePosition(self):
        self.updatePath()
        self.scene().update(self.scene().sceneRect())

    def updatePath(self):
        if self.end_point is None:
            return
        start_point = self.start_point.scenePos() if isinstance(self.start_point, ConnectionPoint) else self.start_point
        end_point = self.end_point.scenePos() if isinstance(self.end_point, ConnectionPoint) else self.end_point

        # start point += (2, 2)
        start_point = start_point + QPointF(2, 2)
        end_point = end_point + QPointF(2, 2)

        is_looper = self.config.get('looper', False)

        if is_looper:
            line_is_under = start_point.y() >= end_point.y()
            if (line_is_under and start_point.y() > end_point.y()) or (start_point.y() < end_point.y() and not line_is_under):
                extender_side = 'left'
            else:
                extender_side = 'right'
            y_diff = abs(start_point.y() - end_point.y())
            if not line_is_under:
                y_diff = -y_diff

            path = QPainterPath(start_point)

            x_rad = 25
            y_rad = 25 if line_is_under else -25

            # Draw half of the right side of the loop
            cp1 = QPointF(start_point.x() + x_rad, start_point.y())
            cp2 = QPointF(start_point.x() + x_rad, start_point.y() + y_rad)
            path.cubicTo(cp1, cp2, QPointF(start_point.x() + x_rad, start_point.y() + y_rad))

            if extender_side == 'right':
                # Draw a vertical line
                path.lineTo(QPointF(start_point.x() + x_rad, start_point.y() + y_rad + y_diff))

            # Draw the other half of the right hand side loop
            var = y_diff if extender_side == 'right' else 0
            cp3 = QPointF(start_point.x() + x_rad, start_point.y() + y_rad + var + y_rad)
            cp4 = QPointF(start_point.x(), start_point.y() + y_rad + var + y_rad)
            path.cubicTo(cp3, cp4, QPointF(start_point.x(), start_point.y() + y_rad + var + y_rad))

            # # Draw the horizontal line
            # x_diff = start_point.x() - end_point.x()
            # if x_diff < 50:
            #     x_diff = 50
            # path.lineTo(QPointF(start_point.x() - x_diff, start_point.y() + y_rad + var + y_rad))
            # self.looper_midpoint = QPointF(start_point.x() - (x_diff / 2), start_point.y() + y_rad + var + y_rad)

            # # set to solid line
            # current_style = self.pen().style()
            # path.setPen(QPen(self.color, 2, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin))

            # Draw the horizontal line with a gapped, left-pointing equilateral triangle
            x_diff = start_point.x() - end_point.x()
            if x_diff < 50:
                x_diff = 50

            # Define the y-coordinate and midpoint for the horizontal line
            line_y = start_point.y() + y_rad + var + y_rad
            mid_point = QPointF(start_point.x() - (x_diff / 2), line_y)
            self.looper_midpoint = mid_point

            # --- Define Triangle and Gap Geometry ---
            side_length = 15.0
            # Height of an equilateral triangle: (side * sqrt(3)) / 2
            triangle_height = (side_length * math.sqrt(3)) / 2
            half_side = side_length / 2.0
            gap = 4.0  # Gap space around the triangle
            half_gap = gap / 2.0

            # --- Calculate Coordinates for a Left-Pointing Triangle ---
            # The main line is drawn from right to left.

            # The triangle's base is now a vertical line at mid_point.x()
            # The apex points left along the horizontal line's y-axis.
            p_base_top = QPointF(mid_point.x(), mid_point.y() - half_side)
            p_base_bottom = QPointF(mid_point.x(), mid_point.y() + half_side)
            p_apex_left = QPointF(mid_point.x() - triangle_height, mid_point.y())

            # End of the first line segment (right of the triangle's base)
            line1_end = QPointF(mid_point.x() + half_gap, line_y)

            # Start of the second line segment (left of the triangle's apex)
            line2_start = QPointF(p_apex_left.x() - half_gap, line_y)

            # The final destination for the entire horizontal line
            final_line_end = QPointF(start_point.x() - x_diff, line_y)

            # --- Update the QPainterPath ---

            # 1. Draw the first line segment, stopping before the triangle
            path.lineTo(line1_end)

            # 2. Draw the equilateral triangle (now pointing left)
            path.moveTo(p_base_top)
            path.lineTo(p_apex_left)
            path.lineTo(p_base_bottom)
            path.closeSubpath()  # Draws the vertical base to close the shape

            # 3. Move painter to the start of the second line segment
            path.moveTo(line2_start)

            # 4. Draw the final line segment
            path.lineTo(final_line_end)

            # # set the pen style back to the original style
            # self.setPen(QPen(self.color, 2, current_style, Qt.RoundCap, Qt.RoundJoin))

            # Draw half of the left side of the loop
            line_to = QPointF(start_point.x() - x_diff - x_rad, start_point.y() + y_rad + var)
            cp5 = QPointF(start_point.x() - x_diff - x_rad, start_point.y() + y_rad + var + y_rad)
            cp6 = line_to
            path.cubicTo(cp5, cp6, line_to)

            if extender_side == 'left':
                # Draw the vertical line up y_diff pixels
                line_to = QPointF(start_point.x() - x_diff - x_rad, start_point.y() + y_rad - y_diff)
                path.lineTo(line_to)
            else:
                # Draw the vertical line down y_diff pixels
                line_to = QPointF(start_point.x() - x_diff - x_rad, start_point.y() + y_rad + y_diff)
                path.lineTo(line_to)

            # Draw the other half of the left hand side loop
            # cp7 = QPointF(start_point.x() - x_diff - 25, start_point.y() + 25 - y_diff - 25)
            # cp8 = QPointF(start_point.x(), start_point.y() + 25 - y_diff - 25)
            diag_pt_top_right = QPointF(line_to.x() + x_rad, line_to.y() - y_rad)
            # diag_pt_top_right = line_to + QPointF(25, 25 * (-1 if line_is_under else 1))
            cp7 = QPointF(diag_pt_top_right.x() - x_rad, diag_pt_top_right.y() + y_rad)
            cp8 = QPointF(diag_pt_top_right.x() - x_rad, diag_pt_top_right.y())
            path.cubicTo(cp7, cp8, diag_pt_top_right)

            # Draw line to the end point
            path.lineTo(end_point)
        else:
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
            self.looper_midpoint = None

        self.setPath(path)
        self.updateSelectionPath()

    def updateSelectionPath(self):
        stroker = QPainterPathStroker()
        stroker.setWidth(20)
        self.selection_path = stroker.createStroke(self.path())

    def shape(self):
        if self.selection_path is None:
            return super().shape()
        return self.selection_path


# class ConnectionLine(QGraphicsPathItem):  # todo dupe code above
#     def __init__(self, parent, source_member, target_member=None, config=None):
#         super().__init__()
#         from src.gui.style import TEXT_COLOR
#         self.parent = parent
#         self.source_member_id = source_member.id
#         self.target_member_id = target_member.id if target_member else None
#         self.start_point = source_member.output_point
#         self.end_point = target_member.input_point if target_member else None
#         self.selection_path = None
#         self.looper_midpoint = None
#
#         self.config: Dict[str, Any] = config if config else {}
#
#         self.setAcceptHoverEvents(True)
#         self.setFlag(QGraphicsItem.ItemIsSelectable)
#         self.color = QColor(TEXT_COLOR)
#
#         self.updatePath()
#
#         self.setPen(QPen(self.color, 2, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin))
#         self.setZValue(-1)
#
#     def paint(self, painter, option, widget):
#         line_width = 4 if self.isSelected() else 2
#         # painter.setBrush(QBrush(self.color))
#         current_pen = self.pen()
#         current_pen.setWidth(line_width)
#
#         mappings_data = self.config.get('mappings.data', [])
#         has_no_mappings = len(mappings_data) == 0
#         is_conditional = self.config.get('conditional', False)
#         if is_conditional:
#             current_pen.setStyle(Qt.DashLine)
#
#         if has_no_mappings:
#             # current_pen.setStyle(Qt.DashLine)
#             # painter.setPen(current_pen)
#             # painter.drawPath(self.path())
#             # Get the current color, set its alpha to 50%, and apply it
#             faded_color = current_pen.color()
#             faded_color.setAlphaF(0.31)
#             current_pen.setColor(faded_color)
#             painter.setPen(current_pen)
#             painter.drawPath(self.path())
#
#         else:
#             from src.gui.style import TEXT_COLOR, PARAM_COLOR, STRUCTURE_COLOR
#             color_codes = {
#                 "Output": QColor(TEXT_COLOR),
#                 "Message": QColor(TEXT_COLOR),
#                 "Param": QColor(PARAM_COLOR),
#                 "Structure": QColor(STRUCTURE_COLOR),
#             }
#
#             start_point = self.path().pointAtPercent(0)
#             end_point = self.path().pointAtPercent(1)
#
#             gradient = QLinearGradient(start_point, end_point)
#
#             source_colors = []
#             target_colors = []
#
#             for mapping in mappings_data:
#                 source_color = color_codes.get(mapping['source'], QColor(TEXT_COLOR))
#                 target_color = color_codes.get(mapping['target'], QColor(TEXT_COLOR))
#                 if source_color not in source_colors:
#                     source_colors.append(source_color)
#                 if target_color not in target_colors:
#                     target_colors.append(target_color)
#
#             dash_length = 10
#             total_length = self.path().length()
#             num_dashes = int(total_length / dash_length)
#
#             if len(source_colors) > 1 and len(target_colors) == 1:
#                 # Multiple sources, single target
#                 target_color = target_colors[0]
#                 for i in range(num_dashes):
#                     t1 = i / num_dashes
#                     t2 = (i + 1) / num_dashes
#
#                     source_color = source_colors[i % len(source_colors)]
#
#                     gradient.setColorAt(t1, source_color)
#                     gradient.setColorAt(t2, self.blend_colors(source_color, target_color, 0.5))
#
#             elif len(source_colors) > 1 or len(target_colors) > 1:
#                 # Multiple sources and multiple targets, or single source and multiple targets
#                 for i in range(num_dashes):
#                     t1 = i / num_dashes
#                     t2 = (i + 1) / num_dashes
#
#                     source_color = source_colors[i % len(source_colors)]
#                     target_color = target_colors[i % len(target_colors)]
#
#                     gradient.setColorAt(t1, source_color)
#                     gradient.setColorAt(t2, target_color)
#             else:
#                 # Simple gradient from single source to single target
#                 source_color = source_colors[0] if source_colors else QColor(255, 255, 255)
#                 target_color = target_colors[0] if target_colors else QColor(255, 255, 255)
#                 gradient.setColorAt(0, source_color)
#                 gradient.setColorAt(1, target_color)
#
#             current_pen.setBrush(gradient)
#             painter.setPen(current_pen)
#             painter.drawPath(self.path())
#
#         # # Draw the looper triangle
#         # if self.looper_midpoint:
#         #     painter.drawPolygon(QPolygonF(
#         #         [self.looper_midpoint, self.looper_midpoint + QPointF(10, 5), self.looper_midpoint + QPointF(10, -5)]))
#
#     @staticmethod
#     def blend_colors(color1, color2, ratio):
#         r = int(color1.red() * (1 - ratio) + color2.red() * ratio)
#         g = int(color1.green() * (1 - ratio) + color2.green() * ratio)
#         b = int(color1.blue() * (1 - ratio) + color2.blue() * ratio)
#         return QColor(r, g, b)
#
#     def updateEndPoint(self, end_point):
#         # find the closest start point
#         closest_member_id = None
#         closest_start_point = None
#         closest_distance = 1000
#         for member_id, member in self.parent.members_in_view.items():
#             if member_id == self.source_member_id:
#                 continue
#             start_point = member.input_point.scenePos()
#             distance = (start_point - end_point).manhattanLength()
#             if distance < closest_distance:
#                 closest_distance = distance
#                 closest_start_point = start_point
#                 closest_member_id = member_id
#
#         if closest_distance < 20:
#             self.end_point = closest_start_point
#             cr_check = self.parent.check_for_circular_references(closest_member_id, [self.source_member_id])
#             self.config['looper'] = True if cr_check else False
#         else:
#             self.end_point = end_point
#             self.config['looper'] = False
#         self.updatePath()
#
#     def updatePosition(self):
#         self.updatePath()
#         self.scene().update(self.scene().sceneRect())
#
#     def updatePath(self):
#         if self.end_point is None:
#             return
#         start_point = self.start_point.scenePos() if isinstance(self.start_point, ConnectionPoint) else self.start_point
#         end_point = self.end_point.scenePos() if isinstance(self.end_point, ConnectionPoint) else self.end_point
#
#         # start point += (2, 2)
#         start_point = start_point + QPointF(2, 2)
#         end_point = end_point + QPointF(2, 2)
#
#         is_looper = self.config.get('looper', False)
#
#         if is_looper:
#             line_is_under = start_point.y() >= end_point.y()
#             if (line_is_under and start_point.y() > end_point.y()) or (start_point.y() < end_point.y() and not line_is_under):
#                 extender_side = 'left'
#             else:
#                 extender_side = 'right'
#             y_diff = abs(start_point.y() - end_point.y())
#             if not line_is_under:
#                 y_diff = -y_diff
#
#             path = QPainterPath(start_point)
#
#             x_rad = 25
#             y_rad = 25 if line_is_under else -25
#
#             # Draw half of the right side of the loop
#             cp1 = QPointF(start_point.x() + x_rad, start_point.y())
#             cp2 = QPointF(start_point.x() + x_rad, start_point.y() + y_rad)
#             path.cubicTo(cp1, cp2, QPointF(start_point.x() + x_rad, start_point.y() + y_rad))
#
#             if extender_side == 'right':
#                 # Draw a vertical line
#                 path.lineTo(QPointF(start_point.x() + x_rad, start_point.y() + y_rad + y_diff))
#
#             # Draw the other half of the right hand side loop
#             var = y_diff if extender_side == 'right' else 0
#             cp3 = QPointF(start_point.x() + x_rad, start_point.y() + y_rad + var + y_rad)
#             cp4 = QPointF(start_point.x(), start_point.y() + y_rad + var + y_rad)
#             path.cubicTo(cp3, cp4, QPointF(start_point.x(), start_point.y() + y_rad + var + y_rad))
#
#             # # Draw the horizontal line
#             # x_diff = start_point.x() - end_point.x()
#             # if x_diff < 50:
#             #     x_diff = 50
#             # path.lineTo(QPointF(start_point.x() - x_diff, start_point.y() + y_rad + var + y_rad))
#             # self.looper_midpoint = QPointF(start_point.x() - (x_diff / 2), start_point.y() + y_rad + var + y_rad)
#
#             # # set to solid line
#             # current_style = self.pen().style()
#             # path.setPen(QPen(self.color, 2, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin))
#
#             # Draw the horizontal line with a gapped, left-pointing equilateral triangle
#             x_diff = start_point.x() - end_point.x()
#             if x_diff < 50:
#                 x_diff = 50
#
#             # Define the y-coordinate and midpoint for the horizontal line
#             line_y = start_point.y() + y_rad + var + y_rad
#             mid_point = QPointF(start_point.x() - (x_diff / 2), line_y)
#             self.looper_midpoint = mid_point
#
#             # --- Define Triangle and Gap Geometry ---
#             side_length = 15.0
#             # Height of an equilateral triangle: (side * sqrt(3)) / 2
#             triangle_height = (side_length * math.sqrt(3)) / 2
#             half_side = side_length / 2.0
#             gap = 4.0  # Gap space around the triangle
#             half_gap = gap / 2.0
#
#             # --- Calculate Coordinates for a Left-Pointing Triangle ---
#             # The main line is drawn from right to left.
#
#             # The triangle's base is now a vertical line at mid_point.x()
#             # The apex points left along the horizontal line's y-axis.
#             p_base_top = QPointF(mid_point.x(), mid_point.y() - half_side)
#             p_base_bottom = QPointF(mid_point.x(), mid_point.y() + half_side)
#             p_apex_left = QPointF(mid_point.x() - triangle_height, mid_point.y())
#
#             # End of the first line segment (right of the triangle's base)
#             line1_end = QPointF(mid_point.x() + half_gap, line_y)
#
#             # Start of the second line segment (left of the triangle's apex)
#             line2_start = QPointF(p_apex_left.x() - half_gap, line_y)
#
#             # The final destination for the entire horizontal line
#             final_line_end = QPointF(start_point.x() - x_diff, line_y)
#
#             # --- Update the QPainterPath ---
#
#             # 1. Draw the first line segment, stopping before the triangle
#             path.lineTo(line1_end)
#
#             # 2. Draw the equilateral triangle (now pointing left)
#             path.moveTo(p_base_top)
#             path.lineTo(p_apex_left)
#             path.lineTo(p_base_bottom)
#             path.closeSubpath()  # Draws the vertical base to close the shape
#
#             # 3. Move painter to the start of the second line segment
#             path.moveTo(line2_start)
#
#             # 4. Draw the final line segment
#             path.lineTo(final_line_end)
#
#             # # set the pen style back to the original style
#             # self.setPen(QPen(self.color, 2, current_style, Qt.RoundCap, Qt.RoundJoin))
#
#             # Draw half of the left side of the loop
#             line_to = QPointF(start_point.x() - x_diff - x_rad, start_point.y() + y_rad + var)
#             cp5 = QPointF(start_point.x() - x_diff - x_rad, start_point.y() + y_rad + var + y_rad)
#             cp6 = line_to
#             path.cubicTo(cp5, cp6, line_to)
#
#             if extender_side == 'left':
#                 # Draw the vertical line up y_diff pixels
#                 line_to = QPointF(start_point.x() - x_diff - x_rad, start_point.y() + y_rad - y_diff)
#                 path.lineTo(line_to)
#             else:
#                 # Draw the vertical line down y_diff pixels
#                 line_to = QPointF(start_point.x() - x_diff - x_rad, start_point.y() + y_rad + y_diff)
#                 path.lineTo(line_to)
#
#             # Draw the other half of the left hand side loop
#             # cp7 = QPointF(start_point.x() - x_diff - 25, start_point.y() + 25 - y_diff - 25)
#             # cp8 = QPointF(start_point.x(), start_point.y() + 25 - y_diff - 25)
#             diag_pt_top_right = QPointF(line_to.x() + x_rad, line_to.y() - y_rad)
#             # diag_pt_top_right = line_to + QPointF(25, 25 * (-1 if line_is_under else 1))
#             cp7 = QPointF(diag_pt_top_right.x() - x_rad, diag_pt_top_right.y() + y_rad)
#             cp8 = QPointF(diag_pt_top_right.x() - x_rad, diag_pt_top_right.y())
#             path.cubicTo(cp7, cp8, diag_pt_top_right)
#
#             # Draw line to the end point
#             path.lineTo(end_point)
#         else:
#             x_distance = (end_point - start_point).x()
#             y_distance = abs((end_point - start_point).y())
#
#             # Set control points offsets to be a fraction of the horizontal distance
#             fraction = 0.61  # Adjust the fraction as needed (e.g., 0.2 for 20%)
#             offset = x_distance * fraction
#             if offset < 0:
#                 offset *= 3
#                 offset = min(offset, -40)
#             else:
#                 offset = max(offset, 40)
#                 offset = min(offset, y_distance)
#             offset = abs(offset)  # max(abs(offset), 10)
#
#             path = QPainterPath(start_point)
#             ctrl_point1 = start_point + QPointF(offset, 0)
#             ctrl_point2 = end_point - QPointF(offset, 0)
#             path.cubicTo(ctrl_point1, ctrl_point2, end_point)
#             self.looper_midpoint = None
#
#         self.setPath(path)
#         self.updateSelectionPath()
#
#     def updateSelectionPath(self):
#         stroker = QPainterPathStroker()
#         stroker.setWidth(20)
#         self.selection_path = stroker.createStroke(self.path())
#
#     def shape(self):
#         if self.selection_path is None:
#             return super().shape()
#         return self.selection_path


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


class RoundedRectWidget(QGraphicsWidget):
    def __init__(self, parent, points, member_ids, rounding_radius=25):
        super().__init__()
        self.parent = parent
        self.member_ids = member_ids

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
