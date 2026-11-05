

from PySide6.QtCore import QRegularExpression
from PySide6.QtGui import QColor, QSyntaxHighlighter, QTextCharFormat


class PythonHighlighter(QSyntaxHighlighter):
    associated_extensions = ['py']
    
    def __init__(self, parent=None, workflow_settings=None):
        super().__init__(parent)

        # --- formats (kept your colors) ---
        self.keywordFormat = QTextCharFormat()
        self.keywordFormat.setForeground(QColor('#c78953'))

        self.blueKeywordFormat = QTextCharFormat()
        self.blueKeywordFormat.setForeground(QColor('#438BB9'))

        self.purpleKeywordFormat = QTextCharFormat()
        self.purpleKeywordFormat.setForeground(QColor('#9B859D'))

        self.pinkKeywordFormat = QTextCharFormat()
        self.pinkKeywordFormat.setForeground(QColor('#FF6B81'))

        self.stringFormat = QTextCharFormat()
        self.stringFormat.setForeground(QColor('#6aab73'))

        self.commentFormat = QTextCharFormat()
        self.commentFormat.setForeground(QColor('#808080'))

        self.decoratorFormat = QTextCharFormat()
        self.decoratorFormat.setForeground(QColor('#AA6D91'))

        self.parameterFormat = QTextCharFormat()
        self.parameterFormat.setForeground(QColor('#B94343'))

        # --- keywords (same as you had) ---
        self.keywords = [
            'and', 'as', 'async', 'await', 'assert', 'break', 'class', 'continue', 'def', 'del',
            'elif', 'else', 'except', 'finally', 'for', 'from', 'global', 'if',
            'import', 'in', 'is', 'lambda', 'nonlocal', 'not', 'or', 'pass',
            'raise', 'return', 'try', 'while', 'with', 'yield', 'True', 'False', 'None',
        ]
        self.blue_keywords = [
            'get_os_environ',
            'print', 'input', 'int', 'str', 'float', 'list', 'dict', 'tuple', 'set', 'bool', 'len',
            'range', 'enumerate', 'zip', 'map', 'filter', 'reduce', 'sorted', 'sum', 'min', 'max',
            'abs', 'round', 'random', 'randint', 'choice', 'sample', 'shuffle', 'seed',
            'time', 'sleep', 'datetime', 'timedelta', 'date', 'time', 'strftime', 'strptime',
            're', 'search', 'match', 'findall', 'sub', 'split', 'compile',
        ]
        self.purple_keywords = ['self', 'cls', 'super']
        self.pink_keywords = [
            '__init__', '__str__', '__repr__', '__len__', '__getitem__', '__setitem__',
            '__delitem__', '__iter__', '__next__', '__contains__',
        ]

        self.keyword_rules = [
            (QRegularExpression(
                r'\b(' + '|'.join(QRegularExpression.escape(k) for k in words) + r')\b'
            ), fmt)
            for words, fmt in (
                (self.keywords, self.keywordFormat),
                (self.blue_keywords, self.blueKeywordFormat),
                (self.purple_keywords, self.purpleKeywordFormat),
                (self.pink_keywords, self.pinkKeywordFormat),
            )
        ]

        # inline single-line string regexes (tolerant)
        self.single_quote = QRegularExpression(r"'([^'\\]|\\.)*(')?")
        self.double_quote = QRegularExpression(r'"([^"\\]|\\.)*(")?')

        # comment / decorator / parameter regexes
        self.comment = QRegularExpression(r'#.*')
        self.decorator = QRegularExpression(r'@\w+(\.\w+)*')
        self.parameter = QRegularExpression(r'\b\w+(?=\s*=(?!=)\s*[^,\)]*(?:[,\)]|$))')

        # triple-quote delimiters as plain strings (we'll handle them across blocks)
        self.tri_single = "'''"
        self.tri_double = '"""'

        # Block states: use distinct non-zero integers for each triple-quote type
        self.STATE_IN_TRIPLE_DOUBLE = 1
        self.STATE_IN_TRIPLE_SINGLE = 2

    def highlightBlock(self, text):
        # --- keywords ---
        for expression, fmt in self.keyword_rules:
            it = expression.globalMatch(text)
            while it.hasNext():
                m = it.next()
                self.setFormat(m.capturedStart(), m.capturedLength(), fmt)

        # decorators, inline comments, parameters
        self.match_decorator(text, self.decorator, self.decoratorFormat)
        self.match_inline_comment(text, self.comment, self.commentFormat)
        self.match_parameter(text, self.parameter, self.parameterFormat)

        # single-line strings
        self.match_inline_string(text, self.single_quote, self.stringFormat)
        self.match_inline_string(text, self.double_quote, self.stringFormat)

        # multiline triple-quoted strings (must be done with block state)
        # handle triple-double first and triple-single next
        self.match_multiline(text, self.tri_double, self.stringFormat, self.STATE_IN_TRIPLE_DOUBLE)
        self.match_multiline(text, self.tri_single, self.stringFormat, self.STATE_IN_TRIPLE_SINGLE)

    def match_multiline(self, text: str, delimiter: str, fmt: QTextCharFormat, in_state: int):
        start = 0

        # if previous block left us inside the same triple-quote, continue searching for end
        if self.previousBlockState() == in_state:
            end_index = text.find(delimiter)
            if end_index == -1:
                # whole block belongs to string
                self.setFormat(0, len(text), fmt)
                self.setCurrentBlockState(in_state)
                return
            else:
                # highlight from start of block through the delimiter
                self.setFormat(0, end_index + len(delimiter), fmt)
                start = end_index + len(delimiter)
                self.setCurrentBlockState(0)  # closed in this block

        # search for new starting delimiters in the remainder of the block
        start_index = text.find(delimiter, start)
        while start_index != -1:
            # find end delimiter after the start
            end_index = text.find(delimiter, start_index + len(delimiter))
            if end_index == -1:
                # no end in this block -> highlight to end and set state
                prefix_len = 0
                if start_index >= 1 and text[start_index - 1].lower() in 'rubf':
                    prefix_len = 1
                    if start_index >= 2 and text[start_index - 2].lower() in 'rubf':
                        prefix_len = 2
                prefix_start = max(0, start_index - prefix_len)
                self.setFormat(prefix_start, len(text) - prefix_start, fmt)
                self.setCurrentBlockState(in_state)
                break
            else:
                # highlight from optional prefix through the end delimiter
                prefix_len = 0
                if start_index >= 1 and text[start_index - 1].lower() in 'rubf':
                    prefix_len = 1
                    if start_index >= 2 and text[start_index - 2].lower() in 'rubf':
                        prefix_len = 2
                prefix_start = max(0, start_index - prefix_len)
                length = end_index + len(delimiter) - prefix_start
                self.setFormat(prefix_start, length, fmt)
                # continue searching after the end delimiter
                start_index = text.find(delimiter, end_index + len(delimiter))

    def match_inline_string(self, text, expression, fmt):
        it = expression.globalMatch(text)
        while it.hasNext():
            m = it.next()
            if m.capturedLength() > 0:
                self.setFormat(m.capturedStart(), m.capturedLength(), fmt)

    def match_inline_comment(self, text, expression, fmt):
        it = expression.globalMatch(text)
        while it.hasNext():
            m = it.next()
            # primitive heuristic to ensure '#' is not inside a string in the same line
            pos = m.capturedStart()
            in_string = False
            i = 0
            while i < pos:
                ch = text[i]
                if ch in ('"', "'"):
                    # if the quote is not escaped, toggle in_string and skip potential triple-quote detection
                    if i == 0 or text[i - 1] != '\\':
                        # check for triple quotes
                        if text[i:i+3] in ('"""', "'''"):
                            # jump over the triple quote
                            i += 3
                            if in_string:
                                in_string = False
                            else:
                                in_string = True
                            continue
                        in_string = not in_string
                i += 1
            if not in_string:
                self.setFormat(m.capturedStart(), m.capturedLength(), fmt)

    def match_decorator(self, text, expression, fmt):
        it = expression.globalMatch(text)
        while it.hasNext():
            m = it.next()
            self.setFormat(m.capturedStart(), m.capturedLength(), fmt)

    def match_parameter(self, text, expression, fmt):
        it = expression.globalMatch(text)
        while it.hasNext():
            m = it.next()
            start = m.capturedStart()
            length = m.capturedLength()
            # ensure this is inside parens and not a def parameter list
            open_paren = text.rfind('(', 0, start)
            if open_paren != -1 and not text[:open_paren].strip().endswith('def'):
                if text.count(')', 0, start) < text.count('(', 0, start):
                    self.setFormat(start, length, fmt)
