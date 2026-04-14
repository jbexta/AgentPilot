import json
import math
import sqlite3
import uuid
from functools import partial
from typing import Optional, Dict, Tuple, List, Any

from typing_extensions import override

from plugins.workflows.widgets.input_settings import InputSettings
from plugins.workflows.widgets.video_settings import VideoSettings
from plugins.workflows.widgets.image_settings import ImageSettings
from utils import sql

from PySide6.QtCore import QPointF, QRectF, QPoint, Signal, QSize
from PySide6.QtGui import QIcon, QPixmap, Qt, QPen, QColor, QBrush, QPainter, QPainterPath, QCursor, QRadialGradient, \
    QPainterPathStroker, QLinearGradient, QAction, QFont, QWheelEvent, QTransform
from PySide6.QtWidgets import *

from gui import system
from gui.widgets.config_widget import ConfigWidget
from gui.widgets.config_fields import ConfigFields
from gui.widgets.config_json_tree import ConfigJsonTree
from gui.widgets.config_joined import ConfigJoined

from gui.util import CustomMenu, IconButton, TreeDialog, CVBoxLayout, CHBoxLayout, \
    BaseTreeWidget, colorize_pixmap, find_main, clear_layout, safe_single_shot, get_selected_pages, set_selected_pages, \
    find_attribute, get_member_settings_class
from utils.helpers import path_to_pixmap, display_message_box, get_avatar_paths_from_config, \
    get_member_name_from_config, block_signals, display_message, apply_alpha_to_hex, \
    set_module_type, merge_config_into_workflow_config, merge_multiple_into_workflow_config, \
    resolve_linked_config, save_linked_config, has_circular_link


@set_module_type('Widgets')
class WorkflowSettings(ConfigWidget):
    def __init__(self, parent, **kwargs):
        super().__init__(parent=parent)
        self.compact_mode: bool = kwargs.get('compact_mode', False)  # For use in agent page
        self.compact_mode_editing: bool = False
        self.workflow_editable: bool = kwargs.get('workflow_editable', True)
        self.collapsible: bool = kwargs.get('collapsible', False)
        self.linked_id = None

        self.setSizePolicy(QSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding))

        self.members_in_view: Dict[str, DraggableMember] = {}
        self.inputs_in_view: Dict[Tuple[str, str], ConnectionLine] = {}  # (source_member_id, target_member_id): line

        self.new_lines: Optional[List[ConnectionLine]] = None
        self.new_members: Optional[List[Tuple[QPointF, DraggableMember]]] = None  # InsertableMember]]] = None
        self.adding_line: Optional[ConnectionLine] = None
        self.del_pairs: Optional[Any] = None

        self.autorun: bool = True

        self.layout = CVBoxLayout(self)

        self.header_widget = HeaderFields(self)
        self.scene = QGraphicsScene(self)
        self.scene.setSceneRect(0, 0, 2000, 2000)

        self.view = self.CustomGraphicsView(self.scene, self)

        self.workflow_buttons = self.WorkflowButtons(self)

        self.compact_mode_back_button = self.CompactModeBackButton(parent=self)
        self.member_config_widget = MemberConfigWidget(parent=self)
        # self.member_config_widget.hide()  # 32

        h_layout = CHBoxLayout()
        h_layout.addWidget(self.view)

        # self.member_list = self.MemberList(parent=self)
        # h_layout.addWidget(self.member_list)
        # self.member_list.hide()

        self.workflow_options = self.WorkflowOptions(parent=self)
        self.workflow_options.build_schema()

        self.workflow_description = self.WorkflowDescription(parent=self)
        self.workflow_description.build_schema()

        self.workflow_params = self.WorkflowParams(parent=self)
        self.workflow_params.build_schema()

        self.scene.selectionChanged.connect(self.on_selection_changed)
        
        self.layout.addWidget(self.compact_mode_back_button)
        self.layout.addWidget(self.header_widget)

        self.workflow_panel = QWidget()
        self.workflow_panel.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
        panel_layout = CVBoxLayout(self.workflow_panel)
        panel_layout.addWidget(self.workflow_buttons)
        panel_layout.addLayout(h_layout)

        self.splitter = QSplitter(Qt.Vertical)
        self.splitter.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.splitter.setChildrenCollapsible(False)

        self.splitter.addWidget(self.workflow_params)
        self.splitter.addWidget(self.workflow_description)
        self.splitter.addWidget(self.workflow_options)

        self.splitter.addWidget(self.workflow_panel)

        self.splitter.addWidget(self.member_config_widget)
        self.layout.addWidget(self.splitter)

        if not self.workflow_editable:
            self.splitter.hide()
            # self.workflow_panel.hide()
            # self.member_config_widget.hide()

    @override
    def load_config(self, json_config=None):
        if json_config is None:
            if hasattr(self.parent, 'config'):
                if self.conf_namespace is None:
                    json_config = self.parent.config.copy()
                else:
                    json_config = {k: v for k, v in self.parent.config.items() if k.startswith(f'{self.conf_namespace}.')}

        elif isinstance(json_config, str):
            json_config = json.loads(json_config)
            
        json_config = merge_config_into_workflow_config(json_config)

        self.linked_id = json_config.get('linked_id', None)

        json_wf_options = json_config.get('options', {})
        json_wf_params = json_config.get('params', [])
        wf_desc = json_config.get('description', '')
        self.header_widget.load_config(json_config)

        header_fields = self.header_widget.widgets[0]
        header_fields._update_link_icon(self.linked_id is not None)
        
        self.workflow_buttons.autorun = json_wf_options.get('autorun', True)
        self.workflow_buttons.show_hidden_bubbles = json_wf_options.get('show_hidden_bubbles', False)
        self.workflow_buttons.show_nested_bubbles = json_wf_options.get('show_nested_bubbles', False)
        self.workflow_buttons.mini_view = json_wf_options.get('mini_view', False)

        self.workflow_options.load_config(json_wf_options)
        self.workflow_params.load_config({'data': json_wf_params})  # !55! #
        self.workflow_description.load_config({'description': wf_desc})
        super().load_config(json_config)

    @override
    def get_config(self):
        workflow_toolbar = {
            'autorun': self.workflow_buttons.autorun,
            'show_hidden_bubbles': self.workflow_buttons.show_hidden_bubbles,
            'show_nested_bubbles': self.workflow_buttons.show_nested_bubbles,
            'mini_view': self.workflow_buttons.mini_view,
        }
        workflow_opts = self.workflow_options.get_config()
        workflow_opts.update(workflow_toolbar)

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
        if self.linked_id:
            config['linked_id'] = self.linked_id

        for member_id, member in self.members_in_view.items():
            # # add _TYPE to member_config
            if '_TYPE' not in member.member_config:
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

        for m in self.members_in_view.values():
            m.update_visuals()  # refresh_avatar()
        self.refresh_member_highlights()
        # self.refresh_member_headers()
        # if hasattr(self, 'member_list'):
        #     self.member_list.load()

    @override
    def load(self):
        # # self.setUpdatesEnabled(False)
        sel_member_ids = [x.id for x in self.scene.selectedItems()
                          if isinstance(x, DraggableMember)]

        # Reset member config widget before reloading to avoid stale references
        self.member_config_widget.config_widget = None
        self.member_config_widget.hide()
        if self.compact_mode_editing:
            self.set_edit_mode(False)
        self.header_widget.setVisible(True)
        self.workflow_panel.setVisible(True)

        self.load_members()
        self.load_inputs()
        self.header_widget.load()
        self.workflow_params.load()
        self.workflow_options.load()
        self.workflow_buttons.reload_predicates()
        # self.workflow_buttons.load()

        # if hasattr(self, 'member_list'):
        #     self.member_list.load()

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
            # if not self.compact_mode:
            self.select_ids(sel_member_ids)

        # from gui import system
        # view_type = system.manager.config.get('display.workflow_view', 'Mini')
        # self.view.mini_view = view_type == 'Mini'
        # self.view.mini_view = self.workflow_options.get('mini_view', True)
        self.view.refresh_mini_view()
        self.refresh_member_highlights()
        # self.refresh_member_headers()
        # self.setUpdatesEnabled(True)

    def load_members(self):
        # Block signals during cleanup to prevent on_selection_changed
        # from firing with stale state mid-reload
        with block_signals(self.scene):
            # Remove inputs before members so connection lines don't
            # reference destroyed member connection points
            for _, line in self.inputs_in_view.items():
                self.scene.removeItem(line)
            self.inputs_in_view = {}

            for m_id, member in self.members_in_view.items():
                self.scene.removeItem(member)
            self.members_in_view = {}

        members_data = self.config.get('members', [])
        for member_info in members_data:
            _id = member_info['id']
            linked_id = member_info.get('linked_id', None)
            member_config = member_info.get('config')

            # Resolve linked config from source entity
            if linked_id:
                resolved = resolve_linked_config(linked_id)
                if resolved is not None:
                    member_config = resolved
                    member_info['config'] = resolved

            loc_x = member_info.get('loc_x')
            loc_y = member_info.get('loc_y')
            width = member_info.get('width', None)
            height = member_info.get('height', None)

            member = DraggableMember(self, _id, linked_id, loc_x, loc_y, width, height, member_config)
            self.scene.addItem(member)
            self.members_in_view[_id] = member

        self.view.fit_to_all()

    def load_inputs(self):
        with block_signals(self.scene):
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

        members = list(self.members_in_view.values())
        if member_count == 1:
            member_config = members[0].member_config
            types_to_simplify = ['text', 'code', 'prompt', 'audio', 'image', 'video']
            if member_config.get('_TYPE', 'agent') in types_to_simplify:
                return True

        elif member_count == 2:
            members.sort(key=lambda m: m.x())
            first_member = members[0]
            second_member = members[1]
            conversation_types_except_user = ['agent', 'claude_code']
            if first_member.member_type == 'user' and second_member.member_type in conversation_types_except_user:
                return True

        return False

    def toggle_view(self, visible):
        self.view.setVisible(visible)
        self.splitter.setHandleWidth(0 if not visible else 1)
        handle = self.splitter.handle(4)
        handle.setStyleSheet('' if visible else 'border: none;')
        handle.setMaximumHeight(16777215 if visible else 0)
        if visible and self.compact_mode:
            safe_single_shot(10, lambda: self.splitter.setSizes([0, 0, 0, 1000, 0]))
        else:
            safe_single_shot(10, lambda: self.splitter.setSizes([0, 0, 0, 0, 1000]))

    def reposition_view(self):
        # return
        min_scroll_x = self.view.horizontalScrollBar().minimum()
        min_scroll_y = self.view.verticalScrollBar().minimum()
        self.view.horizontalScrollBar().setValue(min_scroll_x)
        self.view.verticalScrollBar().setValue(min_scroll_y)

    def set_edit_mode(self, state):
        # # if not self.compact_mode:
        # #     return
        # if not hasattr(self.parent.parent, 'view'):  # todo clean
        #     return

        tree_container = find_attribute(self.parent, 'tree_container', None)
        # is_root_workflow = tree_container is not None
        is_nested_workflow = hasattr(self.parent.parent, 'view')
        is_root_workflow = not is_nested_workflow

        if is_root_workflow:
            if tree_container:
                splitter = tree_container.parent()  # .splitter
                if splitter.orientation() == Qt.Horizontal:
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

        if is_nested_workflow:  # todo clean
            wf_settings = self.parent.parent
            wf_settings.toggle_view(not state)
            parent_is_nested = hasattr(
                wf_settings.parent.parent, 'view'
            )
            root_tree_container = find_attribute(
                wf_settings.parent, 'tree_container', None
            )
            hide_header = (
                root_tree_container is not None or parent_is_nested
            )
            if hide_header:
                wf_settings.header_widget.setVisible(not state)
                wf_settings.workflow_panel.setVisible(not state)
                show_description = wf_settings.workflow_buttons.inner_widget.btn_description.isChecked()
                show_options = wf_settings.workflow_buttons.inner_widget.btn_workflow_options.isChecked()
                show_params = wf_settings.workflow_buttons.inner_widget.btn_workflow_params.isChecked()
                wf_settings.workflow_description.setVisible(not state and show_description)
                wf_settings.workflow_options.setVisible(not state and show_options)
                wf_settings.workflow_params.setVisible(not state and show_params)
                if state:
                    wf_settings.compact_mode_back_button.hide()
                else:
                    if wf_settings.compact_mode_editing:
                        wf_settings.compact_mode_back_button.show()
            if not state:
                wf_settings.member_config_widget.hide()
            self.compact_mode_back_button.setVisible(state)

        elif is_root_workflow:
            tree_container = find_attribute(self.parent, 'tree_container', None)
            if tree_container:
                tree_container.setVisible(not state)
                self.compact_mode_back_button.setVisible(state)
                print(f'compact_mode_back_button for root workflow is {state}')
                # return

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
        if not can_simplify and len(selected_objects) > 0 and not self.compact_mode_editing:
            self.set_edit_mode(True)

        if len(selected_objects) == 1 and (self.view.mini_view or not self.view.isVisible()):
            if len(selected_agents) == 1:
                member = selected_agents[0]
                self.member_config_widget.display_member(member=member)
                if hasattr(self.member_config_widget.config_widget, 'reposition_view'):
                    self.member_config_widget.config_widget.reposition_view()

            elif len(selected_lines) == 1:
                line = selected_lines[0]
                self.member_config_widget.show_input(line)

        else:
            # is_vis = self.member_config_widget.isVisible()
            self.member_config_widget.hide()  # 32

        # self.workflow_buttons.load()  # !404!
        self.workflow_buttons.reload_predicates()

        # if hasattr(self, 'member_list'):
        #     self.member_list.refresh_selected()

    def add_insertable_entity(self, item, del_pairs=None):
        # if self.compact_mode:
        self.set_edit_mode(True)
        if self.new_members:
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

        self.new_members = [
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

        for pos, entity in self.new_members:
            self.scene.addItem(entity)

        self.view.setFocus()

    def add_insertable_input(self, item, member_bundle):
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
                ConnectionLine(
                    self,
                    None,
                    None,
                    config=config,
                    temp_indices=(source_member_index, member_index, self.new_members)
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
        for i, enitity_tup in enumerate(self.new_members):
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

        transform = self.view.transform()
        h_scroll = self.view.horizontalScrollBar().value()
        v_scroll = self.view.verticalScrollBar().value()

        self.update_config()
        # if hasattr(self.parent, 'top_bar'):
        if hasattr(self.parent, 'load'):
            self.parent.load()

        self.view.setTransform(transform)
        self.view.horizontalScrollBar().setValue(h_scroll)
        self.view.verticalScrollBar().setValue(v_scroll)

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
            display_message(
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
        if self.new_members:
            for pos, entity in self.new_members:
                self.view.scene().removeItem(entity)
        if self.del_pairs:
            for item in self.del_pairs:
                if isinstance(item, QGraphicsItem):
                    item.setOpacity(1.0)

        self.new_members = None
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
        if not self.linked_workflow():
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
        # scaleChanged = Signal(float)  # Add signal for scale changes

        def __init__(self, scene, parent):
            super().__init__(scene, parent)
            self.parent = parent
            self.mini_view = True

            self._is_panning = False
            self._mouse_press_pos = None
            self._mouse_press_scroll_x_val = None
            self._mouse_press_scroll_y_val = None

            self.temp_block_move_flag = False

            self.setMinimumHeight(120)
            self.setHorizontalScrollBarPolicy(Qt.ScrollBarAsNeeded)
            self.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
            self.setRenderHint(QPainter.Antialiasing)

            self.setTransformationAnchor(QGraphicsView.ViewportAnchor.AnchorUnderMouse)
            self.setResizeAnchor(QGraphicsView.ViewportAnchor.AnchorUnderMouse)

            from gui.style import TEXT_COLOR
            from utils.helpers import apply_alpha_to_hex
            self.setBackgroundBrush(QBrush(QColor(apply_alpha_to_hex(TEXT_COLOR, 0.05))))
            self.setFrameShape(QFrame.Shape.NoFrame)

        def toggle_mini_view(self):
            self.mini_view = not self.mini_view
            self.refresh_mini_view()
            self.parent.update_config()

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
            if self.mini_view:
                self.setDragMode(QGraphicsView.RubberBandDrag)
                # drag_mode = QGraphicsView.RubberBandDrag
                self.setTransform(QTransform())
                # self.parent.select_ids([])
            else:
                self.setDragMode(QGraphicsView.NoDrag)
                # self.fit_to_all()
                # drag_mode = QGraphicsView.NoDrag

            # self.setDragMode(drag_mode)
            for item in self.scene().items():
                if isinstance(item, DraggableMember):
                    item.update_visuals()
            for line in self.parent.inputs_in_view.values():
                line.updatePosition()
            self.update()

        def wheelEvent(self, event: QWheelEvent):
            if self.mini_view:
                super().wheelEvent(event)
                return

            # Ensure the scene and view are valid
            if not self.scene() or not self.isEnabled():
                return

            # Zoom factor with bounds
            mult = 1.03
            zoom_factor = mult if event.angleDelta().y() > 0 else 1.0 / mult
            current_scale = self.transform().m11()
            if (zoom_factor > 1 and current_scale > 10) or (zoom_factor < 1 and current_scale < 0.1):
                return  # Prevent extreme zooming

            # # Get mouse position safely
            # try:
            mouse_pos = event.position()  # QPointF
            scene_pos = self.mapToScene(mouse_pos.toPoint())  # Convert to QPoint
            # except Exception as e:
            #     print(f"Error mapping mouse position: {e}")
            #     return

            # Apply transformation
            current_transform = self.transform()
            new_transform = (
                current_transform
                .translate(scene_pos.x(), scene_pos.y())
                .scale(zoom_factor, zoom_factor)
                .translate(-scene_pos.x(), -scene_pos.y())
            )
            # Check if transform is valid
            if new_transform.isInvertible():
                self.setTransform(new_transform)
            # else:
            #     print("Invalid transformation matrix, skipping zoom")
            # except Exception as e:
            #     print(f"Error applying transform: {e}")

        def contextMenuEvent(self, event):
            workflow_menu = self.parent.workflow_buttons
            schema = [item.copy() for item in workflow_menu.schema]
            schema[0].pop('target')
            schema[0]['submenu'] = workflow_menu.create_new_member_menu()
            menu = CustomMenu(parent=self, schema=schema)
            menu.show_popup_menu()

        def closest_connection_point(self, mouse_screen_pos, use_point='output'):
            """Return (member, distance) of the closest output_point to mouse_screen_pos within max_dist, or (None, None)."""
            closest_member = None
            max_dist = 20
            max_inward_x_dist = 10
            
            closest_dist = max_dist + 1
            for member in self.parent.members_in_view.values():
                if not isinstance(member, DraggableMember):
                    continue

                if use_point == 'output':
                    point_scene_pos = member.output_point.scenePos()
                elif use_point == 'input':
                    point_scene_pos = member.input_point.scenePos()
                else:
                    raise ValueError(f"Invalid point type: {use_point}")

                view = self
                point_view_pos = view.mapFromScene(point_scene_pos)
                point_view_pos_int = point_view_pos.toPoint() if hasattr(point_view_pos, "toPoint") else point_view_pos
                if not view.viewport().rect().contains(point_view_pos_int):
                    continue
                point_screen_pos = view.viewport().mapToGlobal(point_view_pos_int)
                dx = point_screen_pos.x() - mouse_screen_pos.x()
                dy = point_screen_pos.y() - mouse_screen_pos.y()
                dist = (dx ** 2 + dy ** 2) ** 0.5

                # Inward/outward logic
                inward = False
                x_dist = abs(dx)
                if use_point == 'output':
                    if mouse_screen_pos.x() < point_screen_pos.x():
                        inward = True
                elif use_point == 'input':
                    if mouse_screen_pos.x() > point_screen_pos.x():
                        inward = True

                if inward and x_dist > max_inward_x_dist:
                    continue

                if dist < closest_dist:
                    closest_dist = dist
                    closest_member = member

            if closest_dist <= max_dist:
                return closest_member
                
            return None

        def mouseReleaseEvent(self, event):
            self._is_panning = False
            self._mouse_press_pos = None
            self._mouse_press_scroll_x_val = None
            self._mouse_press_scroll_y_val = None

            # Reset drag mode if it was temporarily changed for rubber banding in non-mini view.
            if not self.mini_view and self.dragMode() == QGraphicsView.RubberBandDrag:
                self.setDragMode(QGraphicsView.NoDrag)

            super().mouseReleaseEvent(event)

        def mousePressEvent(self, event):
            self.temp_block_move_flag = False

            if self.parent.new_members:
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

            # --- New Logic: InsertableLine on closest_connection_point ---
            if event.button() == Qt.LeftButton:
                if self.parent.adding_line is not None:

                    mouse_screen_pos = self.viewport().mapToGlobal(event.pos())
                    closest_member = self.closest_connection_point(mouse_screen_pos, use_point='input')
                    if closest_member is None:
                        self.parent.cancel_new_line()
                    else:
                        self.parent.add_input(closest_member.id)


                else:
                    mouse_screen_pos = self.viewport().mapToGlobal(event.pos())
                    closest_member = self.closest_connection_point(mouse_screen_pos, use_point='output')
                    if closest_member is not None:
                        # # Check if mouse is over the draggable member
                        # mouse_scene_pos = self.mapToScene(event.pos())
                        # item = self.scene().itemAt(mouse_scene_pos, self.transform())
                        # if item is closest_member or (hasattr(item, 'parentItem') and item.parentItem() is closest_member):
                        #     # Mouse is on the member, do not select or start InsertableLine
                        #     return
                        # Begin InsertableLine from closest_member
                        self.parent.adding_line = ConnectionLine(self.parent, closest_member)
                        self.parent.scene.addItem(self.parent.adding_line)
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
            self.parent.cancel_new_line()

        def mouseMoveEvent(self, event):
            update = False
            mouse_point = self.mapToScene(event.pos())
            # Get mouse position in global (screen) coordinates
            mouse_screen_pos = self.viewport().mapToGlobal(event.pos())

            # --- Only show the closest output_point within 20px ---
            closest_member = self.closest_connection_point(mouse_screen_pos, use_point='output')
            for member in self.parent.members_in_view.values():
                if isinstance(member, DraggableMember):
                    member.output_point.setVisible(member is closest_member)

            if self.parent.adding_line:
                self.parent.adding_line.updateEndPoint(mouse_point)
                update = True
            if self.parent.new_members:
                for pos, entity in self.parent.new_members:
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
                if self.parent.new_members:
                    self.parent.cancel_new_entity()
                event.accept()

            elif event.key() == Qt.Key_Delete:
                if self.parent.new_lines or self.parent.adding_line:
                    self.parent.cancel_new_line()
                    event.accept()
                    return
                if self.parent.new_members:
                    self.parent.cancel_new_entity()
                    event.accept()
                    return

                self.parent.workflow_buttons.delete_selected_items()  # !404!
                event.accept()
            elif event.modifiers() == Qt.ControlModifier:
                if event.key() == Qt.Key_C:
                    self.parent.workflow_buttons.copy_selected_items()  # !404!
                    event.accept()
                elif event.key() == Qt.Key_V:
                    self.parent.workflow_buttons.paste_items()  # !404!
                    event.accept()
            else:
                super().keyPressEvent(event)
    
    class WorkflowButtons(CustomMenu):
        def __init__(self, parent):
            super().__init__(parent)
            self.parent = parent

            self.autorun = True
            self.mini_view = True
            self.show_hidden_bubbles = False
            self.show_nested_bubbles = False

            self.schema = [
                {
                    'text': 'Add',
                    'icon_path': ':/resources/icon-new.png',
                    'target': lambda: self.show_add_context_menu(),
                },
                {
                    'type': 'separator',
                },
                {
                    'text': 'Copy',
                    'icon_path': ':/resources/icon-copy.png',
                    'target': self.copy_selected_items,
                    'enabled': lambda: len(parent.scene.selectedItems()) > 0,
                    'visibility_predicate': lambda: parent.count_other_members() > 1,
                },
                {
                    'text': 'Paste',
                    'icon_path': ':/resources/icon-paste.png',
                    'target': self.paste_items,
                    'enabled': lambda: self.has_copied_items(),
                    'visibility_predicate': lambda: parent.count_other_members() > 1,
                },
                {
                    'text': 'Delete',
                    'icon_path': ':/resources/icon-delete-2.png',
                    'target': self.delete_selected_items,
                    'enabled': lambda: len(parent.scene.selectedItems()) > 0,
                    'visibility_predicate': lambda: parent.count_other_members() > 1,
                },
                {
                    'type': 'separator',
                },
                {
                    'text': 'Group',
                    'icon_path': ':/resources/icon-screenshot.png',
                    'target': self.group_selected_items,
                    'enabled': lambda: len(parent.scene.selectedItems()) > 1,
                    'visibility_predicate': lambda: parent.count_other_members() > 1,
                },
                {
                    'text': 'Explode',
                    'icon_path': ':/resources/icon-screenshot.png',
                    'target': self.explode_selected_item,
                    'enabled': lambda: len(parent.scene.selectedItems()) == 1 and isinstance(parent.scene.selectedItems()[0], DraggableMember) and parent.scene.selectedItems()[0].member_type == 'workflow',
                    'visibility_predicate': lambda: parent.count_other_members() > 1,
                },
                {
                    'type': 'stretch',
                },
                {
                    'text': 'View',
                    'icon_path': ':/resources/icon-eye.png',
                    'submenu': [
                        {
                            'text': 'Show hidden bubbles',
                            'target': lambda: self.toggle_attribute('show_hidden_bubbles'),
                            'visibility_predicate': lambda: self.parent.linked_workflow() is not None,
                            'checkable': True,
                            'checked_state': lambda: self.show_hidden_bubbles,
                        },
                        {
                            'text': 'Show nested bubbles',
                            'target': lambda: self.toggle_attribute('show_nested_bubbles'),
                            'visibility_predicate': lambda: self.parent.linked_workflow() is not None,
                            'checkable': True,
                            'checked_state': lambda: self.show_nested_bubbles,
                        },
                        {
                            'text': 'Mini view',
                            'target': lambda: self.toggle_attribute('mini_view'),
                            'visibility_predicate': lambda: self.parent.linked_workflow() is not None,
                            'checkable': True,
                            'checked_state': lambda: self.mini_view,
                        },
                    ],
                },
                # {
                #     'text': 'Member List',
                #     'icon_path': ':/resources/icon-list.png',
                #     'target': self.toggle_member_list,
                #     'checkable': True,
                #     'visibility_predicate': lambda: self.parent.linked_workflow() is not None,
                # },
                {
                    'text': 'Workflow Params',
                    'icon_path': ':/resources/icon-parameter.png',
                    # 'target': lambda: print('state:', self.inner_widget.btn_workflow_params.isChecked()),
                    'checkable': True,
                    'target': self.toggle_workflow_params,
                },
                {
                    'text': 'Description',
                    'icon_path': ':/resources/icon-description.png',
                    'target': self.toggle_description,
                    'checkable': True,
                },
                {
                    'text': 'Workflow Options',
                    'icon_path': ':/resources/icon-settings-solid.png',
                    'target': self.toggle_workflow_options,
                    'checkable': True,
                },
                {
                    'text': 'Save As',
                    'icon_path': ':/resources/icon-save.png',
                    'target': self.show_save_context_menu,
                },
            ]
            self.create_toolbar(parent)
        
        def toggle_attribute(self, attr):
            new_state = not getattr(self, attr)
            setattr(self, attr, new_state)
            self.parent.update_config()

        def create_new_member_menu(self, parent=None):
            def add_contxt_menu_header(menu, title):  # todo dedupe
                section = QAction(title, menu)
                section.setEnabled(False)
                font = QFont()
                font.setPointSize(8)
                section.setFont(font)
                menu.addAction(section)
            
            menu = QMenu('Add', parent)

            member_modules = system.manager.modules.get_modules_in_folder(
                module_type='Members',
                fetch_keys=('name', 'kind_folder', 'class',)
            )
            type_dict = {}
            for module_name, kind_folder, module_class in member_modules:
                if kind_folder not in type_dict:
                    type_dict[kind_folder] = []
                type_dict[kind_folder].append((module_name, module_class))
            
            type_dict.pop('models', None)  # todo integrate kinds

            for module_kind, kind_modules in type_dict.items():
                if not module_kind:
                    continue
                add_contxt_menu_header(menu, module_kind.capitalize())
                for module_name, module_class in kind_modules:
                    default_name = getattr(module_class, 'default_name', module_name.capitalize())
                    workflow_insert_mode = getattr(module_class, 'workflow_insert_mode', None)
                    icon_path = getattr(module_class, 'default_avatar', None)
                    if icon_path:
                        icon = QIcon(colorize_pixmap(QPixmap(icon_path)))
                    if workflow_insert_mode == 'single':
                        menu.addAction(
                            icon,
                            module_name.replace('_', ' ').title(), 
                            partial(
                                self.parent.add_insertable_entity,
                                {"_TYPE": module_name, "name": default_name}
                            )
                        )
                    elif workflow_insert_mode == 'list':
                        menu.addAction(icon, module_name.replace('_', ' ').title(), partial(self.choose_member, module_name))
                    else:
                        continue
            return menu

        def show_add_context_menu(self):
            menu = self.create_new_member_menu()
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
            save_task = menu.addAction('Save as Task')
            save_task.triggered.connect(partial(self.save_as, 'TASK'))
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

                elif save_type == 'TASK':
                    sql.execute("""
                        INSERT INTO tasks (uuid, name, kind, config)
                        VALUES (?, ?, ?, ?)
                    """, (str(uuid.uuid4()), new_name, 'SCHEDULED', workflow_config,))

                display_message(
                    message='Entity saved',
                    icon=QMessageBox.Information,
                )
            except sqlite3.IntegrityError as e:
                display_message(
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

        # def toggle_link(self):
        #     selected_member = next(iter(self.parent.view.scene().selectedItems()), None)
        #     if not selected_member or not isinstance(selected_member, DraggableMember):
        #         return
        #     if selected_member.linked_id is not None:
        #         # Unlink — keep current config as standalone
        #         selected_member.linked_id = None
        #         self.parent.update_config()
        #     else:
        #         # Link — open library to pick source entity
        #         from gui.util import LibraryDialog
        #         dialog = LibraryDialog(
        #             parent=self.parent,
        #             callback=lambda item: self._on_link_selected(selected_member, item),
        #         )
        #         dialog.open()

        # def _on_link_selected(self, member, item):
        #     """Handle library selection for linking a member."""
        #     item_data = item.data(0, Qt.UserRole)
        #     if not item_data or item_data == 'folder':
        #         return

        #     item_config = json.loads(item_data.get('config', '{}'))

        #     # The config returned has linked_id baked in from
        #     # merge_config_into_workflow_config. Extract it from members.
        #     members = item_config.get('members', [])
        #     linked_id = None
        #     for m in members:
        #         if m.get('linked_id'):
        #             linked_id = m['linked_id']
        #             break

        #     if not linked_id:
        #         linked_id = item_config.get('linked_id')

        #     if not linked_id:
        #         return

        #     # Check for circular references
        #     # Build existing chain from current workflow
        #     existing_chain = set()
        #     for m_id, m in self.parent.members_in_view.items():
        #         if m.linked_id and m.id != member.id:
        #             existing_chain.add(m.linked_id)

        #     if has_circular_link(linked_id, existing_chain=existing_chain):
        #         display_message(
        #             message='Cannot link: this would create a circular reference.',
        #             icon='Warning',
        #         )
        #         return

        #     # Resolve the source config
        #     resolved = resolve_linked_config(linked_id)
        #     if resolved is not None:
        #         member.member_config.clear()
        #         member.member_config.update(resolved)
        #     else:
        #         # Use the config from the library item as fallback
        #         member_config = members[0].get('config', {}) if members else item_config
        #         member.member_config.clear()
        #         member.member_config.update(member_config)

        #     member.linked_id = linked_id
        #     self.parent.update_config()
        #     self.parent.load()

        def copy_selected_items(self):
            member_configs, member_inputs = self.get_member_configs()

            relative_members = [(pos.x(), pos.y(), config) for pos, config in member_configs]
            member_bundle = (relative_members, member_inputs)
            # add to clipboard
            clipboard = QApplication.clipboard()
            copied_data = 'WORKFLOW_MEMBERS:' + json.dumps(member_bundle)
            clipboard.setText(copied_data)
            # self.load()

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

                member_configs = [(QPointF(pos_x, pos_y), config) for pos_x, pos_y, config in member_configs]

                self.parent.add_insertable_entity(member_configs)
                self.parent.add_insertable_input(member_inputs, member_bundle=member_bundle)

            except Exception as e:
                display_message(
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
            inputs = explode_item.member_config.get('inputs', [])
            if not members:
                return
            # parent_inputs = [
            #     inp for inp in self.parent.config.get('inputs', []) 
            #     if inp.get('source_member_id') == explode_item.id
            #     or inp.get('target_member_id') == explode_item.id
            # ]
            # # delete parent inputs
            # add as insertable entities
            member_id_indexes = {}  # dict of member_id: index

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
                member_id_indexes[member['id']] = len(member_configs) - 1
                
            for input in inputs:
                source_member_index = member_id_indexes[input['source_member_id']]
                target_member_index = member_id_indexes[input['target_member_id']]
                member_inputs.append((source_member_index, target_member_index, input['config']))
            
            relative_members = [(pos.x(), pos.y(), config) for pos, config in member_configs]
            member_bundle = (relative_members, member_inputs)

            del_pairs = scene.selectedItems()
            self.parent.add_insertable_entity(member_configs, del_pairs=del_pairs)
            self.parent.add_insertable_input(member_inputs, member_bundle=member_bundle)

        def group_selected_items(self):
            member_configs, member_inputs = self.get_member_configs()
            group_member_config = merge_multiple_into_workflow_config(member_configs, member_inputs)
            scene = self.parent.view.scene()
            del_pairs = scene.selectedItems()
            self.parent.add_insertable_entity(group_member_config, del_pairs=del_pairs)

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
                        painter = QPainter()
                        if painter.begin(new_pixmap):
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
            # if hasattr(workflow_settings.parent, 'top_bar'):
            if hasattr(workflow_settings.parent, 'load'):
                workflow_settings.parent.load()

        # def toggle_member_list(self):
        #     is_checked = self.inner_widget.btn_member_list.isChecked()
        #     self.parent.member_list.setVisible(is_checked)

        def toggle_workflow_params(self):
            self.show_toggle_widget(self.inner_widget.btn_workflow_params)

        def toggle_description(self):
            self.show_toggle_widget(self.inner_widget.btn_description)

        def toggle_workflow_options(self):
            self.show_toggle_widget(self.inner_widget.btn_workflow_options)

        def show_toggle_widget(self, toggle_btn):
            all_toggle_widgets = {
                self.inner_widget.btn_workflow_params: self.parent.workflow_params,
                self.inner_widget.btn_workflow_options: self.parent.workflow_options,
                self.inner_widget.btn_description: self.parent.workflow_description,
            }

            is_now_checked = toggle_btn.isChecked()

            # Show/hide the widget associated with the clicked button
            all_toggle_widgets[toggle_btn].setVisible(is_now_checked)

            # Ensure all other toggleable widgets are hidden and their buttons unchecked
            for btn, widget in all_toggle_widgets.items():
                if btn is not toggle_btn and btn.isChecked():
                    btn.setChecked(False)
                    widget.setVisible(False)

    class CompactModeBackButton(QWidget):
        def __init__(self, parent):
            super().__init__(parent)
            self.parent = parent
            self.layout = CHBoxLayout(self)
            depth = self.get_depth()
            self.btn_back = IconButton(
                parent=self,
                icon_path=':/resources/icon-back.png',
                tooltip='Back',
                size=22,
                icon_size_percent=0.7,
                text=f'Close edit mode ({depth} deep)',
            )
            self.btn_back.clicked.connect(partial(self.parent.set_edit_mode, False))

            self.layout.addWidget(self.btn_back)
            self.layout.addStretch(1)
            self.hide()
        
        def get_depth(self):
            depth = 0
            widget = self.parent
            while widget is not None:
                if hasattr(widget, 'view'):
                    depth += 1
                widget = getattr(widget, 'parent', None)
            return depth

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
                        'transparent': True,
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
        member_type = member_config.get('_TYPE', 'agent')
        self.member_config = member_config

        # --- State for resizing logic ---
        self.is_resizing = False
        self.current_resize_handle = self.NoHandle
        # self.resize_handle_size = 10.0
        self.original_geometry = QRectF()
        self.original_mouse_pos = QPointF()
        # ---

        self.member_ellipse = self.MemberEllipse(self, diameter=50 if member_type != 'node' else 20)
        self.member_proxy = self.MemberProxy(self)

        # Apply initial size for proxy
        if width and height:
            scale = self.member_proxy.scale()
            self.member_proxy.resize(width / scale, height / scale)
        self.member_proxy.setScale(0.1)

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
    
    @property
    def member_type(self):
        return self.member_config.get('_TYPE', 'agent')

    class MemberEllipse(QGraphicsEllipseItem):
        def __init__(self, parent, diameter):
            super().__init__(0, 0, diameter, diameter, parent=parent)
            from gui.style import TEXT_COLOR
            self.setPen(QPen(QColor(TEXT_COLOR), 0) if parent.member_type in ['user', 'agent', 'claude_code'] else Qt.NoPen)
            self.setAcceptHoverEvents(True)

    class MemberProxy(QGraphicsProxyWidget):
        def __init__(self, parent):
            super().__init__(parent=parent)
            self.parent = parent
            self.workflow_settings = parent.workflow_settings
            self.member_config_widget = MemberConfigWidget(parent=self)
            self.setWidget(self.member_config_widget)
            self.load()
        
        def load(self):
            return
            member_id = self.parent.id
            member_type = self.parent.member_type
            member_config = self.parent.member_config

            member_settings_class = get_member_settings_class(member_type)
            if member_settings_class is not None:
                self.member_config_widget.display_member(
                    member_id=member_id,
                    member_type=member_type,
                    member_config=member_config
                )

    def geometry(self) -> QRectF:
        """Returns the item's geometry (its bounding rectangle translated by its position) in scene coordinates."""
        content_rect = self._content_rect()
        return content_rect.translated(self.pos())

    def _content_rect(self) -> QRectF:
        """Returns the content rectangle (excluding resize handle padding) in local coordinates."""
        if self.workflow_settings.view.mini_view or not self.member_proxy.widget():
            return self.member_ellipse.rect()
        else:
            pr = self.member_proxy.boundingRect()
            scale = self.member_proxy.scale()
            return QRectF(pr.topLeft(), QSize(pr.width() * scale, pr.height() * scale))

    def boundingRect(self) -> QRectF:
        """Returns the bounding rectangle including resize handle padding."""
        content_rect = self._content_rect()

        handle_size = int(content_rect.width() * 0.05)
        padding = handle_size
        top_padding = padding + 20 if self.linked_id is not None else padding
        return content_rect.adjusted(-padding, -top_padding, padding, padding)

    def paint(self, painter, option, widget=None):
        from gui.style import TEXT_COLOR
        if option.state & QStyle.State_Selected:
            painter.setPen(QPen(QColor(TEXT_COLOR), 0, Qt.DashLine))
            painter.setBrush(Qt.NoBrush)
            border_rect = self._content_rect().adjusted(-1, -1, 1, 1)
            painter.drawRect(border_rect)

        # Visual indicator for linked members
        if self.linked_id is not None:
            from gui.style import TEXT_COLOR as _text_color
            content_rect = self._content_rect()
            icon_path = ':/resources/icon-link.png'
            pixmap = colorize_pixmap(QPixmap(icon_path), color=_text_color)
            pixmap = pixmap.scaled(16, 16, Qt.KeepAspectRatio, Qt.SmoothTransformation)
            icon_x = content_rect.right() - 14 # - 4  # pixmap.width() / 2
            icon_y = content_rect.top() - 4  # - pixmap.height() + 4  # - 4
            painter.setOpacity(0.5)
            painter.drawPixmap(QPointF(icon_x, icon_y), pixmap)
            painter.setOpacity(1.0)

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

        has_proxy = self.member_proxy.member_config_widget is not None
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
        self.output_point.setPos(rect.right(), rect.center().y() - self.output_point.boundingRect().height() / 2)

        self.refresh_avatar()
        self.highlight_background.updatePosition()

    def refresh_avatar(self):
        from gui.style import TEXT_COLOR
        if self.member_type == 'node':
            self.member_ellipse.setBrush(QBrush(QColor(TEXT_COLOR)))
            return

        hide_bubbles = self.member_config.get('group.hide_bubbles', False)
        in_del_pairs = self in (self.workflow_settings.del_pairs or [])
        opacity = 0.2 if (hide_bubbles or in_del_pairs) else 1
        avatar_paths = get_avatar_paths_from_config(self.member_config)

        diameter = self.member_ellipse.rect().width()
        pixmap = path_to_pixmap(avatar_paths, opacity=opacity, diameter=diameter)

        if pixmap and not pixmap.isNull():
            self.member_ellipse.setBrush(QBrush(pixmap.scaled(diameter, diameter)))

    def get_handle_at(self, pos: QPointF):  # todo dedupe
        # Map the proxy's bounding rect to the parent (this DraggableMember)
        # to get a rect in local coordinates that accounts for the proxy's scale.
        proxy_br = self.member_proxy.boundingRect()
        rect = self.member_proxy.mapToParent(proxy_br).boundingRect()
        content_rect = self._content_rect()
        handle_size = int(content_rect.width() * 0.05)

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
        if self.workflow_settings.view.temp_block_move_flag:
            return

        if self.is_resizing:
            delta = event.scenePos() - self.original_mouse_pos
            new_geom = QRectF(self.original_geometry)
            handle = self.current_resize_handle
            scale = self.member_proxy.scale()

            # Calculate new content geometry (excluding padding)
            if handle in (self.Left, self.TopLeft, self.BottomLeft):
                new_geom.setLeft(self.original_geometry.left() + delta.x())
            if handle in (self.Right, self.TopRight, self.BottomRight):
                new_geom.setRight(self.original_geometry.right() + delta.x())
            if handle in (self.Top, self.TopLeft, self.TopRight):
                new_geom.setTop(self.original_geometry.top() + delta.y())
            if handle in (self.Bottom, self.BottomLeft, self.BottomRight):
                new_geom.setBottom(self.original_geometry.bottom() + delta.y())

            # Adjust position to keep the opposite corner/edge fixed
            new_pos = self.pos()
            if handle in (self.Right, self.Bottom, self.BottomRight):
                new_pos = self.original_geometry.topLeft()  # Keep top-left fixed
            elif handle == self.Top:
                new_pos.setY(self.original_geometry.top() + delta.y())
            elif handle == self.Bottom:
                new_pos.setY(self.original_geometry.top())
            elif handle == self.Left:
                new_pos.setX(self.original_geometry.left() + delta.x())
            elif handle == self.Right:
                new_pos.setX(self.original_geometry.left())
            elif handle == self.TopLeft:
                new_pos = QPointF(self.original_geometry.left() + delta.x(), self.original_geometry.top() + delta.y())
            elif handle == self.TopRight:
                new_pos = QPointF(self.original_geometry.left(), self.original_geometry.top() + delta.y())
            elif handle == self.BottomLeft:
                new_pos = QPointF(self.original_geometry.left() + delta.x(), self.original_geometry.top())

            # Update position and size
            self.prepareGeometryChange()
            self.setPos(new_pos)
            self.member_proxy.resize(new_geom.size() / scale)
            self.update_visuals()
            event.accept()
        else:
            super().mouseMoveEvent(event)

        for line in self.workflow_settings.inputs_in_view.values():
            if line.source_member_id == self.id or line.target_member_id == self.id:
                line.updatePosition()

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

        current_size = self.member_proxy.size() # * self.member_proxy.scale()

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
            self.padding = 5

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
            from gui.style import TEXT_COLOR
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


class ConnectionLine(QGraphicsPathItem):
    def __init__(self, parent, source_member, target_member=None, config=None, *, temp_indices=None):
        super().__init__()
        from gui.style import TEXT_COLOR
        self.parent = parent
        self.selection_path = None
        # self.looper_midpoint = None
        self.config: Dict[str, Any] = config if config else {}

        self.setAcceptHoverEvents(True)
        self.color = QColor(TEXT_COLOR)
        self.setPen(QPen(self.color, 2, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin))
        self.setZValue(-1)
        self.setFlag(QGraphicsItem.ItemIsSelectable)
        # temp_indices: (source_index, target_index, new_members_ref)
        self.temp_indices = temp_indices
        if temp_indices is not None:
            source_index, target_index, new_members = temp_indices
            self.source_member_index = source_index
            self.target_member_index = target_index
            self.new_members = new_members
            self.source_member_id = None
            self.target_member_id = None
            self.start_point = None
            self.end_point = None
        else:
            self.source_member_id = source_member.id
            self.target_member_id = target_member.id if target_member else None
            self.start_point = source_member.output_point
            self.end_point = target_member.input_point if target_member else None
        self.updatePath()

    def updateEndPoint(self, end_point_pos):
        # Use the new closest_connection_point method from the view
        view = self.parent.view
        mouse_screen_pos = view.viewport().mapToGlobal(view.mapFromScene(end_point_pos.toPoint() if hasattr(end_point_pos, "toPoint") else end_point_pos))
        closest_member = view.closest_connection_point(mouse_screen_pos, use_point='input')

        if closest_member and closest_member.id != self.source_member_id:
            self.end_point = closest_member.input_point.scenePos()
            self.config['looper'] = self.parent.check_for_circular_references(closest_member.id, [self.source_member_id])
        else:
            self.end_point = end_point_pos
            self.config['looper'] = False
        self.updatePath()

    def updatePosition(self):
        self.updatePath()
        if self.scene():
            self.scene().update(self.scene().sceneRect())

    def updatePath(self):
        if self.temp_indices:
            source_index, target_index, new_members = self.temp_indices
            start_point = new_members[source_index][1].output_point.scenePos()
            end_point = new_members[target_index][1].input_point.scenePos()
        else:
            if self.end_point is None:
                return
            try:
                start_point = self.start_point.scenePos() if isinstance(self.start_point, QGraphicsItem) else self.start_point
                end_point = self.end_point.scenePos() if isinstance(self.end_point, QGraphicsItem) else self.end_point
            except RuntimeError:
                return
        
        start_point.setX(start_point.x() - 2)
        end_point.setX(end_point.x() - 2)

        path = self._calculate_path(start_point, end_point)
        self.setPath(path)
        self.updateSelectionPath()

    @staticmethod
    def blend_colors(color1, color2, ratio):
        r = int(color1.red() * (1 - ratio) + color2.red() * ratio)
        g = int(color1.green() * (1 - ratio) + color2.green() * ratio)
        b = int(color1.blue() * (1 - ratio) + color2.blue() * ratio)
        return QColor(r, g, b)

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
            side_length, gap = 15.0, 2.0
            triangle_height = (side_length * math.sqrt(3)) / 2
            line_y = start_point.y() + y_rad + var + y_rad
            mid_point = QPointF(start_point.x() - (x_diff / 2) + triangle_height / 2, line_y)
            # mid_point = mid_point - QPointF(triangle_height / 2, 0)
            # self.looper_midpoint = mid_point

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
            # self.looper_midpoint = None

        return path

    def updateSelectionPath(self):
        stroker = QPainterPathStroker()
        stroker.setWidth(20)
        self.selection_path = stroker.createStroke(self.path())

    def shape(self):
        return self.selection_path if self.selection_path else super().shape()

    def paint(self, painter, option, widget):
        # For temp lines, use thicker width
        line_width = 4 if self.isSelected() and self.temp_indices else (2 if self.isSelected() else 0)
        current_pen = self.pen()
        current_pen.setWidth(line_width)


        mappings_data = self.config.get('mappings.data', [])
        is_conditional = self.config.get('conditional', False)
        if is_conditional:
            current_pen.setStyle(Qt.DashLine)

        if self.temp_indices:
            has_no_mappings = len(self.config.get('mappings.data', [])) == 0
            if has_no_mappings:
                color = current_pen.color()
                color.setAlphaF(0.5)
                current_pen.setColor(color)
        else:
            if not mappings_data:
                faded_color = current_pen.color()
                faded_color.setAlphaF(0.31)
                current_pen.setColor(faded_color)
                
        painter.setPen(current_pen)
        painter.drawPath(self.path())

        is_looper = self.config.get('looper', False)
        max_loops = self.config.get('max_loops', None)
        # num_chars = len(str(max_loops))
        text_radius = painter.fontMetrics().horizontalAdvance(str(max_loops)) / 2
        if is_looper and max_loops:
            line_is_under = self.start_point.y() >= self.end_point.y()
            if line_is_under:
                y = self.path().boundingRect().top() - 4
            else:
                y = self.path().boundingRect().bottom() + 4
            # draw the number of loops
            painter.drawText(self.path().boundingRect().center().x() - text_radius, y, str(max_loops))


class ConnectionPoint(QGraphicsEllipseItem):
    def __init__(self, parent, is_input):
        super().__init__(0, 0, 3, 3, parent)
        self.is_input = is_input
        # self.setBrush(QBrush(Qt.darkGray))
        self.setFlag(QGraphicsItem.ItemIgnoresTransformations)
        from gui.style import TEXT_COLOR
        self.setPen(QPen(QColor(TEXT_COLOR), 0, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin))
        self.connections = []
        self.setVisible(False)

    def setHighlighted(self, highlighted):
        if highlighted:
            self.setBrush(QBrush(Qt.red))
        else:
            self.setBrush(QBrush(Qt.darkGray))

    def contains(self, point):
        distance = (point - self.rect().center()).manhattanLength()
        return distance <= 12


class MemberConfigWidget(ConfigWidget):
    def __init__(self, parent):
        super().__init__(parent=parent)
        self.layout = CVBoxLayout(self)
        # self.object = None
        self.config_widget = None
        self.member_header_widget = HeaderFields(self)
        self.layout.addWidget(self.member_header_widget)
    
    def load_config(self, json_config=None):
        super().load_config(json_config)
        self.member_header_widget.load_config(json_config)

    def get_config(self):
        if not self.config_widget:
            return {}
        if isinstance(self.config_widget, WorkflowSettings):  # todo clean
            header_config = self.config_widget.header_widget.get_config()
        else:
            header_config = self.member_header_widget.get_config()
        config = self.config_widget.get_config()
        return config | header_config

    def update_config(self):
        self.save_config()

    def save_config(self):
        if not self.config_widget:
            return
        config = self.get_config()

        if isinstance(self.parent, WorkflowSettings):
            workflow_settings = self.parent
            member_id = getattr(self.config_widget, 'member_id', None)
            if member_id is None or member_id not in workflow_settings.members_in_view:
                return
            member = workflow_settings.members_in_view[member_id]
            member.member_config.clear()
            member.member_config.update(config)

            # Save back to source entity if linked
            if member.linked_id:
                save_linked_config(member.linked_id, config)

            workflow_settings.update_config()
            member.member_proxy.load()
        else:
            draggable_member = self.parent.parent
            draggable_member.member_config.clear()
            draggable_member.member_config.update(config)

            # Save back to source entity if linked
            if draggable_member.linked_id:
                save_linked_config(draggable_member.linked_id, config)

            draggable_member.workflow_settings.update_config()
            draggable_member.workflow_settings.member_config_widget.hide()  # todo

    def display_member(self, **kwargs):
        clear_layout(self.layout, skip_count=1)
        member_type = kwargs.get('member_type', None)  # member.member_type)
        member_config = kwargs.get('member_config', None)  # , member.member_config)
        member_id = kwargs.get('member_id', None)  # , member.id)
        member = kwargs.get('member', None)  # member.member_type
        if member:
            member_type = member.member_type
            member_config = member.member_config
            member_id = member.id

        workflow_settings = None
        if hasattr(self.parent, 'workflow_settings'):
            workflow_settings = self.parent.workflow_settings
        else:
            workflow_settings = self.parent
        
        member_settings_class = get_member_settings_class(member_type)
        if not member_settings_class or member_type == 'workflow' or not workflow_settings.view.isVisible():
            self.member_header_widget.hide()
        else:
            self.member_header_widget.show()
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
        self.config_widget.member_id = member_id

        if member_settings_class == WorkflowSettings and member is not None:
            linked_id = getattr(member, 'linked_id', None)
            if linked_id is not None:
                member_config = dict(member_config)
                member_config['linked_id'] = linked_id

        self.rebuild_member(config=member_config)

        ignore_page_maps = [
            ImageSettings,
            VideoSettings,
        ]
        if page_map and not any(isinstance(self.config_widget, m) for m in ignore_page_maps):
            set_selected_pages(self.config_widget, page_map)
        
        if getattr(workflow_settings, 'workflow_editable', True):
            self.show()

    def show_input(self, line):
        source_member_id, target_member_id = line.source_member_id, line.target_member_id
        self.config_widget = InputSettings(self.parent)
        self.config_widget.input_key = (source_member_id, target_member_id)
        self.rebuild_member(config=line.config)
        self.show()

    def rebuild_member(self, config):
        clear_layout(self.layout, skip_count=1)  #
        member_type = config.get('_TYPE', 'agent')

        header_fields = self.member_header_widget.widgets[0]
        header_fields._current_member_type = member_type

        member_class = system.manager.modules.get_module_class('Members', module_name=member_type)
        if member_class:
            default_avatar = getattr(member_class, 'default_avatar', '')
            header_fields.schema[0]['default'] = default_avatar
            for s in header_fields.schema:
                if s.get('type') == 'popup_button':
                    s['member_type'] = member_type
                    break
            self.member_header_widget.build_schema()

        self.member_header_widget.load_config(config)
        self.member_header_widget.load()

        # Update link button icon based on member's linked state
        member_obj = header_fields._get_current_member()
        is_linked = member_obj is not None and member_obj.linked_id is not None
        header_fields._update_link_icon(is_linked)

        popup_btn = getattr(header_fields, 'member_options_wgt', None)
        if popup_btn and hasattr(popup_btn, 'config_widget'):
            popup_btn.config_widget.load_config(config)
            popup_btn.config_widget.load()

        condition_btn = getattr(header_fields, 'condition_wgt', None)
        if condition_btn and hasattr(condition_btn, 'config_widget'):
            condition_btn.config_widget.load_config(config)
            condition_btn.config_widget.load()
        
        self.config_widget.load_config(config)
        self.config_widget.build_schema()
        self.config_widget.load()
        if hasattr(self.config_widget, 'reload_predicates'):
            self.config_widget.reload_predicates()  # todo auto bubble down
        self.layout.addWidget(self.config_widget)

        if hasattr(self.config_widget, 'reposition_view'):
            self.config_widget.reposition_view()


class HeaderFields(ConfigJoined):
    NARROW_THRESHOLD = 450
    NARROW_INDENT = 50
    NARROW_TITLE_Y = 25
    NARROW_TITLE_H = 22

    def __init__(self, parent):
        super().__init__(
            parent=parent,
            layout_type='horizontal',
        )
        self.setFixedHeight(50)
        self.collapsible = getattr(parent, 'collapsible', False)
        self.widgets = [self.ConfigFields(parent=self)]
        if hasattr(parent.parent, 'workflow'):
            self.context_bar = self.ContextBar(parent=self)
            self.widgets.append(self.context_bar)
        self.build_schema()
        if self.collapsible:
            self.btn_collapse = IconButton(
                parent=self,
                icon_path=':/resources/icon-settings-solid.png',
            )
            self.btn_collapse.setFixedSize(25, 25)
            self.btn_collapse.clicked.connect(self.toggle_collapse)
            self.layout.addWidget(self.btn_collapse)
        config_fields = self.widgets[0]
        if hasattr(config_fields, '_TYPE_wgt'):
            sp = config_fields._TYPE_wgt.sizePolicy()
            sp.setRetainSizeWhenHidden(True)
            config_fields._TYPE_wgt.setSizePolicy(sp)
        if hasattr(config_fields, 'link_wgt'):
            sp = config_fields.link_wgt.sizePolicy()
            sp.setRetainSizeWhenHidden(True)
            config_fields.link_wgt.setSizePolicy(sp)
        self._is_narrow = None

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if not hasattr(self, 'context_bar'):
            return
        is_narrow = self.width() < self.NARROW_THRESHOLD
        if is_narrow != self._is_narrow:
            self._is_narrow = is_narrow
            if is_narrow:
                self.layout.removeWidget(self.context_bar)
                self.context_bar.setParent(self)
                self.context_bar.show()
                self.context_bar.raise_()
            else:
                self.context_bar.layout.setContentsMargins(0, 0, 0, 0)
                self.layout.insertWidget(1, self.context_bar)
            self.setFixedHeight(50)
        if is_narrow:
            self.context_bar.setGeometry(
                self.NARROW_INDENT,
                self.NARROW_TITLE_Y,
                max(0, self.width() - self.NARROW_INDENT),
                self.NARROW_TITLE_H,
            )

    def load_config(self, json_config=None):
        if json_config:
            _type = json_config.get('_TYPE', 'agent')
            if 'name' not in json_config:
                json_config['name'] = _type.replace('_', ' ').title()
        super().load_config(json_config)

    def enterEvent(self, event):
        header_fields_widget = self.widgets[0]
        if hasattr(header_fields_widget, '_TYPE_wgt'):
            header_fields_widget._TYPE_wgt.show()
        # if hasattr(header_fields_widget, 'link_wgt'):
        #     if header_fields_widget._link_button_visible():
        #         header_fields_widget.link_wgt.show()

        if hasattr(self, 'context_bar'):
            self.context_bar.btn_prev_context.show()
            self.context_bar.btn_next_context.show()
            self.context_bar.btn_info.show()

    def leaveEvent(self, event):
        header_fields_widget = self.widgets[0]
        if hasattr(header_fields_widget, '_TYPE_wgt'):
            header_fields_widget._TYPE_wgt.hide()
        # if hasattr(header_fields_widget, 'link_wgt'):
        #     header_fields_widget.link_wgt.hide()

        if hasattr(self, 'context_bar'):
            self.context_bar.btn_prev_context.hide()
            self.context_bar.btn_next_context.hide()
            self.context_bar.btn_info.hide()

    def toggle_collapse(self):
        workflow_settings = self.parent
        splitter = workflow_settings.splitter
        is_visible = splitter.isVisible()
        splitter.setVisible(not is_visible)
        if is_visible:
            workflow_settings.setMaximumHeight(self.height())
        else:
            workflow_settings.setMaximumHeight(16777215)

    class ConfigFields(ConfigFields):
        def __init__(self, parent):
            super().__init__(parent=parent)  # , add_stretch_to_end=True)
            self.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Fixed)
            self.is_member_header = self.parent.parent.__class__.__name__ == 'MemberConfigWidget'
            is_readonly = False
            if not self.is_member_header:
                workflow_settings = self.parent.parent
                is_readonly = not getattr(workflow_settings, 'workflow_editable', True)


            self.schema = [
                {
                    'text': 'Avatar',
                    'key': 'avatar_path',
                    'type': 'image',
                    'diameter': 30 if self.is_member_header else 40,
                    'circular': False,
                    'border': False,
                    'default': '',
                    'label_position': None,
                    'row_key': 0,
                    'readonly': is_readonly,
                },
                {
                    'text': 'Name',
                    'type': str,
                    'default': 'Unnamed',
                    'text_size': 14,
                    'label_position': None,
                    'transparent': True,
                    'row_key': 0,
                    'readonly': is_readonly,
                },
                {
                    'text': '',
                    'key': 'link',
                    'type': 'button',
                    'icon_path': ':/resources/icon-unlink.png',
                    'clicked': self.toggle_link,
                    'tooltip': 'Unlink this member',
                    'label_position': None,
                    'row_key': 0,
                    'size': 20,
                    'visibility_predicate': self._link_button_visible,
                },
                {
                    'key': '_TYPE',
                    'text': 'Member type',
                    'type': 'member_type_menu',
                    'label_position': None,
                    'visibility_predicate': self.member_type_visibility_predicate,
                    'default': '',
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
                    'visibility_predicate': lambda: self.is_member_header,
                },
                {
                    'text': 'Condition',
                    'type': 'condition_popup_button',
                    'use_namespace': 'condition',
                    'label_position': None,
                    'default': '',
                    'row_key': 0,
                    'visibility_predicate': self.condition_visibility_predicate,
                },
            ]
            # if self.is_member_header:
            self.schema.insert(4, {
                'type': 'stretch',
                'text': '',  # todo remove
                'row_key': 0,
            })

        def _get_current_member(self):
            """Get the DraggableMember currently being configured."""
            grandparent = self.parent.parent
            if isinstance(grandparent, MemberConfigWidget):
                member_config_widget = grandparent
            elif isinstance(grandparent, WorkflowSettings):
                # Header is inside WorkflowSettings itself
                member_config_widget = grandparent.parent
                if not isinstance(member_config_widget, MemberConfigWidget):
                    return None
            else:
                return None
            workflow_settings = member_config_widget.parent
            if not isinstance(workflow_settings, WorkflowSettings):
                return None
            member_id = getattr(member_config_widget.config_widget, 'member_id', None)
            if member_id and member_id in workflow_settings.members_in_view:
                return workflow_settings.members_in_view[member_id]
            return None

        def toggle_link(self):
            """Unlink the current member."""
            retval = display_message_box(
                icon=QMessageBox.Warning,
                title="Unlink",
                text="Are you sure you want to unlink this member?",
                buttons=QMessageBox.Yes | QMessageBox.No,
            )
            if retval != QMessageBox.Yes:
                return

            member = self._get_current_member()
            if not member:
                if not self.is_member_header:
                    ws = self.parent.parent
                    if isinstance(ws, WorkflowSettings):
                        self._toggle_root_link(ws)
                return

            if member.linked_id is not None:
                member.linked_id = None
                link_wgt = getattr(self, 'link_wgt', None)
                if link_wgt:
                    link_wgt.hide()
                member.workflow_settings.update_config()

        def _update_link_icon(self, is_linked):
            """Update the link button icon based on linked state."""
            link_btn = getattr(self, 'link_wgt', None)
            if link_btn:
                icon_path = ':/resources/icon-link.png'  # ':/resources/icon-unlink.png' if is_linked else ':/resources/icon-link.png'
                link_btn.setIcon(QIcon(colorize_pixmap(QPixmap(icon_path))))

        def _toggle_root_link(self, ws):
            """Unlink the root WorkflowSettings."""
            if ws.linked_id is not None:
                ws.linked_id = None
                link_wgt = getattr(self, 'link_wgt', None)
                if link_wgt:
                    link_wgt.hide()
                ws.update_config()

        def _link_button_visible(self):
            """Show link button only when the member is linked."""
            if self.is_member_header:
                member = self._get_current_member()
                return member is not None and member.linked_id is not None
            ws = self.parent.parent
            if isinstance(ws, WorkflowSettings):
                return ws.linked_id is not None
            return False

        def condition_visibility_predicate(self):
            if not self.is_member_header:
                return False
            member_type = getattr(self, '_current_member_type', 'agent')
            member_class = system.manager.modules.get_module_class(
                'Members', module_name=member_type,
            )
            if member_class is None:
                return True
            return getattr(member_class, 'allow_condition', True)

        def member_type_visibility_predicate(self):
            if self.is_member_header:
                return True
            else:
                workflow_settings = self.parent.parent
                return workflow_settings.can_simplify_view()

    class ContextBar(ConfigWidget):
        def __init__(self, parent):
            super().__init__(parent)
            self.propagate_config = False
            # self.setMouseTracking(True)
            self.workflow_settings = parent.parent
            # self.workflow = parent.parent.workflow

            self.layout = CHBoxLayout(self)

            self.title_label = QLineEdit(self)
            self.small_font = self.title_label.font()
            self.small_font.setPointSize(10)
            self.title_label.setFont(self.small_font)
            text_color = system.manager.config.get('display.text_color', '#c4c4c4')
            self.title_label.setStyleSheet(f"QLineEdit {{ color: {apply_alpha_to_hex(text_color, 0.90)}; background-color: transparent; }}"
                                           f"QLineEdit:hover {{ color: {text_color}; }}")
            self.title_label.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)


            # Create buttons
            self.btn_prev_context = IconButton(parent=self, icon_path=':/resources/icon-arrow-left.png')
            self.btn_next_context = IconButton(parent=self, icon_path=':/resources/icon-arrow-right.png')

            # # add a combobox with 'CHAT', 'BLOCK', 'TOOL' options
            # self.combo_kind = BaseCombo(self, items=['CHAT', 'BLOCK', 'TOOL'])
            # self.combo_kind.setFixedSize(80, 25)
            # self.combo_kind.setCurrentText('CHAT')

            self.btn_info = QPushButton()
            self.btn_info.setText('i')
            self.btn_info.setFixedSize(25, 25)

            self.title_label.textChanged.connect(self.title_edited)
            self.btn_prev_context.clicked.connect(self.previous_context)
            self.btn_next_context.clicked.connect(self.next_context)
            # self.combo_kind.currentTextChanged.connect(self.combo_kind_changed)
            self.btn_info.clicked.connect(self.showContextInfo)

            self.layout.addWidget(self.title_label)
            # self.layout.addWidget(self.combo_kind)
            self.layout.addWidget(self.btn_prev_context)
            self.layout.addWidget(self.btn_next_context)
            self.layout.addWidget(self.btn_info)

            for btn in (self.btn_prev_context, self.btn_next_context, self.btn_info):
                sp = btn.sizePolicy()
                sp.setRetainSizeWhenHidden(True)
                btn.setSizePolicy(sp)

            self.btn_prev_context.hide()
            self.btn_next_context.hide()
            self.btn_info.hide()
        
        @property
        def workflow(self):
            return self.workflow_settings.linked_workflow()

        def load(self):
            # self.agent_name_label.setText(self.parent.workflow.chat_name)
            with block_signals(self):
                linked_workflow = self.workflow_settings.linked_workflow()
                if linked_workflow:
                    self.title_label.setText(linked_workflow.chat_title)
                    self.title_label.setCursorPosition(0)
                else:
                    self.title_label.setText('')

                # member_paths = get_avatar_paths_from_config(self.workflow_settings.get_config()) # 69 #
                # member_pixmap = path_to_pixmap(member_paths, diameter=35, circular=True)
                # self.profile_pic_label.setPixmap(member_pixmap)

                # self.combo_kind.setCurrentText(self.workflow_settings.kind)
                # is_chat_kind = (self.parent.kind == 'CHAT')
                # self.combo_kind.setVisible(not is_chat_kind)

        def title_edited(self, text):
            sql.execute(f"""
                UPDATE contexts
                SET name = ?
                WHERE id = ?
            """, (text, self.workflow.context_id,))
            self.workflow.chat_title = text

        def showContextInfo(self):
            context_id = self.workflow.context_id
            leaf_id = self.workflow.leaf_id
            branches = self.workflow.message_history.branches

            display_message_box(
                icon=QMessageBox.Warning,
                text=f"Context ID: {context_id}\nLeaf ID: {leaf_id}\nBranches: {branches}",
                title="Context Info",
                buttons=QMessageBox.Ok,
            )

        def next_context(self):
            # current_kind = self.workflow.kind
            current_kind = 'CHAT'
            context_id = self.workflow.context_id
            next_context_id = sql.get_scalar("""
                SELECT
                    id
                FROM contexts
                WHERE parent_id IS NULL
                    AND kind = ?
                    AND id > ?
                ORDER BY
                    id
                LIMIT 1;""", (current_kind, context_id,))

            if next_context_id:
                chat_widget = self.workflow.chat_widget
                chat_widget.goto_context(next_context_id)
                self.btn_prev_context.setEnabled(True)
            else:
                self.btn_next_context.setEnabled(False)

        def previous_context(self):
            # current_kind = self.workflow.kind
            current_kind = 'CHAT'
            context_id = self.workflow.context_id
            prev_context_id = sql.get_scalar("""
                SELECT
                    id
                FROM contexts
                WHERE parent_id IS NULL
                    AND kind = ?
                    AND id < ?
                ORDER BY
                    id DESC
                LIMIT 1;""", (current_kind, context_id,))
            if prev_context_id:
                chat_widget = self.workflow.chat_widget
                chat_widget.goto_context(prev_context_id)
                self.btn_next_context.setEnabled(True)
            else:
                self.btn_prev_context.setEnabled(False)

        # def enterEvent(self, event):
        #     self.cog_icon.pixmap = QPixmap(':/resources/icon-settings-solid.png')
        #     self.cog_icon.setIconPixmap()  # QPixmap(':/resources/icon-settings-solid.png'))
        #     self.button_container.show()

        # def leaveEvent(self, event):
        #     # Don't hide if the mouse is over the combo box's popup
        #     if not self.combo_kind.view() or not self.combo_kind.view().isVisible():
        #         self.button_container.hide()
        #         self.cog_icon.pixmap = QPixmap(0, 0)  # Clear the icon pixmap
        #         self.cog_icon.setIconPixmap()

        # def agent_name_clicked(self, event):
        #     if self.parent.show_settings:
        #         if not self.parent.workflow_settings.isVisible():
        #             self.parent.workflow_settings.show()
        #             self.parent.workflow_settings.load()
        #         else:
        #             self.parent.workflow_settings.hide()

        # def combo_kind_changed(self, kind):
        #     self.parent.kind = kind
        #     self.parent.workflow.context_id = 0  # todo hacky
        #     self.btn_next_context.setEnabled(True)
        #     self.btn_prev_context.setEnabled(True)
        #     self.parent.load()