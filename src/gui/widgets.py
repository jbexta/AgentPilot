import inspect
from functools import partial

from PySide6.QtWidgets import *
from PySide6.QtCore import Signal, QSize, QRegularExpression, QRect, QEvent
from PySide6.QtGui import QPixmap, QPalette, QColor, QIcon, QFont, Qt, QStandardItemModel, QStandardItem, QPainter, \
    QPainterPath, QFontDatabase, QSyntaxHighlighter, QTextCharFormat, QTextOption, QTextDocument, QCursor

from src.utils import sql, resources_rc
from src.utils.helpers import block_pin_mode, path_to_pixmap, display_messagebox, block_signals, apply_alpha_to_hex
from src.utils.filesystem import simplify_path, unsimplify_path
from PySide6.QtWidgets import QAbstractItemView


def find_main_widget(widget):
    if hasattr(widget, 'main'):
        return widget.main
    if not hasattr(widget, 'parent'):
        return None
    return find_main_widget(widget.parent)


class ContentPage(QWidget):
    def __init__(self, main, title=''):
        super().__init__(parent=main)
        from src.gui.config import CHBoxLayout

        self.main = main
        self.layout = QVBoxLayout(self)
        self.layout.setContentsMargins(0, 0, 0, 0)
        self.layout.setSpacing(0)

        self.back_button = IconButton(parent=self, icon_path=':/resources/icon-back.png', size=40)
        self.back_button.setStyleSheet("border-top-left-radius: 22px;")
        self.back_button.clicked.connect(self.go_back)

        # print('#431')

        self.title_container = QWidget()
        # self.title_container.setStyleSheet("background-color:
        self.title_layout = CHBoxLayout(self.title_container)
        self.title_layout.setSpacing(20)
        self.title_layout.setContentsMargins(0, 0, 10, 0)
        self.title_layout.addWidget(self.back_button)

        if title != '':
            self.label = QLabel(title)
            self.font = QFont()
            self.font.setPointSize(15)
            self.label.setFont(self.font)
            self.label.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)
            self.title_layout.addWidget(self.label)
            self.title_layout.addStretch(1)

        # self.title_container.setLayout(self.title_layout)

        self.layout.addWidget(self.title_container)

    def go_back(self):
        history = self.main.page_history
        if len(history) > 1:
            last_page_index = history[-2]
            self.main.page_history.pop()
            self.main.sidebar.button_group.button(last_page_index).click()
        else:
            # self.main.main_menu.content.setCurrentWidget(self.main.page_chat)
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


class ToggleButton(IconButton):
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
    def __init__(self, parent=None):
        super().__init__(parent)

        # Create a button and set its properties
        # self.button = QPushButton("Button", self)
        self.button = IconButton(parent=self, icon_path=':/resources/icon-expand.png', size=22)
        # set bg color to transparent, except when hovered
        self.button.setStyleSheet("background-color: transparent;")

        # self.button.setFixedSize(100, 30)  # You can adjust the size as needed

        # You can connect the button's clicked signal to a slot here
        self.button.clicked.connect(self.on_button_clicked)
        self.text_editor = None

        # Reposition the button initially
        self.updateButtonPosition()

        # Update button position when the text edit is resized
        self.textChanged.connect(self.updateButtonPosition)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self.updateButtonPosition()

    def updateButtonPosition(self):
        # Calculate the position for the button
        button_width = self.button.width()
        button_height = self.button.height()
        edit_rect = self.contentsRect()

        # Position the button at the bottom-right corner
        x = edit_rect.right() - button_width - 2
        y = edit_rect.bottom() - button_height - 2
        self.button.move(x, y)

    # Example slot for button click
    def on_button_clicked(self):
        from src.gui.windows.text_editor import TextEditorWindow
        self.text_editor = TextEditorWindow(self)  # this is a QMainWindow
        self.text_editor.show()
        self.text_editor.activateWindow()


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
        self.setItemDelegate(NonSelectableItemDelegate(self))
        self.setFixedWidth(150)

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
        elif self.combo_type == 'SandboxComboBox':
            combo = SandboxComboBox(parent)
        else:
            raise NotImplementedError('Combo type not implemented')

        if self.default:
            index = combo.findText(self.default)
            combo.setCurrentIndex(index)

        combo.currentIndexChanged.connect(self.commitAndCloseEditor)
        return combo

    def setEditorData(self, editor, index):
        value = index.model().data(index, Qt.EditRole)
        editor.setCurrentText(value)
        editor.showPopup()

    def setModelData(self, editor, model, index):
        model.setData(index, editor.currentText(), Qt.EditRole)

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
        from src.gui.style import TEXT_COLOR
        self.parent = parent
        self.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.setSelectionMode(QAbstractItemView.SingleSelection)

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

    def build_columns_from_schema(self, schema):
        self.setColumnCount(len(schema))
        # add columns to tree from schema list
        for i, header_dict in enumerate(schema):
            column_type = header_dict.get('type', str)
            column_visible = header_dict.get('visible', True)
            column_width = header_dict.get('width', None)
            column_stretch = header_dict.get('stretch', None)
            wrap_text = header_dict.get('wrap_text', False)

            if isinstance(column_type, tuple):
                # create a combobox cell
                # combo = QComboBox()
                # for item in column_type:
                #     combo.addItem(item)
                combo_delegate = ComboBoxDelegate(self, column_type)  # , default)
                self.setItemDelegateForColumn(i, combo_delegate)

            elif column_type == 'SandboxComboBox':
                combo = SandboxComboBox()
                combo_delegate = ComboBoxDelegate(self, column_type)
                self.setItemDelegateForColumn(i, combo_delegate)

            if column_width:
                self.setColumnWidth(i, column_width)
            if column_stretch:
                self.header().setSectionResizeMode(i, QHeaderView.Stretch)
            if wrap_text:
                self.setItemDelegateForColumn(i, WrappingDelegate([i], self))
            self.setColumnHidden(i, not column_visible)

        headers = [header_dict['text'] for header_dict in schema]
        self.setHeaderLabels(headers)

    def load(self, data, folders_data, **kwargs):
        # self.tree.setUpdatesEnabled(False)
        folder_key = kwargs.get('folder_key', None)
        select_id = kwargs.get('select_id', None)
        init_select = kwargs.get('init_select', False)
        readonly = kwargs.get('readonly', False)
        schema = kwargs.get('schema', [])
        append = kwargs.get('append', False)
        group_folders = kwargs.get('group_folders', False)

        with block_signals(self):
            expanded_folders = self.get_expanded_folder_ids()
            if not append:
                self.clear()
                # Load folders
                folder_items_mapping = {None: self}
                while folders_data:
                    for folder_id, name, parent_id, folder_type, order in list(folders_data):
                        if parent_id in folder_items_mapping:
                            parent_item = folder_items_mapping[parent_id]
                            folder_item = QTreeWidgetItem(parent_item, [str(name), str(folder_id)])
                            folder_item.setData(0, Qt.UserRole, 'folder')
                            folder_pixmap = colorize_pixmap(QPixmap(':/resources/icon-folder.png'))
                            folder_item.setIcon(0, QIcon(folder_pixmap))
                            folder_items_mapping[folder_id] = folder_item
                            folders_data.remove((folder_id, name, parent_id, folder_type, order))

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
                        image_index = [i for i, d in enumerate(schema) if d.get('key', None) == image_key][0]
                        image_paths = row_data[image_index] or ''
                        image_paths_list = image_paths.split('//##//##//')
                        pixmap = path_to_pixmap(image_paths_list, diameter=25)
                        item.setIcon(i, QIcon(pixmap))

                    is_encrypted = col_schema.get('encrypt', False)
                    if is_encrypted:
                        pass
                        # todo

            # Restore expanded folders
            for folder_id in expanded_folders:
                folder_item = folder_items_mapping.get(int(folder_id))
                if folder_item:
                    folder_item.setExpanded(True)

            if group_folders:
                for i in range(self.topLevelItemCount()):
                    item = self.topLevelItem(i)
                    self.group_nested_folders(item)
                    self.delete_empty_folders(item)
            # if True:  # auto delete empty folders
            #

        # self.tree.setUpdatesEnabled(True)

        if init_select and self.topLevelItemCount() > 0:
            if select_id:
                self.select_item_by_id(select_id)
            else:
                self.setCurrentItem(self.topLevelItem(0))
                item = self.currentItem()
                self.scrollToItem(item)
        else:
            if hasattr(self.parent, 'toggle_config_widget'):
                self.parent.toggle_config_widget(False)

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

    # def delete_empty_folders(self, item):
    #     if item.childCount() == 0: # and item.data(0, Qt.UserRole) == 'folder':
    #         parent = item.parent()
    #         if parent:
    #             parent.removeChild(item)
    #             return
    #
    #     for i in range(item.childCount()):
    #         child = item.child(i)
    #         if child.data(0, Qt.UserRole) == 'folder':
    #             self.delete_empty_folders(child)

    def apply_stylesheet(self):
        from src.gui.style import TEXT_COLOR
        palette = self.palette()
        # h_col = apply_alpha_to_hex(TEXT_COLOR, 0.05)
        palette.setColor(QPalette.Highlight, apply_alpha_to_hex(TEXT_COLOR, 0.05))
        palette.setColor(QPalette.HighlightedText, apply_alpha_to_hex(TEXT_COLOR, 0.80))
        palette.setColor(QPalette.Text, QColor(TEXT_COLOR))
        self.setPalette(palette)

    def get_selected_item_id(self):
        item = self.currentItem()
        if not item:
            return None
        tag = item.data(0, Qt.UserRole)
        if tag == 'folder':
            return None
        return int(item.text(1))

    def get_selected_folder_id(self):
        item = self.currentItem()
        if not item:
            return None
        tag = item.data(0, Qt.UserRole)
        if tag != 'folder':
            return None
        return int(item.text(1))

    def select_item_by_id(self, id):
        for i in range(self.topLevelItemCount()):
            item = self.topLevelItem(i)
            if item.text(1) == str(id):
                self.setCurrentItem(item)
                self.scrollToItem(item)
                break

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
            folder_id = target_item.text(1)
            print('MOVE TO FOLDER ' + folder_id)
            if dragging_type == 'folder':
                self.update_folder_parent(dragging_id, folder_id)
            else:
                self.update_item_folder(dragging_id, folder_id)
        else:
            # remove the visual line when event ignore
            # self.update()
            event.ignore()

    def setItemIconButtonColumn(self, item, column, icon, func):  # partial(self.on_chat_btn_clicked, row_data)
        btn_chat = QPushButton('')
        btn_chat.setIcon(icon)
        btn_chat.setIconSize(QSize(25, 25))
        # btn_chat.setStyleSheet("QPushButton { background-color: transparent; }"
        #                        "QPushButton:hover { background-color: rgba(255, 255, 255, 0.1); }")
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

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        from src.gui.style import TEXT_COLOR
        self.avatar_path = None
        self.setAlignment(Qt.AlignCenter)
        self.setCursor(Qt.PointingHandCursor)
        self.setFixedSize(100, 100)
        self.setStyleSheet(
            f"border: 1px dashed {TEXT_COLOR}; border-radius: 50px;")  # A custom style for the empty label
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
        # color_dialog.setOption(QColorDialog.ShowAlphaChannel, True)
        with block_pin_mode():
            # show alpha channel
            color = color_dialog.getColor(current_color, parent=None, options=QColorDialog.ShowAlphaChannel)
            # alpha = color.alpha()
            # cname = color.name(QColor.HexArgb)
            # pass

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
        hex_argb = self.color.name(QColor.HexArgb)
        # if alpha is 'ff' return without alpha, alpha is first 2 characters
        ret = hex_argb if hex_argb[:2] == 'ff' else hex_argb[2:]
        return self.color.name(QColor.HexArgb) if self.color and self.color.isValid() else None


class ModelComboBox(BaseComboBox):
    def __init__(self, *args, **kwargs):
        self.first_item = kwargs.pop('first_item', None)
        super().__init__(*args, **kwargs)

        self.load()

    def load(self):
        with block_signals(self):
            self.clear()

            model = QStandardItemModel()
            self.setModel(model)

            models = sql.get_results("""
                SELECT
                    m.name,
                    CASE
                    WHEN json_extract(a.config, '$.litellm_prefix') != '' THEN
                        json_extract(a.config, '$.litellm_prefix') || '/' || json_extract(m.config, '$.model_name')
                        ELSE
                            json_extract(m.config, '$.model_name')
                    END AS model_name,
                    a.name AS api_name
                FROM models m
                LEFT JOIN apis a
                    ON m.api_id = a.id
                WHERE a.api_key != ''
                ORDER BY
                    a.name,
                    m.name
            """)

            current_api = None

            if self.first_item:
                first_item = QStandardItem(self.first_item)
                first_item.setData(0, Qt.UserRole)
                model.appendRow(first_item)

            for alias, model_name, api_id in models:
                if current_api != api_id:
                    header_item = QStandardItem(api_id)
                    header_item.setData('header', Qt.UserRole)
                    header_item.setEnabled(False)
                    model.appendRow(header_item)

                    current_api = api_id

                item = QStandardItem(alias)
                item.setData(model_name, Qt.UserRole)
                model.appendRow(item)

    def paintEvent(self, event):
        current_item = self.model().item(self.currentIndex())
        if current_item:
            # Check if the selected item's text color is red
            if current_item.foreground().color() == QColor('red'):
                # Set the text color to red when
                # painter = QPainter(self)
                option = QStyleOptionComboBox()
                self.initStyleOption(option)

                painter = QStylePainter(self)
                painter.setPen(QColor('red'))
                painter.drawComplexControl(QStyle.CC_ComboBox, option)

                # Get the text rectangle
                text_rect = self.style().subControlRect(QStyle.CC_ComboBox, option, QStyle.SC_ComboBoxEditField)
                text_rect.adjust(2, 0, -2, 0)  # Adjust the rectangle to provide some padding

                # Draw the text with red color
                current_text = self.currentText()
                painter.drawText(text_rect, Qt.AlignLeft, current_text)
                return

        super().paintEvent(event)


class PluginComboBox(BaseComboBox):
    def __init__(self, plugin_type, centered=False, none_text="Choose Plugin"):
        super().__init__()  # parent=parent)
        self.none_text = none_text
        self.plugin_type = plugin_type
        self.centered = centered
        # self.setFixedWidth(175)

        if centered:
            self.setItemDelegate(AlignDelegate(self))
            self.setStyleSheet(
                "QComboBox::drop-down {border-width: 0px;} QComboBox::down-arrow {image: url(noimg); border-width: 0px;}")

        self.load()

    def load(self):
        from src.system.plugins import all_plugins

        self.clear()
        self.addItem(self.none_text, "")

        for plugin in all_plugins[self.plugin_type]:
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


class SandboxComboBox(BaseComboBox):
    def __init__(self, *args, **kwargs):
        self.first_item = kwargs.pop('first_item', None)
        super().__init__(*args, **kwargs)

        self.load()

    def load(self):
        with block_signals(self):
            self.clear()
            models = sql.get_results("SELECT name, id FROM sandboxes ORDER BY name")
            if self.first_item:
                self.addItem(self.first_item, 0)
            for model in models:
                self.addItem(model[0], model[1])


class RoleComboBox(BaseComboBox):
    def __init__(self, *args, **kwargs):
        self.first_item = kwargs.pop('first_item', None)
        super().__init__(*args, **kwargs)

        self.load()

    def load(self):
        self.clear()
        models = sql.get_results("SELECT name, id FROM roles")
        if self.first_item:
            self.addItem(self.first_item, 0)
        for model in models:
            self.addItem(model[0].title(), model[0])


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


class ListDialog(QDialog):
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
        self.listWidget = QListWidget()
        if multiselect:
            self.listWidget.setSelectionMode(QAbstractItemView.MultiSelection)
        layout.addWidget(self.listWidget)

        list_type_lower = self.list_type.lower()
        empty_config_str = "{}" if list_type_lower == "agent" else f"""{{"_TYPE": "{list_type_lower}"}}"""
        if self.list_type == 'AGENT' or self.list_type == 'USER':
            def_avatar = ':/resources/icon-agent-solid.png' if self.list_type == 'AGENT' else ':/resources/icon-user.png'
            col_name_list = ['name', 'id', 'avatar', 'config']
            empty_entity_label = 'Empty agent' if self.list_type == 'AGENT' else 'You'
            query = f"""
                SELECT name, id, avatar, config
                FROM (
                    SELECT '{empty_entity_label}' AS name, 0 AS id, '' AS avatar, '{empty_config_str}' AS config
                    UNION
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
            pass
        elif self.list_type == 'TOOL':
            def_avatar = ':/resources/icon-tool.png'
            col_name_list = ['tool', 'id', 'avatar', 'config']
            query = f"""
                SELECT
                    name,
                    id,
                    '' as avatar,
                    '{empty_config_str}' as config
                FROM tools
                ORDER BY name"""
        else:
            raise NotImplementedError(f'List type {self.list_type} not implemented')

        data = sql.get_results(query)
        # for val_list in data:
        # zip colname and data into a dict
        # zipped_dict = [dict(zip(col_name_list, val_list)) for val_list in data]

        for i, val_list in enumerate(data):
            # id = row_data[0]
            row_data = {col_name_list[i]: val_list[i] for i in range(len(val_list))}
            name = val_list[0]
            icon = None
            if len(val_list) > 2:
                avatar_path = val_list[2].split('//##//##//') if val_list[2] else None
                pixmap = path_to_pixmap(avatar_path, def_avatar=def_avatar)
                icon = QIcon(pixmap) if avatar_path is not None else None

            item = QListWidgetItem()
            item.setText(name)
            item.setData(Qt.UserRole, row_data)

            if icon:
                item.setIcon(icon)

            self.listWidget.addItem(item)

        if self.callback:
            self.listWidget.itemDoubleClicked.connect(self.itemSelected)

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
        item = self.listWidget.currentItem()
        self.itemSelected(item)


class HelpIcon(QLabel):
    def __init__(self, parent, tooltip):
        super().__init__(parent=parent)
        self.parent = parent
        pixmap = colorize_pixmap(QPixmap(':/resources/icon-info.png'), opacity=0.5)
        pixmap = pixmap.scaled(12, 12, Qt.KeepAspectRatio, Qt.SmoothTransformation)
        self.setPixmap(pixmap)
        self.setToolTip(tooltip)


# class CustomTabBar(QTabBar):
#     def __init__(self, parent=None):
#         super().__init__(parent)
#
#     def setTabVisible(self, index, visible):
#         super().setTabVisible(index, visible)
#         if not visible:
#             # Set the tab width to 0 when it is hidden
#             self.setTabEnabled(index, False)
#             self.setStyleSheet(f"QTabBar::tab {{ width: 0px; height: 0px; }}")
#         else:
#             # Reset the tab size when it is shown again
#             self.setTabEnabled(index, True)
#             self.setStyleSheet("")  # Reset the stylesheet


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

        self.stringFormat = QTextCharFormat()
        self.stringFormat.setForeground(QColor('#6aab73'))

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


def clear_layout(layout):
    """Clear all layouts and widgets from the given layout"""
    while layout.count():
        item = layout.takeAt(0)
        widget = item.widget()
        if widget is not None:
            widget.deleteLater()
        else:
            child_layout = item.layout()
            if child_layout is not None:
                clear_layout(child_layout)
