import asyncio
import inspect
import json
import re
from functools import partial

from PySide6.QtWidgets import *
from PySide6.QtCore import Signal, QSize, QRegularExpression, QEvent, QRunnable, Slot, QRectF
from PySide6.QtGui import QPixmap, QPalette, QColor, QIcon, QFont, Qt, QStandardItem, QPainter, \
    QPainterPath, QFontDatabase, QSyntaxHighlighter, QTextCharFormat, QTextOption, QTextDocument, QKeyEvent, \
    QTextCursor, QFontMetrics, QCursor, QTextBlockFormat

from src.utils import sql, resources_rc
from src.utils.helpers import block_pin_mode, path_to_pixmap, display_messagebox, block_signals, apply_alpha_to_hex, \
    get_avatar_paths_from_config
from src.utils.filesystem import unsimplify_path
from PySide6.QtWidgets import QAbstractItemView


def find_main_widget(widget):
    if hasattr(widget, 'main'):
        if widget.main is not None:
            return widget.main

    clss = widget.__class__.__name__
    if clss == 'Main':
        return widget
    if not hasattr(widget, 'parent'):
        return QApplication.activeWindow()
    return find_main_widget(widget.parent)


def find_breadcrumb_widget(widget):
    if hasattr(widget, 'breadcrumb_widget'):
        return widget.breadcrumb_widget
    if not hasattr(widget, 'parent'):
        return None
    return find_breadcrumb_widget(widget.parent)


def find_attribute(widget, attribute):
    if hasattr(widget, attribute):
        return getattr(widget, attribute)
    if not hasattr(widget, 'parent'):
        return None
    return find_attribute(widget.parent, attribute)


class BreadcrumbWidget(QWidget):
    def __init__(self, parent, root_title=None):
        super().__init__(parent=parent)
        from src.gui.config import CHBoxLayout

        self.setFixedHeight(45)
        self.parent = parent
        self.main = find_main_widget(self)
        self.root_title = root_title

        self.back_button = IconButton(parent=self, icon_path=':/resources/icon-back.png', size=40)
        self.back_button.setStyleSheet("border-top-left-radius: 22px;")
        self.back_button.clicked.connect(self.go_back)

        self.title_layout = CHBoxLayout(self)
        self.title_layout.setSpacing(20)
        self.title_layout.setContentsMargins(0, 0, 10, 0)
        self.title_layout.addWidget(self.back_button)

        self.label = QLabel(root_title)
        self.font = QFont()
        self.font.setPointSize(15)
        self.label.setFont(self.font)
        self.label.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.title_layout.addWidget(self.label)
        self.title_layout.addStretch(1)

    def set_nodes(self, nodes):
        # set text to each node joined by ' > '
        nodes.insert(0, self.root_title)
        nodes = [n for n in nodes if n is not None]
        self.label.setText('   >   '.join(reversed(nodes)))

    def go_back(self):
        history = self.main.page_history
        if len(history) > 1:
            last_page_index = history[-2]
            self.main.page_history.pop()
            self.main.sidebar.button_group.button(last_page_index).click()
        else:
            self.main.page_chat.ensure_visible()


class IconButton(QPushButton):
    def __init__(
            self,
            parent,
            icon_path,
            size=25,
            tooltip=None,
            icon_size_percent=0.75,
            colorize=True,
            opacity=1.0,
            text=None,
            checkable=False,
    ):
        super().__init__(parent=parent)
        self.parent = parent
        self.colorize = colorize
        self.opacity = opacity

        self.icon = None
        self.pixmap = QPixmap(icon_path)
        self.setIconPixmap(self.pixmap)

        character_width = 8
        width = size + (len(text) * character_width if text else 0)
        icon_size = int(size * icon_size_percent)
        self.setFixedSize(width, size)
        self.setIconSize(QSize(icon_size, icon_size))

        self.setAutoExclusive(False)  # To disable visual selection

        if tooltip:
            self.setToolTip(tooltip)

        if text:
            self.setText(text)

        if checkable:
            self.setCheckable(True)

    def setIconPath(self, icon_path):
        self.pixmap = QPixmap(icon_path)
        self.setIconPixmap(self.pixmap)

    def setIconPixmap(self, pixmap=None):
        if not pixmap:
            pixmap = self.pixmap
        else:
            self.pixmap = pixmap

        if self.colorize:
            pixmap = colorize_pixmap(pixmap, opacity=self.opacity)

        self.icon = QIcon(pixmap)
        self.setIcon(self.icon)


class ToggleIconButton(IconButton):
    def __init__(self, **kwargs):
        self.icon_path_checked = kwargs.pop('icon_path_checked', None)
        self.tooltip_when_checked = kwargs.pop('tooltip_when_checked', None)
        super().__init__(**kwargs)
        self.setCheckable(True)
        self.icon_path = kwargs.get('icon_path', None)
        self.ttip = kwargs.get('tooltip', '')
        self.clicked.connect(self.on_click)

    def on_click(self):
        self.refresh_icon()

    def setChecked(self, state):
        super().setChecked(state)
        self.refresh_icon()

    def refresh_icon(self):
        is_checked = self.isChecked()
        if self.icon_path_checked:
            self.setIconPixmap(QPixmap(self.icon_path_checked if is_checked else self.icon_path))
        if self.tooltip_when_checked:
            self.setToolTip(self.tooltip_when_checked if is_checked else self.ttip)


class CTextEdit(QTextEdit):
    on_enhancement_chunk_signal = Signal(str)
    enhancement_error_occurred = Signal(str)

    def __init__(self, gen_block_folder_name=None):
        super().__init__()
        # self.highlighter_field = kwargs.get('highlighter_field', None)
        self.text_editor = None
        self.setTabStopDistance(40)
        self.gen_block_folder_name = gen_block_folder_name
        self.available_blocks = {}
        self.enhancing_text = ''

        if gen_block_folder_name:
            self.wand_button = IconButton(parent=self, icon_path=':/resources/icon-wand.png', size=22)
            self.wand_button.setStyleSheet("background-color: transparent;")
            self.wand_button.clicked.connect(self.on_wand_clicked)
            self.wand_button.hide()

        self.expand_button = IconButton(parent=self, icon_path=':/resources/icon-expand.png', size=22)
        self.expand_button.setStyleSheet("background-color: transparent;")
        self.expand_button.clicked.connect(self.on_button_clicked)
        self.expand_button.hide()

        self.on_enhancement_chunk_signal.connect(self.on_enhancement_chunk, Qt.QueuedConnection)
        self.enhancement_error_occurred.connect(self.on_enhancement_error, Qt.QueuedConnection)

        self.updateButtonPosition()

    def on_wand_clicked(self):
        self.available_blocks = sql.get_results("""
            SELECT b.name, b.config
            FROM blocks b
            LEFT JOIN folders f ON b.folder_id = f.id
            WHERE f.name = ? AND f.ordr = 5""", (self.gen_block_folder_name,), return_type='dict')
        if len(self.available_blocks) == 0:
            display_messagebox(
                icon=QMessageBox.Warning,
                title="No supported blocks",
                text="No blocks found in designated folder, create one in the blocks page.",
                buttons=QMessageBox.Ok
            )
            return

        messagebox_input = self.toPlainText().strip()
        if messagebox_input == '':
            display_messagebox(
                icon=QMessageBox.Warning,
                title="No message found",
                text="Type a message in the message box to enhance.",
                buttons=QMessageBox.Ok
            )
            return

        menu = QMenu(self)
        for name in self.available_blocks.keys():
            action = menu.addAction(name)
            action.triggered.connect(partial(self.on_block_selected, name))

        menu.exec_(QCursor.pos())

    def on_block_selected(self, block_name):
        self.run_block(block_name)

    def run_block(self, block_name):
        self.enhancing_text = self.toPlainText().strip()
        self.clear()
        enhance_runnable = self.EnhancementRunnable(self, block_name, self.enhancing_text)
        main = find_main_widget(self)
        main.threadpool.start(enhance_runnable)

    class EnhancementRunnable(QRunnable):
        def __init__(self, parent, block_name, input_text):
            super().__init__()
            self.parent = parent
            # self.main = parent.main
            self.block_name = block_name
            self.input_text = input_text

        def run(self):
            asyncio.run(self.enhance_text())

        async def enhance_text(self):
            from src.system.base import manager
            try:
                async for key, chunk in manager.blocks.receive_block(self.block_name, add_input=self.input_text):
                    self.parent.on_enhancement_chunk_signal.emit(chunk)

            except Exception as e:
                self.parent.enhancement_error_occurred.emit(str(e))

    @Slot(str)
    def on_enhancement_chunk(self, chunk):
        self.insertPlainText(chunk)

    @Slot(str)
    def on_enhancement_error(self, error_message):
        self.setPlainText(self.enhancing_text)
        self.enhancing_text = ''
        display_messagebox(
            icon=QMessageBox.Warning,
            title="Enhancement error",
            text=f"An error occurred while enhancing the text: {error_message}",
            buttons=QMessageBox.Ok
        )

    def keyPressEvent(self, event: QKeyEvent):
        if event.key() == Qt.Key_Backtab:
            self.dedent()
            event.accept()
        elif event.key() == Qt.Key_Tab:
            if event.modifiers() & Qt.ShiftModifier:
                self.dedent()
            else:
                self.indent()
            event.ignore()
        else:
            super().keyPressEvent(event)

    def indent(self):
        cursor = self.textCursor()
        start_block = self.document().findBlock(cursor.selectionStart())
        end_block = self.document().findBlock(cursor.selectionEnd())

        cursor.beginEditBlock()
        while True:
            cursor.setPosition(start_block.position())
            cursor.insertText("\t")
            if start_block == end_block:
                break
            start_block = start_block.next()
        cursor.endEditBlock()

    def dedent(self):
        cursor = self.textCursor()
        start_block = self.document().findBlock(cursor.selectionStart())
        end_block = self.document().findBlock(cursor.selectionEnd())

        cursor.beginEditBlock()
        while True:
            cursor.setPosition(start_block.position())
            cursor.movePosition(QTextCursor.NextCharacter, QTextCursor.KeepAnchor)
            if cursor.selectedText() == "\t":
                cursor.removeSelectedText()
            if start_block == end_block:
                break
            start_block = start_block.next()
        cursor.endEditBlock()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self.updateButtonPosition()

    # def on_edited(self):  # CAUSE OF SEGFAULT
    #     all_windows = QApplication.topLevelWidgets()
    #     for window in all_windows:
    #         if isinstance(window, TextEditorWindow) and window.parent == self:
    #             with block_signals(window.editor):
    #                 window.editor.setPlainText(self.toPlainText())

    def updateButtonPosition(self):
        # Calculate the position for the button
        button_width = self.expand_button.width()
        button_height = self.expand_button.height()
        edit_rect = self.contentsRect()

        # Position the button at the bottom-right corner
        x = edit_rect.right() - button_width - 2
        y = edit_rect.bottom() - button_height - 2
        self.expand_button.move(x, y)

        # position wand button just above expand button
        if hasattr(self, 'wand_button'):
            self.wand_button.move(x, y - button_height)

    def on_button_clicked(self):
        from src.gui.windows.text_editor import TextEditorWindow
        # check if the window is already open where parent is self
        all_windows = QApplication.topLevelWidgets()
        for window in all_windows:
            if isinstance(window, TextEditorWindow) and window.parent == self:
                window.activateWindow()
                return
        self.text_editor = TextEditorWindow(self)  # this is a QMainWindow
        self.text_editor.show()
        self.text_editor.activateWindow()

    def insertFromMimeData(self, source):
        # Insert plain text from the MIME data
        if source.hasText():
            self.insertPlainText(source.text())
        else:
            super().insertFromMimeData(source)

    def dropEvent(self, event):
        # Handle text drop event
        mime_data = event.mimeData()
        if mime_data.hasText():
            cursor = self.cursorForPosition(event.position().toPoint())
            cursor.insertText(mime_data.text())
            event.acceptProposedAction()
        else:
            super().dropEvent(event)

    def enterEvent(self, event):
        self.expand_button.show()
        if hasattr(self, 'wand_button'):
            self.wand_button.show()
        # self.enhance_button.show()
        super().enterEvent(event)

    def leaveEvent(self, event):
        self.expand_button.hide()
        if hasattr(self, 'wand_button'):
            self.wand_button.hide()
        # self.enhance_button.hide()
        super().leaveEvent(event)


def colorize_pixmap(pixmap, opacity=1.0):
    from src.gui.style import TEXT_COLOR
    colored_pixmap = QPixmap(pixmap.size())
    colored_pixmap.fill(Qt.transparent)

    painter = QPainter(colored_pixmap)
    painter.setCompositionMode(QPainter.CompositionMode_Source)
    painter.drawPixmap(0, 0, pixmap)
    painter.setOpacity(opacity)
    painter.setCompositionMode(QPainter.CompositionMode_SourceIn)

    painter.fillRect(colored_pixmap.rect(), TEXT_COLOR)
    painter.end()

    return colored_pixmap


class BaseComboBox(QComboBox):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.current_pin_state = None
        self.setFixedHeight(20)

    def showPopup(self):
        from src.gui import main
        self.current_pin_state = main.PIN_MODE
        main.PIN_MODE = True
        super().showPopup()

    def hidePopup(self):
        from src.gui import main
        super().hidePopup()
        if self.current_pin_state is None:
            return
        main.PIN_MODE = self.current_pin_state

    def set_key(self, key):
        index = self.findData(key)
        self.setCurrentIndex(index)
        if index == -1:
            # Get last item todo dirty
            last_item = self.model().item(self.model().rowCount() - 1)
            last_key = last_item.data(Qt.UserRole)
            if last_key != key:
                # Create a new item with the missing model key and set its color to red, and set the data to the model key
                item = QStandardItem(key)
                item.setData(key, Qt.UserRole)
                item.setForeground(QColor('red'))
                self.model().appendRow(item)
                self.setCurrentIndex(self.model().rowCount() - 1)


class WrappingDelegate(QStyledItemDelegate):
    def __init__(self, wrap_columns, parent=None):
        super().__init__(parent=parent)
        self.wrap_columns = wrap_columns

    def createEditor(self, parent, option, index):
        if index.column() in self.wrap_columns:
            editor = QTextEdit(parent)
            editor.setWordWrapMode(QTextOption.WordWrap)
            return editor
        else:
            return super().createEditor(parent, option, index)

    def setEditorData(self, editor, index):
        if index.column() in self.wrap_columns:
            text = index.model().data(index, Qt.EditRole)
            editor.setText(text)
        else:
            super().setEditorData(editor, index)

    def setModelData(self, editor, model, index):
        if index.column() in self.wrap_columns:
            model.setData(index, editor.toPlainText(), Qt.EditRole)
        else:
            super().setModelData(editor, model, index)

    def paint(self, painter, option, index):
        if index.column() in self.wrap_columns:
            from src.gui.style import TEXT_COLOR
            text = index.data()

            # Set the text color for the painter
            textColor = QColor(TEXT_COLOR)  #  option.palette.color(QPalette.Text)
            painter.setPen(textColor)  # Ensure we use a QColor object
            # Apply the default palette text color too
            option.palette.setColor(QPalette.Text, textColor)

            painter.save()

            textDocument = QTextDocument()
            textDocument.setDefaultFont(option.font)
            textDocument.setPlainText(text)
            textDocument.setTextWidth(option.rect.width())
            painter.translate(option.rect.x(), option.rect.y())
            textDocument.drawContents(painter)
            painter.restore()
        else:
            super().paint(painter, option, index)

    def sizeHint(self, option, index):  # V1
        if index.column() in self.wrap_columns:
            textDocument = QTextDocument()
            textDocument.setDefaultFont(option.font)
            textDocument.setPlainText(index.data())
            textDocument.setTextWidth(option.rect.width())
            return QSize(option.rect.width(), int(textDocument.size().height()))
        else:
            return super().sizeHint(option, index)


class ComboBoxDelegate(QStyledItemDelegate):
    def __init__(self, parent, combo_type, default=None):
        super(ComboBoxDelegate, self).__init__(parent)
        self.combo_type = combo_type
        self.default = default

    def createEditor(self, parent, option, index):
        if isinstance(self.combo_type, tuple):
            combo = QComboBox(parent)
            combo.addItems(self.combo_type)
        elif self.combo_type == 'EnvironmentComboBox':
            combo = EnvironmentComboBox(parent)
        elif self.combo_type == 'RoleComboBox':
            combo = RoleComboBox(parent)
        else:
            raise NotImplementedError('Combo type not implemented')

        if self.default:
            index = combo.findText(self.default)
            combo.setCurrentIndex(index)

        combo.currentIndexChanged.connect(self.commitAndCloseEditor)
        return combo

    def setEditorData(self, editor, index):
        value = index.model().data(index, Qt.EditRole)
        if isinstance(editor, RoleComboBox):
            data_index = editor.findData(value)
            if data_index >= 0:
                editor.setCurrentIndex(data_index)
            else:
                editor.setCurrentIndex(0)
        else:
            editor.setCurrentText(value)
        editor.showPopup()

    def setModelData(self, editor, model, index):
        if isinstance(editor, RoleComboBox):
            value = editor.currentData()
        else:
            value = editor.currentText()
        model.setData(index, value, Qt.EditRole)

    def commitAndCloseEditor(self):
        editor = self.sender()
        self.commitData.emit(editor)
        self.closeEditor.emit(editor)

    def eventFilter(self, editor, event):
        if event.type() == QEvent.MouseButtonPress:
            editor.showPopup()
        return super(ComboBoxDelegate, self).eventFilter(editor, event)


class BaseTreeWidget(QTreeWidget):
    def __init__(self, parent, row_height=18, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.parent = parent
        self.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.setSelectionMode(QAbstractItemView.SingleSelection)
        # multi select
        # self.setSelectionMode(QAbstractItemView.ExtendedSelection)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)

        self.apply_stylesheet()

        header = self.header()
        header.setDefaultAlignment(Qt.AlignLeft)
        header.setStretchLastSection(False)
        header.setDefaultSectionSize(row_height)

        # Enable drag and drop
        self.setDragEnabled(True)
        self.setAcceptDrops(True)
        self.setDropIndicatorShown(True)

        # Set the drag and drop mode to internal moves only
        self.setDragDropMode(QTreeWidget.InternalMove)
        # header.setSectionResizeMode(1, QHeaderView.Stretch)
        self.header().sectionResized.connect(self.update_tooltips)

    # Connect signal to handle resizing of the headers, and call the function once initially

    def build_columns_from_schema(self, schema):
        self.setColumnCount(len(schema))
        # add columns to tree from schema list
        for i, header_dict in enumerate(schema):
            column_type = header_dict.get('type', str)
            column_visible = header_dict.get('visible', True)
            column_width = header_dict.get('width', None)
            column_stretch = header_dict.get('stretch', None)
            wrap_text = header_dict.get('wrap_text', False)
            # hide_header = header_dict.get('hide_header', False)

            combo_widgets = ['EnvironmentComboBox', 'RoleComboBox']
            is_combo_column = isinstance(column_type, tuple) or column_type in combo_widgets
            if is_combo_column:
                combo_delegate = ComboBoxDelegate(self, column_type)
                self.setItemDelegateForColumn(i, combo_delegate)

            if column_width:
                self.setColumnWidth(i, column_width)
            if column_stretch:
                self.header().setSectionResizeMode(i, QHeaderView.Stretch)
            if wrap_text:
                self.setItemDelegateForColumn(i, WrappingDelegate([i], self))
            self.setColumnHidden(i, not column_visible)

        headers = ['' if header_dict.get('hide_header') else header_dict['text']
                   for header_dict in schema]
        self.setHeaderLabels(headers)

    def load(self, data, folders_data, **kwargs):
        # self.tree.setUpdatesEnabled(False)
        folder_key = kwargs.get('folder_key', None)
        select_id = kwargs.get('select_id', None)
        silent_select_id = kwargs.get('silent_select_id', None)  # todo dirty
        init_select = kwargs.get('init_select', False)
        readonly = kwargs.get('readonly', False)
        schema = kwargs.get('schema', [])
        append = kwargs.get('append', False)
        group_folders = kwargs.get('group_folders', False)
        default_item_icon = kwargs.get('default_item_icon', None)
        # icon_from_config = kwargs.get('icon_from_config', False)

        with block_signals(self):
            # # selected_index = self.currentIndex().row()
            # # is_refresh = self.topLevelItemCount() > 0
            # expanded_folders = self.get_expanded_folder_ids()
            if not append:
                self.clear()
                # Load folders
                folder_items_mapping = {None: self}
                while folders_data:
                    for folder_id, name, parent_id, icon_path, folder_type, expanded, order in list(folders_data):
                        # folder_id, name, parent_id, icon_path, folder_type, expanded, order = folder_item
                        if parent_id in folder_items_mapping:
                            parent_item = folder_items_mapping[parent_id]
                            folder_item = QTreeWidgetItem(parent_item, [str(name), str(folder_id)])
                            folder_item.setData(0, Qt.UserRole, 'folder')
                            use_icon_path = icon_path or ':/resources/icon-folder.png'
                            folder_pixmap = colorize_pixmap(QPixmap(use_icon_path))
                            folder_item.setIcon(0, QIcon(folder_pixmap))
                            folder_items_mapping[folder_id] = folder_item
                            folders_data.remove((folder_id, name, parent_id, icon_path, folder_type, expanded, order))
                            expand = (expanded == 1)
                            folder_item.setExpanded(expand)

            # Load items
            for row_data in data:
                parent_item = self
                if folder_key is not None:
                    folder_id = row_data[-1]
                    parent_item = folder_items_mapping.get(folder_id) if folder_id else self

                if len(row_data) > len(schema):
                    row_data = row_data[:-1]  # remove folder_id

                item = QTreeWidgetItem(parent_item, [str(v) for v in row_data])

                if not readonly:
                    item.setFlags(item.flags() | Qt.ItemIsEditable)
                else:
                    item.setFlags(item.flags() & ~Qt.ItemIsEditable)

                for i in range(len(row_data)):
                    col_schema = schema[i]
                    cell_type = col_schema.get('type', None)
                    if cell_type == QPushButton:
                        btn_func = col_schema.get('func', None)
                        btn_partial = partial(btn_func, row_data)
                        btn_icon_path = col_schema.get('icon', '')
                        pixmap = colorize_pixmap(QPixmap(btn_icon_path))
                        self.setItemIconButtonColumn(item, i, pixmap, btn_partial)

                    image_key = col_schema.get('image_key', None)
                    if image_key:
                        if image_key == 'config':
                            config_index = [i for i, d in enumerate(schema) if d.get('key', d['text']) == 'config'][0]
                            config_dict = json.loads(row_data[config_index])
                            image_paths_list = get_avatar_paths_from_config(config_dict)
                        else:
                            image_index = [i for i, d in enumerate(schema) if d.get('key', d['text']) == image_key][0]
                            image_paths = row_data[image_index] or ''
                            image_paths_list = image_paths.split('//##//##//')
                        pixmap = path_to_pixmap(image_paths_list, diameter=25)
                        item.setIcon(i, QIcon(pixmap))
                    elif default_item_icon:
                        pixmap = colorize_pixmap(QPixmap(default_item_icon))
                        item.setIcon(i, QIcon(pixmap))

                    is_encrypted = col_schema.get('encrypt', False)
                    if is_encrypted:
                        pass
                        # todo

            if group_folders:
                for i in range(self.topLevelItemCount()):
                    item = self.topLevelItem(i)
                    if item is None:
                        continue
                    self.group_nested_folders(item)
                    self.delete_empty_folders(item)

            self.update_tooltips()
            if silent_select_id:
                self.select_items_by_id(silent_select_id)

        if init_select and self.topLevelItemCount() > 0:
            if select_id:
                self.select_items_by_id(select_id)
            elif not silent_select_id:
                self.setCurrentItem(self.topLevelItem(0))
                item = self.currentItem()
                self.scrollToItem(item)
        else:
            if hasattr(self.parent, 'toggle_config_widget'):
                self.parent.toggle_config_widget(False)

    def reload_selected_item(self, data, schema):
        # data is same as in `load`
        current_id = self.get_selected_item_id()
        if current_id is None:
            return

        row_data = next((row for row in data if row[1] == current_id), None)
        if row_data:
            if len(row_data) > len(schema):
                row_data = row_data[:-1]  # remove folder_id

            item = self.currentItem()
            # set values for each column in item
            for i in range(len(row_data)):
                item.setText(i, str(row_data[i]))

    # Function to group nested folders in the tree recursively
    def group_nested_folders(self, item):
        # Keep grouping while the item has exactly one folder child
        while item.childCount() == 1 and item.child(0).data(0, Qt.UserRole) == 'folder':
            child = item.takeChild(0)

            # Update the text to the current item's text plus the child's text
            item.setText(0, item.text(0) + '/' + child.text(0))

            # Add child's children to the current item
            while child.childCount() > 0:
                item.addChild(child.takeChild(0))

        # Recur into each child item (in case there are other nested structures)
        for i in range(item.childCount()):
            self.group_nested_folders(item.child(i))

    def delete_empty_folders(self, item):
        # First, recursively check and delete empty children
        for i in reversed(range(item.childCount())):  # Reversed because we might remove items
            child = item.child(i)
            if child.data(0, Qt.UserRole) == 'folder':
                self.delete_empty_folders(child)

        # Now check the current item itself
        if item.childCount() == 0 and item.data(0, Qt.UserRole) == 'folder':
            parent = item.parent()
            if parent:
                parent.removeChild(item)
            else:
                # If there's no parent, it means this is a top-level item
                index = self.indexOfTopLevelItem(item)
                if index != -1:
                    self.takeTopLevelItem(index)

    def get_column_value(self, column):
        item = self.currentItem()
        if not item:
            return None
        return item.text(column)

    def apply_stylesheet(self):
        from src.gui.style import TEXT_COLOR
        palette = self.palette()
        palette.setColor(QPalette.Highlight, apply_alpha_to_hex(TEXT_COLOR, 0.05))
        palette.setColor(QPalette.HighlightedText, apply_alpha_to_hex(TEXT_COLOR, 0.80))
        palette.setColor(QPalette.Text, QColor(TEXT_COLOR))
        self.setPalette(palette)

    def update_tooltips(self):
        font_metrics = QFontMetrics(self.font())

        def update_item_tooltips(self, item):
            for col in range(self.columnCount()):
                text = item.text(col)
                text_width = font_metrics.horizontalAdvance(text) + 45  # Adding some padding
                column_width = self.columnWidth(col)
                if column_width == 0:
                    continue
                if text_width > column_width:
                    item.setToolTip(col, text)
                else:
                    item.setToolTip(col, "")  # Remove tooltip if not cut off

            # Recursively update tooltips for child items
            for i in range(item.childCount()):
                update_item_tooltips(self, item.child(i))

        # Update tooltips for all top-level items and their children
        with block_signals(self):
            for i in range(self.topLevelItemCount()):
                update_item_tooltips(self, self.topLevelItem(i))

    def get_selected_item_id(self):
        item = self.currentItem()
        if not item:
            return None
        tag = item.data(0, Qt.UserRole)
        if tag == 'folder':
            return None
        return int(item.text(1))

    def get_selected_item_ids(self):  # todo merge with above
        sel_item_ids = []
        for item in self.selectedItems():
            if item.data(0, Qt.UserRole) != 'folder':
                sel_item_ids.append(int(item.text(1)))
        return sel_item_ids

    def get_selected_folder_id(self):
        item = self.currentItem()
        if not item:
            return None
        tag = item.data(0, Qt.UserRole)
        if tag != 'folder':
            return None
        return int(item.text(1))

    def select_items_by_id(self, ids):
        if not isinstance(ids, list):
            ids = [ids]
        # map id ints to strings
        ids = [str(i) for i in ids]
        for i in range(self.topLevelItemCount()):
            item = self.topLevelItem(i)
            item_in_ids = item.text(1) in ids
            item.setSelected(item_in_ids)
            if item_in_ids:
                self.scrollToItem(item)

                # # Set item to selected
                # self.setCurrentItem(item)
                # # item.setSelected(True)
                # self.scrollToItem(item)
                # break

    def get_selected_tag(self):
        item = self.currentItem()
        if not item:
            return None
        tag = item.data(0, Qt.UserRole)
        return tag

    def dragMoveEvent(self, event):
        target_item = self.itemAt(event.pos())
        can_drop = (target_item.data(0, Qt.UserRole) == 'folder') if target_item else False

        # distance to edge of the item
        distance = 0
        if target_item:
            rect = self.visualItemRect(target_item)
            bottom_distance = rect.bottom() - event.pos().y()
            top_distance = event.pos().y() - rect.top()
            distance = min(bottom_distance, top_distance)

        # only allow dropping on folders and reordering in between items
        if can_drop or distance < 4:
            super().dragMoveEvent(event)
        else:
            event.ignore()

    def dropEvent(self, event):
        dragging_item = self.currentItem()
        target_item = self.itemAt(event.pos())
        dragging_type = dragging_item.data(0, Qt.UserRole)
        target_type = target_item.data(0, Qt.UserRole) if target_item else None
        dragging_id = dragging_item.text(1)

        can_drop = (target_type == 'folder') if target_item else False

        # distance to edge of the item
        distance = 0
        if target_item:
            rect = self.visualItemRect(target_item)
            distance = min(event.pos().y() - rect.top(), rect.bottom() - event.pos().y())

        # only allow dropping on folders and reordering in between items
        if distance < 4:
            # REORDER AND/OR MOVE
            target_item_parent = target_item.parent() if target_item else None
            target_item_parent_id = target_item_parent.text(1) if target_item_parent else None

            dragging_item_parent = dragging_item.parent() if dragging_item else None
            dragging_item_parent_id = dragging_item_parent.text(1) if dragging_item_parent else None

            if target_item_parent_id == dragging_item_parent_id:
                # display message box
                display_messagebox(
                    icon=QMessageBox.Warning,
                    title='Not implemented yet',
                    text='Reordering is not implemented yet'
                )
                event.ignore()
                return

            if dragging_type == 'folder':
                self.update_folder_parent(dragging_id, target_item_parent_id)
            else:
                self.update_item_folder(dragging_id, target_item_parent_id)

        elif can_drop:
            is_locked = sql.get_scalar(f"""SELECT json_extract(config, '$.locked') FROM folders WHERE id = ?""", (dragging_id,)) or False
            if is_locked:
                event.ignore()
                return

            folder_id = target_item.text(1)
            if dragging_type == 'folder':
                self.update_folder_parent(dragging_id, folder_id)
            else:
                self.update_item_folder(dragging_id, folder_id)
        else:
            event.ignore()

    def setItemIconButtonColumn(self, item, column, icon, func):
        btn_chat = QPushButton('')
        btn_chat.setIcon(icon)
        btn_chat.setIconSize(QSize(25, 25))
        btn_chat.clicked.connect(func)
        self.setItemWidget(item, column, btn_chat)

    def get_expanded_folder_ids(self):
        expanded_ids = []

        def recurse_children(item):
            for i in range(item.childCount()):
                child = item.child(i)
                id = child.text(1)
                if child.isExpanded():
                    expanded_ids.append(id)
                recurse_children(child)

        recurse_children(self.invisibleRootItem())
        return expanded_ids

    def update_folder_parent(self, dragging_folder_id, to_folder_id):
        sql.execute(f"UPDATE folders SET parent_id = ? WHERE id = ?", (to_folder_id, dragging_folder_id))
        self.parent.load()
        # expand the folder
        for i in range(self.topLevelItemCount()):
            item = self.topLevelItem(i)
            if item.text(1) == to_folder_id:
                item.setExpanded(True)
                break

    def update_item_folder(self, dragging_item_id, to_folder_id):
        sql.execute(f"UPDATE `{self.parent.db_table}` SET folder_id = ? WHERE id = ?", (to_folder_id, dragging_item_id))
        self.parent.load()
        # expand the folder
        for i in range(self.topLevelItemCount()):
            item = self.topLevelItem(i)
            if item.text(1) == to_folder_id:
                item.setExpanded(True)
                break

    def mouseReleaseEvent(self, event):
        super().mouseReleaseEvent(event)
        if event.button() == Qt.RightButton and hasattr(self.parent, 'show_context_menu'):
            self.parent.show_context_menu()
            return

        item = self.itemAt(event.pos())
        if item:
            col = self.columnAt(event.pos().x())
            # Check if the delegate for this column is an instance of ComboBoxDelegate
            delegate = self.itemDelegateForColumn(col)
            if isinstance(delegate, ComboBoxDelegate):
                # force the item into edit mode
                self.editItem(item, col)

    def keyPressEvent(self, event):
        # delete button press
        super().keyPressEvent(event)
        if event.key() == Qt.Key_Delete and hasattr(self.parent, 'delete_item'):
            self.parent.delete_item()


class CircularImageLabel(QLabel):
    clicked = Signal()
    avatarChanged = Signal()

    def __init__(self, *args, diameter=50, **kwargs):
        super().__init__(*args, **kwargs)
        from src.gui.style import TEXT_COLOR
        self.avatar_path = None
        self.setAlignment(Qt.AlignCenter)
        self.setCursor(Qt.PointingHandCursor)
        radius = int(diameter / 2)
        self.setFixedSize(diameter, diameter)
        self.setStyleSheet(
            f"border: 1px dashed {TEXT_COLOR}; border-radius: {str(radius)}px;")  # A custom style for the empty label
        self.clicked.connect(self.change_avatar)

    def setImagePath(self, path):
        self.avatar_path = unsimplify_path(path)
        pixmap = path_to_pixmap(self.avatar_path, diameter=100)
        self.setPixmap(pixmap)
        self.avatarChanged.emit()

    def change_avatar(self):
        with block_pin_mode():
            fd = QFileDialog()
            fd.setStyleSheet("QFileDialog { color: black; }")  # Modify text color

            filename, _ = fd.getOpenFileName(None, "Choose Avatar", "",
                                                        "Images (*.png *.jpeg *.jpg *.bmp *.gif *.webp)", options=QFileDialog.Options())

        if filename:
            self.setImagePath(filename)

    def mousePressEvent(self, event):
        super().mousePressEvent(event)
        if event.button() == Qt.LeftButton:
            self.clicked.emit()

    def setPixmap(self, pixmap):
        if not pixmap:  # todo
            return
        super().setPixmap(pixmap.scaled(
            self.width(), self.height(),
            Qt.KeepAspectRatioByExpanding,
            Qt.SmoothTransformation
        ))

    def paintEvent(self, event):
        # Override paintEvent to draw a circular image
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)

        path = QPainterPath()
        path.addEllipse(0, 0, self.width(), self.height())
        painter.setClipPath(path)
        painter.drawPixmap(0, 0, self.pixmap())
        painter.end()


class ColorPickerWidget(QPushButton):
    colorChanged = Signal(str)
    def __init__(self):
        super().__init__()
        from src.gui.style import TEXT_COLOR
        self.color = None
        self.setFixedSize(24, 24)
        self.setProperty('class', 'color-picker')
        self.setStyleSheet(f"background-color: white; border: 1px solid {apply_alpha_to_hex(TEXT_COLOR, 0.20)};")
        self.clicked.connect(self.pick_color)

    def pick_color(self):
        from src.gui.style import TEXT_COLOR
        current_color = self.color if self.color else Qt.white
        color_dialog = QColorDialog()
        with block_pin_mode():
            # show alpha channel
            color = color_dialog.getColor(current_color, parent=None, options=QColorDialog.ShowAlphaChannel)

        if color.isValid():
            self.color = color
            self.setStyleSheet(f"background-color: {color.name(QColor.HexArgb)}; border: 1px solid {apply_alpha_to_hex(TEXT_COLOR, 0.20)};")
            self.colorChanged.emit(color.name(QColor.HexArgb))

    def setColor(self, hex_color):
        from src.gui.style import TEXT_COLOR
        color = QColor(hex_color)
        if color.isValid():
            self.color = color
            self.setStyleSheet(f"background-color: {color.name(QColor.HexArgb)}; border: 1px solid {apply_alpha_to_hex(TEXT_COLOR, 0.20)};")

    def get_color(self):
        return self.color.name(QColor.HexArgb) if self.color and self.color.isValid() else None


class PluginComboBox(BaseComboBox):
    def __init__(self, plugin_type, centered=False, none_text="Choose Plugin"):
        super().__init__()
        self.none_text = none_text
        self.plugin_type = plugin_type
        self.centered = centered

        if centered:
            self.setItemDelegate(AlignDelegate(self))
            self.setStyleSheet(
                "QComboBox::drop-down {border-width: 0px;} QComboBox::down-arrow {image: url(noimg); border-width: 0px;}")

        self.load()

    def load(self):
        from src.system.plugins import ALL_PLUGINS

        self.clear()
        if self.none_text:
            self.addItem(self.none_text, "")

        for plugin in ALL_PLUGINS[self.plugin_type]:
            if inspect.isclass(plugin):
                self.addItem(plugin.__name__.replace('_', ' '), plugin.__name__)
            else:
                self.addItem(plugin, plugin)

    def paintEvent(self, event):
        if not self.centered:
            super().paintEvent(event)
            return

        painter = QStylePainter(self)
        option = QStyleOptionComboBox()

        # Init style options with the current state of this widget
        self.initStyleOption(option)

        # Draw the combo box without the current text (removes the default left-aligned text)
        painter.setPen(self.palette().color(QPalette.Text))
        painter.drawComplexControl(QStyle.CC_ComboBox, option)

        # Manually draw the text, centered
        text_rect = self.style().subControlRect(QStyle.CC_ComboBox, option, QStyle.SC_ComboBoxEditField)
        text_rect.adjust(18, 0, 0, 0)  # left, top, right, bottom

        current_text = self.currentText()
        painter.drawText(text_rect, Qt.AlignCenter, current_text)


class APIComboBox(BaseComboBox):
    def __init__(self, *args, **kwargs):
        self.first_item = kwargs.pop('first_item', None)
        self.with_model_kinds = kwargs.pop('with_model_kinds', None)  # None means show all
        super().__init__(*args, **kwargs)

        self.load()

    def load(self):
        with block_signals(self):
            self.clear()
            if self.with_model_kinds:
                apis = sql.get_results(f"""
                    SELECT DISTINCT a.name, a.id
                    FROM apis a
                    JOIN models m
                        ON a.id = m.api_id
                    WHERE m.kind IN ({', '.join(['?' for _ in self.with_model_kinds])})
                    ORDER BY a.name
                """, self.with_model_kinds)
            else:
                apis = sql.get_results("SELECT name, id FROM apis ORDER BY name")

            if self.first_item:
                self.addItem(self.first_item, 0)
            for api in apis:
                self.addItem(api[0], api[1])


class EnvironmentComboBox(BaseComboBox):
    def __init__(self, *args, **kwargs):
        self.first_item = kwargs.pop('first_item', None)
        super().__init__(*args, **kwargs)
        # self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.load()

    def load(self):
        with block_signals(self):
            self.clear()
            models = sql.get_results("SELECT name, id FROM sandboxes ORDER BY name")
            for model in models:
                self.addItem(model[0], model[1])


class VenvComboBox(BaseComboBox):
    def __init__(self, parent, *args, **kwargs):
        from src.gui.config import CHBoxLayout
        self.parent = parent
        self.first_item = kwargs.pop('first_item', None)
        super().__init__(*args, **kwargs)
        self.current_key = None
        self.currentIndexChanged.connect(self.on_current_index_changed)

        self.btn_delete = self.DeleteButton(
            parent=self,
            icon_path=':/resources/icon-minus.png',
            tooltip='Delete Venv',
            size=20,
        )
        self.layout = CHBoxLayout(self)
        self.layout.addWidget(self.btn_delete)
        self.btn_delete.move(-20, 0)

        self.load()

    class DeleteButton(IconButton):
        def __init__(self, parent, *args, **kwargs):
            super().__init__(parent=parent, *args, **kwargs)
            self.clicked.connect(self.delete_venv)
            self.hide()

        def showEvent(self, event):
            super().showEvent(event)
            self.parent.btn_delete.move(self.parent.width() - 40, 0)

        def delete_venv(self):
            ok = display_messagebox(
                icon=QMessageBox.Warning,
                title='Delete Virtual Environment',
                text=f'Are you sure you want to delete the venv `{self.parent.current_key}`?',
                buttons=QMessageBox.Yes | QMessageBox.No
            )
            if ok != QMessageBox.Yes:
                return

            from src.system.base import manager
            manager.venvs.delete_venv(self.parent.current_key)
            self.parent.load()
            self.parent.reset_index()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self.btn_delete.move(self.width() - 40, 0)

    # only show options button when the mouse is over the combobox
    def enterEvent(self, event):
        self.btn_delete.show()
        super().enterEvent(event)

    def leaveEvent(self, event):
        self.btn_delete.hide()
        super().leaveEvent(event)

    def mouseMoveEvent(self, event):
        self.btn_delete.show()
        super().mouseMoveEvent(event)

    def load(self):
        from src.system.base import manager
        with block_signals(self):
            self.clear()
            venvs = manager.venvs.venvs  # a dict of name: Venv
            for venv_name, venv in venvs.items():
                item_user_data = f"{venv_name} ({venv.path})"
                self.addItem(item_user_data, venv_name)
            # add create new venv option
            self.addItem('< Create New Venv >', '<NEW>')

    def set_key(self, key):
        super().set_key(key)
        self.current_key = key

    def on_current_index_changed(self):
        from src.system.base import manager
        key = self.itemData(self.currentIndex())
        if key == '<NEW>':
            dlg_title, dlg_prompt = ('Enter Name', 'Enter a name for the new virtual environment')
            text, ok = QInputDialog.getText(self, dlg_title, dlg_prompt)
            if not ok or not text:
                self.reset_index()
                return
            if text == 'default':
                display_messagebox(
                    icon=QMessageBox.Warning,
                    title='Invalid Name',
                    text='The name `default` is reserved and cannot be used.'
                )
                self.reset_index()
                return
            manager.venvs.create_venv(text)
            self.load()
            self.set_key(text)
        else:
            self.current_key = key

    def reset_index(self):
        current_key_index = self.findData(self.current_key)
        has_items = self.count() - 1 > 0  # -1 for <new> item
        if current_key_index >= 0 and has_items:
            self.setCurrentIndex(current_key_index)
        else:
            self.set_key(self.current_key)


class RoleComboBox(BaseComboBox):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.load()
        self.currentIndexChanged.connect(self.on_index_changed)

    def load(self):
        with block_signals(self):
            self.clear()
            roles = sql.get_results("SELECT name FROM roles", return_type='list')
            for role in roles:
                self.addItem(role.title(), role)
            # add a 'New Role' option
            self.addItem('< New >', '<NEW>')

    def setCurrentIndex(self, index):
        super().setCurrentIndex(index)
        # print(f"Setting current index to {index}, text: {self.itemText(index)}, data: {self.itemData(index)}")

    def currentData(self, role=Qt.UserRole):
        data = super().currentData(role)
        # print(f"Current data: {data}, current index: {self.currentIndex()}, current text: {self.currentText()}")
        return data

    def on_index_changed(self, index):
        if self.itemData(index) == '<NEW>':
            new_role, ok = QInputDialog.getText(self, "New Role", "Enter the name for the new role:")
            if ok and new_role:
                sql.execute("INSERT INTO roles (name) VALUES (?)", (new_role.lower(),))

                self.load()

                new_index = self.findText(new_role.title())
                if new_index != -1:
                    self.setCurrentIndex(new_index)
            else:
                # If dialog was cancelled or empty input, revert to previous selection
                self.setCurrentIndex(self.findData('<NEW>') - 1)


class FontComboBox(BaseComboBox):
    class FontItemDelegate(QStyledItemDelegate):
        def paint(self, painter, option, index):
            font_name = index.data()

            self.font = option.font
            self.font.setFamily(font_name)
            self.font.setPointSize(12)

            painter.setFont(self.font)
            painter.drawText(option.rect, Qt.TextSingleLine, index.data())

    def __init__(self, *args, **kwargs):
        self.first_item = kwargs.pop('first_item', None)
        super().__init__(*args, **kwargs)

        self.addItem('')
        available_fonts = QFontDatabase.families()
        self.addItems(available_fonts)

        font_delegate = self.FontItemDelegate(self)
        self.setItemDelegate(font_delegate)


class LanguageComboBox(BaseComboBox):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        self.load()

    def load(self):
        self.clear()
        langs = [
            ('English', 'en'),
            # ('Russian', 'ru'),
            # ('Spanish', 'es'),
            # ('French', 'fr'),
            # ('German', 'de'),
            # ('Italian', 'it'),
            # ('Portuguese', 'pt'),
            # ('Chinese', 'zh'),
            # ('Japanese', 'ja'),
            # ('Korean', 'ko'),
            # ('Arabic', 'ar'),
            # ('Hindi', 'hi'),
        ]
        for lang in langs:
            self.addItem(lang[0], lang[1])


class NonSelectableItemDelegate(QStyledItemDelegate):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

    def paint(self, painter, option, index):
        is_header = index.data(Qt.UserRole) == 'header'
        if is_header:
            option.font.setBold(True)
        super().paint(painter, option, index)

    def editorEvent(self, event, model, option, index):
        if index.data(Qt.UserRole) == 'header':
            # Disable selection/editing of header items by consuming the event
            return True
        return super().editorEvent(event, model, option, index)

    def sizeHint(self, option, index):
        # Call the base implementation to get the default size hint
        return super().sizeHint(option, index)


class TreeDialog(QDialog):
    def __init__(self, parent, *args, **kwargs):
        super().__init__(parent=parent)
        self.parent = parent
        self.setWindowFlag(Qt.WindowMinimizeButtonHint, False)
        self.setWindowFlag(Qt.WindowMaximizeButtonHint, False)

        self.setWindowTitle(kwargs.get('title', ''))
        self.list_type = kwargs.get('list_type')
        self.callback = kwargs.get('callback', None)
        multiselect = kwargs.get('multiselect', False)

        layout = QVBoxLayout(self)
        self.tree_widget = BaseTreeWidget(self)
        self.tree_widget.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        layout.addWidget(self.tree_widget)

        list_type_lower = self.list_type.lower()
        if self.list_type == 'AGENT' or self.list_type == 'USER':
            def_avatar = ':/resources/icon-agent-solid.png' if self.list_type == 'AGENT' else ':/resources/icon-user.png'
            col_name_list = ['name', 'id', 'avatar', 'config']
            empty_member_label = 'Empty agent' if self.list_type == 'AGENT' else 'You'
            query = f"""
                SELECT name, id, avatar, config
                FROM (
                    SELECT
                        e.name,
                        e.id,
                        CASE
                            WHEN json_extract(config, '$._TYPE') = 'workflow' THEN
                                (
                                    SELECT GROUP_CONCAT(json_extract(m.value, '$.config."info.avatar_path"'), '//##//##//')
                                    FROM json_each(json_extract(e.config, '$.members')) m
                                    WHERE COALESCE(json_extract(m.value, '$.del'), 0) = 0
                                )
                            ELSE
                                COALESCE(json_extract(config, '$."info.avatar_path"'), '')
                        END AS avatar,
                        e.config
                    FROM entities e
                    WHERE kind = '{self.list_type}'
                )
                ORDER BY
                    CASE WHEN id = 0 THEN 0 ELSE 1 END,
                    id DESC"""
        elif self.list_type == 'TOOL':
            def_avatar = ':/resources/icon-tool.png'
            col_name_list = ['name', 'id', 'avatar', 'config']
            empty_member_label = None
            query = """
                SELECT
                    name,
                    uuid as id,
                    '' as avatar,
                    '{}' as config
                FROM tools
                ORDER BY name"""

        elif self.list_type == 'TEXT':
            def_avatar = ':/resources/icon-blocks.png'
            col_name_list = ['block', 'id', 'avatar', 'config']
            empty_member_label = 'Empty text block'
            query = f"""
                SELECT
                    name,
                    id,
                    '' as avatar,
                    COALESCE(json_extract(config, '$.members[0].config'), config) as config
                FROM blocks
                WHERE (json_array_length(json_extract(config, '$.members')) = 1
                    OR json_type(json_extract(config, '$.members')) IS NULL)
                    AND COALESCE(json_extract(config, '$.block_type'), 'Text') = 'Text'
                ORDER BY name"""

        elif self.list_type == 'PROMPT':
            def_avatar = ':/resources/icon-brain.png'
            col_name_list = ['block', 'id', 'avatar', 'config']
            empty_member_label = 'Empty prompt block'
            # extract members[0] of workflow `block_type` when `members` is not null
            query = f"""
                SELECT
                    name,
                    id,
                    '' as avatar,
                    COALESCE(json_extract(config, '$.members[0].config'), config) as config
                FROM blocks
                WHERE (json_array_length(json_extract(config, '$.members')) = 1
                    OR json_type(json_extract(config, '$.members')) IS NULL)
                    AND json_extract(config, '$.block_type') = 'Prompt'
                ORDER BY name"""
            
        elif self.list_type == 'CODE':
            def_avatar = ':/resources/icon-code.png'
            col_name_list = ['block', 'id', 'avatar', 'config']
            empty_member_label = 'Empty code block'
            query = f"""
                SELECT
                    name,
                    id,
                    '' as avatar,
                    COALESCE(json_extract(config, '$.members[0].config'), config) as config
                FROM blocks
                WHERE (json_array_length(json_extract(config, '$.members')) = 1
                    OR json_type(json_extract(config, '$.members')) IS NULL)
                    AND json_extract(config, '$.block_type') = 'Code'
                ORDER BY name"""
        else:
            raise NotImplementedError(f'List type {self.list_type} not implemented')

        column_schema = [
            {
                'text': 'Name',
                'key': 'name',
                'type': str,
                'stretch': True,
                'image_key': 'avatar',
            },
            {
                'text': 'id',
                'key': 'id',
                'type': int,
                'visible': False,
            },
            {
                'key': 'avatar',
                'text': '',
                'type': str,
                'visible': False,
            },
            {
                'text': 'config',
                'type': str,
                'visible': False,
            },
        ]
        self.tree_widget.build_columns_from_schema(column_schema)
        self.tree_widget.setHeaderHidden(True)

        data = sql.get_results(query)
        if empty_member_label:
            if list_type_lower == 'workflow':
                pass
            if list_type_lower in ['code', 'text', 'prompt']:
                empty_config_str = f"""{{"_TYPE": "block", "block_type": "{list_type_lower.capitalize()}"}}"""
            elif list_type_lower == 'agent':
                empty_config_str = "{}"
            else:
                empty_config_str = f"""{{"_TYPE": "{list_type_lower}"}}"""

            data.insert(0, [empty_member_label, 0, '', empty_config_str])

        # do it for QTreeWidget instead
        for i, val_list in enumerate(data):
            row_data = {col_name_list[i]: val_list[i] for i in range(len(val_list))}
            name = val_list[0]
            avatar_path = val_list[2].split('//##//##//') if val_list[2] else None
            pixmap = path_to_pixmap(avatar_path, def_avatar=def_avatar)
            icon = QIcon(pixmap) if avatar_path is not None else None

            item = QTreeWidgetItem()
            item.setText(0, name)
            item.setData(0, Qt.UserRole, row_data)

            if icon:
                item.setIcon(0, icon)

            self.tree_widget.addTopLevelItem(item)

        if self.callback:
            self.tree_widget.itemDoubleClicked.connect(self.itemSelected)

    def open(self):
        with block_pin_mode():
            self.exec_()

    def itemSelected(self, item):
        self.callback(item)
        self.close()

    def keyPressEvent(self, event):
        super().keyPressEvent(event)
        if event.key() != Qt.Key_Return:
            return
        item = self.tree_widget.currentItem()
        self.itemSelected(item)


class HelpIcon(QLabel):
    def __init__(self, parent, tooltip):
        super().__init__(parent=parent)
        self.parent = parent
        pixmap = colorize_pixmap(QPixmap(':/resources/icon-info.png'), opacity=0.5)
        pixmap = pixmap.scaled(12, 12, Qt.KeepAspectRatio, Qt.SmoothTransformation)
        self.setPixmap(pixmap)
        self.setToolTip(tooltip)


class AlignDelegate(QStyledItemDelegate):
    def paint(self, painter, option, index):
        option.displayAlignment = Qt.AlignCenter
        super(AlignDelegate, self).paint(painter, option, index)


class PythonHighlighter(QSyntaxHighlighter):
    def __init__(self, parent=None):
        super().__init__(parent)

        self.keywordFormat = QTextCharFormat()
        self.keywordFormat.setForeground(QColor('#c78953'))
        # self.keywordFormat.setFontWeight(QTextCharFormat.Bold)

        self.blueKeywordFormat = QTextCharFormat()
        self.blueKeywordFormat.setForeground(QColor('#6ab0de'))

        self.stringFormat = QTextCharFormat()
        self.stringFormat.setForeground(QColor('#6aab73'))

        self.commentFormat = QTextCharFormat()
        self.commentFormat.setForeground(QColor('#808080'))  # Grey color for comments

        self.blue_keywords = [
            'get_os_environ',
        ]

        self.keywords = [
            'and', 'as', 'assert', 'break', 'class', 'continue', 'def', 'del',
            'elif', 'else', 'except', 'finally', 'for', 'from', 'global', 'if',
            'import', 'in', 'is', 'lambda', 'nonlocal', 'not', 'or', 'pass',
            'raise', 'return', 'try', 'while', 'with', 'yield'
        ]

        # Regular expressions for python's syntax
        self.tri_single_quote = QRegularExpression("f?'''([^'\\\\]|\\\\.|'{1,2}(?!'))*(''')?")
        self.tri_double_quote = QRegularExpression('f?"""([^"\\\\]|\\\\.|"{1,2}(?!"))*(""")?')
        self.single_quote = QRegularExpression(r"'([^'\\]|\\.)*(')?")
        self.double_quote = QRegularExpression(r'"([^"\\]|\\.)*(")?')
        self.comment = QRegularExpression(r'#.*')  # Regular expression for comments

    def highlightBlock(self, text):
        # String matching
        self.match_multiline(text, self.tri_single_quote, 1, self.stringFormat)
        self.match_multiline(text, self.tri_double_quote, 2, self.stringFormat)
        self.match_inline_string(text, self.single_quote, self.stringFormat)
        self.match_inline_string(text, self.double_quote, self.stringFormat)

        # Keyword matching
        for keyword in self.keywords:
            expression = QRegularExpression('\\b' + keyword + '\\b')
            match_iterator = expression.globalMatch(text)
            while match_iterator.hasNext():
                match = match_iterator.next()
                self.setFormat(match.capturedStart(), match.capturedLength(), self.keywordFormat)

        for keyword in self.blue_keywords:
            expression = QRegularExpression('\\b' + keyword + '\\b')
            match_iterator = expression.globalMatch(text)
            while match_iterator.hasNext():
                match = match_iterator.next()
                self.setFormat(match.capturedStart(), match.capturedLength(), self.blueKeywordFormat)

        # Comment matching
        self.match_inline_comment(text, self.comment, self.commentFormat)

    def match_multiline(self, text, expression, state, format):
        if self.previousBlockState() == state:
            start = 0
            length = len(text)
        else:
            start = -1
            length = 0

        # Look for the start of a multi-line string
        if start == 0:
            match = expression.match(text)
            if match.hasMatch():
                length = match.capturedLength()
                if match.captured(3):  # Closing quotes are found
                    self.setCurrentBlockState(0)
                else:
                    self.setCurrentBlockState(state)  # Continue to the next line
                self.setFormat(match.capturedStart(), length, format)
                start = match.capturedEnd()
        while start >= 0:
            match = expression.match(text, start)
            # We've got a match
            if match.hasMatch():
                # Multiline string
                length = match.capturedLength()
                if match.captured(3):  # Closing quotes are found
                    self.setCurrentBlockState(0)
                else:
                    self.setCurrentBlockState(state)  # The string is not closed
                # Apply the formatting and then look for the next possible match
                self.setFormat(match.capturedStart(), length, format)
                start = match.capturedEnd()
            else:
                # No further matches; if we are in a multi-line string, color the rest of the text
                if self.currentBlockState() == state:
                    self.setFormat(start, len(text) - start, format)
                break

    def match_inline_string(self, text, expression, format):
        match_iterator = expression.globalMatch(text)
        while match_iterator.hasNext():
            match = match_iterator.next()
            if match.capturedLength() > 0:
                if match.captured(1):
                    self.setFormat(match.capturedStart(), match.capturedLength(), format)

    def match_inline_comment(self, text, expression, format):
        match_iterator = expression.globalMatch(text)
        while match_iterator.hasNext():
            match = match_iterator.next()
            in_string = False
            for i in range(match.capturedStart()):  # Check if comment # is inside a string
                if text[i] in ['"', "'"]:
                    quote = text[i]
                    if i == 0 or text[i - 1] != '\\':  # Not escaped
                        if in_string:
                            if text[i + 1:i + 3] == quote * 2:  # Triple quote ends
                                in_string = False
                                i += 2
                            elif quote == text[i]:  # Single or double quote ends
                                in_string = False
                        else:
                            in_string = True
            if not in_string:
                self.setFormat(match.capturedStart(), match.capturedLength(), format)


def clear_layout(layout, skip_count=0):
    """Clear all layouts and widgets from the given layout"""
    while layout.count() > skip_count:
        item = layout.takeAt(skip_count)
        widget = item.widget()
        if widget is not None:
            widget.deleteLater()
        else:
            child_layout = item.layout()
            if child_layout is not None:
                clear_layout(child_layout)
