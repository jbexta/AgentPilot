
from PySide6.QtCore import QRegularExpression
from PySide6.QtGui import QColor, QSyntaxHighlighter, QTextCharFormat


class XMLHighlighter(QSyntaxHighlighter):
    associated_extensions = ['xml']

    def __init__(self, parent=None, workflow_settings=None):
        super().__init__(parent)
        self.workflow_settings = workflow_settings

        # XML tags
        self.tag_format = QTextCharFormat()
        self.tag_format.setForeground(QColor('#438BB9'))

        # Jinja2 expressions {{ ... }}
        self.jinja_expr_format = QTextCharFormat()
        self.jinja_expr_format.setForeground(QColor('#D19A66'))

        # Jinja2 statements {% ... %}
        self.jinja_stmt_format = QTextCharFormat()
        self.jinja_stmt_format.setForeground(QColor('#C678DD'))

        # Jinja2 comments {# ... #}
        self.jinja_comment_format = QTextCharFormat()
        self.jinja_comment_format.setForeground(QColor('#7F848E'))
        self.jinja_comment_format.setFontItalic(True)

        # Define regex patterns
        self.patterns = [
            (QRegularExpression(r"<[^>]*>"), self.tag_format),
            (QRegularExpression(r"\{\{.*?\}\}"), self.jinja_expr_format),
            (QRegularExpression(r"\{%.*?%\}"), self.jinja_stmt_format),
            (QRegularExpression(r"\{#.*?#\}"), self.jinja_comment_format),
        ]

    def highlightBlock(self, text):
        for pattern, fmt in self.patterns:
            match = pattern.match(text)
            while match.hasMatch():
                start = match.capturedStart()
                length = match.capturedLength()
                self.setFormat(start, length, fmt)
                match = pattern.match(text, start + length)
    #     self.workflow_settings = workflow_settings  # todo link classes
    #     self.tag_format = QTextCharFormat()
    #     self.tag_format.setForeground(QColor('#438BB9'))

    # def highlightBlock(self, text):
    #     pattern = QRegularExpression(r"<[^>]*>")
    #     match = pattern.match(text)
    #     while match.hasMatch():
    #         start = match.capturedStart()
    #         length = match.capturedLength()
    #         self.setFormat(start, length, self.tag_format)
    #         match = pattern.match(text, start + length)
