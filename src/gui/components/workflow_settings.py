import json
from abc import abstractmethod

from PySide6.QtCore import QPointF
from PySide6.QtGui import Qt, QPen, QColor, QBrush, QPixmap, QPainter, QPainterPath
from PySide6.QtWidgets import QWidget, QGraphicsScene, QPushButton, QGraphicsEllipseItem, QGraphicsItem, QGraphicsView, \
    QMessageBox, QGraphicsPathItem

from src.gui.components.config import ConfigWidget, CVBoxLayout, CHBoxLayout
# from src.gui.components.group_settings import ConnectionLine, ConnectionPoint, TemporaryConnectionLine
from src.gui.style import TEXT_COLOR
from src.gui.widgets.base import IconButton, ToggleButton, find_main_widget, colorize_pixmap
from src.utils import sql
from src.utils.helpers import path_to_pixmap, display_messagebox


class WorkflowSettings(ConfigWidget):
    def __init__(self, parent, **kwargs):
        super().__init__(parent)
        self.main = find_main_widget(self)
        self.paged_mode = kwargs.get('paged_mode', False)  # For use with composite agents

        self.members_in_view = {}  # id: member
        self.lines = {}  # (member_id, inp_member_id): line

        self.new_line = None
        self.new_agent = None

        self.layout = CVBoxLayout(self)
        self.workflow_buttons = WorkflowButtonsWidget(parent=self)
        # self.workflow_buttons.btn_add.clicked.connect(self.add_item)
        # self.workflow_buttons.btn_del.clicked.connect(self.delete_item)

        self.scene = QGraphicsScene(self)
        self.scene.setSceneRect(0, 0, 500, 200)
        self.scene.selectionChanged.connect(self.on_selection_changed)

        self.view = CustomGraphicsView(self.scene, self)

        self.view.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.view.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.view.setFixedHeight(200)

        self.user_bubble = FixedUserBubble(self)
        self.scene.addItem(self.user_bubble)

        self.layout.addWidget(self.workflow_buttons)
        self.layout.addWidget(self.view)

    def load_config(self, json_config=None):
        if isinstance(json_config, str):
            json_config = json.loads(json_config)
        if '_TYPE' not in json_config:  # todo maybe change
            json_config = json.dumps({
                '_TYPE': 'workflow',
                'members': [
                    {'id': None, 'agent_id': 0, 'loc_x': 37, 'loc_y': 30, 'config': json_config, 'del': 0}
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
                'agent_id': member.agent_id,
                'loc_x': member.x(),
                'loc_y': member.y(),
                'config': member.agent_config,
            })
            for input_member_id, input_type in member.member_inputs.items():
                config['inputs'].append({
                    'member_id': member_id,
                    'input_member_id': input_member_id,
                    'type': input_type,
                })
        return config  # json.dumps(config)

    @abstractmethod
    def save_config(self):
        # pass
        self.main.page_chat.workflow.load_members()

    def update_member(self, update_list):
        for member_id, attribute, value in update_list:
            member = self.members_in_view.get(member_id)
            if not member:
                return
            setattr(member, attribute, value)
        self.save_config()

    def load(self):
        workflow = self.main.page_chat.workflow
        self.load_config(workflow.config)

        self.load_members()
        # self.load_member_inputs()  # <-  agent settings is also loaded here

    def load_members(self):
        # Clear any existing members from the scene
        for m_id, member in self.members_in_view.items():
            self.scene.removeItem(member)
        self.members_in_view = {}

        members_data = self.config.get('members', [])
        inputs_data = {input_entry['member_id']: input_entry for input_entry in self.config.get('inputs', [])}

        # Iterate over the parsed 'members' data and add them to the scene
        for member_info in members_data:
            id = member_info.get('id')
            agent_id = member_info.get('agent_id')
            member_config = member_info.get('config')  # Assumes 'config' is a nested JSON object
            loc_x = member_info.get('loc_x')
            loc_y = member_info.get('loc_y')

            # Derive input_members and input_member_types from 'inputs' data
            input_members = [str(inputs_data.get(id, {}).get('input_member_id', 0))]
            input_member_types = [str(inputs_data.get(id, {}).get('type', ''))]

            # Join the lists into comma-separated strings
            member_inp_str = ",".join(input_members)
            member_type_str = ",".join(input_member_types)

            member = DraggableMember(self, id, loc_x, loc_y, member_config)  # member_inp_str, member_type_str,
            self.scene.addItem(member)
            self.members_in_view[id] = member

        # Conditional logic based on count of members_in_view
        if len(self.members_in_view) == 1:
            self.select_ids([list(self.members_in_view.keys())[0]])
            self.view.hide()
        else:
            self.view.show()

    # def load_member_inputs(self):
    #     for _, line in self.lines.items():
    #         self.scene.removeItem(line)
    #     self.lines = {}
    #
    #     for m_id, member in self.members_in_view.items():
    #         for input_member_id, input_type in member.member_inputs.items():
    #             if input_member_id == 0:
    #                 input_member = self.user_bubble
    #             else:
    #                 input_member = self.members_in_view[input_member_id]
    #             key = (m_id, input_member_id)
    #             line = ConnectionLine(key, member.input_point, input_member.output_point, input_type)
    #             self.scene.addItem(line)
    #             self.lines[key] = line

    def select_ids(self, ids):
        for item in self.scene.selectedItems():
            item.setSelected(False)

        for _id in ids:
            self.members_in_view[_id].setSelected(True)

    def on_selection_changed(self):
        selected_agents = [x for x in self.scene.selectedItems() if isinstance(x, DraggableMember)]
        selected_lines = [x for x in self.scene.selectedItems() if isinstance(x, ConnectionLine)]

        # get all member and input configs
        # merge all similar configs like in gamecad
        # dynamic config widget based on object schemas

        # with block_signals(self.group_topbar):  todo
        #     if len(selected_agents) == 1:
        #         self.agent_settings.show()
        #         self.load_agent_settings(selected_agents[0].id)
        #     else:
        #         self.agent_settings.hide()
        #
        #     if len(selected_lines) == 1:
        #         self.group_topbar.input_type_label.show()
        #         self.group_topbar.input_type_combo_box.show()
        #         line = selected_lines[0]
        #         self.group_topbar.input_type_combo_box.setCurrentIndex(line.input_type)
        #     else:
        #         self.group_topbar.input_type_label.hide()
        #         self.group_topbar.input_type_combo_box.hide()

    def add_input(self, input_member_id, member_id):
        pass


class WorkflowButtonsWidget(QWidget):
    def __init__(self, parent):  # , extra_tree_buttons=None):
        super().__init__(parent=parent)
        self.layout = CHBoxLayout(self)

        self.btn_add = IconButton(
            parent=self,
            icon_path=':/resources/icon-new.png',
            tooltip='Add',
            size=18,
        )
        self.btn_del = IconButton(
            parent=self,
            icon_path=':/resources/icon-minus.png',
            tooltip='Delete',
            size=18,
        )
        self.layout.addWidget(self.btn_add)
        self.layout.addWidget(self.btn_del)

        if getattr(parent, 'folder_key', False):
            self.btn_new_folder = IconButton(
                parent=self,
                icon_path=':/resources/icon-new-folder.png',
                tooltip='New Folder',
                size=18,
            )
            self.layout.addWidget(self.btn_new_folder)

        if getattr(parent, 'filterable', False):
            self.btn_filter = ToggleButton(
                parent=self,
                icon_path=':/resources/icon-filter.png',
                icon_path_checked=':/resources/icon-filter-filled.png',
                tooltip='Filter',
                size=18,
            )
            self.layout.addWidget(self.btn_filter)

        if getattr(parent, 'searchable', False):
            self.btn_search = ToggleButton(
                parent=self,
                icon_path=':/resources/icon-search.png',
                icon_path_checked=':/resources/icon-search-filled.png',
                tooltip='Search',
                size=18,
            )
            self.layout.addWidget(self.btn_search)

        self.layout.addStretch(1)

        self.btn_clear = QPushButton('Clear', self)
        # self.btn_clear.clicked.connect(self.clear_chat)
        self.btn_clear.setFixedWidth(75)
        self.layout.addWidget(self.btn_clear)


class CustomGraphicsView(QGraphicsView):
    def __init__(self, scene, parent):
        super(CustomGraphicsView, self).__init__(scene, parent)
        self.setMouseTracking(True)
        self.setRenderHint(QPainter.Antialiasing)
        self.parent = parent

    def mouseMoveEvent(self, event):
        mouse_point = self.mapToScene(event.pos())
        if self.parent.new_line:
            self.parent.new_line.updateEndPoint(mouse_point)
        if self.parent.new_agent:
            self.parent.new_agent.setCentredPos(mouse_point)

        if self.scene():
            self.scene().update()
        self.update()

        super(CustomGraphicsView, self).mouseMoveEvent(event)

    def keyPressEvent(self, event):
        if event.key() == Qt.Key_Escape:  # todo - refactor
            if self.parent.new_line:
                # Remove the temporary line from the scene and delete it
                self.scene().removeItem(self.parent.new_line)
                self.parent.new_line = None
                self.update()
            if self.parent.new_agent:
                # Remove the temporary line from the scene and delete it
                self.scene().removeItem(self.parent.new_agent)
                self.parent.new_agent = None
                self.update()
        elif event.key() == Qt.Key_Delete:
            if self.parent.new_line:
                # Remove the temporary line from the scene and delete it
                self.scene().removeItem(self.parent.new_line)
                self.parent.new_line = None
                self.update()
                return
            if self.parent.new_agent:
                # Remove the temporary line from the scene and delete it
                self.scene().removeItem(self.parent.new_agent)
                self.parent.new_agent = None
                self.update()
                return

            all_del_objects = set()
            all_del_objects_old_brushes = []
            all_del_objects_old_pens = []
            del_input_ids = set()
            del_agents = set()
            for sel_item in self.parent.scene.selectedItems():
                all_del_objects.add(sel_item)
                if isinstance(sel_item, ConnectionLine):
                    # key of self.parent.lines where val = sel_item
                    for key, val in self.parent.lines.items():
                        if val == sel_item:
                            del_input_ids.add(key)
                            break
                elif isinstance(sel_item, DraggableMember):
                    del_agents.add(sel_item.id)
                    # get all connected lines
                    for line_key in self.parent.lines.keys():
                        if line_key[0] == sel_item.id or line_key[1] == sel_item.id:
                            all_del_objects.add(self.parent.lines[line_key])
                            del_input_ids.add(line_key)

            if len(all_del_objects):
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
                    # delete all inputs from context
                    for member_id, inp_member_id in del_input_ids:
                        if inp_member_id == 0:  # todo - clean
                            sql.execute("""
                                DELETE FROM contexts_members_inputs 
                                WHERE member_id = ? 
                                    AND input_member_id IS NULL""",
                                        (member_id,))
                        else:
                            sql.execute("""
                                DELETE FROM contexts_members_inputs 
                                WHERE member_id = ? 
                                    AND input_member_id = ?""",
                                        (member_id, inp_member_id))
                    # delete all agents from context
                    for agent_id in del_agents:
                        sql.execute("""
                            UPDATE contexts_members 
                            SET del = 1
                            WHERE id = ?""", (agent_id,))

                    # load page chat
                    self.parent.parent.parent.load()
                else:
                    for item in all_del_objects:
                        item.setBrush(all_del_objects_old_brushes.pop(0))
                        item.setPen(all_del_objects_old_pens.pop(0))

        else:
            super(CustomGraphicsView, self).keyPressEvent(event)

    def mousePressEvent(self, event):
        if self.parent.new_agent:
            self.parent.add_member()
        else:
            mouse_scene_position = self.mapToScene(event.pos())
            for agent_id, agent in self.parent.members_in_view.items():
                if isinstance(agent, DraggableMember):
                    if self.parent.new_line:
                        input_point_pos = agent.input_point.scenePos()
                        # if within 20px
                        if (mouse_scene_position - input_point_pos).manhattanLength() <= 20:
                            self.parent.add_input(self.input_member_id, member_id)
                            # self.parent.new_line.attach_to_member(agent.id)
                            # # agent.close_btn.hide()
                    else:
                        output_point_pos = agent.output_point.scenePos()
                        output_point_pos.setX(output_point_pos.x() + 8)
                        # if within 20px
                        if (mouse_scene_position - output_point_pos).manhattanLength() <= 20:
                            self.parent.new_line = TemporaryConnectionLine(self.parent, agent)
                            self.parent.scene.addItem(self.parent.new_line)
                            return
            # check user bubble
            output_point_pos = self.parent.user_bubble.output_point.scenePos()
            output_point_pos.setX(output_point_pos.x() + 8)
            # if within 20px
            if (mouse_scene_position - output_point_pos).manhattanLength() <= 20:
                if self.parent.new_line:
                    self.parent.scene.removeItem(self.parent.new_line)

                self.parent.new_line = TemporaryConnectionLine(self.parent, self.parent.user_bubble)
                self.parent.scene.addItem(self.parent.new_line)
                return
            if self.parent.new_line:
                # Remove the temporary line from the scene and delete it
                self.scene().removeItem(self.parent.new_line)
                self.parent.new_line = None

        super(CustomGraphicsView, self).mousePressEvent(event)


class FixedUserBubble(QGraphicsEllipseItem):
    def __init__(self, parent):
        super(FixedUserBubble, self).__init__(0, 0, 50, 50)
        self.id = 0
        self.parent = parent

        self.setPos(-42, 75)

        pixmap = colorize_pixmap(QPixmap(":/resources/icon-user.png"))
        self.setBrush(QBrush(pixmap.scaled(50, 50, Qt.KeepAspectRatio, Qt.SmoothTransformation)))

        # set border color
        self.setPen(QPen(QColor(TEXT_COLOR), 1))

        self.output_point = ConnectionPoint(self, False)
        self.output_point.setPos(self.rect().width() - 4, self.rect().height() / 2)

        self.setAcceptHoverEvents(True)

    def hoverMoveEvent(self, event):
        # Check if the mouse is within 20 pixels of the output point
        if self.output_point.contains(event.pos() - self.output_point.pos()):
            self.output_point.setHighlighted(True)
        else:
            self.output_point.setHighlighted(False)
        super(FixedUserBubble, self).hoverMoveEvent(event)

    def hoverLeaveEvent(self, event):
        self.output_point.setHighlighted(False)
        super(FixedUserBubble, self).hoverLeaveEvent(event)


# class DraggableMember(QGraphicsEllipseItem):
#     def __init__(self, id, parent, x, y, member_inp_str, member_type_str, agent_config):
class DraggableMember(QGraphicsEllipseItem):
    def __init__(self, parent, member_id, loc_x, loc_y, member_config):
        super(DraggableMember, self).__init__(0, 0, 50, 50)
        if isinstance(member_config, str):
            member_config = json.loads(member_config)  # todo - clean

        self.parent = parent
        self.id = member_id

        # set border color
        self.setPen(QPen(QColor(TEXT_COLOR), 1))

        # if member_type_str:
        #     member_inp_str = '0' if member_inp_str == 'NULL' else member_inp_str  # todo dirty
        # self.member_inputs = dict(
        #     zip([int(x) for x in member_inp_str.split(',')],
        #         member_type_str.split(','))) if member_type_str else {}

        self.setPos(loc_x, loc_y)

        # agent_config = json.loads(agent_config)
        hide_responses = member_config.get('group.hide_responses', False)
        agent_avatar_path = member_config.get('info.avatar_path', '')
        opacity = 0.2 if hide_responses else 1
        diameter = 50
        pixmap = path_to_pixmap(agent_avatar_path, opacity=opacity, diameter=diameter)

        self.setBrush(QBrush(pixmap.scaled(diameter, diameter)))

        self.setFlag(QGraphicsItem.ItemIsMovable)
        self.setFlag(QGraphicsItem.ItemIsSelectable)

        self.input_point = ConnectionPoint(self, True)
        self.output_point = ConnectionPoint(self, False)
        self.input_point.setPos(0, self.rect().height() / 2)
        self.output_point.setPos(self.rect().width() - 4, self.rect().height() / 2)

        self.setAcceptHoverEvents(True)

    def mouseReleaseEvent(self, event):
        super(DraggableMember, self).mouseReleaseEvent(event)
        new_loc_x = self.x()
        new_loc_y = self.y()
        self.parent.update_member([
            (self.id, 'loc_x', new_loc_x),
            (self.id, 'loc_y', new_loc_y)
        ])
        # sql.execute('UPDATE contexts_members SET loc_x = ?, loc_y = ? WHERE id = ?',
        #             (new_loc_x, new_loc_y, self.id))
        # self.parent.main.page_chat.workflow.load_members()

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


class TemporaryConnectionLine(QGraphicsPathItem):
    def __init__(self, parent, agent):
        super(TemporaryConnectionLine, self).__init__()
        self.parent = parent
        self.input_member_id = agent.id
        self.output_point = agent.output_point
        self.setPen(QPen(QColor(TEXT_COLOR), 2, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin))
        self.temp_end_point = self.output_point.scenePos()
        self.updatePath()

    def updatePath(self):
        path = QPainterPath(self.output_point.scenePos())
        ctrl_point1 = self.output_point.scenePos() + QPointF(50, 0)
        ctrl_point2 = self.temp_end_point - QPointF(50, 0)
        path.cubicTo(ctrl_point1, ctrl_point2, self.temp_end_point)
        self.setPath(path)

    def updateEndPoint(self, end_point):
        self.temp_end_point = end_point
        self.updatePath()

    def attach_to_member(self, member_id):
        self.parent.add_input(self.input_member_id, member_id)


class ConnectionLine(QGraphicsPathItem):
    def __init__(self, key, start_point, end_point=None, input_type=0):
        super(ConnectionLine, self).__init__()
        self.key = key
        self.input_type = int(input_type)
        self.start_point = start_point
        self.end_point = end_point
        self.setFlag(QGraphicsItem.ItemIsSelectable)

        self.color = QColor(TEXT_COLOR)

        self.updatePath()

        self.setPen(QPen(self.color, 2, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin))
        self.setZValue(-1)

        self.setAcceptHoverEvents(True)

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
        path = QPainterPath(self.start_point.scenePos())
        ctrl_point1 = self.start_point.scenePos() + QPointF(50, 0)
        ctrl_point2 = self.end_point.scenePos() - QPointF(50, 0)
        path.cubicTo(ctrl_point1, ctrl_point2, self.end_point.scenePos())
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
