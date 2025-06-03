import re

from PySide6.QtCore import QRect
from PySide6.QtGui import Qt, QTextCursor, QPainter, QFontDatabase
from PySide6.QtWidgets import QLineEdit, QWidget, QPlainTextEdit, QApplication

from src.gui.util import TextEnhancerButton, IconButton, TextEditorWindow, CVBoxLayout, \
    XMLHighlighter, PythonHighlighter, DockerfileHighlighter  # XML used dynamically
from src.utils.helpers import set_module_type


@set_module_type('Fields')
class Text(QWidget):
    def __init__(self, parent, **kwargs):
        super().__init__(parent)
        num_lines = kwargs.get('num_lines', 1)
        default_value = kwargs.get('default', '')
        param_width = kwargs.get('width', None)
        text_size = kwargs.get('text_size', None)
        text_align = kwargs.get('text_alignment', Qt.AlignLeft)  # only works for single line
        highlighter = kwargs.get('highlighter', None)
        highlighter_field = kwargs.get('highlighter_field', None)
        monospaced = kwargs.get('monospaced', False)
        # expandable = kwargs.get('expandable', False)
        transparent = kwargs.get('transparent', False)
        stretch_y = kwargs.get('stretch_y', False)
        placeholder_text = kwargs.get('placeholder_text', None)

        if num_lines > 1:
            fold_mode = kwargs.get('fold_mode', 'xml')
            enhancement_key = kwargs.get('enhancement_key', None)
            self.widget = CTextEdit(fold_mode=fold_mode, enhancement_key=enhancement_key)
            self.widget.setTabStopDistance(self.widget.fontMetrics().horizontalAdvance(' ') * 4)
        else:
            self.widget = QLineEdit(self)
            self.widget.setAlignment(text_align)

        transparency = 'background-color: transparent;' if transparent else ''
        self.widget.setStyleSheet(f"border-radius: 6px;" + transparency)

        font = self.widget.font()
        if monospaced:
            font = QFontDatabase.systemFont(QFontDatabase.FixedFont)
        if text_size:
            font.setPointSize(text_size)
        self.widget.setFont(font)

        if highlighter:
            try:
                # highlighter is a string name of the highlighter class, imported in this file
                # reassign highlighter to the highlighter class
                highlighter = globals()[highlighter]
                self.widget.highlighter = highlighter(self.widget.document(), self.parent)
                if isinstance(highlighter, PythonHighlighter) or isinstance(highlighter, DockerfileHighlighter):
                    self.widget.setLineWrapMode(QPlainTextEdit.NoWrap)
            except Exception as e:
                pass
        elif highlighter_field:
            self.widget.highlighter_field = highlighter_field

        if placeholder_text:
            self.widget.setPlaceholderText(placeholder_text)

        if not stretch_y:
            font_metrics = self.widget.fontMetrics()
            height = (font_metrics.lineSpacing() + 2) * num_lines + self.widget.contentsMargins().top() + self.widget.contentsMargins().bottom()
            self.widget.setFixedHeight(height)

        self.widget.textChanged.connect(parent.update_config)
        self.layout = CVBoxLayout(self)
        self.layout.addWidget(self.widget)

    def set_value(self, value):
        if isinstance(self.widget, CTextEdit):
            self.widget.setPlainText(value)
        else:
            self.widget.setText(value)

    def get_value(self):
        if isinstance(self.widget, CTextEdit):
            return self.widget.toPlainText()
        else:
            return self.widget.text()

    def clear_value(self):
        self.widget.clear()


class CTextEdit(QPlainTextEdit):
    def __init__(self, parent=None, fold_mode='xml', enhancement_key=None):
        super().__init__(parent)
        self.foldRegions = []  # top-level fold regions
        self.text_editor = None
        self.setTabStopDistance(40)

        # Recompute fold regions whenever content changes
        self.document().blockCountChanged.connect(self.updateFoldRegions)
        self.textChanged.connect(self.updateFoldRegions)

        if enhancement_key:
            self.wand_button = TextEnhancerButton(self, self, key=enhancement_key)
            self.wand_button.hide()

        self.fold_mode = fold_mode

        self.expand_button = IconButton(parent=self, icon_path=':/resources/icon-expand.png', size=22)
        self.expand_button.setStyleSheet("background-color: transparent;")
        self.expand_button.clicked.connect(self.on_button_clicked)
        self.expand_button.hide()

        self.updateButtonPosition()

    def updateFoldRegions(self, *args):
        # Everything is initially unfolded
        # If you want them folded from the start, set region.isFolded = True
        # and call foldRegion(...).
        if self.fold_mode == 'xml':
            self.set_xml_fold_regions()
        elif self.fold_mode == 'python':
            self.set_python_fold_regions()
        self.repaint()

    def set_xml_fold_regions(self):
        all_lines = self.toPlainText().split('\n')

        # We'll build a tree of fold regions by maintaining:
        #  - A stack of (tagName, startLine, parentRegion)
        #  - Another stack for open markdown headings
        new_fold_regions = []
        xml_stack = []
        md_heading_stack = []

        # Simple pattern to extract *all* tags (open or close) from a line.
        #   group(1): '/' if it's a close tag
        #   group(2): the actual tag name
        xmlTagPattern = re.compile(r"<(/)?(\w+)[^>]*>")

        # Helper function to add a child region to its parent's .children list
        def addChild(parent, region):
            if parent:
                parent.children.append(region)
                region.parent = parent
            else:
                # no parent => top-level region
                new_fold_regions.append(region)

        # We'll proceed line by line.
        for i, line in enumerate(all_lines):
            stripped = line.strip()

            # 1) Detect markdown headings
            #    If a line starts with #, #..., we treat it as a fold start
            #    until the next heading or end of doc
            #    We do *not* allow nested headings in the same sense as nested tags,
            #    but you can extend as you wish.
            if stripped.startswith('#'):
                # If there's a heading already open, close it at i-1
                if md_heading_stack:
                    startLine, parentReg = md_heading_stack.pop()
                    # if the heading was on line startLine, it folds up to i-1
                    if i - 1 > startLine:
                        headingReg = FoldRegion(startLine, i - 1, parent=parentReg)
                        addChild(parentReg, headingReg)

                # Now start a new heading region
                # For simplicity, we treat headings as top-level folds (no parent).
                md_heading_stack.append((i, None))

            # 2) Extract *all* tags in the line (there can be multiple)
            for m in xmlTagPattern.finditer(line):
                isClosingSlash = m.group(1)  # '/' or None
                tagName = m.group(2)

                if not isClosingSlash:
                    # Opening tag <tagName>
                    # We push onto stack with the line number
                    # The *parent region* for an opened tag is the region on top of the stack,
                    #   or None if no open region yet.
                    parentRegion = xml_stack[-1][2] if xml_stack else None
                    xml_stack.append((tagName, i, parentRegion))
                else:
                    # Closing tag </tagName>
                    # We pop from the stack until we find a matching open for the *same* tagName
                    poppedIndex = None
                    for idx in reversed(range(len(xml_stack))):
                        openTagName, openLine, openParent = xml_stack[idx]
                        if openTagName == tagName:
                            poppedIndex = idx
                            break
                    if poppedIndex is not None:
                        openTagName, openLine, parentReg = xml_stack.pop(poppedIndex)
                        # create a region from openLine to i
                        if i > openLine:
                            region = FoldRegion(openLine, i, parent=parentReg)
                            addChild(parentReg, region)

        # If we still have an open heading on the stack, close it at the last line
        lastLineIndex = len(all_lines) - 1
        while md_heading_stack:
            startLine, parentReg = md_heading_stack.pop()
            if lastLineIndex > startLine:
                headingReg = FoldRegion(startLine, lastLineIndex, parent=parentReg)
                addChild(parentReg, headingReg)

        # If there are unclosed XML tags, you *could* forcibly close them at EOF,
        # if you want. For demonstration, we’ll leave them unmatched.

        self.foldRegions = new_fold_regions

    def set_python_fold_regions(self):
        all_lines = self.toPlainText().split('\n')
        new_fold_regions = []
        indent_stack = []  # Stack of (indent_level, FoldRegion)

        # Helper function to add a child region to its parent's .children list
        def addChild(parent, region):
            if parent:
                parent.children.append(region)
                region.parent = parent
            else:
                new_fold_regions.append(region)

        # Regular expression to match 'def', 'async def', and 'class' at the beginning of a line
        line_regex = re.compile(r'^\s*(async\s+def|def|class)\b')

        for i, line in enumerate(all_lines):
            # Expand tabs to spaces
            line_expanded = line.expandtabs(4)
            leading_ws = line_expanded[:len(line_expanded) - len(line_expanded.lstrip())]
            indent_level = len(leading_ws)
            stripped = line_expanded.strip()

            # Skip empty lines and comments
            if not stripped or stripped.startswith('#'):
                continue

            # Check if indent_stack is not empty and current indent level is less than the top's (unindent)
            while indent_stack and indent_level <= indent_stack[-1][0]:
                prev_indent_level, region = indent_stack.pop()
                if region.endLine is None:
                    # Adjust the end line to the last non-empty line before this line
                    # This prevents folding the newlines after the code block
                    end = i - 1
                    while end > region.startLine and not all_lines[end].strip():
                        end -= 1
                    region.endLine = end

            if line_regex.match(line_expanded):
                # New code block
                parent_region = indent_stack[-1][1] if indent_stack else None
                region = FoldRegion(startLine=i, endLine=None)
                region.children = []
                region.parent = parent_region
                region.isFolded = False  # Initially unfolded

                addChild(parent_region, region)
                # Push onto stack
                indent_stack.append((indent_level, region))

        # After processing all lines, close any remaining regions
        while indent_stack:
            prev_indent_level, region = indent_stack.pop()
            if region.endLine is None:
                # Adjust the end line to the last non-empty line before the end
                end = len(all_lines) - 1
                while end != region.startLine and not all_lines[end].strip():
                    end -= 1
                region.endLine = end

        self.foldRegions = new_fold_regions

    def keyPressEvent(self, event):
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

    def mousePressEvent(self, event):
        """
        Detect if user clicked on the fold icon margin (left ~12px).
        If so, figure out which region was clicked and toggle it.
        """
        if event.x() <= 12:
            # figure out which line was clicked
            lineNumber = self.lineNumberAtY(event.y())
            if lineNumber is not None:
                # find if there's a region whose 'startLine' matches lineNumber
                #   (including nested ones)
                clickedRegion = self.findRegionAtLine(lineNumber, self.foldRegions)
                if clickedRegion:
                    clickedRegion.isFolded = not clickedRegion.isFolded
                    if clickedRegion.isFolded:
                        self.foldRegion(clickedRegion)
                    else:
                        self.unfoldRegion(clickedRegion)
                    self.viewport().update()

        super().mousePressEvent(event)

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

    def updateButtonPosition(self):
        # Calculate the position for the button
        button_width = self.expand_button.width()
        button_height = self.expand_button.height()
        edit_rect = self.contentsRect()

        # Position the button at the bottom-right corner
        x = edit_rect.right() - button_width - 2
        y = edit_rect.bottom() - button_height - 2
        self.expand_button.move(x, y)

        # position wand button just above expand button
        if hasattr(self, 'wand_button'):
            self.wand_button.move(x, y - button_height)

    def on_button_clicked(self):
        # check if the window is already open where parent is self
        all_windows = QApplication.topLevelWidgets()
        for window in all_windows:
            if isinstance(window, TextEditorWindow) and window.parent == self:
                window.activateWindow()
                return
        self.text_editor = TextEditorWindow(self)
        self.text_editor.show()
        self.text_editor.activateWindow()

    def insertFromMimeData(self, source):
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
        if hasattr(self, 'wand_button'):
            self.wand_button.show()
        super().enterEvent(event)

    def leaveEvent(self, event):
        self.expand_button.hide()
        if hasattr(self, 'wand_button'):
            self.wand_button.hide()
        super().leaveEvent(event)

    def lineNumberAtY(self, y):
        """
        Translate a y coordinate in the viewport to a block (line) number.
        We iterate over visible blocks until we find which one covers 'y'.
        """
        block = self.firstVisibleBlock()
        blockNumber = block.blockNumber()
        top = int(self.blockBoundingGeometry(block).translated(self.contentOffset()).top())
        bottom = top + int(self.blockBoundingRect(block).height())

        while block.isValid() and top <= y:
            if y <= bottom:
                return blockNumber
            block = block.next()
            blockNumber = block.blockNumber()
            top = bottom
            bottom = top + int(self.blockBoundingRect(block).height())
        return None

    def findRegionAtLine(self, lineNumber, regionList):
        """
        Given a lineNumber, find a region whose startLine == lineNumber (DFS in regionList).
        Return the first match found.
        """
        for region in regionList:
            if region.startLine == lineNumber:
                return region
            found = self.findRegionAtLine(lineNumber, region.children)
            if found:
                return found
        return None

    # -----------------------
    # 4) Folding / Unfolding
    # -----------------------
    def foldRegion(self, region):
        """
        Hide all lines from region.startLine+1 to region.endLine (inclusive),
        including nested child regions.
        """
        # Mark everything from start+1 to endLine invisible.
        # The region's first line remains visible so the user sees the fold arrow.
        for line in range(region.startLine + 1, region.endLine + 1):
            block = self.document().findBlockByNumber(line)
            if block.isValid():
                block.setVisible(False)

        # Also fold child regions (so that if user expands later,
        # the child regions remain in the correct state).
        for child in region.children:
            child.isFolded = True
            self.foldRegion(child)

    def unfoldRegion(self, region):
        """
        Show all lines from region.startLine+1 to region.endLine (inclusive),
        BUT also check if any children are folded (so their sub-lines remain hidden).
        """
        # If the region is being unfolded, its lines become visible
        # except for lines belonging to a STILL-FOLDED child region.
        for line in range(region.startLine + 1, region.endLine + 1):
            block = self.document().findBlockByNumber(line)
            if block.isValid():
                block.setVisible(True)

        # Recursively unfold all children
        for child in region.children:
            child.isFolded = False  # Ensure the child is marked as unfolded
            self.unfoldRegion(child)  # Recursively unfold child's lines

    def paintEvent(self, event):
        """Draws the text plus fold icons in the margin."""
        super().paintEvent(event)
        painter = QPainter(self.viewport())
        painter.setPen(Qt.black)

        # Draw over margins too
        painter.setClipRect(self.viewport().rect())

        # We'll do a DFS (depth-first) over all fold regions, so that
        # we draw icons for nested regions as well.
        def drawRegionIcons(region):
            block = self.document().findBlockByNumber(region.startLine)
            if block.isValid() and block.isVisible():
                # Top of the block
                block_geom = self.blockBoundingGeometry(block).translated(self.contentOffset())
                top = round(block_geom.top())
                # Draw a small arrow
                rect = QRect(0, top, 12, 12)
                if region.isFolded:
                    painter.drawText(rect, Qt.AlignLeft, '▶')  # Collapsed arrow
                else:
                    painter.drawText(rect, Qt.AlignLeft, '▼')  # Expanded arrow

                # Now recursively draw icons for child regions
                for child in region.children:
                    drawRegionIcons(child)
            else:
                # If the block is not visible, we skip drawing icons for this region
                # and its children because they're within a folded parent region.
                pass

        for topRegion in self.foldRegions:
            drawRegionIcons(topRegion)

        painter.end()


class FoldRegion:
    def __init__(self, startLine, endLine, parent=None):
        self.startLine = startLine
        self.endLine = endLine
        self.parent = parent
        self.children = []
        self.isFolded = False

    def __repr__(self):
        return f"<FoldRegion [{self.startLine}-{self.endLine}] folded={self.isFolded}>"
