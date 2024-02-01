
from functools import partial
from PySide6.QtWidgets import *
from PySide6.QtCore import QSize
from PySide6.QtGui import QIcon, Qt

from agentpilot.utils.helpers import display_messagebox, block_signals
from agentpilot.utils import sql

import logging
from gui.widgets.base import BaseTreeWidget, ContentPage


class Page_Contexts(ContentPage):
    def __init__(self, main):
        super().__init__(main=main, title='Contexts')
        self.main = main

        self.tree = BaseTreeWidget(self)
        self.tree.setColumnCount(5)
        self.tree.setColumnWidth(3, 45)
        self.tree.setColumnWidth(4, 45)
        self.tree.header().setSectionResizeMode(1, QHeaderView.Stretch)

        self.tree.hideColumn(0)
        self.tree.header().hide()

        # remove visual cell selection and only select row
        self.tree.setSelectionMode(QAbstractItemView.SingleSelection)
        self.tree.setSelectionBehavior(QAbstractItemView.SelectRows)

        # Connect the double-click signal with the chat button click
        self.tree.itemDoubleClicked.connect(self.on_row_double_clicked)

        # Add the table to the layout
        self.layout.addWidget(self.tree)

        # Enable the context menu on the table widget
        self.tree.setContextMenuPolicy(Qt.CustomContextMenu)
        self.tree.customContextMenuRequested.connect(self.show_context_menu)
        self.tree.itemChanged.connect(self.item_edited)

    def load(self):  # Load Contexts
        icon_chat = QIcon(':/resources/icon-chat.png')
        icon_del = QIcon(':/resources/icon-delete.png')

        with block_signals(self.tree):
            self.tree.clear()
            data = sql.get_results("""
                SELECT
                    c.id,
                    c.summary,
                    -- group_concat(json_extract(a.config, '$."general.avatar_path"'), ';') as avatar_paths,
                    group_concat(a.name, ' + ') as name,
                    '' AS goto_button,
                    '' AS del_button
                FROM contexts c
                LEFT JOIN contexts_members cp
                    ON c.id = cp.context_id
                LEFT JOIN agents a
                    ON cp.agent_id = a.id
                LEFT JOIN (
                    SELECT
                        context_id,
                        MAX(id) as latest_message_id
                    FROM contexts_messages
                    GROUP BY context_id
                ) cm ON c.id = cm.context_id
                WHERE c.parent_id IS NULL
                GROUP BY c.id
                ORDER BY
                    COALESCE(cm.latest_message_id, 0) DESC, 
                    c.id DESC;
                """)
        for row_data in data:
            item = QTreeWidgetItem(self.tree, [str(i) for i in row_data])
            # Create buttons for Chat and Delete
            btn_chat_func = partial(self.on_chat_btn_clicked, row_data)
            self.tree.setItemIconButtonColumn(item, 3, icon_chat, btn_chat_func)
            btn_del_func = partial(self.delete_context, row_data)
            self.tree.setItemIconButtonColumn(item, 4, icon_del, btn_del_func)

        # # first_desc = 'CURRENT CONTEXT'
        #
        # for row_data in data:
        #
        #
        # self.table_widget.setRowCount(0)
        # data = sql.get_results("""
        #     SELECT
        #         c.id,
        #         c.summary,
        #         group_concat(a.name, ' + ') as name,
        #         '' AS goto_button,
        #         '' AS del_button
        #     FROM contexts c
        #     LEFT JOIN contexts_members cp
        #         ON c.id = cp.context_id
        #     LEFT JOIN agents a
        #         ON cp.agent_id = a.id
        #     LEFT JOIN (
        #         SELECT
        #             context_id,
        #             MAX(id) as latest_message_id
        #         FROM contexts_messages
        #         GROUP BY context_id
        #     ) cm ON c.id = cm.context_id
        #     WHERE c.parent_id IS NULL
        #     GROUP BY c.id
        #     ORDER BY
        #         COALESCE(cm.latest_message_id, 0) DESC,
        #         c.id DESC;
        #     """)
        # # first_desc = 'CURRENT CONTEXT'
        #
        # for row_data in data:
        #     row_position = self.table_widget.rowCount()
        #     self.table_widget.insertRow(row_position)
        #     for column, item in enumerate(row_data):
        #         self.table_widget.setItem(row_position, column, QTableWidgetItem(str(item)))
        #
        #     if row_data[2] is None:  # If agent_name is NULL
        #         self.table_widget.setSpan(row_position, 1, 1, 2)  # Make the summary cell span over the next column
        #
        #     btn_chat = QPushButton('')
        #     btn_chat.setIcon(icon_chat)
        #     btn_chat.setIconSize(QSize(25, 25))
        #     btn_chat.setStyleSheet("QPushButton { background-color: transparent; }"
        #                            "QPushButton:hover { background-color: rgba(255, 255, 255, 0.1); }")
        #
        #     btn_chat.clicked.connect(partial(self.on_chat_btn_clicked, row_data))
        #     self.table_widget.setCellWidget(row_position, 3, btn_chat)
        #
        #     btn_delete = QPushButton('')
        #     btn_delete.setIcon(icon_del)
        #     btn_delete.setIconSize(QSize(25, 25))
        #     btn_delete.setStyleSheet("QPushButton { background-color: transparent; }"
        #                              "QPushButton:hover { background-color: rgba(255, 255, 255, 0.1); }")
        #
        #     btn_delete.clicked.connect(partial(self.delete_context, row_data))
        #     self.table_widget.setCellWidget(row_position, 4, btn_delete)

    def on_row_double_clicked(self, item):
        id = int(item.text(0))
        self.chat_with_context(id)

    def on_chat_btn_clicked(self, row_data):
        id_value = row_data[0]  # self.table_widget.item(row_item, 0).text()
        self.chat_with_context(id_value)

    def chat_with_context(self, id):
        if self.main.page_chat.context.responding:
            return
        self.main.page_chat.goto_context(context_id=id)
        self.main.content.setCurrentWidget(self.main.page_chat)
        self.main.sidebar.btn_new_context.setChecked(True)

    def show_context_menu(self, position):
        menu = QMenu(self)

        # Add actions to the context menu
        rename_action = menu.addAction('Rename')
        chat_action = menu.addAction('Chat')
        delete_action = menu.addAction('Delete')

        # Get the selected row's index
        selected_row_index = self.tree.indexAt(position).row()
        if selected_row_index < 0:
            return

        # Retrieve the row data as a tuple
        row_data = tuple(
            self.tree.item(selected_row_index, col).text() for col in range(self.tree.columnCount()))

        # Connect the actions to specific methods
        rename_action.triggered.connect(partial(self.rename_context, selected_row_index))
        chat_action.triggered.connect(partial(self.on_chat_btn_clicked, row_data))
        delete_action.triggered.connect(partial(self.delete_context, row_data))

        # Execute the menu
        menu.exec_(self.tree.viewport().mapToGlobal(position))

    def rename_context(self, row_item):
        # start editting the summary cell
        self.tree.editItem(self.tree.item(row_item, 1))

    def item_edited(self, item):
        row = item.row()
        context_id = self.tree.item(row, 0).text()

        id_map = {
            1: 'summary',
        }

        column = item.column()
        if column not in id_map:
            return
        column_name = id_map.get(column)
        new_value = item.text()
        sql.execute(f"""
            UPDATE contexts
            SET {column_name} = ?
            WHERE id = ?
        """, (new_value, context_id,))

    def delete_context(self, row_item):
        from agentpilot.context.base import Context

        retval = display_messagebox(
            icon=QMessageBox.Warning,
            text="Are you sure you want to permanently delete this context?",
            title="Delete Context",
            buttons=QMessageBox.Yes | QMessageBox.No,
        )
        if retval != QMessageBox.Yes:
            return

        context_id = row_item[0]
        context_member_ids = sql.get_results("SELECT id FROM contexts_members WHERE context_id = ?",
                                             (context_id,),
                                             return_type='list')
        sql.execute("DELETE FROM contexts_members_inputs WHERE member_id IN ({}) OR input_member_id IN ({})".format(
            ','.join([str(i) for i in context_member_ids]),
            ','.join([str(i) for i in context_member_ids])
        ))
        sql.execute("DELETE FROM contexts_messages WHERE context_id = ?;",
                    (context_id,))  # todo update delete to cascade branches & transaction
        sql.execute('DELETE FROM contexts_members WHERE context_id = ?', (context_id,))
        sql.execute("DELETE FROM contexts WHERE id = ?;", (context_id,))

        self.load()

        if self.main.page_chat.context.id == context_id:
            self.main.page_chat.context = Context(main=self.main)
