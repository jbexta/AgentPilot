from PySide6.QtGui import QColor, QFont, QSyntaxHighlighter, QTextCharFormat


class DiffHighlighter(QSyntaxHighlighter):
    associated_extensions = ['diff', 'patch']

    def __init__(self, parent=None, workflow_settings=None):
        super().__init__(parent)
        self.added = QTextCharFormat()
        self.added.setForeground(QColor('#73c991'))
        self.removed = QTextCharFormat()
        self.removed.setForeground(QColor('#e5737a'))
        self.hunk = QTextCharFormat()
        self.hunk.setForeground(QColor('#6897bb'))
        self.header = QTextCharFormat()
        self.header.setFontWeight(QFont.Bold)

    def highlightBlock(self, text):
        if text.startswith(('diff --git', 'commit ', '+++', '---')):
            fmt = self.header
        elif text.startswith('@@'):
            fmt = self.hunk
        elif text.startswith('+'):
            fmt = self.added
        elif text.startswith('-'):
            fmt = self.removed
        else:
            return
        self.setFormat(0, len(text), fmt)
