from PySide6.QtCore import QRegularExpression
from PySide6.QtGui import QColor, QSyntaxHighlighter, QTextCharFormat


class CelHighlighter(QSyntaxHighlighter):
    associated_extensions = ['cel']

    def __init__(self, parent=None, workflow_settings=None):
        super().__init__(parent)

        self.keywordFormat = QTextCharFormat()
        self.keywordFormat.setForeground(QColor('#c78953'))

        self.operatorFormat = QTextCharFormat()
        self.operatorFormat.setForeground(QColor('#c78953'))

        self.builtinFormat = QTextCharFormat()
        self.builtinFormat.setForeground(QColor('#6897BB'))

        self.stringFormat = QTextCharFormat()
        self.stringFormat.setForeground(QColor('#6aab73'))

        self.numberFormat = QTextCharFormat()
        self.numberFormat.setForeground(QColor('#6897BB'))

        self.commentFormat = QTextCharFormat()
        self.commentFormat.setForeground(QColor('#808080'))

        # Keywords
        self.keyword_regex = QRegularExpression(
            r'\b(true|false|null)\b'
        )

        # Operators (multi-char first)
        self.operator_regex = QRegularExpression(
            r'(&&|\|\||!=|==|>=|<=|!|\bin\b|>|<)'
        )

        # Built-in functions
        builtins = (
            'size|contains|startsWith|endsWith|matches|has|type'
            '|int|uint|double|string|bool|timestamp|duration'
        )
        self.builtin_regex = QRegularExpression(
            r'\b(' + builtins + r')\b'
        )

        # Strings (single and double quoted)
        self.single_string_regex = QRegularExpression(
            r"'([^'\\]|\\.)*'"
        )
        self.double_string_regex = QRegularExpression(
            r'"([^"\\]|\\.)*"'
        )

        # Numbers (integers and floats)
        self.number_regex = QRegularExpression(
            r'\b\d+(\.\d+)?\b'
        )

        # Line comments
        self.comment_regex = QRegularExpression(r'//.*')

    def highlightBlock(self, text):
        self._apply(text, self.keyword_regex, self.keywordFormat)
        self._apply(text, self.operator_regex, self.operatorFormat)
        self._apply(text, self.builtin_regex, self.builtinFormat)
        self._apply(text, self.number_regex, self.numberFormat)
        self._apply(text, self.single_string_regex, self.stringFormat)
        self._apply(text, self.double_string_regex, self.stringFormat)
        self._apply(text, self.comment_regex, self.commentFormat)

    def _apply(self, text, expression, fmt):
        """Apply highlighting for all matches of a regex."""
        it = expression.globalMatch(text)
        while it.hasNext():
            match = it.next()
            self.setFormat(
                match.capturedStart(),
                match.capturedLength(),
                fmt,
            )