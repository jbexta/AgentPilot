from PySide6.QtCore import QSize
from PySide6.QtGui import QColor, QPalette, QTextDocument, QTextOption, Qt
from PySide6.QtWidgets import QStyledItemDelegate, QTextEdit

from gui.style import ACCENT_COLOR_1, TEXT_COLOR


class WrappingDelegate(QStyledItemDelegate):
    def __init__(self, wrap_columns, parent=None):
        super().__init__(parent=parent)
        self.wrap_columns = wrap_columns

    def createEditor(self, parent, option, index):
        if index.column() in self.wrap_columns:
            editor = QTextEdit(parent)
            editor.setWordWrapMode(QTextOption.WordWrap)
            return editor
        else:
            return super().createEditor(parent, option, index)

    def setEditorData(self, editor, index):
        if index.column() in self.wrap_columns:
            text = index.model().data(index, Qt.EditRole)
            editor.setText(text)
        else:
            super().setEditorData(editor, index)

    def setModelData(self, editor, model, index):
        if index.column() in self.wrap_columns:
            model.setData(index, editor.toPlainText(), Qt.EditRole)
        else:
            super().setModelData(editor, model, index)

    def paint(self, painter, option, index):
        if index.column() in self.wrap_columns:
            text = index.data()

            # Set the text color for the painter
            textColor = QColor(TEXT_COLOR)  #  option.palette.color(QPalette.Text)
            painter.setPen(textColor)  # Ensure we use a QColor object
            # Apply the default palette text color too
            option.palette.setColor(QPalette.Text, textColor)

            painter.save()

            textDocument = QTextDocument()
            textDocument.setDefaultFont(option.font)
            textDocument.setPlainText(text)
            textDocument.setTextWidth(option.rect.width())
            painter.translate(option.rect.x(), option.rect.y())
            textDocument.drawContents(painter)
            painter.restore()
        else:
            super().paint(painter, option, index)

    def sizeHint(self, option, index):  # V1
        if index.column() in self.wrap_columns:
            textDocument = QTextDocument()
            textDocument.setDefaultFont(option.font)
            textDocument.setPlainText(index.data())
            textDocument.setTextWidth(option.rect.width())
            return QSize(option.rect.width(), int(textDocument.size().height()))
        else:
            return super().sizeHint(option, index)


class BakedItemDelegate(QStyledItemDelegate):
    """Custom delegate to handle styling for baked items in tree widgets"""

    def paint(self, painter, option, index):
        # Check if this item is baked by looking for our custom data
        item_data = index.data(Qt.UserRole)
        is_baked = False
        if isinstance(item_data, dict) and item_data.get('id'):
            # Check if the tree widget has baked_ids stored
            tree_widget = option.widget
            if hasattr(tree_widget, '_baked_ids'):
                is_baked = item_data.get('id') in tree_widget._baked_ids

        is_disabled = False
        if isinstance(item_data, dict) and item_data.get('id'):
            if hasattr(tree_widget, '_disabled_ids'):
                is_disabled = item_data.get('id') in tree_widget._disabled_ids

        has_notify = False
        if isinstance(item_data, dict) and item_data.get('id'):
            if hasattr(tree_widget, '_notify_ids'):
                has_notify = item_data.get('id') in tree_widget._notify_ids

        if is_disabled:
            painter.save()
            painter.setOpacity(0.4)
            super().paint(painter, option, index)
            painter.restore()
        elif is_baked:
            super().paint(painter, option, index)

            # add a dot of accent color to the left of the text with thickness 3
            accent_color = QColor(ACCENT_COLOR_1)
            painter.setPen(accent_color)
            painter.setBrush(accent_color)
            radius = 2
            center_x = option.rect.left() - 1  # (15 if has_children else 6)
            center_y = option.rect.center().y()
            painter.drawEllipse(center_x - radius, center_y - radius, radius * 2, radius * 2)
        else:
            # Use default painting for non-baked items
            super().paint(painter, option, index)

        if has_notify:
            # notification bubble on the right edge of the row's name column
            accent_color = QColor(ACCENT_COLOR_1)
            painter.save()
            painter.setPen(accent_color)
            painter.setBrush(accent_color)
            radius = 4
            center_x = option.rect.right() - 10
            center_y = option.rect.center().y()
            painter.drawEllipse(center_x - radius, center_y - radius, radius * 2, radius * 2)
            painter.restore()


class NonSelectableItemDelegate(QStyledItemDelegate):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

    def paint(self, painter, option, index):
        is_header = index.data(Qt.UserRole) == 'header'
        if is_header:
            option.font.setBold(True)
        super().paint(painter, option, index)

    def editorEvent(self, event, model, option, index):
        if index.data(Qt.UserRole) == 'header':
            # Disable selection/editing of header items by consuming the event
            return True
        return super().editorEvent(event, model, option, index)

    def sizeHint(self, option, index):
        # Call the base implementation to get the default size hint
        return super().sizeHint(option, index)


class AlignDelegate(QStyledItemDelegate):
    def paint(self, painter, option, index):
        option.displayAlignment = Qt.AlignCenter
        super(AlignDelegate, self).paint(painter, option, index)
