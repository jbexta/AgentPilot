from PySide6.QtCore import QRegularExpression
from PySide6.QtGui import QColor, QSyntaxHighlighter, QTextCharFormat


class JsonHighlighter(QSyntaxHighlighter):
    associated_extensions = ['json', 'jsonc', 'jsonl', 'json5']
    
    def __init__(self, parent=None, workflow_settings=None):
        super().__init__(parent)

        # Define text formats with colors consistent with the theme
        self.keywordFormat = QTextCharFormat()
        self.keywordFormat.setForeground(QColor('#c78953'))  # JSON keywords (true, false, null)
        
        self.stringFormat = QTextCharFormat()
        self.stringFormat.setForeground(QColor('#6aab73'))   # String values
        
        self.numberFormat = QTextCharFormat()
        self.numberFormat.setForeground(QColor('#6897BB'))   # Numeric values
        
        self.propertyFormat = QTextCharFormat()
        self.propertyFormat.setForeground(QColor('#9876AA'))  # Property names
        
        self.punctuationFormat = QTextCharFormat()
        self.punctuationFormat.setForeground(QColor('#CC7832'))  # Brackets, braces, colons, commas

        # Define regular expressions for JSON syntax
        self.string_regex = QRegularExpression(r'"([^"\\]|\\.)*"')
        self.number_regex = QRegularExpression(r'-?\d+(\.\d+)?([eE][+-]?\d+)?')
        self.keyword_regex = QRegularExpression(r'\b(true|false|null)\b')
        self.property_regex = QRegularExpression(r'"([^"\\]|\\.)*"\s*(?=:)')
        self.punctuation_regex = QRegularExpression(r'[{}[\]:,]')

    def highlightBlock(self, text):
        # Highlight JSON keywords (true, false, null)
        self.highlight_pattern(text, self.keyword_regex, self.keywordFormat)
        
        # Highlight property names (strings followed by colon)
        self.highlight_pattern(text, self.property_regex, self.propertyFormat)
        
        # Highlight string values (but not property names)
        self.highlight_strings(text)
        
        # Highlight numbers
        self.highlight_pattern(text, self.number_regex, self.numberFormat)
        
        # Highlight punctuation
        self.highlight_pattern(text, self.punctuation_regex, self.punctuationFormat)

    def highlight_pattern(self, text, expression, fmt):
        """Helper method to highlight text matching a regex pattern"""
        it = expression.globalMatch(text)
        while it.hasNext():
            match = it.next()
            self.setFormat(match.capturedStart(), match.capturedLength(), fmt)

    def highlight_strings(self, text):
        """Highlight string values, avoiding property names"""
        it = self.string_regex.globalMatch(text)
        while it.hasNext():
            match = it.next()
            start = match.capturedStart()
            length = match.capturedLength()
            
            # Check if this string is followed by a colon (making it a property name)
            # If so, skip it as it will be handled by property highlighting
            remainder = text[start + length:].lstrip()
            if not remainder.startswith(':'):
                self.setFormat(start, length, self.stringFormat)
