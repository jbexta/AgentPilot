# from PySide6.QtGui import Qt
#
#
# class WorkspaceWindow(QWidget):
#     def __init__(self, page_chat):
#         super(WorkspaceWindow, self).__init__()
#         self.main = page_chat.main
#         self.setAttribute(Qt.WA_TranslucentBackground)
#         self.setWindowFlags(self.windowFlags() | Qt.FramelessWindowHint)
#
#         # self.setWindowTitle('AgentPilot')
#         # self.setWindowIcon(QIcon(':/resources/icon.png'))
#         self.setMouseTracking(True)
#
#         self.setFixedSize(100, 400)
#         self.oldPosition = None
#
#         self.title_bar = TitleButtonBar(self)
#         self.directory_tree = DirectoryTree(self)
#
#         self.layout = QVBoxLayout(self)
#         self.layout.setContentsMargins(8, 2, 8, 8)
#         self.layout.addWidget(self.title_bar)
#         self.layout.addStretch(1)
#
#         self.mousePressArea = 10  # Area in pixels to detect mouse for resizing.
#         self.dragPosition = None
#         self.resizing = False