import os

from PySide6.QtWidgets import (
    QWidget, QLabel, QGroupBox, QStatusBar,
    QPushButton, QTextEdit, QPlainTextEdit,
    QFileDialog, QMessageBox, QDialog, QLineEdit,
    QCheckBox
)
from PySide6.QtCore import (
    Qt, QRegularExpression, QRect, QSize
)
from PySide6.QtGui import (
    QTextCursor, QColor, QFont, QTextDocument, QPainter,
    QTextFormat, QTextOption, QKeySequence
)

from gui.util import CustomMenu, find_main, CVBoxLayout, CHBoxLayout
from utils.helpers import apply_alpha_to_hex, block_signals, set_module_type
from gui import system
from gui.style import SECONDARY_COLOR


@set_module_type('Studios')
class TextStudio(QWidget):
    """Single-file text editor studio with syntax highlighting and search/replace."""
    associated_extensions = ['txt', 'py', 'js', 'html', 'css', 'json', 'xml', 'md', 'sql', 'yaml', 'yml', 'ini', 'toml', 'cfg', 'conf', 'log', 'csv', 'tsv']

    def __init__(self, parent=None):
        super().__init__(parent)
        self.main = find_main()
        self.filepath = None
        self.search_dialog = None
        self.autosave_enabled = True

        # Build highlighter mapping from available modules
        self.highlighter_map = {}  # {extension: highlighter_class}
        self._load_highlighters()

        # Single editor
        self.editor = CodeEditor()
        self.editor.cursorPositionChanged.connect(self.update_cursor_position)
        self.editor.selectionChanged.connect(self.update_selection_info)
        self.editor.textChanged.connect(lambda: self.mark_modified(self.editor))

        # Menu bar
        self.menubar = self.MenuBar(self)

        # Status bar
        self.status_bar = QStatusBar()
        self.position_label = QLabel("Ln 1, Col 1")
        self.selection_label = QLabel("")
        self.encoding_label = QLabel("UTF-8")
        self.line_ending_label = QLabel("LF")
        self.status_bar.addWidget(self.position_label)
        self.status_bar.addWidget(self.selection_label)
        self.status_bar.addPermanentWidget(self.encoding_label)
        self.status_bar.addPermanentWidget(self.line_ending_label)

        self.layout = CVBoxLayout(self)
        self.layout.addWidget(self.menubar)
        self.layout.addWidget(self.editor)
        self.layout.addWidget(self.status_bar)

    def _load_highlighters(self):
        """Load all available highlighters and build extension mapping."""
        highlighters = system.manager.modules.get_modules_in_folder(
            'Highlighters',
            fetch_keys=('name', 'class',)
        )

        for _, highlighter_class in highlighters:
            if highlighter_class and hasattr(highlighter_class, 'associated_extensions'):
                for ext in highlighter_class.associated_extensions:
                    ext_normalized = ext.lower().lstrip('.')
                    self.highlighter_map[ext_normalized] = highlighter_class

    class MenuBar(CustomMenu):
        def __init__(self, parent):
            super().__init__(parent)
            self.schema = [
                {
                    'text': 'File',
                    'submenu': [
                        {
                            'text': 'Open',
                            'shortcut': QKeySequence.Open,
                            'target': parent.open_file,
                        },
                        {
                            'text': 'Save',
                            'shortcut': QKeySequence.Save,
                            'target': parent.save_file,
                        },
                        {
                            'text': 'Save As',
                            'shortcut': QKeySequence.SaveAs,
                            'target': parent.save_file_as,
                        },
                        {
                            'type': 'separator',
                        },
                        {
                            'text': 'Autosave',
                            'checkable': True,
                            'checked_state': lambda: parent.autosave_enabled,
                            'target': parent.toggle_autosave,
                        },
                    ],
                },
                {
                    'text': 'Edit',
                    'submenu': [
                        {
                            'type': 'create_standard',
                            'widget': lambda: parent.editor,
                        }
                    ],
                },
                {
                    'text': 'View',
                    'submenu': [
                        {
                            'text': 'Zoom In',
                            'shortcut': QKeySequence.ZoomIn,
                            'target': parent.zoom_in,
                        },
                        {
                            'text': 'Zoom Out',
                            'shortcut': QKeySequence.ZoomOut,
                            'target': parent.zoom_out,
                        },
                        {
                            'text': 'Reset Zoom',
                            'shortcut': 'Ctrl+0',
                            'target': parent.reset_zoom,
                        },
                        {
                            'type': 'separator',
                        },
                        {
                            'text': 'Word Wrap',
                            'checkable': True,
                            'checked_state': lambda: parent.editor.lineWrapMode() == QPlainTextEdit.WidgetWidth,
                            'target': parent.toggle_word_wrap,
                        },
                        {
                            'text': 'Toggle Line Numbers',
                            'checkable': True,
                            'checked_state': lambda: parent.editor.line_number_area.isVisible(),
                            'target': parent.toggle_line_numbers,
                        },
                    ],
                },
                {
                    'text': 'Search',
                    'submenu': [
                        {
                            'text': 'Find',
                            'shortcut': QKeySequence.Find,
                            'target': parent.show_find_dialog,
                        },
                        {
                            'text': 'Replace',
                            'shortcut': QKeySequence.Replace,
                            'target': parent.show_replace_dialog,
                        },
                    ],
                },
            ]
            self.create_menubar(parent)

    def open_file(self, filepath=None):
        """Open a file in the editor."""
        if not filepath:
            filepath, _ = QFileDialog.getOpenFileName(
                self,
                "Open File",
                "",
                "All Files (*);;Python Files (*.py);;Text Files (*.txt);;JavaScript Files (*.js)"
            )

        if not filepath:
            return

        try:
            with open(filepath, 'r', encoding='utf-8') as file:
                content = file.read()

            with block_signals(self.editor):
                self.editor.setPlainText(content)
                self.filepath = filepath
                self.editor.filepath = filepath
                self.editor.is_modified = False

                self.apply_syntax_highlighting(self.editor, filepath)

                # Reset modified state after setup (highlighting may trigger textChanged)
                self.editor.is_modified = False

        except Exception as e:
            QMessageBox.critical(self, "Error", f"Failed to open file: {str(e)}")

    def save_file(self):
        """Save the current file."""
        if not self.filepath:
            self.save_file_as()
            return

        try:
            content = self.editor.toPlainText()
            try:
                with open(self.filepath, 'r', encoding='utf-8') as f:
                    if f.read() == content:
                        self.editor.is_modified = False
                        return
            except (OSError, UnicodeDecodeError):
                pass
            with open(self.filepath, 'w', encoding='utf-8') as file:
                file.write(content)

            self.editor.is_modified = False

        except Exception as e:
            QMessageBox.critical(self, "Error", f"Failed to save file: {str(e)}")

    def save_file_as(self):
        """Save the current file with a new name."""
        filepath, _ = QFileDialog.getSaveFileName(
            self,
            "Save File As",
            "",
            "All Files (*);;Python Files (*.py);;Text Files (*.txt);;JavaScript Files (*.js)"
        )

        if not filepath:
            return

        try:
            with open(filepath, 'w', encoding='utf-8') as file:
                file.write(self.editor.toPlainText())

            self.filepath = filepath
            self.editor.filepath = filepath
            self.editor.is_modified = False
            self.apply_syntax_highlighting(self.editor, filepath)

        except Exception as e:
            QMessageBox.critical(self, "Error", f"Failed to save file: {str(e)}")

    def toggle_autosave(self, checked):
        """Toggle autosave mode."""
        self.autosave_enabled = checked

    def mark_modified(self, editor):
        """Mark a file as modified."""
        if not hasattr(editor, 'is_modified'):
            editor.is_modified = False

        if not editor.is_modified:
            editor.is_modified = True

        if self.autosave_enabled and self.filepath:
            self.save_file()

    def apply_syntax_highlighting(self, editor, filepath):
        """Apply syntax highlighting based on file type."""
        ext = os.path.splitext(filepath)[1].lower().lstrip('.')

        highlighter_class = self.highlighter_map.get(ext)

        if highlighter_class:
            highlighter = highlighter_class(editor.document())
            editor.highlighter = highlighter

            # # Update language combo to match
            # class_name = highlighter_class.__name__
            # if class_name.endswith('Highlighter'):
            #     display_name = class_name[:-11]  # Remove "Highlighter"
            # else:
            #     display_name = class_name

        #     index = self.language_combo.findText(display_name)
        #     if index >= 0:
        #         self.language_combo.setCurrentIndex(index)
        # else:
        #     # No highlighter for this extension
        #     editor.highlighter = None
        #     self.language_combo.setCurrentIndex(0)  # Set to "Plain Text"

    def detect_and_set_language(self, filepath):
        """Detect and set language in combo box."""
        return
        ext = os.path.splitext(filepath)[1].lower()
        ext = ext.lstrip('.')

        # Look up highlighter for this extension
        highlighter_class = self.highlighter_map.get(ext)

        if highlighter_class:
            class_name = highlighter_class.__name__
            if class_name.endswith('Highlighter'):
                display_name = class_name[:-11]
            else:
                display_name = class_name

            index = self.language_combo.findText(display_name)
            if index >= 0:
                self.language_combo.setCurrentIndex(index)
        else:
            self.language_combo.setCurrentIndex(0)  # "Plain Text"

    def on_language_changed(self, language):
        """Handle language selection change."""
        if language == "Plain Text":
            self.editor.highlighter = None
        else:
            highlighter_class = None
            for ext, h_class in self.highlighter_map.items():
                class_name = h_class.__name__
                if class_name.endswith('Highlighter'):
                    display_name = class_name[:-11]
                else:
                    display_name = class_name

                if display_name == language:
                    highlighter_class = h_class
                    break

            if highlighter_class:
                highlighter = highlighter_class(self.editor.document())
                self.editor.highlighter = highlighter
            else:
                self.editor.highlighter = None

    def update_cursor_position(self):
        """Update cursor position in status bar."""
        cursor = self.editor.textCursor()
        line = cursor.blockNumber() + 1
        column = cursor.columnNumber() + 1
        self.position_label.setText(f"Ln {line}, Col {column}")

    def update_selection_info(self):
        """Update selection info in status bar."""
        cursor = self.editor.textCursor()
        if cursor.hasSelection():
            sel_text = cursor.selectedText()
            sel_lines = sel_text.count('\n') + 1
            sel_chars = len(sel_text)
            self.selection_label.setText(f"Sel: {sel_chars} chars, {sel_lines} lines")
        else:
            self.selection_label.setText("")

    # Search operations
    def show_find_dialog(self):
        """Show find dialog."""
        if not self.search_dialog:
            self.search_dialog = SearchDialog(self, replace_mode=False)
        else:
            self.search_dialog.set_mode(replace_mode=False)

        if self.editor.textCursor().hasSelection():
            self.search_dialog.search_input.setText(self.editor.textCursor().selectedText())

        self.search_dialog.show()
        self.search_dialog.raise_()
        self.search_dialog.activateWindow()

    def show_replace_dialog(self):
        """Show replace dialog."""
        if not self.search_dialog:
            self.search_dialog = SearchDialog(self, replace_mode=True)
        else:
            self.search_dialog.set_mode(replace_mode=True)

        if self.editor.textCursor().hasSelection():
            self.search_dialog.search_input.setText(self.editor.textCursor().selectedText())

        self.search_dialog.show()
        self.search_dialog.raise_()
        self.search_dialog.activateWindow()

    def find_next(self):
        """Find next occurrence."""
        if self.search_dialog and self.search_dialog.search_input.text():
            self.search_dialog.find_next()

    def find_previous(self):
        """Find previous occurrence."""
        if self.search_dialog and self.search_dialog.search_input.text():
            self.search_dialog.find_previous()

    # View operations
    def zoom_in(self):
        """Zoom in text."""
        self.editor.zoomIn(2)

    def zoom_out(self):
        """Zoom out text."""
        self.editor.zoomOut(2)

    def reset_zoom(self):
        """Reset zoom level."""
        font = self.editor.font()
        font.setPointSize(10)
        self.editor.setFont(font)

    def toggle_line_numbers(self, checked):
        """Toggle line numbers."""
        self.editor.line_number_area.setVisible(checked)
        self.editor.setViewportMargins(self.editor.line_number_area_width() if checked else 0, 0, 0, 0)

    def toggle_word_wrap(self, checked):
        """Toggle word wrap."""
        if checked:
            self.editor.setLineWrapMode(QPlainTextEdit.WidgetWidth)
        else:
            self.editor.setLineWrapMode(QPlainTextEdit.NoWrap)

    def toggle_whitespace(self, checked):
        """Toggle whitespace visibility."""
        option = self.editor.document().defaultTextOption()
        if checked:
            option.setFlags(option.flags() | QTextOption.ShowTabsAndSpaces)
        else:
            option.setFlags(option.flags() & ~QTextOption.ShowTabsAndSpaces)
        self.editor.document().setDefaultTextOption(option)


class CodeEditor(QPlainTextEdit):
    """Enhanced text editor with line numbers and code features."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.line_number_area = LineNumberArea(self)
        self.filepath = None
        self.is_modified = False
        self.highlighter = None
        # self._line_number_area_visible = True  # Track line number visibility

        # Set default font
        font = QFont("Consolas", 10)
        font.setStyleHint(QFont.Monospace)
        self.setFont(font)

        # Connect signals
        self.blockCountChanged.connect(self.update_line_number_area_width)
        self.updateRequest.connect(self.update_line_number_area)
        self.cursorPositionChanged.connect(self.highlight_current_line)

        self.update_line_number_area_width(0)
        self.highlight_current_line()

        # Set tab width
        self.setTabStopDistance(4 * self.fontMetrics().horizontalAdvance(' '))

    def line_number_area_width(self):
        """Calculate width needed for line number area."""
        digits = 1
        max_num = max(1, self.blockCount())
        while max_num >= 10:
            max_num //= 10
            digits += 1
        space = 3 + self.fontMetrics().horizontalAdvance('9') * digits
        return space

    def update_line_number_area_width(self, _):
        """Update the width of the line number area."""
        self.setViewportMargins(self.line_number_area_width(), 0, 0, 0)

    def update_line_number_area(self, rect, dy):
        """Update the line number area when scrolling."""
        if dy:
            self.line_number_area.scroll(0, dy)
        else:
            self.line_number_area.update(0, rect.y(), self.line_number_area.width(), rect.height())

        if rect.contains(self.viewport().rect()):
            self.update_line_number_area_width(0)

    def resizeEvent(self, event):
        """Handle resize events."""
        super().resizeEvent(event)
        cr = self.contentsRect()
        line_number_area_width = self.line_number_area_width() if self.line_number_area.isVisible() else 0
        self.line_number_area.setGeometry(QRect(cr.left(), cr.top(),
                                                line_number_area_width, cr.height()))

    def line_number_area_paint_event(self, event):
        """Paint the line numbers."""
        painter = QPainter()
        if not painter.begin(self.line_number_area):
            return

        try:
            painter.fillRect(event.rect(), QColor(SECONDARY_COLOR))

            block = self.firstVisibleBlock()
            block_number = block.blockNumber()
            top = self.blockBoundingGeometry(block).translated(self.contentOffset()).top()
            bottom = top + self.blockBoundingRect(block).height()

            while block.isValid() and top <= event.rect().bottom():
                if block.isVisible() and bottom >= event.rect().top():
                    number = str(block_number + 1)
                    painter.setPen(QColor(120, 120, 120))
                    painter.drawText(0, top, self.line_number_area.width() - 3,
                                   self.fontMetrics().height(),
                                   Qt.AlignRight, number)

                block = block.next()
                top = bottom
                bottom = top + self.blockBoundingRect(block).height()
                block_number += 1
        finally:
            painter.end()

    def highlight_current_line(self):
        """Highlight the current line."""
        extra_selections = []

        if not self.isReadOnly():
            selection = QTextEdit.ExtraSelection()
            TEXT_COLOR = system.manager.config.get('display.text_color', '#c4c4c4')
            line_color = apply_alpha_to_hex(TEXT_COLOR, 0.1)
            selection.format.setBackground(QColor(line_color))
            selection.format.setProperty(QTextFormat.FullWidthSelection, True)
            selection.cursor = self.textCursor()
            selection.cursor.clearSelection()
            extra_selections.append(selection)

        self.setExtraSelections(extra_selections)


class LineNumberArea(QWidget):
    """Widget for displaying line numbers."""

    def __init__(self, editor):
        super().__init__(editor)
        self.editor = editor

    def sizeHint(self):
        """Return size hint."""
        return QSize(self.editor.line_number_area_width(), 0)

    def paintEvent(self, event):
        """Paint line numbers."""
        self.editor.line_number_area_paint_event(event)


class SearchDialog(QDialog):
    """Search and replace dialog."""

    def __init__(self, parent, replace_mode=False):
        super().__init__(parent)
        self.setWindowFlags(
            Qt.Window
            | Qt.WindowTitleHint
            | Qt.WindowSystemMenuHint
            | Qt.WindowCloseButtonHint
            | Qt.WindowStaysOnTopHint
        )
        self.text_studio = parent
        self.replace_mode = replace_mode

        self.setWindowTitle("Replace" if replace_mode else "Find")
        self.setFixedSize(450, 250 if replace_mode else 200)

        layout = CVBoxLayout(self)

        # Search input
        search_group = QGroupBox("Find what:")
        search_layout = CHBoxLayout(search_group)
        self.search_input = QLineEdit()
        search_layout.addWidget(self.search_input)
        layout.addWidget(search_group)

        # Replace input (if in replace mode)
        if replace_mode:
            replace_group = QGroupBox("Replace with:")
            replace_layout = CHBoxLayout(replace_group)
            self.replace_input = QLineEdit()
            replace_layout.addWidget(self.replace_input)
            layout.addWidget(replace_group)

        # Options
        options_group = QGroupBox("Options")
        options_layout = CVBoxLayout(options_group)

        self.case_sensitive = QCheckBox("Case sensitive")
        self.whole_words = QCheckBox("Whole words only")
        self.regex = QCheckBox("Regular expression")

        options_layout.addWidget(self.case_sensitive)
        options_layout.addWidget(self.whole_words)
        options_layout.addWidget(self.regex)

        layout.addWidget(options_group)

        # Buttons
        button_layout = CHBoxLayout()

        self.find_next_btn = QPushButton("Find Next")
        self.find_prev_btn = QPushButton("Find Previous")
        self.find_next_btn.clicked.connect(self.find_next)
        self.find_prev_btn.clicked.connect(self.find_previous)

        button_layout.addWidget(self.find_next_btn)
        button_layout.addWidget(self.find_prev_btn)

        if replace_mode:
            self.replace_btn = QPushButton("Replace")
            self.replace_all_btn = QPushButton("Replace All")
            self.replace_btn.clicked.connect(self.replace)
            self.replace_all_btn.clicked.connect(self.replace_all)
            button_layout.addWidget(self.replace_btn)
            button_layout.addWidget(self.replace_all_btn)

        self.close_btn = QPushButton("Close")
        self.close_btn.clicked.connect(self.close)
        button_layout.addWidget(self.close_btn)

        layout.addLayout(button_layout)

    def set_mode(self, replace_mode):
        """Set dialog mode (find or replace)."""
        self.replace_mode = replace_mode
        self.setWindowTitle("Replace" if replace_mode else "Find")

    def get_search_flags(self):
        """Get search flags based on options."""
        flags = QTextDocument.FindFlags()

        if self.case_sensitive.isChecked():
            flags |= QTextDocument.FindCaseSensitively
        if self.whole_words.isChecked():
            flags |= QTextDocument.FindWholeWords

        return flags

    def find_next(self):
        """Find next occurrence."""
        editor = self.text_studio.editor
        search_text = self.search_input.text()
        if not search_text:
            return

        flags = self.get_search_flags()

        if self.regex.isChecked():
            regex = QRegularExpression(search_text)
            if self.case_sensitive.isChecked():
                regex.setPatternOptions(QRegularExpression.NoPatternOption)
            else:
                regex.setPatternOptions(QRegularExpression.CaseInsensitiveOption)
            found = editor.find(regex, flags)
        else:
            found = editor.find(search_text, flags)

        if not found:
            # Wrap around to beginning
            cursor = editor.textCursor()
            cursor.movePosition(QTextCursor.Start)
            editor.setTextCursor(cursor)

            if self.regex.isChecked():
                editor.find(regex, flags)
            else:
                editor.find(search_text, flags)

    def find_previous(self):
        """Find previous occurrence."""
        editor = self.text_studio.editor
        search_text = self.search_input.text()
        if not search_text:
            return

        flags = self.get_search_flags() | QTextDocument.FindBackward

        if self.regex.isChecked():
            regex = QRegularExpression(search_text)
            if self.case_sensitive.isChecked():
                regex.setPatternOptions(QRegularExpression.NoPatternOption)
            else:
                regex.setPatternOptions(QRegularExpression.CaseInsensitiveOption)
            found = editor.find(regex, flags)
        else:
            found = editor.find(search_text, flags)

        if not found:
            # Wrap around to end
            cursor = editor.textCursor()
            cursor.movePosition(QTextCursor.End)
            editor.setTextCursor(cursor)

            if self.regex.isChecked():
                editor.find(regex, flags)
            else:
                editor.find(search_text, flags)

    def replace(self):
        """Replace current selection."""
        if not self.replace_mode:
            return

        editor = self.text_studio.editor
        cursor = editor.textCursor()
        if cursor.hasSelection():
            cursor.insertText(self.replace_input.text())
            self.find_next()

    def replace_all(self):
        """Replace all occurrences."""
        if not self.replace_mode:
            return

        editor = self.text_studio.editor
        search_text = self.search_input.text()
        replace_text = self.replace_input.text()

        if not search_text:
            return

        # Move to beginning
        cursor = editor.textCursor()
        cursor.movePosition(QTextCursor.Start)
        editor.setTextCursor(cursor)

        count = 0
        flags = self.get_search_flags()

        if self.regex.isChecked():
            regex = QRegularExpression(search_text)
            if self.case_sensitive.isChecked():
                regex.setPatternOptions(QRegularExpression.NoPatternOption)
            else:
                regex.setPatternOptions(QRegularExpression.CaseInsensitiveOption)

            while editor.find(regex, flags):
                cursor = editor.textCursor()
                cursor.insertText(replace_text)
                count += 1
        else:
            while editor.find(search_text, flags):
                cursor = editor.textCursor()
                cursor.insertText(replace_text)
                count += 1

        QMessageBox.information(self, "Replace All", f"Replaced {count} occurrences.")