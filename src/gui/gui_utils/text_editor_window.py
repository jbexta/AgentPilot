from PySide6.QtGui import QIcon, QTextCursor
from PySide6.QtWidgets import QMainWindow, QTextEdit

from utils.helpers import block_signals


class TextEditorWindow(QMainWindow):
    def __init__(self, parent):
        super(TextEditorWindow, self).__init__()
        self.parent = parent
        self.setWindowTitle('Edit field')
        self.setWindowIcon(QIcon(':/resources/icon.png'))

        self.resize(800, 600)

        self.editor = QTextEdit()
        self.editor.setPlainText(self.parent.toPlainText())
        self.editor.moveCursor(QTextCursor.End)
        self.editor.textChanged.connect(self.on_edited)
        self.setCentralWidget(self.editor)

    def on_edited(self):
        with block_signals(self.parent):
            self.parent.setPlainText(self.editor.toPlainText())
