import json
import logging
import time
from functools import partial

from PySide6.QtWidgets import *
from PySide6.QtCore import QEvent, QPointF
from PySide6.QtGui import QPixmap, QColor, QIcon, QFont, QPainter, QPainterPath, Qt, QCursor, QBrush, QPen, QKeyEvent

from src.gui.components.agent_settings import AgentSettings

from src.utils.helpers import path_to_pixmap, block_signals, display_messagebox, block_pin_mode
from src.utils import sql, resources_rc
from src.gui.style import TEXT_COLOR
from src.gui.widgets.base import colorize_pixmap, IconButton, ListDialog
from src.gui.components.config import CVBoxLayout, CHBoxLayout


class GroupSettings(QWidget):
    def __init__(self, parent):
        super(GroupSettings, self).__init__(parent)
        self.parent = parent
        self.main = parent.parent.main
        layout = CVBoxLayout(self)
        # layout.setSpacing(0)
        # layout.setContentsMargins(0, 0, 0, 0)

        self.group_topbar = GroupTopBar(self)
        layout.addWidget(self.group_topbar)

        self.scene = QGraphicsScene(self)
        self.scene.setSceneRect(0, 0, 500, 200)
        self.scene.selectionChanged.connect(self.on_selection_changed)

        self.view = CustomGraphicsView(self.scene, self)

        self.view.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.view.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.view.setFixedHeight(200)

        layout.addWidget(self.view)

        self.user_bubble = FixedUserBubble(self)
        self.scene.addItem(self.user_bubble)

        self.members_in_view = {}  # id: member
        self.lines = {}  # (member_id, inp_member_id): line

        self.new_line = None
        self.new_agent = None

        self.agent_settings = self.Agent_Config_Widget(self, is_context_member_agent=True)
        self.agent_settings.build_schema()
        self.agent_settings.hide()
        layout.addWidget(self.agent_settings)
        layout.addStretch(1)

    class Agent_Config_Widget(AgentSettings):
        def __init__(self, *args, **kwargs):
            super().__init__(*args, **kwargs)

        def save_config(self):
            """Saves the config to database when modified"""
            agent_id = self.ref_id
            json_config = json.dumps(self.get_config())

            sql.execute("UPDATE contexts_members SET agent_config = ? WHERE id = ?", (json_config, agent_id))
            self.load_config(json_config)  # todo needed for configjsontree, but why
            self.settings_sidebar.load()
            self.main.page_chat.workflow.load_members()

    def load(self):
        self.load_members()
        self.load_member_inputs()  # <-  agent settings is also loaded here

    def load_members(self):
        # Clear any existing members from the scene
        for m_id, member in self.members_in_view.items():
            self.scene.removeItem(member)

        self.members_in_view = {}

        query = """
            SELECT 
                cm.id,
                cm.agent_id,
                cm.agent_config,
                cm.loc_x,
                cm.loc_y,
                (SELECT GROUP_CONCAT(COALESCE(input_member_id, 0)) FROM contexts_members_inputs WHERE member_id = cm.id) as input_members,
                (SELECT GROUP_CONCAT(COALESCE(type, '')) FROM contexts_members_inputs WHERE member_id = cm.id) as input_member_types
            FROM contexts_members cm
            LEFT JOIN contexts_members_inputs cmi
                ON cmi.member_id = cm.id
            WHERE cm.context_id = ?
                AND cm.del = 0
            GROUP BY cm.id
            ORDER BY cm.loc_x, cm.loc_y
        """
        members_data = sql.get_results(query, (self.parent.parent.workflow.id,))  # Pass the current context ID

        # Iterate over the fetched members and add them to the scene
        for id, agent_id, agent_config, loc_x, loc_y, member_inp_str, member_type_str in members_data:
            member = DraggableAgent(id, self, loc_x, loc_y, member_inp_str, member_type_str, agent_config)
            self.scene.addItem(member)
            self.members_in_view[id] = member

        # If there is only one member, hide the graphics view
        if len(self.members_in_view) == 1:
            self.select_ids([list(self.members_in_view.keys())[0]])
            self.view.hide()
        else:
            self.view.show()

    def load_member_inputs(self):
        for _, line in self.lines.items():
            self.scene.removeItem(line)
        self.lines = {}

        for m_id, member in self.members_in_view.items():
            for input_member_id, input_type in member.member_inputs.items():
                if input_member_id == 0:
                    input_member = self.user_bubble
                else:
                    input_member = self.members_in_view[input_member_id]
                key = (m_id, input_member_id)
                line = ConnectionLine(key, member.input_point, input_member.output_point, input_type)
                self.scene.addItem(line)
                self.lines[key] = line

    def select_ids(self, ids):
        for item in self.scene.selectedItems():
            item.setSelected(False)

        for _id in ids:
            self.members_in_view[_id].setSelected(True)

    def delete_ids(self, ids):
        self.select_ids(ids)
        self.view.keyPressEvent(QKeyEvent(QEvent.KeyPress, Qt.Key_Delete, Qt.NoModifier))

    def insertAgent(self, item):
        self.view.show()
        mouse_scene_point = self.view.mapToScene(self.view.mapFromGlobal(QCursor.pos()))
        item = item.data(Qt.UserRole)
        agent_id = item['id']
        agent_avatar = item['avatar']
        self.new_agent = TemporaryInsertableMember(self, agent_id, agent_avatar, mouse_scene_point)
        self.scene.addItem(self.new_agent)
        self.view.setFocus()

    def insertTool(self, item):
        self.view.show()
        mouse_scene_point = self.view.mapToScene(self.view.mapFromGlobal(QCursor.pos()))
        item = item.data(Qt.UserRole)
        tool_id = item['id']
        avatar = colorize_pixmap(QPixmap(':/resources/icon-tool.png'))
        self.new_agent = TemporaryInsertableMember(self, tool_id, avatar, mouse_scene_point)
        self.scene.addItem(self.new_agent)
        self.view.setFocus()

    def add_input(self, input_member_id, member_id):
        # insert self.new_agent into contexts_members table
        if member_id == input_member_id:
            return
        if input_member_id == 0:
            sql.execute("""
                INSERT INTO contexts_members_inputs
                    (member_id, input_member_id)
                SELECT ?, NULL
                WHERE NOT EXISTS (
                    SELECT 1
                    FROM contexts_members_inputs
                    WHERE member_id = ? AND input_member_id IS NULL
                )""", (member_id, member_id))
        else:
            sql.execute("""
                INSERT INTO contexts_members_inputs
                    (member_id, input_member_id)
                SELECT ?, ?
                WHERE NOT EXISTS (
                    SELECT 1
                    FROM contexts_members_inputs
                    WHERE member_id = ? AND input_member_id = ?
                )""", (member_id, input_member_id, member_id, input_member_id))
        self.scene.removeItem(self.new_line)
        self.new_line = None

        self.parent.parent.workflow.load()
        self.parent.parent.refresh()

    def add_member(self):
        workflow_id = self.parent.parent.workflow.id
        agent_id = self.new_agent.id
        sql.execute("""
            INSERT INTO contexts_members
            (context_id, agent_id, agent_config, loc_x, loc_y)
            SELECT
                ?, ?, COALESCE(a.config, '{}'), ?, ?
            FROM (SELECT ? AS agent_id) as a_id
            LEFT JOIN agents a ON a.id = a_id.agent_id""", (workflow_id, agent_id, self.new_agent.x(), self.new_agent.y(), self.new_agent.id))

        self.scene.removeItem(self.new_agent)
        self.new_agent = None

        self.parent.parent.load()

    def on_selection_changed(self):
        selected_agents = [x for x in self.scene.selectedItems() if isinstance(x, DraggableAgent)]
        selected_lines = [x for x in self.scene.selectedItems() if isinstance(x, ConnectionLine)]

        with block_signals(self.group_topbar):
            if len(selected_agents) == 1:
                self.agent_settings.show()
                self.load_agent_settings(selected_agents[0].id)
            else:
                self.agent_settings.hide()

            if len(selected_lines) == 1:
                self.group_topbar.input_type_label.show()
                self.group_topbar.input_type_combo_box.show()
                line = selected_lines[0]
                self.group_topbar.input_type_combo_box.setCurrentIndex(line.input_type)
            else:
                self.group_topbar.input_type_label.hide()
                self.group_topbar.input_type_combo_box.hide()

    def load_agent_settings(self, agent_id):
        agent_json_config = sql.get_scalar('SELECT agent_config FROM contexts_members WHERE id = ?', (agent_id,))

        self.agent_settings.ref_id = agent_id
        self.agent_settings.load_config(agent_json_config)
        self.agent_settings.load()


class GroupTopBar(QWidget):
    def __init__(self, parent):
        super(GroupTopBar, self).__init__(parent)
        self.parent = parent

        self.layout = CHBoxLayout(self)
        # self.layout.setSpacing(0)
        # self.layout.setContentsMargins(0, 0, 0, 0)

        self.btn_add_member = IconButton(self, icon_path=':/resources/icon-new.png', tooltip="Add a new member")
        self.btn_options = IconButton(parent=self, icon_path=':/resources/icon-dots.png')
        self.btn_add_member.clicked.connect(self.show_context_menu)
        self.btn_options.clicked.connect(self.show_options_context_menu)

        self.layout.addSpacing(11)
        self.layout.addWidget(self.btn_add_member)
        self.layout.addWidget(self.btn_options)

        self.layout.addStretch(1)

        self.input_type_label = QLabel("Input type:", self)
        self.input_type_combo_box = QComboBox(self)
        self.input_type_combo_box.addItem("Message")
        self.input_type_combo_box.addItem("Context")
        self.input_type_combo_box.setFixedWidth(115)
        self.layout.addWidget(self.input_type_label)
        self.layout.addWidget(self.input_type_combo_box)
        self.input_type_combo_box.currentIndexChanged.connect(self.input_type_changed)
        self.input_type_combo_box.hide()
        self.input_type_label.hide()

        self.layout.addStretch(1)

        self.btn_clear = QPushButton('Clear', self)
        self.btn_clear.clicked.connect(self.clear_chat)
        self.btn_clear.setFixedWidth(75)
        self.layout.addWidget(self.btn_clear)

        self.dlg = None

    def show_options_context_menu(self):
        menu = QMenu(self)

        export_item = menu.addMenu('Export')
        csv_item = export_item.addAction('Export to CSV')

        # show cursor at top right of menu
        menu.exec_(QCursor.pos())

    def show_context_menu(self):
        menu = QMenu(self)

        add_agent = menu.addAction('Agent')
        add_user = menu.addAction('User')
        add_tool = menu.addAction('Tool')

        add_agent.triggered.connect(partial(self.choose_member, "agents"))
        add_tool.triggered.connect(partial(self.choose_member, "tools"))

        menu.exec_(QCursor.pos())

    def choose_member(self, list_type):
        if list_type == 'agents':
            callback = self.parent.insertAgent
            # multiselect = False
        else:
            callback = self.parent.insertTool
            # multiselect = True

        list_dialog = ListDialog(
            parent=self,
            title="Add Member",
            list_type=list_type,
            callback=callback,
            # multiselect=multiselect
        )
        list_dialog.open()

    def input_type_changed(self, index):
        sel_items = self.parent.scene.selectedItems()
        sel_lines = [item for item in sel_items if isinstance(item, ConnectionLine)]
        if len(sel_lines) != 1:
            return
        line = sel_lines[0]
        line_member_id, line_inp_member_id = line.key

        # 0 = message, 1 = context
        sql.execute("""
            UPDATE contexts_members_inputs
            SET type = ?
            WHERE member_id = ?
                AND COALESCE(input_member_id, 0) = ?""",
                    (index, line_member_id, line_inp_member_id))

        self.parent.load()

    def clear_chat(self):
        from src.context.base import Workflow
        retval = display_messagebox(
            icon=QMessageBox.Warning,
            text="Are you sure you want to permanently clear the chat messages? This should only be used when testing to preserve the context name. To keep your data start a new context.",
            title="Clear Chat",
            buttons=QMessageBox.Ok | QMessageBox.Cancel,
        )

        if retval != QMessageBox.Ok:
            return

        sql.execute("""
            WITH RECURSIVE delete_contexts(id) AS (
                SELECT id FROM contexts WHERE id = ?
                UNION ALL
                SELECT contexts.id FROM contexts
                JOIN delete_contexts ON contexts.parent_id = delete_contexts.id
            )
            DELETE FROM contexts WHERE id IN delete_contexts AND id != ?;
        """, (self.parent.parent.parent.workflow.id, self.parent.parent.parent.workflow.id,))
        sql.execute("""
            WITH RECURSIVE delete_contexts(id) AS (
                SELECT id FROM contexts WHERE id = ?
                UNION ALL
                SELECT contexts.id FROM contexts
                JOIN delete_contexts ON contexts.parent_id = delete_contexts.id
            )
            DELETE FROM contexts_messages WHERE context_id IN delete_contexts;
        """, (self.parent.parent.parent.workflow.id,))
        sql.execute("""
        DELETE FROM contexts_messages WHERE context_id = ?""",
                    (self.parent.parent.parent.workflow.id,))

        page_chat = self.parent.parent.parent
        page_chat.workflow = Workflow(main=page_chat.main)
        self.parent.parent.parent.load()


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


class DraggableAgent(QGraphicsEllipseItem):
    def __init__(self, id, parent, x, y, member_inp_str, member_type_str, agent_config):
        super(DraggableAgent, self).__init__(0, 0, 50, 50)
        # set border color
        self.setPen(QPen(QColor(TEXT_COLOR), 1))

        self.id = id
        self.parent = parent

        if member_type_str:
            member_inp_str = '0' if member_inp_str == 'NULL' else member_inp_str  # todo dirty
        self.member_inputs = dict(
            zip([int(x) for x in member_inp_str.split(',')],
                member_type_str.split(','))) if member_type_str else {}

        self.setPos(x, y)

        agent_config = json.loads(agent_config)
        hide_responses = agent_config.get('group.hide_responses', False)
        agent_avatar_path = agent_config.get('info.avatar_path', '')
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
        super(DraggableAgent, self).mouseReleaseEvent(event)
        new_loc_x = self.x()
        new_loc_y = self.y()
        sql.execute('UPDATE contexts_members SET loc_x = ?, loc_y = ? WHERE id = ?',
                    (new_loc_x, new_loc_y, self.id))
        self.parent.main.page_chat.workflow.load_members()

    def mouseMoveEvent(self, event):
        if self.output_point.contains(event.pos() - self.output_point.pos()):
            return

        if self.parent.new_line:
            return

        # if mouse not inside scene, return
        cursor = event.scenePos()
        if not self.parent.view.rect().contains(cursor.toPoint()):
            return

        super(DraggableAgent, self).mouseMoveEvent(event)
        for line in self.parent.lines.values():
            line.updatePosition()

    def hoverMoveEvent(self, event):
        # Check if the mouse is within 20 pixels of the output point
        if self.output_point.contains(event.pos() - self.output_point.pos()):
            self.output_point.setHighlighted(True)
        else:
            self.output_point.setHighlighted(False)
        super(DraggableAgent, self).hoverMoveEvent(event)

    def hoverLeaveEvent(self, event):
        self.output_point.setHighlighted(False)
        super(DraggableAgent, self).hoverLeaveEvent(event)


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
    def __init__(self, key, start_point, end_point, input_type=0):
        super(ConnectionLine, self).__init__()
        self.key = key
        self.input_type = int(input_type)
        self.start_point = start_point
        self.end_point = end_point
        self.setFlag(QGraphicsItem.ItemIsSelectable)

        self.color = QColor(TEXT_COLOR)

        path = QPainterPath(start_point.scenePos())

        ctrl_point1 = start_point.scenePos() - QPointF(50, 0)  # Control point 1 right of start
        ctrl_point2 = end_point.scenePos() + QPointF(50, 0)  # Control point 2 left of end
        path.cubicTo(ctrl_point1, ctrl_point2, end_point.scenePos())

        self.setPath(path)
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

    def updatePosition(self):
        path = QPainterPath(self.start_point.scenePos())
        ctrl_point1 = self.start_point.scenePos() - QPointF(50, 0)
        ctrl_point2 = self.end_point.scenePos() + QPointF(50, 0)
        path.cubicTo(ctrl_point1, ctrl_point2, self.end_point.scenePos())
        self.setPath(path)
        self.scene().update(self.scene().sceneRect())


class TemporaryInsertableMember(QGraphicsEllipseItem):
    def __init__(self, parent, agent_id, icon, pos):
        super(TemporaryInsertableMember, self).__init__(0, 0, 50, 50)
        # set border color
        self.setPen(QPen(QColor(TEXT_COLOR), 1))

        self.parent = parent
        self.id = agent_id

        if isinstance(icon, QPixmap):
            pixmap = icon
        else:
            pixmap = path_to_pixmap(icon, diameter=50)
        self.setBrush(QBrush(pixmap.scaled(50, 50)))
        self.setCentredPos(pos)

    def setCentredPos(self, pos):
        self.setPos(pos.x() - self.rect().width() / 2, pos.y() - self.rect().height() / 2)


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


class CustomGraphicsView(QGraphicsView):
    def __init__(self, scene, parent):
        super(CustomGraphicsView, self).__init__(scene, parent)
        self.setMouseTracking(True)
        self.setRenderHint(QPainter.Antialiasing)
        self.parent = parent

    def mouseMoveEvent(self, event):
        # point = event.pos()
        if self.parent.new_line:
            self.parent.new_line.updateEndPoint(self.mapToScene(event.pos()))
            if self.scene():
                self.scene().update()
            self.update()
        if self.parent.new_agent:
            self.parent.new_agent.setCentredPos(self.mapToScene(event.pos()))
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
                elif isinstance(sel_item, DraggableAgent):
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
                if isinstance(agent, DraggableAgent):
                    if self.parent.new_line:
                        input_point_pos = agent.input_point.scenePos()
                        # if within 20px
                        if (mouse_scene_position - input_point_pos).manhattanLength() <= 20:
                            self.parent.new_line.attach_to_member(agent.id)
                            # agent.close_btn.hide()
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