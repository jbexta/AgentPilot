from PySide6.QtGui import QTextCharFormat, QColor
from PySide6.QtCore import QRegularExpression
from PySide6.QtWidgets import QSyntaxHighlighter


class DockerfileHighlighter(QSyntaxHighlighter):
    associated_extensions = ['dockerfile']

    def __init__(self, parent=None, workflow_settings=None):
        super().__init__(parent)

        self.instructionFormat = QTextCharFormat()
        self.instructionFormat.setForeground(QColor('#c78953')) # Similar to Python keywords

        self.stringFormat = QTextCharFormat()
        self.stringFormat.setForeground(QColor('#6aab73')) # Similar to Python strings

        self.commentFormat = QTextCharFormat()
        self.commentFormat.setForeground(QColor('#808080'))  # Grey color for comments

        self.instructions = [
            'FROM', 'RUN', 'CMD', 'LABEL', 'EXPOSE', 'ENV', 'ADD', 'COPY',
            'ENTRYPOINT', 'VOLUME', 'USER', 'WORKDIR', 'ARG', 'ONBUILD',
            'STOPSIGNAL', 'HEALTHCHECK', 'SHELL'
        ]

        # Regular expressions for Dockerfile syntax
        self.comment = QRegularExpression(r'#.*')
        self.string_double_quote = QRegularExpression(r'"([^"\\]|\\.)*(")?')
        self.string_single_quote = QRegularExpression(r"'([^'\\]|\\.)*(')?")

    def highlightBlock(self, text):
        # Instruction matching
        for instruction in self.instructions:
            # Match whole word, case-insensitive for instructions
            expression = QRegularExpression(r'\b' + instruction + r'\b', QRegularExpression.CaseInsensitiveOption)
            match_iterator = expression.globalMatch(text)
            while match_iterator.hasNext():
                match = match_iterator.next()
                self.setFormat(match.capturedStart(), match.capturedLength(), self.instructionFormat)

        # Comment matching
        match_iterator = self.comment.globalMatch(text)
        while match_iterator.hasNext():
            match = match_iterator.next()
            self.setFormat(match.capturedStart(), match.capturedLength(), self.commentFormat)

        # String matching (double quotes)
        match_iterator = self.string_double_quote.globalMatch(text)
        while match_iterator.hasNext():
            match = match_iterator.next()
            # Check if not inside a comment
            if not self.is_in_comment(text, match.capturedStart()):
                self.setFormat(match.capturedStart(), match.capturedLength(), self.stringFormat)

        # String matching (single quotes)
        match_iterator = self.string_single_quote.globalMatch(text)
        while match_iterator.hasNext():
            match = match_iterator.next()
            # Check if not inside a comment
            if not self.is_in_comment(text, match.capturedStart()):
                self.setFormat(match.capturedStart(), match.capturedLength(), self.stringFormat)

    def is_in_comment(self, text, position):
        comment_match = self.comment.match(text)
        while comment_match.hasMatch():
            if comment_match.capturedStart() < position < comment_match.capturedEnd():
                return True
            comment_match = self.comment.match(text, comment_match.capturedEnd())
        return False
