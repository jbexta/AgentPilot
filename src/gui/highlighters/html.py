from PySide6.QtCore import QRegularExpression
from PySide6.QtGui import QColor, QSyntaxHighlighter, QTextCharFormat


class HTMLHighlighter(QSyntaxHighlighter):
    associated_extensions = ['html', 'htm', 'xhtml']

    def __init__(self, parent=None, workflow_settings=None):
        super().__init__(parent)

        self.tag_format = QTextCharFormat()
        self.tag_format.setForeground(QColor('#438BB9'))

        self.attribute_format = QTextCharFormat()
        self.attribute_format.setForeground(QColor('#9876AA'))

        self.value_format = QTextCharFormat()
        self.value_format.setForeground(QColor('#6aab73'))

        self.doctype_format = QTextCharFormat()
        self.doctype_format.setForeground(QColor('#c78953'))

        self.entity_format = QTextCharFormat()
        self.entity_format.setForeground(QColor('#6897BB'))

        self.comment_format = QTextCharFormat()
        self.comment_format.setForeground(QColor('#808080'))
        self.comment_format.setFontItalic(True)

        self.tag_regex = QRegularExpression(r'</?[A-Za-z][\w:-]*|/?>')
        self.attribute_regex = QRegularExpression(
            r'<[A-Za-z][\w:-]*\s+([^>]*)'
        )
        self.attribute_name_regex = QRegularExpression(r'[\w:@.-]+(?=\s*=)')
        self.value_regex = QRegularExpression(r'"[^"]*"|\'[^\']*\'')
        self.doctype_regex = QRegularExpression(r'<!DOCTYPE[^>]*>')
        self.doctype_regex.setPatternOptions(
            QRegularExpression.CaseInsensitiveOption
        )
        self.entity_regex = QRegularExpression(r'&#?\w+;')
        self.comment_start = QRegularExpression(r'<!--')
        self.comment_end = QRegularExpression(r'-->')

    def highlightBlock(self, text):
        self.highlight_pattern(text, self.tag_regex, self.tag_format)
        self.highlight_attributes(text)
        self.highlight_pattern(text, self.entity_regex, self.entity_format)
        self.highlight_pattern(text, self.doctype_regex, self.doctype_format)
        self.highlight_comments(text)

    def highlight_pattern(self, text, expression, fmt):
        it = expression.globalMatch(text)
        while it.hasNext():
            match = it.next()
            self.setFormat(match.capturedStart(), match.capturedLength(), fmt)

    def highlight_attributes(self, text):
        it = self.attribute_regex.globalMatch(text)
        while it.hasNext():
            match = it.next()
            offset = match.capturedStart(1)
            attrs = match.captured(1)
            for regex, fmt in (
                (self.attribute_name_regex, self.attribute_format),
                (self.value_regex, self.value_format),
            ):
                sub_it = regex.globalMatch(attrs)
                while sub_it.hasNext():
                    sub = sub_it.next()
                    self.setFormat(
                        offset + sub.capturedStart(),
                        sub.capturedLength(),
                        fmt,
                    )

    def highlight_comments(self, text):
        self.setCurrentBlockState(0)
        start = 0
        if self.previousBlockState() != 1:
            start = self.comment_start.match(text).capturedStart()

        while start >= 0:
            end_match = self.comment_end.match(text, start)
            if end_match.hasMatch():
                length = end_match.capturedEnd() - start
            else:
                self.setCurrentBlockState(1)
                length = len(text) - start
            self.setFormat(start, length, self.comment_format)
            start = self.comment_start.match(text, start + length).capturedStart()
