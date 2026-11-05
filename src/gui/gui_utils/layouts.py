from PySide6.QtCore import QPoint, QRect, QSize
from PySide6.QtGui import Qt
from PySide6.QtWidgets import QHBoxLayout, QLayout, QVBoxLayout


class CVBoxLayout(QVBoxLayout):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setContentsMargins(0, 0, 0, 0)
        self.setSpacing(0)


class CHBoxLayout(QHBoxLayout):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setContentsMargins(0, 0, 0, 0)
        self.setSpacing(0)


class FlowLayout(QLayout):
    """Lays items out left to right, wrapping onto a new row when the
    next one doesn't fit."""
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setContentsMargins(0, 0, 0, 0)
        self.setSpacing(0)
        self.items = []

    def addItem(self, item):
        self.items.append(item)

    def count(self):
        return len(self.items)

    def itemAt(self, index):
        return self.items[index] if 0 <= index < len(self.items) else None

    def takeAt(self, index):
        return self.items.pop(index) if 0 <= index < len(self.items) else None

    def expandingDirections(self):
        return Qt.Orientation(0)

    def hasHeightForWidth(self):
        return True

    def heightForWidth(self, width):
        return self.arrange(QRect(0, 0, width, 0), move=False)

    def setGeometry(self, rect):
        super().setGeometry(rect)
        self.arrange(rect, move=True)

    def sizeHint(self):
        hints = [item.sizeHint() for item in self.items if not item.isEmpty()]
        width = sum(hint.width() for hint in hints)
        width += self.spacing() * max(0, len(hints) - 1)
        height = max((hint.height() for hint in hints), default=0)
        return QSize(width, height)

    def minimumSize(self):
        size = QSize()
        for item in self.items:
            size = size.expandedTo(item.minimumSize())
        return size

    def arrange(self, rect, move):
        """Place the items within rect, returning the height they take."""
        x, y, row_height = rect.x(), rect.y(), 0
        for item in self.items:
            if item.isEmpty():
                continue
            hint = item.sizeHint()
            if x > rect.x() and x + hint.width() > rect.right() + 1:
                x, y = rect.x(), y + row_height + self.spacing()
                row_height = 0
            if move:
                item.setGeometry(QRect(QPoint(x, y), hint))
            x += hint.width() + self.spacing()
            row_height = max(row_height, hint.height())
        return y + row_height - rect.y()
