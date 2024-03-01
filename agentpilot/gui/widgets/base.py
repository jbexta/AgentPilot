# import importlib
# import inspect
# import json
# import os
import json
import logging

from PySide6.QtWidgets import *
from PySide6.QtCore import Signal, QSize
from PySide6.QtGui import QPixmap, QPalette, QColor, QIcon, QFont, Qt, QStandardItemModel, QStandardItem, QPainter, \
    QPainterPath, QFontDatabase

from agentpilot.utils import sql, resources_rc
from agentpilot.utils.helpers import block_pin_mode, path_to_pixmap
from agentpilot.utils.filesystem import simplify_path


class ContentPage(QWidget):
    def __init__(self, main, title=''):
        super().__init__(parent=main)

        self.main = main
        self.layout = QVBoxLayout(self)
        self.layout.setSpacing(0)
        self.layout.setContentsMargins(0, 0, 0, 0)

        self.back_button = IconButton(parent=self, icon_path=':/resources/icon-back.png', size=40)
        self.back_button.setStyleSheet("border-top-left-radius: 10px;")
        self.back_button.clicked.connect(self.go_back)
        self.label = QLabel(title)

        # print('#431')
        self.font = QFont()
        self.font.setPointSize(15)
        self.label.setFont(self.font)
        self.label.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)

        self.title_layout = QHBoxLayout()
        self.title_layout.setSpacing(20)
        self.title_layout.addWidget(self.back_button)
        self.title_layout.addWidget(self.label)
        self.title_layout.addStretch(1)

        self.title_container = QWidget()
        self.title_container.setLayout(self.title_layout)

        self.layout.addWidget(self.title_container)

    def go_back(self):
        self.main.content.setCurrentWidget(self.main.page_chat)
        self.main.sidebar.btn_new_context.setChecked(True)


class IconButton(QPushButton):
    def __init__(self, parent, icon_path, size=25, tooltip=None, icon_size_percent=0.75, colorize=True, opacity=1.0):
        super().__init__(parent=parent)
        self.parent = parent
        self.colorize = colorize
        self.opacity = opacity

        self.icon = None
        self.pixmap = QPixmap(icon_path)
        self.setIconPixmap(self.pixmap)

        icon_size = int(size * icon_size_percent)
        self.setFixedSize(size, size)
        self.setIconSize(QSize(icon_size, icon_size))

        if tooltip:
            self.setToolTip(tooltip)

    def setIconPixmap(self, pixmap=None):
        if not pixmap:
            pixmap = self.pixmap
        else:
            self.pixmap = pixmap
        # else:
        #     self.pixmap = pixmap

        if self.colorize:
            pixmap = colorize_pixmap(pixmap, opacity=self.opacity)

        self.icon = QIcon(pixmap)
        self.setIcon(self.icon)


def colorize_pixmap(pixmap, opacity=1.0):
    from agentpilot.gui.style import TEXT_COLOR
    colored_pixmap = QPixmap(pixmap.size())
    colored_pixmap.fill(Qt.transparent)

    painter = QPainter(colored_pixmap)
    painter.setCompositionMode(QPainter.CompositionMode_Source)
    painter.drawPixmap(0, 0, pixmap)
    painter.setOpacity(opacity)
    painter.setCompositionMode(QPainter.CompositionMode_SourceIn)

    # Choose the color you want to apply to the non-transparent parts of the image
    painter.fillRect(colored_pixmap.rect(), TEXT_COLOR)  # Recolor with red for example
    painter.end()

    return colored_pixmap


class BaseComboBox(QComboBox):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.current_pin_state = None
        self.setItemDelegate(NonSelectableItemDelegate(self))
        self.setFixedWidth(150)

    def showPopup(self):
        from agentpilot.gui import main
        self.current_pin_state = main.PIN_MODE
        main.PIN_MODE = True
        super().showPopup()

    def hidePopup(self):
        from agentpilot.gui import main
        super().hidePopup()
        if self.current_pin_state is None:
            return
        main.PIN_MODE = self.current_pin_state


class BaseTableWidget(QTableWidget):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        from agentpilot.gui.style import TEXT_COLOR, PRIMARY_COLOR

        self.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.verticalHeader().setVisible(False)
        self.verticalHeader().setDefaultSectionSize(18)
        self.setSortingEnabled(True)
        self.setShowGrid(False)
        self.setSelectionMode(QAbstractItemView.SingleSelection)
        self.setColumnHidden(0, True)

        palette = self.palette()
        palette.setColor(QPalette.Highlight, '#0dffffff')
        palette.setColor(QPalette.HighlightedText, QColor(f'#cc{TEXT_COLOR.replace("#", "")}'))  # Setting selected text color to purple
        palette.setColor(QPalette.Text, QColor(TEXT_COLOR))  # Setting unselected text color to purple
        self.setPalette(palette)

        # Set the horizontal header properties (column headers)
        horizontalHeader = self.horizontalHeader()
        # Use a style sheet to change the background color of the column headers
        horizontalHeader.setStyleSheet(
            "QHeaderView::section {"
            f"background-color: {PRIMARY_COLOR};"  # Red background
            f"color: {TEXT_COLOR};"  # White text color
            "padding-left: 4px;"  # Padding from the left edge
            "}"
        )
        horizontalHeader.setDefaultAlignment(Qt.AlignLeft)


class BaseTreeWidget(QTreeWidget):
    def __init__(self, parent, *args, **kwargs):
        super().__init__(*args, **kwargs)
        from agentpilot.gui.style import TEXT_COLOR
        self.parent = parent
        self.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.setSortingEnabled(True)
        self.setSelectionMode(QAbstractItemView.SingleSelection)

        self.apply_stylesheet()

        header = self.header()
        header.setDefaultAlignment(Qt.AlignLeft)
        header.setStretchLastSection(False)
        header.setDefaultSectionSize(18)

        # Enable drag and drop
        self.setDragEnabled(True)
        self.setAcceptDrops(True)
        self.setDropIndicatorShown(True)

        # Set the drag and drop mode to internal moves only
        self.setDragDropMode(QTreeWidget.InternalMove)
        # header.setSectionResizeMode(1, QHeaderView.Stretch)

    def apply_stylesheet(self):
        from agentpilot.gui.style import TEXT_COLOR, PRIMARY_COLOR
        palette = self.palette()
        palette.setColor(QPalette.Highlight, f'#0d{TEXT_COLOR.replace("#", "")}')
        palette.setColor(QPalette.HighlightedText, QColor(f'#cc{TEXT_COLOR.replace("#", "")}'))  # Setting selected text color
        palette.setColor(QPalette.Text, QColor(TEXT_COLOR))  # Setting unselected text color
        self.setPalette(palette)

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
            pass

    def dropEvent(self, event):
        dragged_item = self.currentItem()
        target_item = self.itemAt(event.pos())
        dragging_type = dragged_item.data(0, Qt.UserRole)
        target_type = target_item.data(0, Qt.UserRole) if target_item else None
        dragging_id = dragged_item.text(1)

        can_drop = (target_type == 'folder') if target_item else False

        # distance to edge of the item
        distance = 0
        if target_item:
            rect = self.visualItemRect(target_item)
            distance = min(event.pos().y() - rect.top(), rect.bottom() - event.pos().y())

        # only allow dropping on folders and reordering in between items
        if distance < 4:
            print('REORDER')
            # # You'll need to calculate the new order based on the target position
            # new_order = self.calculate_new_order(target_item, dragged_item)
            # if dragging_type == 'folder':
            #     self.update_folder_order(dragging_id, new_order)
            # else:
            #     self.update_agent_order(dragging_id, new_order)
            # super().dropEvent(event)
        elif can_drop:
            folder_id = target_item.text(1)
            print('MOVE TO FOLDER ' + folder_id)
            if dragging_type == 'folder':
                self.update_folder_parent(dragging_id, folder_id)
            else:
                self.update_agent_folder(dragging_id, folder_id)
            # super().dropEvent(event)
        else:
            event.ignore()

    def setItemIconButtonColumn(self, item, column, icon, func):  # partial(self.on_chat_btn_clicked, row_data)
        btn_chat = QPushButton('')
        btn_chat.setIcon(icon)
        btn_chat.setIconSize(QSize(25, 25))
        btn_chat.setStyleSheet("QPushButton { background-color: transparent; }"
                               "QPushButton:hover { background-color: rgba(255, 255, 255, 0.1); }")
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

    def update_agent_folder(self, dragging_agent_id, to_folder_id):
        sql.execute(f"UPDATE agents SET folder_id = ? WHERE id = ?", (to_folder_id, dragging_agent_id))
        self.parent.load()
        # expand the folder
        for i in range(self.topLevelItemCount()):
            item = self.topLevelItem(i)
            if item.text(1) == to_folder_id:
                item.setExpanded(True)
                break


class CircularImageLabel(QLabel):
    clicked = Signal()
    avatarChanged = Signal()

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        from agentpilot.gui.style import TEXT_COLOR
        self.avatar_path = ''
        self.setAlignment(Qt.AlignCenter)
        self.setCursor(Qt.PointingHandCursor)
        self.setFixedSize(100, 100)
        self.setStyleSheet(
            f"border: 1px dashed {TEXT_COLOR}; border-radius: 50px;")  # A custom style for the empty label
        self.clicked.connect(self.change_avatar)

    def setImagePath(self, path):
        self.avatar_path = simplify_path(path)
        self.setPixmap(QPixmap(path))
        self.avatarChanged.emit()

    def change_avatar(self):
        with block_pin_mode():
            fd = QFileDialog()
            fd.setStyleSheet("QFileDialog { color: black; }")  # Modify text color

            filename, _ = fd.getOpenFileName(self, "Choose Avatar", "",
                                                        "Images (*.png *.jpeg *.jpg *.bmp *.gif)", options=QFileDialog.Options())

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
        self.color = None
        self.setFixedSize(24, 24)
        self.setStyleSheet("background-color: white; border: none;")
        self.clicked.connect(self.pick_color)

    def pick_color(self):
        current_color = self.color if self.color else Qt.white
        with block_pin_mode():
            color = QColorDialog.getColor(current_color, self)

        if color.isValid():
            self.color = color
            self.setStyleSheet(f"background-color: {color.name()}; border: none;")
            self.colorChanged.emit(color.name())

    def setColor(self, hex_color):
        color = QColor(hex_color)
        if color.isValid():
            self.color = color
            self.setStyleSheet(f"background-color: {color.name()}; border: none;")

    def get_color(self):
        return self.color.name() if self.color and self.color.isValid() else None


class ModelComboBox(BaseComboBox):
    def __init__(self, *args, **kwargs):
        self.first_item = kwargs.pop('first_item', None)
        super().__init__(*args, **kwargs)

        self.load()

    def load(self):
        self.clear()

        model = QStandardItemModel()
        self.setModel(model)

        models = sql.get_results("""
            SELECT
                m.alias,
                m.model_name,
                a.name AS api_name
            FROM models m
            LEFT JOIN apis a
                ON m.api_id = a.id
            ORDER BY
                a.name,
                m.alias
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


class APIComboBox(BaseComboBox):
    def __init__(self, *args, **kwargs):
        self.first_item = kwargs.pop('first_item', None)
        super().__init__(*args, **kwargs)

        self.load()

    def load(self):
        logging.debug('Loading APIComboBox')
        self.clear()
        models = sql.get_results("SELECT name, id FROM apis ORDER BY name")
        if self.first_item:
            self.addItem(self.first_item, 0)
        for model in models:
            self.addItem(model[0], model[1])


class RoleComboBox(BaseComboBox):
    def __init__(self, *args, **kwargs):
        logging.debug('Init RoleComboBox')
        self.first_item = kwargs.pop('first_item', None)
        super().__init__(*args, **kwargs)

        self.load()

    def load(self):
        logging.debug('Loading RoleComboBox')
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
            # Modify the style of headers here as you like, for example, bold or different background
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
        query = kwargs.get('query', '')
        list_type = kwargs.get('list_type')
        self.callback = kwargs.get('callback', None)
        multiselect = kwargs.get('multiselect', False)

        layout = QVBoxLayout(self)
        self.listWidget = QListWidget()
        if multiselect:
            self.listWidget.setSelectionMode(QAbstractItemView.MultiSelection)
        layout.addWidget(self.listWidget)

        if list_type == 'agents':
            query = """
                SELECT
                    json_extract(config, '$."info.name"') AS name,
                    id,
                    json_extract(config, '$."info.avatar_path"') AS avatar
                FROM agents
                ORDER BY id DESC"""
        elif list_type == 'tools':
            query = """
                SELECT
                    name,
                    id
                FROM tools
                ORDER BY name"""

        data = sql.get_results(query)
        for row_data in data:
            # id = row_data[0]
            name = row_data[0]
            icon = None
            if len(row_data) > 2:
                avatar_path = row_data[2]
                pixmap = path_to_pixmap(avatar_path)
                icon = QIcon(pixmap)

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


class AlignDelegate(QStyledItemDelegate):
    def paint(self, painter, option, index):
        option.displayAlignment = Qt.AlignCenter
        super(AlignDelegate, self).paint(painter, option, index)


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
