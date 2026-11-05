import re

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QComboBox, QCompleter, QLineEdit, QPushButton, QWidget)

from gui.gui_utils.layouts import CHBoxLayout, CVBoxLayout
from gui.widgets.config_widget import ConfigWidget
from utils.helpers import set_module_type

# operator: (SQL condition with {col}, value conversion or None if the
# operator takes no value)
OPERATORS = {
    'contains': ("{col} LIKE ? ESCAPE '\\'",
                 lambda v: f'%{escape_like(v)}%'),
    'does not contain': ("({col} IS NULL OR {col} NOT LIKE ? ESCAPE '\\')",
                         lambda v: f'%{escape_like(v)}%'),
    'equals': ('{col} = ? COLLATE NOCASE', str),
    '=': ('{col} = ?', float),
    '<': ('{col} < ?', float),
    '≤': ('{col} <= ?', float),
    '>': ('{col} > ?', float),
    '≥': ('{col} >= ?', float),
    'is empty': ("({col} IS NULL OR {col} = '')", None),
    'is not empty': ("{col} != ''", None),
}
TYPE_OPERATORS = {
    'text': ('contains', 'does not contain', 'equals', 'is empty',
             'is not empty'),
    'number': ('=', '<', '≤', '>', '≥', 'is empty', 'is not empty'),
}


def filter_conditions(filters, columns):
    """Build WHERE conditions from a FilterBuilder's filters.

    Parameters
    ----------
    filters : list[dict]
        Each with ``column``, ``op`` and ``value``. Filters on unknown
        columns, or missing a usable value, are skipped.
    columns : dict[str, str]
        The filterable columns and their type, ``'text'`` or
        ``'number'``; guards the column names put into the SQL.

    Returns
    -------
    tuple[list[str], list]
        (conditions to AND together, their parameters)
    """
    conditions, params = [], []
    for f in filters:
        column, op, value = f.get('column'), f.get('op'), f.get('value', '')
        if column not in columns or op not in OPERATORS:
            continue
        template, convert = OPERATORS[op]
        if convert is not None:
            if not value.strip():
                continue
            try:
                params.append(convert(value.strip()))
            except ValueError:
                continue
        conditions.append(template.format(col=f'"{column}"'))
    return conditions, params


def escape_like(text):
    return re.sub(r'([\\%_])', r'\\\1', text)


def column_spec(spec):
    """A column is a type, ``'text'`` or ``'number'``, or a dict that
    may limit its ``ops`` and give value ``choices``."""
    return {'type': spec} if isinstance(spec, str) else spec


@set_module_type('Widgets')
class FilterBuilder(ConfigWidget):
    """Rows of ``[column] [operator] [value]`` filters, ANDed together.

    Set ``columns`` to ``{name: 'text' | 'number'}`` before ``load()``;
    a column can instead be a dict with ``type``, ``ops`` and
    ``choices``, see ``column_spec``.
    The config is ``{'filters': [{'column', 'op', 'value'}, ...]}``;
    pass it to ``filter_conditions`` for SQL.
    """

    changed = Signal()

    def __init__(self, parent, columns=None):
        super().__init__(parent=parent)
        self.columns = columns or {}
        self.rows = []
        self.rows_layout = CVBoxLayout()
        add_button = QPushButton('+ Filter')
        add_button.clicked.connect(lambda: self.add_row())
        self.layout = CVBoxLayout(self)
        self.layout.addLayout(self.rows_layout)
        self.layout.addWidget(add_button, alignment=Qt.AlignLeft)

    def load(self):
        for row in self.rows:
            row.deleteLater()
        self.rows = []
        for f in self.config.get('filters', []):
            if f.get('column') in self.columns:
                self.add_row(f)

    def get_config(self):
        return {'filters': [row.get_filter() for row in self.rows]}

    def add_row(self, f=None):
        row = FilterRow(self, f or {})
        self.rows.append(row)
        self.rows_layout.addWidget(row)
        if f is None:
            self.changed.emit()

    def remove_row(self, row):
        self.rows.remove(row)
        row.deleteLater()
        self.changed.emit()


class FilterRow(QWidget):
    def __init__(self, builder, f):
        super().__init__()
        self.builder = builder
        self.column = QComboBox()
        self.column.setEditable(True)
        self.column.setInsertPolicy(QComboBox.NoInsert)
        self.column.addItems(list(builder.columns))
        self.column.completer().setFilterMode(Qt.MatchContains)
        self.column.completer().setCompletionMode(QCompleter.PopupCompletion)
        self.op = QComboBox()
        self.value = QLineEdit()
        self.choice = QComboBox()
        remove_button = QPushButton('×')
        remove_button.clicked.connect(lambda: builder.remove_row(self))

        self.column.setCurrentText(f.get('column', ''))
        self.refresh_ops()
        self.op.setCurrentText(f.get('op', ''))
        self.value.setText(f.get('value', ''))
        self.refresh_value()
        self.choice.setCurrentText(f.get('value', ''))

        self.column.currentTextChanged.connect(self.column_changed)
        self.op.currentTextChanged.connect(self.op_changed)
        self.value.textChanged.connect(lambda: builder.changed.emit())
        self.choice.currentTextChanged.connect(
            lambda: builder.changed.emit())

        self.layout = CHBoxLayout(self)
        self.layout.addWidget(self.column, stretch=2)
        self.layout.addWidget(self.op, stretch=1)
        self.layout.addWidget(self.value, stretch=2)
        self.layout.addWidget(self.choice, stretch=2)
        self.layout.addWidget(remove_button)

    def get_filter(self):
        return {'column': self.column.currentText(),
                'op': self.op.currentText(),
                'value': (self.choice.currentText() if self.choices()
                          else self.value.text())}

    def spec(self):
        return column_spec(
            self.builder.columns.get(self.column.currentText(), 'text'))

    def choices(self):
        return self.spec().get('choices', [])

    def refresh_ops(self):
        spec = self.spec()
        ops = tuple(spec.get('ops')
                    or TYPE_OPERATORS[spec.get('type', 'text')])
        if tuple(self.op.itemText(i) for i in range(self.op.count())) == ops:
            return
        self.op.blockSignals(True)
        self.op.clear()
        self.op.addItems(ops)
        self.op.blockSignals(False)

    def refresh_value(self):
        takes_value = OPERATORS[self.op.currentText()][1] is not None
        choices = self.choices()
        if [self.choice.itemText(i)
                for i in range(self.choice.count())] != choices:
            self.choice.blockSignals(True)
            self.choice.clear()
            self.choice.addItems(choices)
            self.choice.blockSignals(False)
        self.value.setVisible(takes_value and not choices)
        self.choice.setVisible(takes_value and bool(choices))

    def column_changed(self):
        self.refresh_ops()
        self.refresh_value()
        self.builder.changed.emit()

    def op_changed(self):
        self.refresh_value()
        self.builder.changed.emit()
