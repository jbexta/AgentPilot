import asyncio
import inspect
from functools import partial

from PySide6.QtWidgets import *
from PySide6.QtCore import Signal, QSize, QRegularExpression, QEvent, Slot, QRunnable
from PySide6.QtGui import QPixmap, QPalette, QColor, QIcon, QFont, Qt, QStandardItem, QPainter, \
    QPainterPath, QFontDatabase, QSyntaxHighlighter, QTextCharFormat, QTextOption, QTextDocument, QKeyEvent, \
    QTextCursor, QCursor, QFontMetrics

from src.gui.windows.text_editor import TextEditorWindow
from src.utils import sql, resources_rc
from src.utils.helpers import block_pin_mode, path_to_pixmap, display_messagebox, block_signals, apply_alpha_to_hex
from src.utils.filesystem import unsimplify_path
from PySide6.QtWidgets import QAbstractItemView


def find_main_widget(widget):
    if hasattr(widget, 'main'):
        return widget.main
    if not hasattr(widget, 'parent'):
        # object_name = widget.objectName()
        # print(object_name)
        # ggg = widget.__ne__
        # print(ggg)
        return None
    # if is the main widget
    return find_main_widget(widget.parent)


def find_breadcrumb_widget(widget):
    if hasattr(widget, 'breadcrumb_widget'):
        return widget.breadcrumb_widget
    if not hasattr(widget, 'parent'):
        return None
    return find_breadcrumb_widget(widget.parent)


def find_attribute(widget, attribute):
    if hasattr(widget, attribute):
        return getattr(widget, attribute)
    if not hasattr(widget, 'parent'):
        return None
    return find_attribute(widget.parent, attribute)


# def TitleBarWidget(QWidget):
#     def __init__(self, parent, title):
#         super().__init__(parent)
#         self.layout = CVBoxLayout(self)
#         self.label = QLabel(title)
#         self.layout.addWidget(self.label)
#         self.layout.addStretch(1)
#         self.layout.setContentsMargins(0, 0, 0, 0)
#         self.layout.setSpacing(0)
#         self.setFixedHeight(30)
#         self.setStyleSheet("background-color: #f0f0f0; border-bottom: 1px solid #ddd;")
#
#     def set_title(self, title):
#         self.label.setText(title)


class BreadcrumbWidget(QWidget):
    def __init__(self, parent, root_title=None):
        super().__init__(parent=parent)
        from src.gui.config import CHBoxLayout

        # self.setFixedHeight(75)
        self.parent = parent
        self.main = find_main_widget(self)
        self.root_title = root_title

        self.layout = QVBoxLayout(self)
        self.layout.setContentsMargins(0, 0, 0, 0)
        self.layout.setSpacing(0)

        self.back_button = IconButton(parent=self, icon_path=':/resources/icon-back.png', size=40)
        self.back_button.setStyleSheet("border-top-left-radius: 22px;")
        self.back_button.clicked.connect(self.go_back)

        # print('#431')

        # self.title_container = QWidget()
        # self.title_container.setStyleSheet("background-color:
        self.title_layout = CHBoxLayout()  # self.title_container)
        self.title_layout.setSpacing(20)
        self.title_layout.setContentsMargins(0, 0, 10, 0)
        self.title_layout.addWidget(self.back_button)

        # self.node_title = node_title
        # if title != '':
        self.label = QLabel(root_title)
        self.font = QFont()
        self.font.setPointSize(15)
        self.label.setFont(self.font)
        self.label.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.title_layout.addWidget(self.label)
        self.title_layout.addStretch(1)

        # self.title_container.setLayout(self.title_layout)

        self.layout.addLayout(self.title_layout)

    def set_nodes(self, nodes):
        # set text to each node joined by ' > '
        nodes.insert(0, self.root_title)
        nodes = [n for n in nodes if n is not None]
        self.label.setText('   >   '.join(reversed(nodes)))

    def go_back(self):
        history = self.main.page_history
        if len(history) > 1:
            last_page_index = history[-2]
            self.main.page_history.pop()
            self.main.sidebar.button_group.button(last_page_index).click()
        else:
            # self.main.main_menu.content.setCurrentWidget(self.main.page_chat)
            self.main.page_chat.ensure_visible()


class ContentPage(QWidget):
    def __init__(self, main, title=''):
        super().__init__(parent=main)
        from src.gui.config import CHBoxLayout

        self.main = main
        self.layout = QVBoxLayout(self)
        self.layout.setContentsMargins(0, 0, 0, 0)
        self.layout.setSpacing(0)

        self.back_button = IconButton(parent=self, icon_path=':/resources/icon-back.png', size=40)
        self.back_button.setStyleSheet("border-top-left-radius: 22px;")
        self.back_button.clicked.connect(self.go_back)

        # print('#431')

        self.title_container = QWidget()
        # self.title_container.setStyleSheet("background-color:
        self.title_layout = CHBoxLayout(self.title_container)
        self.title_layout.setSpacing(20)
        self.title_layout.setContentsMargins(0, 0, 10, 0)
        self.title_layout.addWidget(self.back_button)

        if title != '':
            self.label = QLabel(title)
            self.font = QFont()
            self.font.setPointSize(15)
            self.label.setFont(self.font)
            self.label.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)
            self.title_layout.addWidget(self.label)
            self.title_layout.addStretch(1)

        # self.title_container.setLayout(self.title_layout)

        self.layout.addWidget(self.title_container)

    def go_back(self):
        history = self.main.page_history
        if len(history) > 1:
            last_page_index = history[-2]
            self.main.page_history.pop()
            self.main.sidebar.button_group.button(last_page_index).click()
        else:
            # self.main.main_menu.content.setCurrentWidget(self.main.page_chat)
            self.main.page_chat.ensure_visible()


class IconButton(QPushButton):
    def __init__(
            self,
            parent,
            icon_path,
            size=25,
            tooltip=None,
            icon_size_percent=0.75,
            colorize=True,
            opacity=1.0,
            text=None,
            checkable=False,
    ):
        super().__init__(parent=parent)
        self.parent = parent
        self.colorize = colorize
        self.opacity = opacity

        self.icon = None
        self.pixmap = QPixmap(icon_path)
        self.setIconPixmap(self.pixmap)

        character_width = 8
        width = size + (len(text) * character_width if text else 0)
        icon_size = int(size * icon_size_percent)
        self.setFixedSize(width, size)
        self.setIconSize(QSize(icon_size, icon_size))

        self.setAutoExclusive(False)  # To disable visual selection

        if tooltip:
            self.setToolTip(tooltip)

        if text:
            self.setText(text)

        if checkable:
            self.setCheckable(True)

    def setIconPath(self, icon_path):
        self.pixmap = QPixmap(icon_path)
        self.setIconPixmap(self.pixmap)

    def setIconPixmap(self, pixmap=None):
        if not pixmap:
            pixmap = self.pixmap
        else:
            self.pixmap = pixmap

        if self.colorize:
            pixmap = colorize_pixmap(pixmap, opacity=self.opacity)

        self.icon = QIcon(pixmap)
        self.setIcon(self.icon)


class ToggleButton(IconButton):
    def __init__(self, **kwargs):
        self.icon_path_checked = kwargs.pop('icon_path_checked', None)
        self.tooltip_when_checked = kwargs.pop('tooltip_when_checked', None)
        super().__init__(**kwargs)
        self.setCheckable(True)
        self.icon_path = kwargs.get('icon_path', None)
        self.ttip = kwargs.get('tooltip', '')
        self.clicked.connect(self.on_click)

    def on_click(self):
        self.refresh_icon()

    def setChecked(self, state):
        super().setChecked(state)
        self.refresh_icon()

    def refresh_icon(self):
        is_checked = self.isChecked()
        if self.icon_path_checked:
            self.setIconPixmap(QPixmap(self.icon_path_checked if is_checked else self.icon_path))
        if self.tooltip_when_checked:
            self.setToolTip(self.tooltip_when_checked if is_checked else self.ttip)


# class CTextEdit(QTextEdit):
#     def __init__(self, *args, **kwargs):
#         super().__init__(*args, **kwargs)


class CTextEdit(QTextEdit):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.highlighter_field = kwargs.get('highlighter_field', None)
        self.text_editor = None
        self.setTabStopDistance(40)

        self.expand_button = IconButton(parent=self, icon_path=':/resources/icon-expand.png', size=22)
        self.expand_button.setStyleSheet("background-color: transparent;")
        self.expand_button.clicked.connect(self.on_button_clicked)
        self.expand_button.hide()
        self.updateButtonPosition()

        # # Update button position when the text edit is resized
        # self.textChanged.connect(self.on_edited)

    # class EmptyHighlighter(QSyntaxHighlighter):
    #     def highlightBlock(self, text):
    #         pass

    # def refresh_highlighter(self):
    #     from src.gui.config import get_widget_value
    #     if not self.highlighter_field:
    #         return
    #     hl = getattr(self.parent, self.highlighter_field, None)
    #     if not hl:
    #         return
    #
    #     with block_signals(self.parent):
    #         lang = get_widget_value(hl).lower()
    #         if lang == 'python':
    #             self.highlighter = PythonHighlighter(self.document())
    #         else:
    #             # if getattr(self, 'highlighter', None):
    #             #     del self.highlighter
    #             self.highlighter = self.EmptyHighlighter(self.document())

    def keyPressEvent(self, event: QKeyEvent):
        if event.key() == Qt.Key_Backtab:
            self.dedent()
            event.accept()
        elif event.key() == Qt.Key_Tab:
            if event.modifiers() & Qt.ShiftModifier:
                self.dedent()
            else:
                self.indent()
            event.ignore()
        else:
            super().keyPressEvent(event)

    def indent(self):
        cursor = self.textCursor()
        start_block = self.document().findBlock(cursor.selectionStart())
        end_block = self.document().findBlock(cursor.selectionEnd())

        cursor.beginEditBlock()
        while True:
            cursor.setPosition(start_block.position())
            cursor.insertText("\t")
            if start_block == end_block:
                break
            start_block = start_block.next()
        cursor.endEditBlock()

    def dedent(self):
        cursor = self.textCursor()
        start_block = self.document().findBlock(cursor.selectionStart())
        end_block = self.document().findBlock(cursor.selectionEnd())

        cursor.beginEditBlock()
        while True:
            cursor.setPosition(start_block.position())
            cursor.movePosition(QTextCursor.NextCharacter, QTextCursor.KeepAnchor)
            if cursor.selectedText() == "\t":
                cursor.removeSelectedText()
            if start_block == end_block:
                break
            start_block = start_block.next()
        cursor.endEditBlock()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self.updateButtonPosition()

    # def on_edited(self):  # CAUSE OF SEGFAULT
    #     all_windows = QApplication.topLevelWidgets()
    #     for window in all_windows:
    #         if isinstance(window, TextEditorWindow) and window.parent == self:
    #             with block_signals(window.editor):
    #                 window.editor.setPlainText(self.toPlainText())

    def updateButtonPosition(self):
        # Calculate the position for the button
        button_width = self.expand_button.width()
        button_height = self.expand_button.height()
        edit_rect = self.contentsRect()

        # Position the button at the bottom-right corner
        x = edit_rect.right() - button_width - 2
        y = edit_rect.bottom() - button_height - 2
        self.expand_button.move(x, y)
        # self.enhance_button.move(x - button_width - 1, y)

    # Example slot for button click
    def on_button_clicked(self):
        from src.gui.windows.text_editor import TextEditorWindow
        # check if the window is already open where parent is self
        all_windows = QApplication.topLevelWidgets()
        for window in all_windows:
            if isinstance(window, TextEditorWindow) and window.parent == self:
                window.activateWindow()
                return
        self.text_editor = TextEditorWindow(self)  # this is a QMainWindow
        self.text_editor.show()
        self.text_editor.activateWindow()

    def insertFromMimeData(self, source):
        # Insert plain text from the MIME data
        if source.hasText():
            self.insertPlainText(source.text())
        else:
            super().insertFromMimeData(source)

    def dropEvent(self, event):
        # Handle text drop event
        mime_data = event.mimeData()
        if mime_data.hasText():
            cursor = self.cursorForPosition(event.position().toPoint())
            cursor.insertText(mime_data.text())
            event.acceptProposedAction()
        else:
            super().dropEvent(event)

    def enterEvent(self, event):
        self.expand_button.show()
        # self.enhance_button.show()
        super().enterEvent(event)

    def leaveEvent(self, event):
        self.expand_button.hide()
        # self.enhance_button.hide()
        super().leaveEvent(event)

    # class EnhanceButton(IconButton):
    #     def __init__(self, parent):
    #         super().__init__(parent=parent, icon_path=':/resources/icon-wand.png', size=22)
    #         self.main = find_main_widget(self)
    #         self.clicked.connect(self.on_clicked)
    #         self.enhancing_text = ''
    #         self.metaprompt_blocks = {}
    #
    #     @Slot(str)
    #     def on_new_enhanced_sentence(self, chunk):
    #         current_text = self.parent.toPlainText()
    #         # self.main.message_text.setPlainText(current_text + chunk)
    #         # self.main.message_text.keyPressEvent(QKeyEvent(QEvent.KeyPress, Qt.Key.Key_End, Qt.KeyboardModifier.NoModifier))
    #         # self.main.message_text.verticalScrollBar().setValue(self.main.message_text.verticalScrollBar().maximum())
    #
    #     @Slot(str)
    #     def on_enhancement_error(self, error_message):
    #         self.parent.setPlainText(self.enhancing_text)
    #         self.enhancing_text = ''
    #         display_messagebox(
    #             icon=QMessageBox.Warning,
    #             title="Enhancement error",
    #             text=f"An error occurred while enhancing the system message: {error_message}",
    #             buttons=QMessageBox.Ok
    #         )
    #
    #     def on_clicked(self):
    #         self.metaprompt_blocks = {k: v for k, v in self.main.system.blocks.to_dict().items() if v.get('block_type', '') == 'Metaprompt'}
    #         if len(self.metaprompt_blocks) > 1:
    #             # show a context menu with all available metaprompt blocks
    #             menu = QMenu(self)
    #             for name in self.metaprompt_blocks.keys():
    #                 action = menu.addAction(name)
    #                 action.triggered.connect(partial(self.on_metaprompt_selected, name))
    #
    #             menu.exec_(QCursor.pos())
    #
    #         elif len(self.metaprompt_blocks) == 0:
    #             display_messagebox(
    #                 icon=QMessageBox.Warning,
    #                 title="No Metaprompt blocks found",
    #                 text="No Metaprompt blocks found, create them in the blocks page.",
    #                 buttons=QMessageBox.Ok
    #             )
    #         else:
    #             messagebox_input = self.parent.toPlainText().strip()
    #             if messagebox_input == '':
    #                 display_messagebox(
    #                     icon=QMessageBox.Warning,
    #                     title="No message found",
    #                     text="Type a message in the message box to enhance.",
    #                     buttons=QMessageBox.Ok
    #                 )
    #                 return
    #             metablock_name = list(self.metaprompt_blocks.keys())[0]
    #             self.run_metaprompt(metablock_name)
    #
    #     def on_metaprompt_selected(self, metablock_name):
    #         self.run_metaprompt(metablock_name)
    #
    #     def run_metaprompt(self, metablock_name):
    #         metablock_text = self.metaprompt_blocks[metablock_name].get('data', '')
    #         metablock_model = self.metaprompt_blocks[metablock_name].get('prompt_model', '')
    #         messagebox_input = self.main.message_text.toPlainText().strip()
    #
    #         if '{{INPUT}}' not in metablock_text:
    #             ret_val = display_messagebox(
    #                 icon=QMessageBox.Warning,
    #                 title="No {{INPUT}} found",
    #                 text="The Metaprompt block should contain '{{INPUT}}' to be able to enhance the text.",
    #                 buttons=QMessageBox.Ok | QMessageBox.Cancel
    #             )
    #             if ret_val != QMessageBox.Ok:
    #                 return
    #
    #         metablock_text = metablock_text.replace('{{INPUT}}', messagebox_input)
    #
    #         self.enhancing_text = self.parent.toPlainText()
    #         self.parent.clear()
    #         enhance_runnable = self.EnhancementRunnable(self, metablock_model, metablock_text)
    #         self.main.page_chat.threadpool.start(enhance_runnable)
    #
    #     class EnhancementRunnable(QRunnable):
    #         def __init__(self, parent, metablock_model, metablock_text):
    #             super().__init__()
    #             # self.parent = parent
    #             self.main = parent.main
    #             self.metablock_model = metablock_model
    #             self.metablock_text = metablock_text
    #
    #         def run(self):
    #             try:
    #                 asyncio.run(self.enhance_text(self.metablock_model, self.metablock_text))
    #             except Exception as e:
    #                 self.main.enhancement_error_occurred.emit(str(e))
    #
    #         async def enhance_text(self, model, metablock_text):
    #             stream = await self.main.system.providers.run_model(
    #                 model_obj=model,
    #                 messages=[{'role': 'user', 'content': metablock_text}],
    #             )
    #
    #             async for resp in stream:
    #                 delta = resp.choices[0].get('delta', {})
    #                 if not delta:
    #                     continue
    #                 content = delta.get('content', '')
    #                 self.main.new_enhanced_sentence_signal.emit(content)


def colorize_pixmap(pixmap, opacity=1.0):
    from src.gui.style import TEXT_COLOR
    colored_pixmap = QPixmap(pixmap.size())
    colored_pixmap.fill(Qt.transparent)

    painter = QPainter(colored_pixmap)
    painter.setCompositionMode(QPainter.CompositionMode_Source)
    painter.drawPixmap(0, 0, pixmap)
    painter.setOpacity(opacity)
    painter.setCompositionMode(QPainter.CompositionMode_SourceIn)

    painter.fillRect(colored_pixmap.rect(), TEXT_COLOR)
    painter.end()

    return colored_pixmap


class BaseComboBox(QComboBox):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.current_pin_state = None
        # self.setItemDelegate(NonSelectableItemDelegate(self))
        # self.setFixedWidth(150)
        self.setFixedHeight(25)

    def showPopup(self):
        from src.gui import main
        self.current_pin_state = main.PIN_MODE
        main.PIN_MODE = True
        super().showPopup()

    def hidePopup(self):
        from src.gui import main
        super().hidePopup()
        if self.current_pin_state is None:
            return
        main.PIN_MODE = self.current_pin_state

    def set_key(self, key):
        index = self.findData(key)
        self.setCurrentIndex(index)
        if index == -1:
            # Get last item todo dirty
            last_item = self.model().item(self.model().rowCount() - 1)
            last_key = last_item.data(Qt.UserRole)
            if last_key != key:
                # Create a new item with the missing model key and set its color to red, and set the data to the model key
                item = QStandardItem(key)
                item.setData(key, Qt.UserRole)
                item.setForeground(QColor('red'))
                self.model().appendRow(item)
                self.setCurrentIndex(self.model().rowCount() - 1)


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
            from src.gui.style import TEXT_COLOR
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


class ComboBoxDelegate(QStyledItemDelegate):
    def __init__(self, parent, combo_type, default=None):
        super(ComboBoxDelegate, self).__init__(parent)
        self.combo_type = combo_type
        self.default = default

    def createEditor(self, parent, option, index):
        if isinstance(self.combo_type, tuple):
            combo = QComboBox(parent)
            combo.addItems(self.combo_type)
        elif self.combo_type == 'EnvironmentComboBox':
            combo = EnvironmentComboBox(parent)
        else:
            raise NotImplementedError('Combo type not implemented')

        if self.default:
            index = combo.findText(self.default)
            combo.setCurrentIndex(index)

        combo.currentIndexChanged.connect(self.commitAndCloseEditor)
        return combo

    def setEditorData(self, editor, index):
        value = index.model().data(index, Qt.EditRole)
        editor.setCurrentText(value)
        editor.showPopup()

    def setModelData(self, editor, model, index):
        model.setData(index, editor.currentText(), Qt.EditRole)

    def commitAndCloseEditor(self):
        editor = self.sender()
        self.commitData.emit(editor)
        self.closeEditor.emit(editor)

    def eventFilter(self, editor, event):
        if event.type() == QEvent.MouseButtonPress:
            editor.showPopup()
        return super(ComboBoxDelegate, self).eventFilter(editor, event)


class BaseTreeWidget(QTreeWidget):
    def __init__(self, parent, row_height=18, *args, **kwargs):
        super().__init__(*args, **kwargs)
        from src.gui.style import TEXT_COLOR
        self.parent = parent
        self.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.setSelectionMode(QAbstractItemView.SingleSelection)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)

        self.apply_stylesheet()

        header = self.header()
        header.setDefaultAlignment(Qt.AlignLeft)
        header.setStretchLastSection(False)
        header.setDefaultSectionSize(row_height)

        # Enable drag and drop
        self.setDragEnabled(True)
        self.setAcceptDrops(True)
        self.setDropIndicatorShown(True)

        # Set the drag and drop mode to internal moves only
        self.setDragDropMode(QTreeWidget.InternalMove)
        # header.setSectionResizeMode(1, QHeaderView.Stretch)
        self.header().sectionResized.connect(self.update_tooltips)

    # Connect signal to handle resizing of the headers, and call the function once initially

    def build_columns_from_schema(self, schema):
        self.setColumnCount(len(schema))
        # add columns to tree from schema list
        for i, header_dict in enumerate(schema):
            column_type = header_dict.get('type', str)
            column_visible = header_dict.get('visible', True)
            column_width = header_dict.get('width', None)
            column_stretch = header_dict.get('stretch', None)
            wrap_text = header_dict.get('wrap_text', False)
            # hide_header = header_dict.get('hide_header', False)

            is_combo_column = isinstance(column_type, tuple) or column_type == 'EnvironmentComboBox'
            if is_combo_column:
                combo_delegate = ComboBoxDelegate(self, column_type)
                self.setItemDelegateForColumn(i, combo_delegate)

            if column_width:
                self.setColumnWidth(i, column_width)
            if column_stretch:
                self.header().setSectionResizeMode(i, QHeaderView.Stretch)
            if wrap_text:
                self.setItemDelegateForColumn(i, WrappingDelegate([i], self))
            self.setColumnHidden(i, not column_visible)

        headers = ['' if header_dict.get('hide_header') else header_dict['text']
                   for header_dict in schema]
        self.setHeaderLabels(headers)

    def load(self, data, folders_data, **kwargs):
        # self.tree.setUpdatesEnabled(False)
        folder_key = kwargs.get('folder_key', None)
        select_id = kwargs.get('select_id', None)
        silent_select_id = kwargs.get('silent_select_id', None)  # todo dirty
        init_select = kwargs.get('init_select', False)
        readonly = kwargs.get('readonly', False)
        schema = kwargs.get('schema', [])
        append = kwargs.get('append', False)
        group_folders = kwargs.get('group_folders', False)

        with block_signals(self):
            # selected_index = self.currentIndex().row()
            # is_refresh = self.topLevelItemCount() > 0
            expanded_folders = self.get_expanded_folder_ids()
            if not append:
                self.clear()
                # Load folders
                folder_items_mapping = {None: self}
                while folders_data:
                    for folder_id, name, parent_id, folder_type, order in list(folders_data):
                        if parent_id in folder_items_mapping:
                            parent_item = folder_items_mapping[parent_id]
                            folder_item = QTreeWidgetItem(parent_item, [str(name), str(folder_id)])
                            folder_item.setData(0, Qt.UserRole, 'folder')
                            folder_pixmap = colorize_pixmap(QPixmap(':/resources/icon-folder.png'))
                            folder_item.setIcon(0, QIcon(folder_pixmap))
                            folder_items_mapping[folder_id] = folder_item
                            folders_data.remove((folder_id, name, parent_id, folder_type, order))

            # Load items
            for row_data in data:
                parent_item = self
                if folder_key is not None:
                    folder_id = row_data[-1]
                    parent_item = folder_items_mapping.get(folder_id) if folder_id else self

                if len(row_data) > len(schema):
                    row_data = row_data[:-1]  # remove folder_id

                item = QTreeWidgetItem(parent_item, [str(v) for v in row_data])

                if not readonly:
                    item.setFlags(item.flags() | Qt.ItemIsEditable)
                else:
                    item.setFlags(item.flags() & ~Qt.ItemIsEditable)

                for i in range(len(row_data)):
                    col_schema = schema[i]
                    cell_type = col_schema.get('type', None)
                    if cell_type == QPushButton:
                        btn_func = col_schema.get('func', None)
                        btn_partial = partial(btn_func, row_data)
                        btn_icon_path = col_schema.get('icon', '')
                        pixmap = colorize_pixmap(QPixmap(btn_icon_path))
                        self.setItemIconButtonColumn(item, i, pixmap, btn_partial)

                    image_key = col_schema.get('image_key', None)
                    if image_key:
                        image_index = [i for i, d in enumerate(schema) if d.get('key', None) == image_key][0]
                        image_paths = row_data[image_index] or ''
                        image_paths_list = image_paths.split('//##//##//')
                        pixmap = path_to_pixmap(image_paths_list, diameter=25)
                        item.setIcon(i, QIcon(pixmap))

                    is_encrypted = col_schema.get('encrypt', False)
                    if is_encrypted:
                        pass
                        # todo

            if len(expanded_folders) > 0:
                # Restore expanded folders
                for folder_id in expanded_folders:
                    folder_item = folder_items_mapping.get(int(folder_id))
                    if folder_item:
                        folder_item.setExpanded(True)
            else:
                # Expand all top-level folders
                for i in range(self.topLevelItemCount()):
                    item = self.topLevelItem(i)
                    if item.data(0, Qt.UserRole) == 'folder':
                        item.setExpanded(True)

            if group_folders:
                for i in range(self.topLevelItemCount()):
                    item = self.topLevelItem(i)
                    if item is None:
                        continue
                    self.group_nested_folders(item)
                    self.delete_empty_folders(item)

            self.update_tooltips()
            if silent_select_id:
                self.select_item_by_id(silent_select_id)
            # # if selected_index > -1:
            # #     self.setCurrentIndex(self.model().index(selected_index, 0))

        if init_select and self.topLevelItemCount() > 0:
            if select_id:
                self.select_item_by_id(select_id)
            elif not silent_select_id:
                self.setCurrentItem(self.topLevelItem(0))
                item = self.currentItem()
                self.scrollToItem(item)
        else:
            if hasattr(self.parent, 'toggle_config_widget'):
                self.parent.toggle_config_widget(False)

    def reload_selected_item(self, data, schema):
        # data is same as in `load`
        current_id = self.get_selected_item_id()
        if current_id is None:
            return

        for row_data in data:
            row_id = row_data[1]
            if row_id != current_id:
                continue

            if len(row_data) > len(schema):
                row_data = row_data[:-1]  # remove folder_id

            item = self.currentItem()
            # set values for each column in item
            for i in range(len(row_data)):
                item.setText(i, str(row_data[i]))

            # for i in range(len(row_data)):
            #     col_schema = schema[i]
            #     cell_type = col_schema.get('type', None)
            #     if cell_type == QPushButton:
            #         btn_func = col_schema.get('func', None)
            #         btn_partial = partial(btn_func, row_data)
            #         btn_icon_path = col_schema.get('icon', '')
            #         pixmap = colorize_pixmap(QPixmap(btn_icon_path))
            #         self.setItemIconButtonColumn(item, i, pixmap, btn_partial)
            #
            #     image_key = col_schema.get('image_key', None)
            #     if image_key:
            #         image_index = [i for i, d in enumerate(schema) if d.get('key', None) == image_key][0]
            #         image_paths = row_data[image_index] or ''
            #         image_paths_list = image_paths.split('//##//##//')
            #         pixmap = path_to_pixmap(image_paths_list, diameter=25)
            #         item.setIcon(i, QIcon(pixmap))

            break


    # Function to group nested folders in the tree recursively
    def group_nested_folders(self, item):
        # Keep grouping while the item has exactly one folder child
        while item.childCount() == 1 and item.child(0).data(0, Qt.UserRole) == 'folder':
            child = item.takeChild(0)

            # Update the text to the current item's text plus the child's text
            item.setText(0, item.text(0) + '/' + child.text(0))

            # Add child's children to the current item
            while child.childCount() > 0:
                item.addChild(child.takeChild(0))

        # Recur into each child item (in case there are other nested structures)
        for i in range(item.childCount()):
            self.group_nested_folders(item.child(i))

    def delete_empty_folders(self, item):
        # First, recursively check and delete empty children
        for i in reversed(range(item.childCount())):  # Reversed because we might remove items
            child = item.child(i)
            if child.data(0, Qt.UserRole) == 'folder':
                self.delete_empty_folders(child)

        # Now check the current item itself
        if item.childCount() == 0 and item.data(0, Qt.UserRole) == 'folder':
            parent = item.parent()
            if parent:
                parent.removeChild(item)
            else:
                # If there's no parent, it means this is a top-level item
                index = self.indexOfTopLevelItem(item)
                if index != -1:
                    self.takeTopLevelItem(index)

    def get_column_value(self, column):
        item = self.currentItem()
        if not item:
            return None
        return item.text(column)
        # schema_item = self.parent.schema[column]
        # if schema_item['type'] == 'EnvironmentComboBox':
        #     # return the combobox data
        #     print(str(item))
        #     combo_widget = self.itemWidget(item, column)
        #     return combo_widget.currentText()
        #     # return item.data(column, Qt.UserRole)  # todo

    # def delete_empty_folders(self, item):
    #     if item.childCount() == 0: # and item.data(0, Qt.UserRole) == 'folder':
    #         parent = item.parent()
    #         if parent:
    #             parent.removeChild(item)
    #             return
    #
    #     for i in range(item.childCount()):
    #         child = item.child(i)
    #         if child.data(0, Qt.UserRole) == 'folder':
    #             self.delete_empty_folders(child)

    def apply_stylesheet(self):
        from src.gui.style import TEXT_COLOR
        palette = self.palette()
        # h_col = apply_alpha_to_hex(TEXT_COLOR, 0.05)
        palette.setColor(QPalette.Highlight, apply_alpha_to_hex(TEXT_COLOR, 0.05))
        palette.setColor(QPalette.HighlightedText, apply_alpha_to_hex(TEXT_COLOR, 0.80))
        palette.setColor(QPalette.Text, QColor(TEXT_COLOR))
        self.setPalette(palette)

    def update_tooltips(self):
        font_metrics = QFontMetrics(self.font())

        def update_item_tooltips(self, item):
            for col in range(self.columnCount()):
                text = item.text(col)
                text_width = font_metrics.horizontalAdvance(text) + 45  # Adding some padding
                column_width = self.columnWidth(col)
                if column_width == 0:
                    continue
                if text_width > column_width:
                    item.setToolTip(col, text)
                else:
                    item.setToolTip(col, "")  # Remove tooltip if not cut off

            # Recursively update tooltips for child items
            for i in range(item.childCount()):
                update_item_tooltips(self, item.child(i))

        # Update tooltips for all top-level items and their children
        for i in range(self.topLevelItemCount()):
            update_item_tooltips(self, self.topLevelItem(i))

    def get_selected_item_id(self):
        item = self.currentItem()
        if not item:
            return None
        tag = item.data(0, Qt.UserRole)
        if tag == 'folder':
            return None
        return int(item.text(1))

    def get_selected_folder_id(self):
        item = self.currentItem()
        if not item:
            return None
        tag = item.data(0, Qt.UserRole)
        if tag != 'folder':
            return None
        return int(item.text(1))

    def select_item_by_id(self, id):
        for i in range(self.topLevelItemCount()):
            item = self.topLevelItem(i)
            if item.text(1) == str(id):
                # Set item to selected
                self.setCurrentItem(item)
                # item.setSelected(True)
                self.scrollToItem(item)
                break

    def get_selected_tag(self):
        item = self.currentItem()
        if not item:
            return None
        tag = item.data(0, Qt.UserRole)
        return tag

    def dragMoveEvent(self, event):
        target_item = self.itemAt(event.pos())
        can_drop = (target_item.data(0, Qt.UserRole) == 'folder') if target_item else False

        # distance to edge of the item
        distance = 0
        if target_item:
            rect = self.visualItemRect(target_item)
            bottom_distance = rect.bottom() - event.pos().y()
            top_distance = event.pos().y() - rect.top()
            distance = min(bottom_distance, top_distance)

        # only allow dropping on folders and reordering in between items
        if can_drop or distance < 4:
            super().dragMoveEvent(event)
        else:
            event.ignore()

    def dropEvent(self, event):
        dragging_item = self.currentItem()
        target_item = self.itemAt(event.pos())
        dragging_type = dragging_item.data(0, Qt.UserRole)
        target_type = target_item.data(0, Qt.UserRole) if target_item else None
        dragging_id = dragging_item.text(1)

        can_drop = (target_type == 'folder') if target_item else False

        # distance to edge of the item
        distance = 0
        if target_item:
            rect = self.visualItemRect(target_item)
            distance = min(event.pos().y() - rect.top(), rect.bottom() - event.pos().y())

        # only allow dropping on folders and reordering in between items
        if distance < 4:
            # REORDER AND/OR MOVE
            target_item_parent = target_item.parent() if target_item else None
            target_item_parent_id = target_item_parent.text(1) if target_item_parent else None

            dragging_item_parent = dragging_item.parent() if dragging_item else None
            dragging_item_parent_id = dragging_item_parent.text(1) if dragging_item_parent else None

            if target_item_parent_id == dragging_item_parent_id:
                # display message box
                display_messagebox(
                    icon=QMessageBox.Warning,
                    title='Not implemented yet',
                    text='Reordering is not implemented yet'
                )
                event.ignore()
                return

            if dragging_type == 'folder':
                self.update_folder_parent(dragging_id, target_item_parent_id)
            else:
                self.update_item_folder(dragging_id, target_item_parent_id)

        elif can_drop:
            folder_id = target_item.text(1)
            print('MOVE TO FOLDER ' + folder_id)
            if dragging_type == 'folder':
                self.update_folder_parent(dragging_id, folder_id)
            else:
                self.update_item_folder(dragging_id, folder_id)
        else:
            # remove the visual line when event ignore
            # self.update()
            event.ignore()

    def setItemIconButtonColumn(self, item, column, icon, func):  # partial(self.on_chat_btn_clicked, row_data)
        btn_chat = QPushButton('')
        btn_chat.setIcon(icon)
        btn_chat.setIconSize(QSize(25, 25))
        # btn_chat.setStyleSheet("QPushButton { background-color: transparent; }"
        #                        "QPushButton:hover { background-color: rgba(255, 255, 255, 0.1); }")
        btn_chat.clicked.connect(func)
        self.setItemWidget(item, column, btn_chat)

    def get_expanded_folder_ids(self):
        expanded_ids = []

        def recurse_children(item):
            for i in range(item.childCount()):
                child = item.child(i)
                id = child.text(1)
                if child.isExpanded():
                    expanded_ids.append(id)
                recurse_children(child)

        recurse_children(self.invisibleRootItem())
        return expanded_ids

    def update_folder_parent(self, dragging_folder_id, to_folder_id):
        sql.execute(f"UPDATE folders SET parent_id = ? WHERE id = ?", (to_folder_id, dragging_folder_id))
        self.parent.load()
        # expand the folder
        for i in range(self.topLevelItemCount()):
            item = self.topLevelItem(i)
            if item.text(1) == to_folder_id:
                item.setExpanded(True)
                break

    def update_item_folder(self, dragging_item_id, to_folder_id):
        sql.execute(f"UPDATE `{self.parent.db_table}` SET folder_id = ? WHERE id = ?", (to_folder_id, dragging_item_id))
        self.parent.load()
        # expand the folder
        for i in range(self.topLevelItemCount()):
            item = self.topLevelItem(i)
            if item.text(1) == to_folder_id:
                item.setExpanded(True)
                break

    def mouseReleaseEvent(self, event):
        super().mouseReleaseEvent(event)
        if event.button() == Qt.RightButton and hasattr(self.parent, 'show_context_menu'):
            self.parent.show_context_menu()
            return

        item = self.itemAt(event.pos())
        if item:
            col = self.columnAt(event.pos().x())
            # Check if the delegate for this column is an instance of ComboBoxDelegate
            delegate = self.itemDelegateForColumn(col)
            if isinstance(delegate, ComboBoxDelegate):
                # force the item into edit mode
                self.editItem(item, col)

    def keyPressEvent(self, event):
        # delete button press
        super().keyPressEvent(event)
        if event.key() == Qt.Key_Delete and hasattr(self.parent, 'delete_item'):
            self.parent.delete_item()


class CircularImageLabel(QLabel):
    clicked = Signal()
    avatarChanged = Signal()

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        from src.gui.style import TEXT_COLOR
        self.avatar_path = None
        self.setAlignment(Qt.AlignCenter)
        self.setCursor(Qt.PointingHandCursor)
        self.setFixedSize(100, 100)
        self.setStyleSheet(
            f"border: 1px dashed {TEXT_COLOR}; border-radius: 50px;")  # A custom style for the empty label
        self.clicked.connect(self.change_avatar)

    def setImagePath(self, path):
        self.avatar_path = unsimplify_path(path)
        pixmap = path_to_pixmap(self.avatar_path, diameter=100)
        self.setPixmap(pixmap)
        self.avatarChanged.emit()

    def change_avatar(self):
        with block_pin_mode():
            fd = QFileDialog()
            fd.setStyleSheet("QFileDialog { color: black; }")  # Modify text color

            filename, _ = fd.getOpenFileName(None, "Choose Avatar", "",
                                                        "Images (*.png *.jpeg *.jpg *.bmp *.gif *.webp)", options=QFileDialog.Options())

        if filename:
            self.setImagePath(filename)

    def mousePressEvent(self, event):
        super().mousePressEvent(event)
        if event.button() == Qt.LeftButton:
            self.clicked.emit()

    def setPixmap(self, pixmap):
        super().setPixmap(pixmap.scaled(
            self.width(), self.height(),
            Qt.KeepAspectRatioByExpanding,
            Qt.SmoothTransformation
        ))

    def paintEvent(self, event):
        # Override paintEvent to draw a circular image
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)

        path = QPainterPath()
        path.addEllipse(0, 0, self.width(), self.height())
        painter.setClipPath(path)
        painter.drawPixmap(0, 0, self.pixmap())
        painter.end()


class ColorPickerWidget(QPushButton):
    colorChanged = Signal(str)
    def __init__(self):
        super().__init__()
        from src.gui.style import TEXT_COLOR
        self.color = None
        self.setFixedSize(24, 24)
        self.setProperty('class', 'color-picker')
        self.setStyleSheet(f"background-color: white; border: 1px solid {apply_alpha_to_hex(TEXT_COLOR, 0.20)};")
        self.clicked.connect(self.pick_color)

    def pick_color(self):
        from src.gui.style import TEXT_COLOR
        current_color = self.color if self.color else Qt.white
        color_dialog = QColorDialog()
        # color_dialog.setOption(QColorDialog.ShowAlphaChannel, True)
        with block_pin_mode():
            # show alpha channel
            color = color_dialog.getColor(current_color, parent=None, options=QColorDialog.ShowAlphaChannel)
            # alpha = color.alpha()
            # cname = color.name(QColor.HexArgb)
            # pass

        if color.isValid():
            self.color = color
            self.setStyleSheet(f"background-color: {color.name(QColor.HexArgb)}; border: 1px solid {apply_alpha_to_hex(TEXT_COLOR, 0.20)};")
            self.colorChanged.emit(color.name(QColor.HexArgb))

    def setColor(self, hex_color):
        from src.gui.style import TEXT_COLOR
        color = QColor(hex_color)
        if color.isValid():
            self.color = color
            self.setStyleSheet(f"background-color: {color.name(QColor.HexArgb)}; border: 1px solid {apply_alpha_to_hex(TEXT_COLOR, 0.20)};")

    def get_color(self):
        hex_argb = self.color.name(QColor.HexArgb)
        # if alpha is 'ff' return without alpha, alpha is first 2 characters
        ret = hex_argb if hex_argb[:2] == 'ff' else hex_argb[2:]
        return self.color.name(QColor.HexArgb) if self.color and self.color.isValid() else None


class PluginComboBox(BaseComboBox):
    def __init__(self, plugin_type, centered=False, none_text="Choose Plugin"):
        super().__init__()  # parent=parent)
        self.none_text = none_text
        self.plugin_type = plugin_type
        self.centered = centered
        # self.setFixedWidth(175)

        if centered:
            self.setItemDelegate(AlignDelegate(self))
            self.setStyleSheet(
                "QComboBox::drop-down {border-width: 0px;} QComboBox::down-arrow {image: url(noimg); border-width: 0px;}")

        self.load()

    def load(self):
        from src.system.plugins import ALL_PLUGINS

        self.clear()
        self.addItem(self.none_text, "")

        for plugin in ALL_PLUGINS[self.plugin_type]:
            if inspect.isclass(plugin):
                self.addItem(plugin.__name__.replace('_', ' '), plugin.__name__)
            else:
                self.addItem(plugin, plugin)

    def paintEvent(self, event):
        if not self.centered:
            super().paintEvent(event)
            return

        painter = QStylePainter(self)
        option = QStyleOptionComboBox()

        # Init style options with the current state of this widget
        self.initStyleOption(option)

        # Draw the combo box without the current text (removes the default left-aligned text)
        painter.setPen(self.palette().color(QPalette.Text))
        painter.drawComplexControl(QStyle.CC_ComboBox, option)

        # Manually draw the text, centered
        text_rect = self.style().subControlRect(QStyle.CC_ComboBox, option, QStyle.SC_ComboBoxEditField)
        text_rect.adjust(18, 0, 0, 0)  # left, top, right, bottom

        current_text = self.currentText()
        painter.drawText(text_rect, Qt.AlignCenter, current_text)


class APIComboBox(BaseComboBox):
    def __init__(self, *args, **kwargs):
        self.first_item = kwargs.pop('first_item', None)
        self.with_model_kinds = kwargs.pop('with_model_kinds', None)  # None means show all
        super().__init__(*args, **kwargs)

        self.load()

    def load(self):
        with block_signals(self):
            self.clear()
            if self.with_model_kinds:
                apis = sql.get_results(f"""
                    SELECT DISTINCT a.name, a.id
                    FROM apis a
                    JOIN models m
                        ON a.id = m.api_id
                    WHERE m.kind IN ({', '.join(['?' for _ in self.with_model_kinds])})
                    ORDER BY a.name
                """, self.with_model_kinds)
            else:
                apis = sql.get_results("SELECT name, id FROM apis ORDER BY name")

            if self.first_item:
                self.addItem(self.first_item, 0)
            for api in apis:
                self.addItem(api[0], api[1])


class EnvironmentComboBox(BaseComboBox):
    def __init__(self, *args, **kwargs):
        from src.gui.config import CHBoxLayout
        self.first_item = kwargs.pop('first_item', None)
        super().__init__(*args, **kwargs)
        # set to expanding width
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        # self.options_btn = self.GotoButton(
        #     parent=self,
        #     icon_path=':/resources/icon-settings-solid.png',
        #     tooltip='Options',
        #     size=20,
        # )
        # self.layout = CHBoxLayout(self)
        # self.layout.addWidget(self.options_btn)
        # self.options_btn.move(-20, 0)

        self.load()

    def load(self):
        with block_signals(self):
            self.clear()
            models = sql.get_results("SELECT name, id FROM sandboxes ORDER BY name")
            # if self.first_item:
            #     self.addItem(self.first_item, 0)
            for model in models:
                self.addItem(model[0], model[1])

    # class GotoButton(IconButton):
    #     def __init__(self, parent, *args, **kwargs):
    #         super().__init__(parent=parent, *args, **kwargs)
    #         self.clicked.connect(self.show_options)
    #         self.hide()
    #         # self.config_widget = CustomDropdown(self)
    #
    #     def showEvent(self, event):
    #         super().showEvent(event)
    #         self.parent.options_btn.move(self.parent.width() - 40, 0)
    #
    #     def show_options(self):
    #         if self.parent.config_widget.isVisible():
    #             self.parent.config_widget.hide()
    #         else:
    #             self.parent.config_widget.show()


class VenvComboBox(BaseComboBox):
    def __init__(self, parent, *args, **kwargs):
        from src.gui.config import CHBoxLayout
        self.parent = parent
        self.first_item = kwargs.pop('first_item', None)
        super().__init__(*args, **kwargs)
        self.current_key = None
        self.currentIndexChanged.connect(self.on_current_index_changed)

        self.btn_delete = self.DeleteButton(
            parent=self,
            icon_path=':/resources/icon-minus.png',
            tooltip='Delete Venv',
            size=20,
        )
        self.layout = CHBoxLayout(self)
        self.layout.addWidget(self.btn_delete)
        self.btn_delete.move(-20, 0)

        self.load()

    class DeleteButton(IconButton):
        def __init__(self, parent, *args, **kwargs):
            super().__init__(parent=parent, *args, **kwargs)
            self.clicked.connect(self.delete_venv)
            self.hide()

        def showEvent(self, event):
            super().showEvent(event)
            self.parent.btn_delete.move(self.parent.width() - 40, 0)

        def delete_venv(self):
            ok = display_messagebox(
                icon=QMessageBox.Warning,
                title='Delete Virtual Environment',
                text=f'Are you sure you want to delete the venv `{self.parent.current_key}`?',
                buttons=QMessageBox.Yes | QMessageBox.No
            )
            if ok != QMessageBox.Yes:
                return

            from src.system.base import manager
            manager.venvs.delete_venv(self.parent.current_key)
            self.parent.load()
            self.parent.reset_index()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self.btn_delete.move(self.width() - 40, 0)

    # only show options button when the mouse is over the combobox
    def enterEvent(self, event):
        self.btn_delete.show()
        super().enterEvent(event)

    def leaveEvent(self, event):
        self.btn_delete.hide()
        super().leaveEvent(event)

    def mouseMoveEvent(self, event):
        self.btn_delete.show()
        super().mouseMoveEvent(event)

    def load(self):
        from src.system.base import manager
        with block_signals(self):
            self.clear()
            venvs = manager.venvs.venvs  # a dict of name: Venv
            # if self.first_item:
            #     self.addItem(self.first_item, 0)
            for venv_name, venv in venvs.items():
                item_user_data = f"{venv_name} ({venv.path})"
                self.addItem(item_user_data, venv_name)
            # add create new venv option
            self.addItem('< Create New Venv >', '<NEW>')

    def set_key(self, key):
        super().set_key(key)
        self.current_key = key

    def on_current_index_changed(self):
        from src.system.base import manager
        key = self.itemData(self.currentIndex())
        if key == '<NEW>':
            dlg_title, dlg_prompt = ('Enter Name', 'Enter a name for the new virtual environment')
            text, ok = QInputDialog.getText(self, dlg_title, dlg_prompt)
            if not ok or not text:
                self.reset_index()
                return
            if text == 'default':
                display_messagebox(
                    icon=QMessageBox.Warning,
                    title='Invalid Name',
                    text='The name `default` is reserved and cannot be used.'
                )
                self.reset_index()
                return
            manager.venvs.create_venv(text)
            self.load()
            self.set_key(text)
        else:
            self.current_key = key

        # if hasattr(self.parent, 'reload_venv'):
        #     self.parent.reload_venv()

    def reset_index(self):
        current_key_index = self.findData(self.current_key)
        has_items = self.count() - 1 > 0  # -1 for <new> item
        if current_key_index >= 0 and has_items:
            self.setCurrentIndex(current_key_index)
        else:
            self.set_key(self.current_key)

    # # def currentIndexChanged(self, index):
    # #     if self.currentData() == 'NEW':
    # #         self.temp_indx_before_new = index
    # #         self.createNewVenv()
    # #     else:
    # #         super().currentIndexChanged(index)
    #
    # # override to detect when NEW is selected, and keeping track of the old key
    # def setCurrentIndex(self, index):
    #     if self.itemData(index) == 'NEW':
    #         self.temp_indx_before_new = index
    #         # self.createNewVenv()
    #         pass
    #     else:
    #         super().setCurrentIndex(index)



class RoleComboBox(BaseComboBox):
    def __init__(self, *args, **kwargs):
        self.first_item = kwargs.pop('first_item', None)
        super().__init__(*args, **kwargs)

        self.load()

    def load(self):
        self.clear()
        models = sql.get_results("SELECT name, id FROM roles")
        if self.first_item:
            self.addItem(self.first_item, 0)
        for model in models:
            self.addItem(model[0].title(), model[0])


class FontComboBox(BaseComboBox):
    class FontItemDelegate(QStyledItemDelegate):
        def paint(self, painter, option, index):
            font_name = index.data()

            self.font = option.font
            self.font.setFamily(font_name)
            self.font.setPointSize(12)

            painter.setFont(self.font)
            painter.drawText(option.rect, Qt.TextSingleLine, index.data())

    def __init__(self, *args, **kwargs):
        self.first_item = kwargs.pop('first_item', None)
        super().__init__(*args, **kwargs)

        self.addItem('')
        available_fonts = QFontDatabase.families()
        self.addItems(available_fonts)

        font_delegate = self.FontItemDelegate(self)
        self.setItemDelegate(font_delegate)


class LanguageComboBox(BaseComboBox):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        self.load()

    def load(self):
        self.clear()
        langs = [
            ('English', 'en'),
            # ('Russian', 'ru'),
            # ('Spanish', 'es'),
            # ('French', 'fr'),
            # ('German', 'de'),
            # ('Italian', 'it'),
            # ('Portuguese', 'pt'),
            # ('Chinese', 'zh'),
            # ('Japanese', 'ja'),
            # ('Korean', 'ko'),
            # ('Arabic', 'ar'),
            # ('Hindi', 'hi'),
        ]
        for lang in langs:
            self.addItem(lang[0], lang[1])


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


class ListDialog(QDialog):
    def __init__(self, parent, *args, **kwargs):
        super().__init__(parent=parent)
        self.parent = parent
        self.setWindowFlag(Qt.WindowMinimizeButtonHint, False)
        self.setWindowFlag(Qt.WindowMaximizeButtonHint, False)

        self.setWindowTitle(kwargs.get('title', ''))
        self.list_type = kwargs.get('list_type')
        self.callback = kwargs.get('callback', None)
        multiselect = kwargs.get('multiselect', False)

        layout = QVBoxLayout(self)
        self.listWidget = QListWidget()
        if multiselect:
            self.listWidget.setSelectionMode(QAbstractItemView.MultiSelection)
        layout.addWidget(self.listWidget)

        list_type_lower = self.list_type.lower()
        empty_config_str = "{}" if list_type_lower == "agent" else f"""{{"_TYPE": "{list_type_lower}"}}"""
        if self.list_type == 'AGENT' or self.list_type == 'USER':
            def_avatar = ':/resources/icon-agent-solid.png' if self.list_type == 'AGENT' else ':/resources/icon-user.png'
            col_name_list = ['name', 'id', 'avatar', 'config']
            empty_entity_label = 'Empty agent' if self.list_type == 'AGENT' else 'You'
            query = f"""
                SELECT name, id, avatar, config
                FROM (
                    SELECT '{empty_entity_label}' AS name, 0 AS id, '' AS avatar, '{empty_config_str}' AS config
                    UNION
                    SELECT
                        e.name,
                        e.id,
                        CASE
                            WHEN json_extract(config, '$._TYPE') = 'workflow' THEN
                                (
                                    SELECT GROUP_CONCAT(json_extract(m.value, '$.config."info.avatar_path"'), '//##//##//')
                                    FROM json_each(json_extract(e.config, '$.members')) m
                                    WHERE COALESCE(json_extract(m.value, '$.del'), 0) = 0
                                )
                            ELSE
                                COALESCE(json_extract(config, '$."info.avatar_path"'), '')
                        END AS avatar,
                        e.config
                    FROM entities e
                    WHERE kind = '{self.list_type}'
                )
                ORDER BY
                    CASE WHEN id = 0 THEN 0 ELSE 1 END,
                    id DESC"""
            pass
        elif self.list_type == 'TOOL':
            def_avatar = ':/resources/icon-tool.png'
            col_name_list = ['tool', 'id', 'avatar', 'config']
            query = f"""
                SELECT
                    name,
                    uuid as id,
                    '' as avatar,
                    '{empty_config_str}' as config
                FROM tools
                ORDER BY name"""
        else:
            raise NotImplementedError(f'List type {self.list_type} not implemented')

        data = sql.get_results(query)
        # for val_list in data:
        # zip colname and data into a dict
        # zipped_dict = [dict(zip(col_name_list, val_list)) for val_list in data]

        for i, val_list in enumerate(data):
            # id = row_data[0]
            row_data = {col_name_list[i]: val_list[i] for i in range(len(val_list))}
            name = val_list[0]
            icon = None
            if len(val_list) > 2:
                avatar_path = val_list[2].split('//##//##//') if val_list[2] else None
                pixmap = path_to_pixmap(avatar_path, def_avatar=def_avatar)
                icon = QIcon(pixmap) if avatar_path is not None else None

            item = QListWidgetItem()
            item.setText(name)
            item.setData(Qt.UserRole, row_data)

            if icon:
                item.setIcon(icon)

            self.listWidget.addItem(item)

        if self.callback:
            self.listWidget.itemDoubleClicked.connect(self.itemSelected)

    def open(self):
        with block_pin_mode():
            self.exec_()

    def itemSelected(self, item):
        self.callback(item)
        self.close()

    def keyPressEvent(self, event):
        super().keyPressEvent(event)
        if event.key() != Qt.Key_Return:
            return
        item = self.listWidget.currentItem()
        self.itemSelected(item)


class HelpIcon(QLabel):
    def __init__(self, parent, tooltip):
        super().__init__(parent=parent)
        self.parent = parent
        pixmap = colorize_pixmap(QPixmap(':/resources/icon-info.png'), opacity=0.5)
        pixmap = pixmap.scaled(12, 12, Qt.KeepAspectRatio, Qt.SmoothTransformation)
        self.setPixmap(pixmap)
        self.setToolTip(tooltip)


# class CustomTabBar(QTabBar):
#     def __init__(self, parent=None):
#         super().__init__(parent)
#
#     def setTabVisible(self, index, visible):
#         super().setTabVisible(index, visible)
#         if not visible:
#             # Set the tab width to 0 when it is hidden
#             self.setTabEnabled(index, False)
#             self.setStyleSheet(f"QTabBar::tab {{ width: 0px; height: 0px; }}")
#         else:
#             # Reset the tab size when it is shown again
#             self.setTabEnabled(index, True)
#             self.setStyleSheet("")  # Reset the stylesheet


class AlignDelegate(QStyledItemDelegate):
    def paint(self, painter, option, index):
        option.displayAlignment = Qt.AlignCenter
        super(AlignDelegate, self).paint(painter, option, index)


class PythonHighlighter(QSyntaxHighlighter):
    def __init__(self, parent=None):
        super().__init__(parent)

        self.keywordFormat = QTextCharFormat()
        self.keywordFormat.setForeground(QColor('#c78953'))
        # self.keywordFormat.setFontWeight(QTextCharFormat.Bold)

        self.blueKeywordFormat = QTextCharFormat()
        self.blueKeywordFormat.setForeground(QColor('#6ab0de'))

        self.stringFormat = QTextCharFormat()
        self.stringFormat.setForeground(QColor('#6aab73'))

        self.commentFormat = QTextCharFormat()
        self.commentFormat.setForeground(QColor('#808080'))  # Grey color for comments

        self.blue_keywords = [
            'get_os_environ',
        ]

        self.keywords = [
            'and', 'as', 'assert', 'break', 'class', 'continue', 'def', 'del',
            'elif', 'else', 'except', 'finally', 'for', 'from', 'global', 'if',
            'import', 'in', 'is', 'lambda', 'nonlocal', 'not', 'or', 'pass',
            'raise', 'return', 'try', 'while', 'with', 'yield'
        ]

        # Regular expressions for python's syntax
        self.tri_single_quote = QRegularExpression("f?'''([^'\\\\]|\\\\.|'{1,2}(?!'))*(''')?")
        self.tri_double_quote = QRegularExpression('f?"""([^"\\\\]|\\\\.|"{1,2}(?!"))*(""")?')
        self.single_quote = QRegularExpression(r"'([^'\\]|\\.)*(')?")
        self.double_quote = QRegularExpression(r'"([^"\\]|\\.)*(")?')
        self.comment = QRegularExpression(r'#.*')  # Regular expression for comments

    def highlightBlock(self, text):
        # String matching
        self.match_multiline(text, self.tri_single_quote, 1, self.stringFormat)
        self.match_multiline(text, self.tri_double_quote, 2, self.stringFormat)
        self.match_inline_string(text, self.single_quote, self.stringFormat)
        self.match_inline_string(text, self.double_quote, self.stringFormat)

        # Keyword matching
        for keyword in self.keywords:
            expression = QRegularExpression('\\b' + keyword + '\\b')
            match_iterator = expression.globalMatch(text)
            while match_iterator.hasNext():
                match = match_iterator.next()
                self.setFormat(match.capturedStart(), match.capturedLength(), self.keywordFormat)

        for keyword in self.blue_keywords:
            expression = QRegularExpression('\\b' + keyword + '\\b')
            match_iterator = expression.globalMatch(text)
            while match_iterator.hasNext():
                match = match_iterator.next()
                self.setFormat(match.capturedStart(), match.capturedLength(), self.blueKeywordFormat)

        # Comment matching
        self.match_inline_comment(text, self.comment, self.commentFormat)

    def match_multiline(self, text, expression, state, format):
        if self.previousBlockState() == state:
            start = 0
            length = len(text)
        else:
            start = -1
            length = 0

        # Look for the start of a multi-line string
        if start == 0:
            match = expression.match(text)
            if match.hasMatch():
                length = match.capturedLength()
                if match.captured(3):  # Closing quotes are found
                    self.setCurrentBlockState(0)
                else:
                    self.setCurrentBlockState(state)  # Continue to the next line
                self.setFormat(match.capturedStart(), length, format)
                start = match.capturedEnd()
        while start >= 0:
            match = expression.match(text, start)
            # We've got a match
            if match.hasMatch():
                # Multiline string
                length = match.capturedLength()
                if match.captured(3):  # Closing quotes are found
                    self.setCurrentBlockState(0)
                else:
                    self.setCurrentBlockState(state)  # The string is not closed
                # Apply the formatting and then look for the next possible match
                self.setFormat(match.capturedStart(), length, format)
                start = match.capturedEnd()
            else:
                # No further matches; if we are in a multi-line string, color the rest of the text
                if self.currentBlockState() == state:
                    self.setFormat(start, len(text) - start, format)
                break

    def match_inline_string(self, text, expression, format):
        match_iterator = expression.globalMatch(text)
        while match_iterator.hasNext():
            match = match_iterator.next()
            if match.capturedLength() > 0:
                if match.captured(1):
                    self.setFormat(match.capturedStart(), match.capturedLength(), format)

    def match_inline_comment(self, text, expression, format):
        match_iterator = expression.globalMatch(text)
        while match_iterator.hasNext():
            match = match_iterator.next()
            in_string = False
            for i in range(match.capturedStart()):  # Check if comment # is inside a string
                if text[i] in ['"', "'"]:
                    quote = text[i]
                    if i == 0 or text[i - 1] != '\\':  # Not escaped
                        if in_string:
                            if text[i + 1:i + 3] == quote * 2:  # Triple quote ends
                                in_string = False
                                i += 2
                            elif quote == text[i]:  # Single or double quote ends
                                in_string = False
                        else:
                            in_string = True
            if not in_string:
                self.setFormat(match.capturedStart(), match.capturedLength(), format)
# class PythonHighlighter(QSyntaxHighlighter):
#     def __init__(self, parent=None):
#         super().__init__(parent)
#
#         self.keywordFormat = QTextCharFormat()
#         self.keywordFormat.setForeground(QColor('#c78953'))
#         # self.keywordFormat.setFontWeight(QTextCharFormat.Bold)
#
#         self.stringFormat = QTextCharFormat()
#         self.stringFormat.setForeground(QColor('#6aab73'))
#
#         self.commentFormat = QTextCharFormat()
#         self.commentFormat.setForeground(QColor('grey'))
#
#         self.keywords = [
#             'and', 'as', 'assert', 'break', 'class', 'continue', 'def', 'del',
#             'elif', 'else', 'except', 'finally', 'for', 'from', 'global', 'if',
#             'import', 'in', 'is', 'lambda', 'nonlocal', 'not', 'or', 'pass',
#             'raise', 'return', 'try', 'while', 'with', 'yield'
#         ]
#
#         # Regular expressions for python's syntax
#         self.tri_single_quote = QRegularExpression("f?'''([^'\\\\]|\\\\.|'{1,2}(?!'))*(''')?")
#         self.tri_double_quote = QRegularExpression('f?"""([^"\\\\]|\\\\.|"{1,2}(?!"))*(""")?')
#         self.single_quote = QRegularExpression(r"'([^'\\]|\\.)*(')?")
#         self.double_quote = QRegularExpression(r'"([^"\\]|\\.)*(")?')
#         self.single_line_comment = QRegularExpression(r'#.*')
#
#     # def highlightBlock(self, text):
#     #     # Step 1: Highlight strings first
#     #     self.match_multiline(text, self.tri_single_quote, 1, self.stringFormat)
#     #     self.match_multiline(text, self.tri_double_quote, 2, self.stringFormat)
#     #     self.match_inline_string(text, self.single_quote, self.stringFormat)
#     #     self.match_inline_string(text, self.double_quote, self.stringFormat)
#     #
#     #     # Step 2: Highlight comments outside strings
#     #     self.highlight_comments(text)
#     #
#     #     # Step 3: Highlight keywords
#     #     self.highlight_keywords(text)
#     #
#     # def highlight_keywords(self, text):
#     #     # Keyword matching
#     #     for keyword in self.keywords:
#     #         expression = QRegularExpression('\\b' + keyword + '\\b')
#     #         match_iterator = expression.globalMatch(text)
#     #         while match_iterator.hasNext():
#     #             match = match_iterator.next()
#     #             self.setFormat(match.capturedStart(), match.capturedLength(), self.keywordFormat)
#     #
#     # def match_multiline(self, text, expression, state, format):
#     #     if self.previousBlockState() == state:
#     #         start = 0
#     #         length = len(text)
#     #     else:
#     #         start = -1
#     #         length = 0
#     #
#     #     if start == 0:
#     #         match = expression.match(text)
#     #         if match.hasMatch():
#     #             length = match.capturedLength()
#     #             if match.captured(3):  # Closing quotes are found
#     #                 self.setCurrentBlockState(0)
#     #             else:
#     #                 self.setCurrentBlockState(state)  # Continue to the next line
#     #             self.setFormat(match.capturedStart(), length, format)
#     #             start = match.capturedEnd()
#     #
#     #     while start >= 0:
#     #         match = expression.match(text, start)
#     #         if match.hasMatch():
#     #             length = match.capturedLength()
#     #             if match.captured(3):  # Closing quotes are found
#     #                 self.setCurrentBlockState(0)
#     #             else:
#     #                 self.setCurrentBlockState(state)  # The string is not closed
#     #             self.setFormat(match.capturedStart(), length, format)
#     #             start = match.capturedEnd()
#     #         else:
#     #             if self.currentBlockState() == state:
#     #                 self.setFormat(start, len(text) - start, format)
#     #             break
#     #
#     # def match_inline_string(self, text, expression, format):
#     #     match_iterator = expression.globalMatch(text)
#     #     while match_iterator.hasNext():
#     #         match = match_iterator.next()
#     #         if match.capturedLength() > 0:
#     #             if match.captured(1):
#     #                 self.setFormat(match.capturedStart(), match.capturedLength(), format)
#     #
#     # def highlight_comments(self, text):
#     #     match_iterator = self.single_line_comment.globalMatch(text)
#     #     while match_iterator.hasNext():
#     #         match = match_iterator.next()
#     #         start, length = match.capturedStart(), match.capturedLength()
#     #         # Check if the comment is within an already highlighted string
#     #         if self.formats(start, length) == QTextCharFormat():
#     #             self.setFormat(start, length, self.commentFormat)
#
#     def highlightBlock(self, text):
#         # String matching
#         self.match_multiline(text, self.tri_single_quote, 1, self.stringFormat)
#         self.match_multiline(text, self.tri_double_quote, 2, self.stringFormat)
#         self.match_inline_string(text, self.single_quote, self.stringFormat)
#         self.match_inline_string(text, self.double_quote, self.stringFormat)
#
#         # Keyword matching
#         for keyword in self.keywords:
#             expression = QRegularExpression('\\b' + keyword + '\\b')
#             match_iterator = expression.globalMatch(text)
#             while match_iterator.hasNext():
#                 match = match_iterator.next()
#                 self.setFormat(match.capturedStart(), match.capturedLength(), self.keywordFormat)
#
#     def match_multiline(self, text, expression, state, format):
#         if self.previousBlockState() == state:
#             start = 0
#             length = len(text)
#         else:
#             start = -1
#             length = 0
#
#         # Look for the start of a multi-line string
#         if start == 0:
#             match = expression.match(text)
#             if match.hasMatch():
#                 length = match.capturedLength()
#                 if match.captured(3):  # Closing quotes are found
#                     self.setCurrentBlockState(0)
#                 else:
#                     self.setCurrentBlockState(state)  # Continue to the next line
#                 self.setFormat(match.capturedStart(), length, format)
#                 start = match.capturedEnd()
#         while start >= 0:
#             match = expression.match(text, start)
#             # We've got a match
#             if match.hasMatch():
#                 # Multiline string
#                 length = match.capturedLength()
#                 if match.captured(3):  # Closing quotes are found
#                     self.setCurrentBlockState(0)
#                 else:
#                     self.setCurrentBlockState(state)  # The string is not closed
#                 # Apply the formatting and then look for the next possible match
#                 self.setFormat(match.capturedStart(), length, format)
#                 start = match.capturedEnd()
#             else:
#                 # No further matches; if we are in a multi-line string, color the rest of the text
#                 if self.currentBlockState() == state:
#                     self.setFormat(start, len(text) - start, format)
#                 break
#
#     def match_inline_string(self, text, expression, format):
#         match_iterator = expression.globalMatch(text)
#         while match_iterator.hasNext():
#             match = match_iterator.next()
#             if match.capturedLength() > 0:
#                 if match.captured(1):
#                     self.setFormat(match.capturedStart(), match.capturedLength(), format)
#
#     def match_single_line_comment(self, text):
#         match_iterator = self.single_line_comment.globalMatch(text)
#         while match_iterator.hasNext():
#             match = match_iterator.next()
#             self.setFormat(match.capturedStart(), match.capturedLength(), self.commentFormat)



def clear_layout(layout, skip_count=0):
    """Clear all layouts and widgets from the given layout"""
    # from src.gui.main import TitleButtonBar  # todo clean
    # rolling_indx = 0
    while layout.count() > skip_count:
        # item = layout.itemAt(rolling_indx)
        # if isinstance(item, TitleButtonBar):
        #     rolling_indx += 1
        #     continue
        item = layout.takeAt(skip_count)
        widget = item.widget()
        if widget is not None:
            widget.deleteLater()
        else:
            child_layout = item.layout()
            if child_layout is not None:
                clear_layout(child_layout)
