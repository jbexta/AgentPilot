
import json
from functools import partial
from sqlite3 import IntegrityError

from PySide6.QtWidgets import *
from PySide6.QtCore import QSize
from PySide6.QtGui import QPixmap, QIcon, Qt

from agentpilot.utils.helpers import path_to_pixmap, block_signals, display_messagebox, block_pin_mode
from agentpilot.utils import sql, resources_rc

from agentpilot.gui.components.agent_settings import AgentSettings
from agentpilot.gui.widgets import BaseTableWidget, ContentPage, IconButton


class Page_Agents(ContentPage):
    def __init__(self, main):
        super().__init__(main=main, title='Agents')
        self.main = main

        self.btn_new_agent = self.Button_New_Agent(parent=self)
        self.title_layout.addWidget(self.btn_new_agent)  # QPushButton("Add", self))

        self.title_layout.addStretch()

        # Adding input layout to the main layout
        self.table_widget = BaseTableWidget(self)
        self.table_widget.verticalHeader().setDefaultSectionSize(24)
        self.table_widget.setColumnCount(6)
        self.table_widget.setColumnWidth(1, 45)
        self.table_widget.setColumnWidth(4, 45)
        self.table_widget.setColumnWidth(5, 45)
        self.table_widget.horizontalHeader().setSectionResizeMode(3, QHeaderView.Stretch)
        self.table_widget.hideColumn(0)
        self.table_widget.hideColumn(2)
        self.table_widget.horizontalHeader().hide()
        self.table_widget.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.table_widget.itemSelectionChanged.connect(self.on_agent_selected)

        # Connect the double-click signal with the chat button click
        self.table_widget.itemDoubleClicked.connect(self.on_row_double_clicked)

        self.agent_settings = AgentSettings(self)

        # Add table and container to the layout
        self.layout.addWidget(self.table_widget)
        self.layout.addWidget(self.agent_settings)

    def load(self):  # Load agents
        icon_chat = QIcon(':/resources/icon-chat.png')
        icon_del = QIcon(':/resources/icon-delete.png')

        with block_signals(self):
            self.table_widget.setRowCount(0)
            data = sql.get_results("""
                SELECT
                    id,
                    '' AS avatar,
                    config,
                    '' AS name,
                    '' AS chat_button,
                    '' AS del_button
                FROM agents
                ORDER BY id DESC""")
            for row_data in data:
                row_data = list(row_data)
                r_config = json.loads(row_data[2])
                row_data[3] = r_config.get('general.name', 'Assistant')

                row_position = self.table_widget.rowCount()
                self.table_widget.insertRow(row_position)
                for column, item in enumerate(row_data):
                    self.table_widget.setItem(row_position, column, QTableWidgetItem(str(item)))

                # Parse the config JSON to get the avatar path
                agent_avatar_path = r_config.get('general.avatar_path', '')
                pixmap = path_to_pixmap(agent_avatar_path, diameter=25)

                # Create a QLabel to hold the pixmap
                avatar_label = QLabel()
                avatar_label.setPixmap(pixmap)
                # set background to transparent
                avatar_label.setAttribute(Qt.WA_TranslucentBackground, True)

                # Add the new avatar icon column after the ID column
                self.table_widget.setCellWidget(row_position, 1, avatar_label)

                btn_chat = QPushButton('')
                btn_chat.setIcon(icon_chat)
                btn_chat.setIconSize(QSize(25, 25))
                # set background to transparent
                # set background to white at 30% opacity when hovered
                btn_chat.setStyleSheet("QPushButton { background-color: transparent; }"
                                       "QPushButton:hover { background-color: rgba(255, 255, 255, 0.1); }")
                btn_chat.clicked.connect(partial(self.on_chat_btn_clicked, row_data))
                self.table_widget.setCellWidget(row_position, 4, btn_chat)

                btn_del = QPushButton('')
                btn_del.setIcon(icon_del)
                btn_del.setIconSize(QSize(25, 25))
                btn_del.setStyleSheet("QPushButton { background-color: transparent; }"
                                      "QPushButton:hover { background-color: rgba(255, 255, 255, 0.1); }")
                btn_del.clicked.connect(partial(self.delete_agent, row_data))
                self.table_widget.setCellWidget(row_position, 5, btn_del)

        if self.agent_settings.agent_id > 0:
            for row in range(self.table_widget.rowCount()):
                if self.table_widget.item(row, 0).text() == str(self.agent_settings.agent_id):
                    self.table_widget.selectRow(row)
                    break
        else:
            if self.table_widget.rowCount() > 0:
                self.table_widget.selectRow(0)

    def on_row_double_clicked(self, item):
        id = self.table_widget.item(item.row(), 0).text()
        self.chat_with_agent(id)

    def on_agent_selected(self):
        current_row = self.table_widget.currentRow()
        if current_row == -1: return
        sel_id = self.table_widget.item(current_row, 0).text()
        agent_config_json = sql.get_scalar('SELECT config FROM agents WHERE id = ?', (sel_id,))

        self.agent_settings.agent_id = int(self.table_widget.item(current_row, 0).text())
        self.agent_settings.agent_config = json.loads(agent_config_json) if agent_config_json else {}
        self.agent_settings.load()

    def on_chat_btn_clicked(self, row_data):
        id_value = row_data[0]  # self.table_widget.item(row_item, 0).text()
        self.chat_with_agent(id_value)

    def chat_with_agent(self, id):
        if self.main.page_chat.context.responding:
            return
        self.main.page_chat.new_context(agent_id=id)
        self.main.sidebar.btn_new_context.click()

    def delete_agent(self, row_data):
        context_count = sql.get_scalar("""
            SELECT
                COUNT(*)
            FROM contexts_members
            WHERE agent_id = ?""", (row_data[0],))

        if context_count > 0:
            retval = display_messagebox(
                icon=QMessageBox.Warning,
                text=f"Cannot delete '{row_data[3]}' because they exist in {context_count} contexts.",
                title="Warning",
                buttons=QMessageBox.Ok,
            )
        else:
            retval = display_messagebox(
                icon=QMessageBox.Warning,
                text="Are you sure you want to delete this agent?",
                title="Delete Agent",
                buttons=QMessageBox.Yes | QMessageBox.No,
            )

        if retval != QMessageBox.Yes:
            return

        # sql.execute("DELETE FROM contexts_messages WHERE context_id IN (SELECT id FROM contexts WHERE agent_id = ?);", (row_data[0],))
        # sql.execute("DELETE FROM contexts WHERE agent_id = ?;", (row_data[0],))
        # sql.execute('DELETE FROM contexts_members WHERE context_id = ?', (row_data[0],))
        sql.execute("DELETE FROM agents WHERE id = ?;", (row_data[0],))
        self.load()

    class Button_New_Agent(IconButton):
        def __init__(self, parent):
            super().__init__(parent=parent, icon_path=':/resources/icon-new.png')
            self.clicked.connect(self.new_agent)

        def new_agent(self):
            with block_pin_mode():
                text, ok = QInputDialog.getText(self, 'New Agent', 'Enter a name for the agent:')

            if ok:
                global_config_str = sql.get_scalar("SELECT value FROM settings WHERE field = 'global_config'")
                global_conf = json.loads(global_config_str)
                global_conf['general.name'] = text
                global_config_str = json.dumps(global_conf)
                try:
                    sql.execute("INSERT INTO `agents` (`name`, `config`) SELECT ?, ?",
                                (text, global_config_str))
                    self.parent.load()
                except IntegrityError:
                    QMessageBox.warning(self, "Duplicate Agent Name", "An agent with this name already exists.")
