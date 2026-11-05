import asyncio
import json
from functools import partial

from PySide6.QtCore import QEvent, QPoint, QRunnable, Signal, Slot
from PySide6.QtGui import QKeyEvent, Qt
from PySide6.QtWidgets import QHBoxLayout, QLabel, QMenu, QMessageBox, QPushButton, QWidget, QWidgetAction

from gui import system
from gui.gui_utils.helpers import find_main
from gui.gui_utils.icon_button import IconButton
from gui.gui_utils.library_dialog import LibraryDialog
from utils import sql
from utils.helpers import display_message, display_message_box


class TextEnhancerButton(IconButton):
    on_enhancement_chunk_signal = Signal(str)
    enhancement_error_occurred = Signal(str)

    def __init__(self, parent, widget, key):
        super().__init__(parent=parent, size=22, icon_path=':/resources/icon-wand.png', tooltip='Enhance the text using a block. Right click to assign blocks.')
        self.setProperty("class", "send")
        self.widget = widget
        self.enhancement_key = key

        self.available_blocks = {}
        self.enhancing_text = ''

        self.enhancement_runnable = None
        self.on_enhancement_chunk_signal.connect(self.on_enhancement_chunk, Qt.QueuedConnection)
        self.enhancement_error_occurred.connect(self.on_enhancement_error, Qt.QueuedConnection)

    def load_available_blocks(self):
        # Get the enhancement blocks from settings
        enhancement_blocks_json = sql.get_scalar("""
            SELECT value
            FROM settings
            WHERE field = 'enhancement_blocks'""")

        enhancement_blocks = json.loads(enhancement_blocks_json) or {}
        block_uuids = enhancement_blocks.get(self.enhancement_key, [])
        # Query blocks by IDs if we have any
        self.available_blocks = {}
        if block_uuids:
            placeholders = ",".join(["?" for _ in block_uuids])
            self.available_blocks = sql.get_results(f"""
                SELECT name, config
                FROM blocks
                    WHERE uuid IN ({placeholders})""", tuple(block_uuids), return_type='dict')

    def on_click(self):
        self.load_available_blocks()
        menu = QMenu(self)
        new_action = menu.addAction("Add block")
        new_action.triggered.connect(self.add_enhancement_block_dialog)

        if len(self.available_blocks) > 0:
            # add separator
            menu.addSeparator()
            for name in self.available_blocks.keys():
                # Create a custom widget for each block item
                widget = QWidget()
                layout = QHBoxLayout(widget)
                layout.setContentsMargins(5, 2, 5, 2)
                layout.setSpacing(5)

                # Block name label (clickable)
                name_label = QLabel(name)
                name_label.setObjectName('blockMenuName')
                name_label.mousePressEvent = lambda event, block_name=name: self.on_block_selected(block_name)
                name_label.setCursor(Qt.PointingHandCursor)

                # Delete button
                delete_btn = QPushButton("×")
                delete_btn.setFixedSize(20, 20)
                delete_btn.setObjectName('blockMenuDelete')
                delete_btn.clicked.connect(partial(self.delete_block, name, menu))

                layout.addWidget(name_label)
                layout.addWidget(delete_btn)

                # Create QWidgetAction and add to menu
                widget_action = QWidgetAction(menu)
                widget_action.setDefaultWidget(widget)
                menu.addAction(widget_action)

        # Bottom right of menu at top right of widget
        menu_pos = self.mapToGlobal(QPoint(self.rect().topRight().x() - menu.sizeHint().width(), self.rect().topRight().y()))
        menu.exec_(menu_pos)

    def on_block_selected(self, block_name):
        messagebox_input = self.widget.toPlainText().strip()
        if messagebox_input == '':
            display_message(
                icon=QMessageBox.Warning,
                title="Warning",
                message="No content to enhance",
            )
            return

        self.run_block(block_name)

    def delete_block(self, block_name, menu):
        # Remove the block from the enhancement_blocks setting
        existing_uuids = sql.get_scalar(f"""
            SELECT json_extract(value, '$.{self.enhancement_key}')
            FROM settings
            WHERE field = 'enhancement_blocks'""") or '[]'
        existing_uuids = json.loads(existing_uuids)

        matching_uuids = sql.get_results("""
            SELECT uuid
            FROM blocks
            WHERE name = ?""", (block_name,), return_type='list')

        new_uuids = [uuid for uuid in existing_uuids if uuid not in matching_uuids]
        # We need to properly format the JSON path for the json_set function
        json_path = f'$.{self.enhancement_key}'
        sql.execute("""
            UPDATE settings
            SET value = json_set(value, ?, json(?))
            WHERE field = 'enhancement_blocks'""", (json_path, json.dumps(new_uuids)))
        # Close the menu
        menu.close()

        # Reopen the menu
        self.click()

    def add_enhancement_block_dialog(self):
        LibraryDialog(
            parent=self,
            callback=self.add_enhancement_block,
            kind='blocks',
        ).open()

    def add_enhancement_block(self, item, link=False):
        # item is a QTreeWidgetItem
        if not item:
            return
        item_id = item.text(1)

        # json insert into `settings`.`value` where `field` = 'enhancement_blocks'
        # where the key in the json field = self.enhancement_key
        existing_uuids = sql.get_scalar(f"""
            SELECT json_extract(value, '$.{self.enhancement_key}')
            FROM settings
            WHERE field = 'enhancement_blocks'""") or '[]'
        existing_uuids = json.loads(existing_uuids)
        existing_uuids.append(item_id)
        # We need to properly format the JSON path for the json_set function
        json_path = f'$.{self.enhancement_key}'
        sql.execute("""
            UPDATE settings
            SET value = json_set(value, ?, json(?))
            WHERE field = 'enhancement_blocks'""", (json_path, json.dumps(existing_uuids)))
        # Reopen the menu
        self.click()

    def run_block(self, block_name):
        self.enhancing_text = self.widget.toPlainText().strip()
        self.widget.clear()
        enhance_runnable = self.EnhancementRunnable(self, block_name)
        main = find_main()
        main.threadpool.start(enhance_runnable)

    class EnhancementRunnable(QRunnable):
        def __init__(self, parent, block_name):
            super().__init__()
            self.parent = parent
            self.block_name = block_name

        def run(self):
            asyncio.run(self.enhance_text())

        async def enhance_text(self):
            try:
                no_output = True
                params = {'INPUT': self.parent.enhancing_text}
                async for key, chunk in system.manager.blocks.receive_block(self.block_name, params=params):
                    self.parent.on_enhancement_chunk_signal.emit(chunk)
                    no_output = False

                if no_output:
                    self.parent.on_enhancement_error.emit('No output from block')
            except Exception as e:
                self.parent.enhancement_error_occurred.emit(str(e))

    @Slot(str)
    def on_enhancement_chunk(self, chunk):
        self.widget.insertPlainText(chunk)
        # Press key to call resize
        self.widget.keyPressEvent(QKeyEvent(QEvent.KeyPress, Qt.Key.Key_End, Qt.KeyboardModifier.NoModifier))
        self.widget.verticalScrollBar().setValue(self.widget.verticalScrollBar().maximum())

    @Slot(str)
    def on_enhancement_error(self, error_message):
        self.widget.setPlainText(self.enhancing_text)
        self.enhancing_text = ''
        display_message_box(
            icon=QMessageBox.Warning,
            title="Enhancement error",
            text=f"An error occurred while enhancing the text: {error_message}",
            buttons=QMessageBox.Ok
        )
