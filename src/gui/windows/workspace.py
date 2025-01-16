from PySide6.QtCore import QPoint
from PySide6.QtGui import Qt, QIcon, QPixmap, QMouseEvent, QCursor
from PySide6.QtWidgets import QWidget, QVBoxLayout

from src.gui.config import CVBoxLayout, CHBoxLayout
from src.gui.widgets import IconButton, BaseTreeWidget
# from src.utils.helpers import block_signals


class WorkspaceWindow(QWidget):
    def __init__(self, page_chat):
        super(WorkspaceWindow, self).__init__()
        self.main = page_chat.main
        # self.setAttribute(Qt.WA_TranslucentBackground)
        self.setWindowFlags(self.windowFlags() | Qt.FramelessWindowHint)
        self.setWindowTitle('AgentPilot')
        self.setWindowIcon(QIcon(':/resources/icon.png'))
        self.setMouseTracking(True)

        # set class to window
        # self.setProperty("class", "central")

        # set border radius to 10
        self.setStyleSheet('''
            QWidget {
                border-radius: 10px;
                border-top-left-radius: 30px;
            }
        ''')

        self.resize(800, 600)
        self.oldPosition = None

        self.title_bar = TitleButtonBar(self)
        self.directory_tree = DirectoryTree(self)

        self.layout = QVBoxLayout(self)
        self.layout.setContentsMargins(8, 2, 8, 8)
        self.layout.addWidget(self.title_bar)
        self.layout.addStretch(1)

        self.mousePressArea = 10  # Area in pixels to detect mouse for resizing.
        self.dragPosition = None
        self.resizing = False
    # def mousePressEvent(self, event):
    #     self.oldPosition = event.globalPosition().toPoint()
    #
    # def mouseMoveEvent(self, event):
    #     if self.oldPosition is None:
    #         return
    #     delta = QPoint(event.globalPosition().toPoint() - self.oldPosition)
    #     self.move(self.x() + delta.x(), self.y() + delta.y())
    #     self.oldPosition = event.globalPosition().toPoint()

    def mousePressEvent(self, event):
        super().mousePressEvent(event)
        self.dragPosition = event.globalPosition().toPoint()
        self.resizing = self.mouseIsOnEdge(event)

    def mouseIsOnCorner(self, event):
        rect = self.rect()
        return (event.pos().x() >= rect.width() - self.mousePressArea and
                event.pos().y() >= rect.height() - self.mousePressArea)

    def mouseIsOnEdge(self, event):
        rect = self.rect()
        return (event.pos().x() >= rect.width() - self.mousePressArea or
                event.pos().y() >= rect.height() - self.mousePressArea)

    def mouseReleaseEvent(self, event):
        super().mouseReleaseEvent(event)
        self.resizing = False
        self.dragPosition = None

    def mouseMoveEvent(self, event):
        if self.dragPosition is not None:
            if self.resizing:
                movePos = event.globalPosition().toPoint() - self.dragPosition
                minWidth = self.minimumSize().width()
                minHeight = self.minimumSize().height()
                newWidth = max(self.width() + movePos.x(), minWidth)
                newHeight = max(self.height() + movePos.y(), minHeight)
                self.resize(newWidth, newHeight)
                self.dragPosition = event.globalPosition().toPoint()
            else:
                delta = QPoint(event.globalPosition().toPoint() - self.dragPosition)
                self.move(self.x() + delta.x(), self.y() + delta.y())
                self.dragPosition = event.globalPosition().toPoint()
        else:
            on_edge = self.mouseIsOnEdge(event)
            on_corner = self.mouseIsOnCorner(event)
            if on_corner:
                self.setCursor(QCursor(Qt.SizeFDiagCursor))
            elif on_edge:
                self.setCursor(QCursor(Qt.SizeHorCursor))
            else:
                self.setCursor(QCursor(Qt.ArrowCursor))

    def eventFilter(self, source, event):
        if event.type() == QMouseEvent.MouseMove and source == self:
            if (event.pos().x() >= self.width() - self.mousePressArea and
                    event.pos().y() >= self.height() - self.mousePressArea):
                self.setCursor(QCursor(Qt.SizeFDiagCursor))  # Diagonal resize cursor.
            else:
                self.setCursor(QCursor(Qt.ArrowCursor))      # Standard arrow cursor.
        return super(WorkspaceWindow, self).eventFilter(source, event)


class DirectoryTree(QWidget):
    def __init__(self, parent, **kwargs):
        super().__init__()
        self.tree_buttons = WorkspaceButtonsWidget(parent=self)
        self.tree = BaseTreeWidget(parent=self)
        self.tree.setHeaderHidden(True)
        self.tree.setSortingEnabled(False)

        self.layout = CVBoxLayout(self)
        self.layout.addWidget(self.tree_buttons)
        self.layout.addWidget(self.tree)

    # def load(self):
    #     with block_signals(self.tree):
    #         self.tree.clear()
    #
    #         row_data_json_str = next(iter(self.config.values()), None)
    #         if row_data_json_str is None:
    #             return
    #         data = json.loads(row_data_json_str)
    #
    #         # col_names = [col['text'] for col in self.schema]
    #         for row_dict in data:
    #             # values = [row_dict.get(col_name, '') for col_name in col_names]
    #
    #             path = row_dict['location']
    #             icon_provider = QFileIconProvider()
    #             icon = icon_provider.icon(QFileInfo(path))
    #             if icon is None or isinstance(icon, QIcon) is False:
    #                 icon = QIcon()
    #
    #             self.add_new_entry(row_dict, icon=icon)
    #
    # def add_item(self, column_vals=None, icon=None):
    #     with block_pin_mode():
    #         file_dialog = QFileDialog()
    #         file_dialog.setFileMode(QFileDialog.ExistingFile)
    #         file_dialog.setOption(QFileDialog.ShowDirsOnly, False)
    #         file_dialog.setFileMode(QFileDialog.Directory)
    #         # fd.setStyleSheet("QFileDialog { color: black; }")
    #         path, _ = file_dialog.getOpenFileName(self, "Choose Files", "", options=file_dialog.Options())
    #
    #     if path:
    #         self.add_path(path)
    #
    # def add_folder(self):
    #     with block_pin_mode():
    #         file_dialog = QFileDialog()
    #         file_dialog.setFileMode(QFileDialog.Directory)
    #         file_dialog.setOption(QFileDialog.ShowDirsOnly, True)
    #         path = file_dialog.getExistingDirectory(self, "Choose Directory", "")
    #         if path:
    #             self.add_path(path)
    #
    # def add_path(self, path):
    #     filename = os.path.basename(path)
    #     is_dir = os.path.isdir(path)
    #     row_dict = {'filename': filename, 'location': path, 'is_dir': is_dir}
    #
    #     icon_provider = QFileIconProvider()
    #     icon = icon_provider.icon(QFileInfo(path))
    #     if icon is None or isinstance(icon, QIcon) is False:
    #         icon = QIcon()
    #
    #     super().add_item(row_dict, icon)
    #
    # def dragEnterEvent(self, event):
    #     # Check if the event contains file paths to accept it
    #     if event.mimeData().hasUrls():
    #         event.acceptProposedAction()
    #
    # def dragMoveEvent(self, event):
    #     # Check if the event contains file paths to accept it
    #     if event.mimeData().hasUrls():
    #         event.acceptProposedAction()
    #
    # def dropEvent(self, event):
    #     # Get the list of URLs from the event
    #     urls = event.mimeData().urls()
    #
    #     # Extract local paths from the URLs
    #     paths = [url.toLocalFile() for url in urls]
    #
    #     for path in paths:
    #         self.add_path(path)
    #
    #     event.acceptProposedAction()


class WorkspaceButtonsWidget(QWidget):
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
        self.btn_add_folder = IconButton(
            parent=self,
            icon_path=':/resources/icon-new-folder.png',
            tooltip='Add Folder',
            size=18,
        )
        # self.btn_add_folder.clicked.connect(self.add_folder)
        self.layout.addWidget(self.btn_add)
        self.layout.addWidget(self.btn_del)
        self.layout.addWidget(self.btn_add_folder)
        self.layout.addStretch(1)


class TitleButtonBar(QWidget):
    def __init__(self, parent):
        super().__init__()
        self.parent = parent
        self.main = parent.main

        # self.setAttribute(Qt.WA_StyledBackground, True)
        self.setFixedHeight(20)
        # sizePolicy = QSizePolicy()
        # sizePolicy.setHorizontalPolicy(QSizePolicy.Policy.Fixed)

        self.btn_minimise = self.TitleBarButtonMin(parent=self)
        self.btn_pin = self.TitleBarButtonPin(parent=self)
        self.btn_close = self.TitleBarButtonClose(parent=self)

        self.layout = CHBoxLayout(self)
        self.layout.addStretch(1)
        self.layout.addWidget(self.btn_minimise)
        self.layout.addWidget(self.btn_pin)
        self.layout.addWidget(self.btn_close)

        self.setMouseTracking(True)

    class TitleBarButtonPin(IconButton):
        def __init__(self, parent):
            super().__init__(parent=parent, icon_path=":/resources/icon-pin-on.png", size=20, opacity=0.7)
            self.clicked.connect(self.toggle_pin)

        def toggle_pin(self):
            global PIN_MODE
            PIN_MODE = not PIN_MODE
            icon_iden = "on" if PIN_MODE else "off"
            icon_file = f":/resources/icon-pin-{icon_iden}.png"
            self.setIconPixmap(QPixmap(icon_file))

    class TitleBarButtonMin(IconButton):
        def __init__(self, parent):
            super().__init__(parent=parent, icon_path=":/resources/minus.png", size=20, opacity=0.7)
            self.clicked.connect(self.window_action)

        def window_action(self):
            self.parent.main.collapse()
            if self.window().isMinimized():
                self.window().showNormal()
            else:
                self.window().showMinimized()

    class TitleBarButtonClose(IconButton):
        def __init__(self, parent):
            super().__init__(parent=parent, icon_path=":/resources/close.png", size=20, opacity=0.7)
            self.clicked.connect(self.closeApp)

        def closeApp(self):
            self.window().close()