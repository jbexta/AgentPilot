import asyncio
import inspect
import json
import re
from functools import partial

from PySide6.QtWidgets import *
from PySide6.QtCore import Signal, QSize, QRegularExpression, QEvent, QRunnable, Slot, QRect, QSizeF
from PySide6.QtGui import QPixmap, QPalette, QColor, QIcon, QFont, Qt, QStandardItem, QPainter, \
    QPainterPath, QFontDatabase, QSyntaxHighlighter, QTextCharFormat, QTextOption, QTextDocument, QKeyEvent, \
    QTextCursor, QFontMetrics, QCursor

from src.system.modules import get_page_definitions
from src.utils import sql, resources_rc
from src.utils.helpers import block_pin_mode, path_to_pixmap, display_message_box, block_signals, apply_alpha_to_hex, \
    get_avatar_paths_from_config, convert_model_json_to_obj, display_message
from src.utils.filesystem import unsimplify_path
from PySide6.QtWidgets import QAbstractItemView


def find_main_widget(widget):
    if hasattr(widget, 'main'):
        if widget.main is not None:
            return widget.main

    clss = widget.__class__.__name__
    if clss == 'Main':
        return widget
    if not hasattr(widget, 'parent'):
        return None  # QApplication.activeWindow()
    return find_main_widget(widget.parent)


def find_breadcrumb_widget(widget):
    if hasattr(widget, 'breadcrumb_widget'):
        return widget.breadcrumb_widget
    if not hasattr(widget, 'parent'):
        return None
    return find_breadcrumb_widget(widget.parent)


def find_editing_module_id(widget):
    if getattr(widget, 'module_id', None):
        return widget.module_id
    if not hasattr(widget, 'parent'):
        return None
    return find_editing_module_id(widget.parent)


def find_page_editor_widget(widget):
    if hasattr(widget, 'module_popup'):
        return widget.module_popup  #  find_page_editor_widget(widget.parent)
    if hasattr(widget, 'parent'):
        return find_page_editor_widget(widget.parent)
    return None
    # if not hasattr(widget.parent, 'main_menu'):
    #     return find_page_editor_widget(widget.parent)
    # else:
    #     if getattr(widget.parent.main_menu.settings_sidebar, 'module_popup', None):
    #         return widget.parent.main_menu.settings_sidebar.module_popup
    # # if not hasattr(widget, 'parent'):
    # #     return None
    # # return find_page_editor_widget(widget.parent)


def find_workflow_widget(widget):
    from src.members.workflow import WorkflowSettings
    if isinstance(widget, WorkflowSettings):
        return widget
    if hasattr(widget, 'workflow_settings'):
        return widget.workflow_settings
    if not hasattr(widget, 'parent'):
        return None
    return find_workflow_widget(widget.parent)


def find_input_key(widget):
    if hasattr(widget, 'input_key'):
        return widget.input_key
    if not hasattr(widget, 'parent'):
        return None
    return find_input_key(widget.parent)


def find_attribute(widget, attribute, default=None):
    if hasattr(widget, attribute):
        return getattr(widget, attribute)
    if not hasattr(widget, 'parent'):
        return default
    return find_attribute(widget.parent, attribute)


class BreadcrumbWidget(QWidget):
    def __init__(self, parent, root_title=None):
        super().__init__(parent=parent)
        from src.gui.config import CHBoxLayout

        self.setFixedHeight(45)
        self.parent = parent
        self.main = find_main_widget(self)
        self.root_title = root_title

        self.back_button = IconButton(parent=self, icon_path=':/resources/icon-back.png', size=40)
        self.back_button.setStyleSheet("border-top-left-radius: 22px;")
        self.back_button.clicked.connect(self.go_back)

        self.title_layout = CHBoxLayout(self)
        self.title_layout.setSpacing(20)
        self.title_layout.setContentsMargins(0, 0, 10, 0)
        self.title_layout.addWidget(self.back_button)

        self.label = QLabel(root_title)
        self.font = QFont()
        self.font.setPointSize(15)
        self.label.setFont(self.font)

        self.title_layout.addWidget(self.label)

        self.edit_btn = IconButton(
            parent=self,
            icon_path=':/resources/icon-edit.png',
            tooltip='Edit this page'
        )
        self.edit_btn.setStyleSheet("border-top-left-radius: 22px;")
        self.edit_btn.clicked.connect(self.edit_page)
        self.edit_btn.hide()

        self.finish_btn = IconButton(
            parent=self,
            icon_path=':/resources/icon-tick.svg',
            tooltip='Finish editing'
        )
        self.finish_btn.setStyleSheet("border-top-left-radius: 22px;")
        self.finish_btn.clicked.connect(self.finish_edit)
        self.finish_btn.hide()

        self.title_layout.addWidget(self.edit_btn)
        self.title_layout.addWidget(self.finish_btn)

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
            self.main.page_chat.ensure_visible()

    def edit_page(self):
        module_id = find_attribute(self.parent, 'module_id')
        if not module_id:
            return

        page_widget = self.parent
        # setattr(page_widget, 'user_editing', True)
        if hasattr(page_widget, 'toggle_widget_edit'):
            page_widget.toggle_widget_edit(True)
            # page_widget.build_schema()  # !! #

        from src.gui.pages.modules import PageEditor
        main = find_main_widget(self)
        if getattr(main, 'module_popup', None):
            main.module_popup.close()
            main.module_popup = None
        main.module_popup = PageEditor(main, module_id)
        main.module_popup.load()
        main.module_popup.show()
        self.edit_btn.hide()

    def finish_edit(self):
        module_id = find_attribute(self.parent, 'module_id')
        if not module_id:
            return

        page_widget = self.parent
        # setattr(page_widget, 'user_editing', True)
        if hasattr(page_widget, 'toggle_widget_edit'):
            page_widget.toggle_widget_edit(False)
            # page_widget.build_schema()  # !! #

        from src.gui.pages.modules import PageEditor
        main = find_main_widget(self)
        if getattr(main, 'module_popup', None):
            main.module_popup.close()
            main.module_popup = None

        edit_bar = getattr(self.parent, 'edit_bar', None)
        if edit_bar:
            edit_bar.hide()

        self.finish_btn.hide()

    def enterEvent(self, event):
        user_editing = find_attribute(self.parent, 'user_editing', False)
        if user_editing:
            self.finish_btn.show()
            return

        can_edit = find_attribute(self.parent, 'module_id') is not None
        if can_edit:
            self.edit_btn.show()
            self.finish_btn.hide()

    def leaveEvent(self, event):
        # user_editing = find_attribute(self.parent, 'user_editing', False)
        # if user_editing:
        #     self.finish_btn.hide()
        #     return

        self.edit_btn.hide()


class IconButton(QPushButton):
    def __init__(
            self,
            parent,
            icon_path=None,
            hover_icon_path=None,
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
        self.pixmap = QPixmap(icon_path) if icon_path else QPixmap(0, 0)
        self.hover_pixmap = QPixmap(hover_icon_path) if hover_icon_path else None

        character_width = 8
        width = size + (len(text) * character_width if text else 0)
        icon_size = int(size * icon_size_percent)
        self.setFixedSize(width, size)
        self.setIconSize(QSize(icon_size, icon_size))
        self.setIconPixmap(self.pixmap)

        self.setAutoExclusive(False)  # To disable visual selection

        if tooltip:
            self.setToolTip(tooltip)

        if text:
            self.setText(text)

        if checkable:
            self.setCheckable(True)

    # def setIconPath(self, icon_path):
    #     self.pixmap = QPixmap(icon_path)
    #     self.setIconPixmap(self.pixmap)

    def setIconPixmap(self, pixmap=None, color=None):
        if not pixmap:
            pixmap = self.pixmap

        # self.pixmap = pixmap

        if self.colorize:
            pixmap = colorize_pixmap(pixmap, opacity=self.opacity, color=color)

        self.icon = QIcon(pixmap)
        self.setIcon(self.icon)

    def enterEvent(self, event):
        if self.hover_pixmap:
            self.setIconPixmap(self.hover_pixmap)
        super().enterEvent(event)

    def leaveEvent(self, event):
        if self.hover_pixmap:
            self.setIconPixmap(self.pixmap)
        super().leaveEvent(event)


class ToggleIconButton(IconButton):
    def __init__(self, **kwargs):
        self.icon_path = kwargs.get('icon_path', None)
        self.ttip = kwargs.get('tooltip', '')
        self.icon_path_checked = kwargs.pop('icon_path_checked', self.icon_path)
        self.tooltip_when_checked = kwargs.pop('tooltip_when_checked', None)
        self.color_when_checked = kwargs.pop('color_when_checked', None)
        super().__init__(**kwargs)
        self.setCheckable(True)
        self.clicked.connect(self.on_click)

    def on_click(self):
        self.refresh_icon()

    def setChecked(self, state):
        super().setChecked(state)
        self.refresh_icon()

    def refresh_icon(self):
        is_checked = self.isChecked()
        if self.icon_path_checked:
            pixmap = QPixmap(self.icon_path_checked if is_checked else self.icon_path)
            self.setIconPixmap(pixmap, color=self.color_when_checked if is_checked else None)
        if self.tooltip_when_checked:
            self.setToolTip(self.tooltip_when_checked if is_checked else self.ttip)


class FoldRegion:
    def __init__(self, startLine, endLine, parent=None):
        self.startLine = startLine
        self.endLine = endLine
        self.parent = parent
        self.children = []
        self.isFolded = False

    def __repr__(self):
        return f"<FoldRegion [{self.startLine}-{self.endLine}] folded={self.isFolded}>"


class FoldableDocumentLayout(QPlainTextDocumentLayout):
    def __init__(self, doc):
        super().__init__(doc)

    def blockBoundingRect(self, block):
        """
        Return a zero-height rect for folded blocks.
        """
        # Start with the normal bounding rect:
        rect = super().blockBoundingRect(block)

        # If the block is not visible (block.userState() or some custom check),
        # shrink rect to zero height
        if not block.isVisible():
            # Or check some property instead
            rect.setHeight(0)

        return rect

    def documentSize(self):
        """
        Compute the total bounding rectangle of all (visible) blocks.
        """
        width = 0
        yPos = 0
        block = self.document().firstBlock()

        while block.isValid():
            r = self.blockBoundingRect(block)
            # Because we might have set r.height=0 for folded blocks
            # we just accumulate each block's height
            yPos += r.height()
            width = max(width, r.width())
            # QPlainTextDocumentLayout accounts for line spacing, etc.
            # so you might need to factor that in as well.

            block = block.next()

        return QSizeF(width, yPos)


class CTextEdit(QPlainTextEdit):
    def __init__(self, gen_block_folder_name=None, fold_mode=None):
        super().__init__()
        self.foldRegions = []  # top-level fold regions
        self.text_editor = None
        self.setTabStopDistance(40)

        # Recompute fold regions whenever content changes
        self.document().blockCountChanged.connect(self.updateFoldRegions)
        self.textChanged.connect(self.updateFoldRegions)

        if gen_block_folder_name:
            self.wand_button = TextEnhancerButton(self, self, gen_block_folder_name=gen_block_folder_name)
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
        from src.gui.windows.text_editor import TextEditorWindow
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


class TextEnhancerButton(IconButton):
    on_enhancement_chunk_signal = Signal(str)
    enhancement_error_occurred = Signal(str)

    def __init__(self, parent, widget, gen_block_folder_name):
        super().__init__(parent=parent, size=22, icon_path=':/resources/icon-wand.png', tooltip='Enhance the text using a system block.')
        self.setProperty("class", "send")
        self.widget = widget

        self.gen_block_folder_name = gen_block_folder_name
        self.available_blocks = {}
        self.enhancing_text = ''

        self.enhancement_runnable = None
        self.on_enhancement_chunk_signal.connect(self.on_enhancement_chunk, Qt.QueuedConnection)
        self.enhancement_error_occurred.connect(self.on_enhancement_error, Qt.QueuedConnection)

        self.clicked.connect(self.on_click)

    def on_click(self):
        self.available_blocks = sql.get_results("""
            SELECT b.name, b.config
            FROM blocks b
            LEFT JOIN folders f ON b.folder_id = f.id
            WHERE f.name = ? AND f.locked = 1""", (self.gen_block_folder_name,), return_type='dict')
        if len(self.available_blocks) == 0:
            # display_message(self,
            #     # message=error,
            #     icon=QMessageBox.Warning,
            # )
            display_message_box(
                icon=QMessageBox.Warning,
                title="No supported blocks",
                text="No blocks found in designated folder, create one in the blocks page.",
                buttons=QMessageBox.Ok
            )
            return

        messagebox_input = self.widget.toPlainText().strip()
        if messagebox_input == '':
            display_message_box(
                icon=QMessageBox.Warning,
                title="No message found",
                text="Type a message in the message box to enhance.",
                buttons=QMessageBox.Ok
            )
            return

        menu = QMenu(self)
        for name in self.available_blocks.keys():
            action = menu.addAction(name)
            action.triggered.connect(partial(self.on_block_selected, name))

        menu.exec_(QCursor.pos())

    def on_block_selected(self, block_name):
        self.run_block(block_name)

    def run_block(self, block_name):
        self.enhancing_text = self.widget.toPlainText().strip()
        self.widget.clear()
        enhance_runnable = self.EnhancementRunnable(self, block_name)
        main = find_main_widget(self)
        main.threadpool.start(enhance_runnable)

    class EnhancementRunnable(QRunnable):
        def __init__(self, parent, block_name):
            super().__init__()
            self.parent = parent
            self.block_name = block_name

        def run(self):
            asyncio.run(self.enhance_text())

        async def enhance_text(self):
            from src.system.base import manager
            try:
                no_output = True
                params = {'INPUT': self.parent.enhancing_text}
                async for key, chunk in manager.blocks.receive_block(self.block_name, params=params):
                    self.parent.on_enhancement_chunk_signal.emit(chunk)
                    no_output = False

                if no_output:
                    self.parent.on_enhancement_error.emit('No output from block')
            except Exception as e:
                self.parent.enhancement_error_occurred.emit(str(e))

    @Slot(str)
    def on_enhancement_chunk(self, chunk):
        self.widget.insertPlainText(chunk)
        # Press key to call resize
        self.widget.keyPressEvent(QKeyEvent(QEvent.KeyPress, Qt.Key.Key_End, Qt.KeyboardModifier.NoModifier))
        self.widget.verticalScrollBar().setValue(self.widget.verticalScrollBar().maximum())

    @Slot(str)
    def on_enhancement_error(self, error_message):
        self.widget.setPlainText(self.enhancing_text)
        self.enhancing_text = ''
        display_message_box(
            icon=QMessageBox.Warning,
            title="Enhancement error",
            text=f"An error occurred while enhancing the text: {error_message}",
            buttons=QMessageBox.Ok
        )

def colorize_pixmap(pixmap, opacity=1.0, color=None):
    from src.gui.style import TEXT_COLOR
    colored_pixmap = QPixmap(pixmap.size())
    colored_pixmap.fill(Qt.transparent)

    painter = QPainter(colored_pixmap)
    painter.setCompositionMode(QPainter.CompositionMode_Source)
    painter.drawPixmap(0, 0, pixmap)
    painter.setOpacity(opacity)
    painter.setCompositionMode(QPainter.CompositionMode_SourceIn)

    painter.fillRect(colored_pixmap.rect(), TEXT_COLOR if not color else color)
    painter.end()

    return colored_pixmap


class BaseComboBox(QComboBox):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.current_pin_state = None
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
        elif self.combo_type == 'RoleComboBox':
            combo = RoleComboBox(parent)
        elif self.combo_type == 'ModuleComboBox':
            combo = ModuleComboBox(parent)
        else:
            raise NotImplementedError('Combo type not implemented')

        if self.default:
            index = combo.findText(self.default)
            combo.setCurrentIndex(index)

        combo.currentIndexChanged.connect(self.commitAndCloseEditor)
        return combo

    def setEditorData(self, editor, index):
        value = index.model().data(index, Qt.EditRole)
        if isinstance(editor, RoleComboBox) or isinstance(editor, ModuleComboBox):
            data_index = editor.findData(value)
            if data_index >= 0:
                editor.setCurrentIndex(data_index)
            else:
                editor.setCurrentIndex(0)
        else:
            editor.setCurrentText(value)
        editor.showPopup()

    def setModelData(self, editor, model, index):
        if isinstance(editor, RoleComboBox) or isinstance(editor, ModuleComboBox):
            value = editor.currentData()
        else:
            value = editor.currentText()
        model.setData(index, value, Qt.EditRole)

    def commitAndCloseEditor(self):
        editor = self.sender()
        self.commitData.emit(editor)
        self.closeEditor.emit(editor)

    def eventFilter(self, editor, event):
        if event.type() == QEvent.MouseButtonPress:
            editor.showPopup()
        return super(ComboBoxDelegate, self).eventFilter(editor, event)


class CheckBoxDelegate(QStyledItemDelegate):
    def __init__(self, parent=None):
        super().__init__(parent)

    def paint(self, painter, option, index):
        self.initStyleOption(option, index)
        if index.column() == 1:  # Checkbox column
            option.features |= option.HasCheckIndicator
            option.state |= option.State_Enabled
            option.checkState = index.data(Qt.CheckStateRole)
        QStyledItemDelegate.paint(self, painter, option, index)

    def editorEvent(self, event, model, option, index):
        if index.column() == 1 and event.type() in [event.MouseButtonRelease, event.MouseButtonDblClick]:
            current_state = index.data(Qt.CheckStateRole)
            new_state = Qt.Checked if current_state != Qt.Checked else Qt.Unchecked
            model.setData(index, new_state, Qt.CheckStateRole)
            return True
        return False


class BaseTreeWidget(QTreeWidget):
    def __init__(self, parent, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.parent = parent
        self.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.setSelectionMode(QAbstractItemView.SingleSelection)
        self.folder_items_mapping = {None: self}

        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)

        self.apply_stylesheet()

        header = self.header()
        header.setDefaultAlignment(Qt.AlignLeft)
        header.setStretchLastSection(False)
        header.setDefaultSectionSize(100)

        self.row_height = kwargs.get('row_height', 20)
        # set default row height


        # Enable drag and drop
        self.setDragEnabled(True)
        self.setAcceptDrops(True)
        self.setDropIndicatorShown(True)

        self.setDragDropMode(QTreeWidget.InternalMove)
        self.header().sectionResized.connect(self.update_tooltips)

    # Connect signal to handle resizing of the headers, and call the function once initially

    def drawBranches(self, painter, rect, index):
        item = self.itemFromIndex(index)
        if item.childCount() > 0:
            icon = ':/resources/icon-expanded-solid.png' if item.isExpanded() else ':/resources/icon-collapsed-solid.png'
            icon = colorize_pixmap(path_to_pixmap(icon, diameter=10))
            indent = self.indentation() * self.getDepth(item)
            painter.drawPixmap(rect.left() + 7 + indent, rect.top() + 7, icon)
        else:
            super().drawBranches(painter, rect, index)
        # pass

    def getDepth(self, item):
        depth = 0
        while item.parent() is not None:
            item = item.parent()
            depth += 1
        return depth

    def build_columns_from_schema(self, schema):
        self.setColumnCount(len(schema))
        # add columns to tree from schema list
        for i, header_dict in enumerate(schema):
            column_type = header_dict.get('type', str)
            column_visible = header_dict.get('visible', True)
            column_width = header_dict.get('width', None)
            column_stretch = header_dict.get('stretch', None)
            wrap_text = header_dict.get('wrap_text', False)

            combo_widgets = ['EnvironmentComboBox', 'RoleComboBox', 'ModuleComboBox']
            is_combo_column = isinstance(column_type, tuple) or column_type in combo_widgets
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

    def load(self, data, **kwargs):
        folder_key = kwargs.get('folder_key', None)
        select_id = kwargs.get('select_id', None)
        silent_select_id = kwargs.get('silent_select_id', None)  # todo dirty
        init_select = kwargs.get('init_select', False)
        readonly = kwargs.get('readonly', False)
        schema = kwargs.get('schema', [])
        append = kwargs.get('append', False)
        group_folders = kwargs.get('group_folders', False)
        default_item_icon = kwargs.get('default_item_icon', None)

        current_selected_id = self.get_selected_item_id()
        if not select_id and current_selected_id:
            select_id = current_selected_id

        kind = self.parent.filter_widget.get_kind() if hasattr(self.parent, 'filter_widget') else getattr(self.parent, 'kind', None)
        folder_key = folder_key.get(kind, None) if isinstance(folder_key, dict) else folder_key
        folders_data = None
        if folder_key:
            folder_query = """
                SELECT 
                    id, 
                    name, 
                    parent_id, 
                    json_extract(config, '$.icon_path'),
                    type, 
                    expanded, 
                    ordr 
                FROM folders 
                WHERE `type` = ?
                ORDER BY locked DESC, pinned DESC, ordr, name
            """
            folders_data = sql.get_results(query=folder_query, params=(folder_key,))

        with block_signals(self):
            if not append:
                self.clear()
                # Load folders
                self.folder_items_mapping = {None: self}
                while folders_data:
                    for folder_id, name, parent_id, icon_path, folder_type, expanded, order in list(folders_data):
                        if parent_id in self.folder_items_mapping:
                            parent_item = self.folder_items_mapping[parent_id]
                            folder_item = QTreeWidgetItem(parent_item, [str(name), str(folder_id)])
                            folder_item.setData(0, Qt.UserRole, 'folder')
                            use_icon_path = icon_path or ':/resources/icon-folder.png'
                            folder_pixmap = colorize_pixmap(QPixmap(use_icon_path))
                            folder_item.setIcon(0, QIcon(folder_pixmap))
                            self.folder_items_mapping[folder_id] = folder_item
                            folders_data.remove((folder_id, name, parent_id, icon_path, folder_type, expanded, order))
                            expand = (expanded == 1)
                            folder_item.setExpanded(expand)

            col_name_list = [header_dict.get('key', header_dict['text']) for header_dict in schema]
            # Load items
            for r, row_data in enumerate(data):
                parent_item = self
                if folder_key is not None:
                    folder_id = row_data[-1]
                    parent_item = self.folder_items_mapping.get(folder_id) if folder_id else self

                if len(row_data) > len(schema):
                    row_data = row_data[:-1]  # remove folder_id

                item = QTreeWidgetItem(parent_item, [str(v) for v in row_data])
                field_dict = {col_name_list[i]: row_data[i] for i in range(len(row_data))}
                item.setData(0, Qt.UserRole, field_dict)

                if not readonly:
                    item.setFlags(item.flags() | Qt.ItemIsEditable)
                else:
                    item.setFlags(item.flags() & ~Qt.ItemIsEditable)

                if default_item_icon:
                    pixmap = colorize_pixmap(QPixmap(default_item_icon))
                    item.setIcon(0, QIcon(pixmap))

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
                        if image_key == 'config':
                            config_index = [i for i, d in enumerate(schema) if d.get('key', d['text']) == 'config'][0]
                            config_dict = json.loads(row_data[config_index])
                            image_paths_list = get_avatar_paths_from_config(config_dict)
                        else:
                            image_index = [i for i, d in enumerate(schema) if d.get('key', d['text']) == image_key][0]
                            image_paths = row_data[image_index] or ''
                            image_paths_list = image_paths.split('//##//##//')
                        pixmap = path_to_pixmap(image_paths_list, diameter=25)
                        item.setIcon(i, QIcon(pixmap))

                        is_encrypted = col_schema.get('encrypt', False)
                        if is_encrypted:
                            pass
                            # todo

            if group_folders:
                for i in range(self.topLevelItemCount()):
                    item = self.topLevelItem(i)
                    if item is None:
                        continue
                    self.group_nested_folders(item)
                    self.delete_empty_folders(item)

            self.update_tooltips()
            if silent_select_id:
                self.select_items_by_id(silent_select_id)

        pass
        if init_select and self.topLevelItemCount() > 0:
            if select_id:
                self.select_items_by_id(select_id)
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

        row_data = next((row for row in data if row[1] == current_id), None)
        if row_data:
            if len(row_data) > len(schema):
                row_data = row_data[:-1]  # remove folder_id

            item = self.currentItem()
            # set values for each column in item
            for i in range(len(row_data)):
                item.setText(i, str(row_data[i]))

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

    def apply_stylesheet(self):
        from src.gui.style import TEXT_COLOR
        palette = self.palette()
        palette.setColor(QPalette.Highlight, apply_alpha_to_hex(TEXT_COLOR, 0.05))
        palette.setColor(QPalette.HighlightedText, apply_alpha_to_hex(TEXT_COLOR, 0.80))
        palette.setColor(QPalette.Text, QColor(TEXT_COLOR))
        palette.setColor(QPalette.ColorRole.Button, QColor(TEXT_COLOR))
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
        with block_signals(self):
            for i in range(self.topLevelItemCount()):
                update_item_tooltips(self, self.topLevelItem(i))

    def get_selected_item_id(self):  # todo clean
        item = self.currentItem()
        if not item:
            return None
        tag = item.data(0, Qt.UserRole)
        if tag == 'folder':
            return None
        id = item.text(1)
        if id.isdigit():
            return int(item.text(1))
        if id == 'None':
            return None
        return id

    def get_selected_item_ids(self):  # todo merge with above
        sel_item_ids = []
        for item in self.selectedItems():
            if item.data(0, Qt.UserRole) != 'folder':
                sel_item_ids.append(int(item.text(1)))
        return sel_item_ids

    def get_selected_folder_id(self):
        item = self.currentItem()
        if not item:
            return None
        tag = item.data(0, Qt.UserRole)
        if tag != 'folder':
            return None
        return int(item.text(1))

    def select_items_by_id(self, ids):
        if not isinstance(ids, list):
            ids = [str(ids)]
        # map id ints to strings
        ids = [str(i) for i in ids]

        def select_recursive(item):
            item_in_ids = item.text(1) in ids
            item.setSelected(item_in_ids)

            if item_in_ids:
                self.scrollToItem(item)
                self.setCurrentItem(item)

            for child_index in range(item.childCount()):
                select_recursive(item.child(child_index))

        with block_signals(self):
            for i in range(self.topLevelItemCount()):
                select_recursive(self.topLevelItem(i))

        if hasattr(self.parent, 'on_item_selected'):
            self.parent.on_item_selected()

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

        if dragging_type == 'folder':
            is_locked = sql.get_scalar(f"""SELECT locked FROM folders WHERE id = ?""", (dragging_id,)) or False
            if is_locked == 1:
                event.ignore()
                return

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
            folder_id = target_item_parent.text(1) if target_item_parent else None

            dragging_item_parent = dragging_item.parent() if dragging_item else None
            dragging_item_parent_id = dragging_item_parent.text(1) if dragging_item_parent else None

            if folder_id == dragging_item_parent_id:
                display_message(self, 'Reordering is not implemented yet', 'Error', QMessageBox.Warning)
                event.ignore()
                return

        elif can_drop:
            folder_id = target_item.text(1)
        else:
            event.ignore()
            return

        if dragging_type == 'folder':
            self.update_folder_parent(dragging_id, folder_id)
        else:
            self.update_item_folder(dragging_id, folder_id)

    def setItemIconButtonColumn(self, item, column, icon, func):
        btn_chat = QPushButton('')
        btn_chat.setIcon(icon)
        btn_chat.setIconSize(QSize(25, 25))
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
        if hasattr(self.parent, 'on_edited'):
            self.parent.on_edited()
        self.parent.load()
        # expand the folder
        for i in range(self.topLevelItemCount()):
            item = self.topLevelItem(i)
            if item.text(1) == to_folder_id:
                item.setExpanded(True)
                break

    def update_item_folder(self, dragging_item_id, to_folder_id):
        sql.execute(f"UPDATE `{self.parent.table_name}` SET folder_id = ? WHERE id = ?", (to_folder_id, dragging_item_id))
        if hasattr(self.parent, 'on_edited'):
            self.parent.on_edited()
        self.parent.load()
        # expand the folder
        for i in range(self.topLevelItemCount()):
            item = self.topLevelItem(i)
            if item.text(1) == to_folder_id:
                item.setExpanded(True)
                break

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.RightButton and hasattr(self.parent, 'show_context_menu'):
            self.parent.show_context_menu()
            # return
        elif event.button() == Qt.LeftButton:
            item = self.itemAt(event.pos())
            if item:
                col = self.columnAt(event.pos().x())
                # Check if the delegate for this column is an instance of ComboBoxDelegate
                delegate = self.itemDelegateForColumn(col)
                if isinstance(delegate, ComboBoxDelegate):
                    # force the item into edit mode
                    self.editItem(item, col)
            else:
                main = find_main_widget(self)
                main.mouseReleaseEvent(event)
                return True  # Event handled

        super().mouseReleaseEvent(event)

    def mousePressEvent(self, event):
        super().mousePressEvent(event)
        main = find_main_widget(self)
        if not main:
            return
        if event.button() == Qt.LeftButton:
            item = self.itemAt(event.pos())
            if item is None:
                main.mousePressEvent(event)
                return True  # Event handled

    def mouseMoveEvent(self, event):
        main = find_main_widget(self)
        if not main:
            return
        super().mouseMoveEvent(event)
        main.mouseMoveEvent(event)

    def keyPressEvent(self, event):
        # delete button press
        super().keyPressEvent(event)
        if event.key() == Qt.Key_Delete and hasattr(self.parent, 'delete_item'):
            self.parent.delete_item()


class CircularImageLabel(QLabel):
    clicked = Signal()
    avatarChanged = Signal()

    def __init__(self, *args, diameter=50, **kwargs):
        super().__init__(*args, **kwargs)
        from src.gui.style import TEXT_COLOR
        self.avatar_path = None
        self.setAlignment(Qt.AlignCenter)
        self.setCursor(Qt.PointingHandCursor)
        radius = int(diameter / 2)
        self.setFixedSize(diameter, diameter)
        self.setStyleSheet(
            f"border: 1px dashed {TEXT_COLOR}; border-radius: {str(radius)}px;")  # A custom style for the empty label
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
        if not pixmap:  # todo
            return
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
        # self.setFixedSize(24, 24)
        self.setFixedWidth(24)
        self.setProperty('class', 'color-picker')
        self.setStyleSheet(f"background-color: white; border: 1px solid {apply_alpha_to_hex(TEXT_COLOR, 0.20)};")
        self.clicked.connect(self.pick_color)

    def pick_color(self):
        from src.gui.style import TEXT_COLOR
        current_color = self.color if self.color else Qt.white
        color_dialog = QColorDialog()
        with block_pin_mode():
            # show alpha channel
            color = color_dialog.getColor(current_color, parent=self, options=QColorDialog.ShowAlphaChannel)

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
        return self.color.name(QColor.HexArgb) if self.color and self.color.isValid() else None


class PluginComboBox(BaseComboBox):
    def __init__(self, plugin_type, centered=False, none_text="Choose Plugin"):
        super().__init__()
        self.none_text = none_text
        self.plugin_type = plugin_type
        self.centered = centered

        if centered:
            self.setItemDelegate(AlignDelegate(self))
            self.setStyleSheet(
                "QComboBox::drop-down {border-width: 0px;} QComboBox::down-arrow {image: url(noimg); border-width: 0px;}")

        self.load()

    def load(self):
        from src.system.plugins import ALL_PLUGINS

        self.clear()
        if self.none_text:
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
                    ORDER BY a.pinned DESC, a.ordr, a.name
                """, self.with_model_kinds)
            else:
                apis = sql.get_results("SELECT name, id FROM apis ORDER BY name")

            if self.first_item:
                self.addItem(self.first_item, 0)
            for api in apis:
                self.addItem(api[0], api[1])


class EnvironmentComboBox(BaseComboBox):
    def __init__(self, *args, **kwargs):
        self.first_item = kwargs.pop('first_item', None)
        super().__init__(*args, **kwargs)
        # self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.load()

    def load(self):
        with block_signals(self):
            self.clear()
            models = sql.get_results("SELECT name, id FROM environments ORDER BY name")
            for model in models:
                self.addItem(model[0], model[1])


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
            ok = display_message_box(
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
                display_message(
                    self,
                    message='The name `default` is reserved and cannot be used.',
                    icon=QMessageBox.Warning,
                )
                self.reset_index()
                return
            manager.venvs.create_venv(text)
            self.load()
            self.set_key(text)
        else:
            self.current_key = key

    def reset_index(self):
        current_key_index = self.findData(self.current_key)
        has_items = self.count() - 1 > 0  # -1 for <new> item
        if current_key_index >= 0 and has_items:
            self.setCurrentIndex(current_key_index)
        else:
            self.set_key(self.current_key)


class RoleComboBox(BaseComboBox):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.load()
        self.currentIndexChanged.connect(self.on_index_changed)

    def load(self):
        with block_signals(self):
            self.clear()
            roles = sql.get_results("SELECT name FROM roles", return_type='list')
            for role in roles:
                self.addItem(role.title(), role)
            # add a 'New Role' option
            self.addItem('< New >', '<NEW>')

    def on_index_changed(self, index):
        if self.itemData(index) == '<NEW>':
            new_role, ok = QInputDialog.getText(self, "New Role", "Enter the name for the new role:")
            if ok and new_role:
                sql.execute("INSERT INTO roles (name) VALUES (?)", (new_role.lower(),))

                self.load()

                new_index = self.findText(new_role.title())
                if new_index != -1:
                    self.setCurrentIndex(new_index)
            else:
                # If dialog was cancelled or empty input, revert to previous selection
                self.setCurrentIndex(self.findData('<NEW>') - 1)


class WorkspaceTypeComboBox(BaseComboBox):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.load()
        # self.currentIndexChanged.connect(self.on_index_changed)

    def load(self):
        with block_signals(self):
            self.clear()
            roles = sql.get_results("SELECT name FROM workspace_types", return_type='list')
            for role in roles:
                self.addItem(role.title(), role)
            # add a 'New Role' option
            # self.addItem('< New >', '<NEW>')

    # def on_index_changed(self, index):
    #     if self.itemData(index) == '<NEW>':
    #         new_role, ok = QInputDialog.getText(self, "New Type", "Enter the name for the new workspace type:")
    #         if ok and new_role:
    #             sql.execute("INSERT INTO roles (name) VALUES (?)", (new_role.lower(),))
    #
    #             self.load()
    #
    #             new_index = self.findText(new_role.title())
    #             if new_index != -1:
    #                 self.setCurrentIndex(new_index)
    #         else:
    #             # If dialog was cancelled or empty input, revert to previous selection
    #             self.setCurrentIndex(self.findData('<NEW>') - 1)


class InputSourceComboBox(QWidget):
    currentIndexChanged = Signal(int)
    def __init__(self, parent):
        super().__init__(parent)
        self.parent = parent
        self.source_member_id, _ = find_input_key(self)

        from src.gui.config import CVBoxLayout
        self.layout = CVBoxLayout(self)

        self.main_combo = self.SourceComboBox(self)
        self.output_combo = self.SourceOutputOptions(self)
        self.structure_combo = self.SourceStructureOptions(self)

        # self.main_combo.setCur

        self.layout.addWidget(self.main_combo)
        self.layout.addWidget(self.output_combo)
        self.layout.addWidget(self.structure_combo)

        self.main_combo.currentIndexChanged.connect(self.on_main_combo_index_changed)
        self.output_combo.currentIndexChanged.connect(self.on_main_combo_index_changed)
        self.structure_combo.currentIndexChanged.connect(self.on_main_combo_index_changed)

        self.load()

    def on_main_combo_index_changed(self):
        # Emit our own signal when the main_combo's index changes
        print('on_main_combo_index_changed()')
        index = self.main_combo.currentIndex()
        self.currentIndexChanged.emit(index)
        self.update_visibility()

    def load(self):
        print('load()')
        with block_signals(self):
            self.main_combo.load()
            self.output_combo.load()
        self.update_visibility()
        self.currentIndexChanged.emit(self.currentIndex())

    def update_visibility(self):
        print('update_visibility()')
        source_type = self.main_combo.currentText()
        self.output_combo.setVisible(False)
        self.structure_combo.setVisible(False)
        if source_type == 'Output':
            self.output_combo.setVisible(True)
        elif source_type == 'Structure':
            self.structure_combo.setVisible(True)

    def get_structure_sources(self):
        workflow = find_workflow_widget(self)
        source_member = workflow.members_in_view[self.source_member_id]
        source_member_config = source_member.member_config
        source_member_type = source_member_config.get('_TYPE', 'agent')

        structure = []
        if source_member_type == 'agent':
            model_obj = convert_model_json_to_obj(source_member_config.get('chat.model', {}))
            source_member_model_params = model_obj.get('model_params', {})
            structure_data = source_member_model_params.get('structure.data', [])
            structure.extend([p['attribute'] for p in structure_data])

        elif source_member_type == 'block':
            block_type = source_member_config.get('block_type', 'Text')
            if block_type == 'Prompt':
                model_obj = convert_model_json_to_obj(source_member_config.get('prompt_model', {}))
                source_member_model_params = model_obj.get('model_params', {})
                structure_data = source_member_model_params.get('structure.data', [])
                structure.extend([p['attribute'] for p in structure_data])

        return structure

    def setCurrentIndex(self, index):
        print('setCurrentIndex()')
        self.main_combo.setCurrentIndex(index)
        self.update_visibility()
        # if self.output_combo.isVisible():
        #     self.output_combo.setCurrentIndex(0)
        # if self.structure_combo.isVisible():
        #     self.structure_combo.setCurrentIndex(0)

    def currentIndex(self):
        print('currentIndex()')
        return self.main_combo.currentIndex()

    def currentData(self):
        print('currentData()')
        return self.main_combo.currentText()

    def itemData(self, index):
        print('itemData()')
        return self.main_combo.itemData(index)

    def findData(self, data):
        print('findData()')
        return self.main_combo.findData(data)

    def current_options(self):
        if self.output_combo.isVisible():
            return self.output_combo.currentData()
        else:
            return self.structure_combo.currentData()

    def set_options(self, source_type, options):
        if source_type == 'Output':
            # self.structure_combo.setVisible(False)
            # self.output_combo.setVisible(True)
            index = self.output_combo.findData(options)
            if index != -1:
                self.output_combo.setCurrentIndex(index)
            else:
                self.output_combo.setCurrentIndex(0)
                self.on_main_combo_index_changed()
        elif source_type == 'Structure':
            # self.output_combo.setVisible(False)
            # self.structure_combo.setVisible(True)
            index = self.structure_combo.findData(options)
            if index != -1:
                self.structure_combo.setCurrentIndex(index)
            else:
                self.structure_combo.setCurrentIndex(0)
                self.on_main_combo_index_changed()

    class SourceComboBox(BaseComboBox):
        def __init__(self, parent):
            super().__init__(parent)
            self.parent = parent
            self.load()

        def showPopup(self):
            # self.load()
            super().showPopup()

        def load(self):
            print('SourceComboBox.load()')
            allowed_outputs = ['Output']
            structure = self.parent.get_structure_sources()
            if len(structure) > 0:
                allowed_outputs.append('Structure')

            with block_signals(self):
                self.clear()
                for output in allowed_outputs:
                    # if not already in the combobox
                    if output not in [self.itemText(i) for i in range(self.count())]:
                        self.addItem(output, output)

    class SourceOutputOptions(BaseComboBox):
        def __init__(self, parent):
            super().__init__(parent)
            self.parent = parent
            self.load()

        def showPopup(self):
            # self.load()
            super().showPopup()

        def load(self):
            print('SourceOutputOptions.load()')
            roles = sql.get_results("SELECT name FROM roles", return_type='list')
            with block_signals(self):
                self.clear()
                self.addItem('  Any role', '<ANY>')
                for role in roles:
                    self.addItem(f'  {role.title()}', role)

    class SourceStructureOptions(BaseComboBox):
        def __init__(self, parent):
            super().__init__(parent)
            self.parent = parent
            self.load()

        def showPopup(self):
            # self.load()
            super().showPopup()

        def load(self):
            print('SourceStructureOptions.load()')
            structure = self.parent.get_structure_sources()
            with block_signals(self):
                self.clear()
                for s in structure:
                    self.addItem(f'  {s}', s)


class InputTargetComboBox(QWidget):
    currentIndexChanged = Signal(int)
    def __init__(self, parent):
        super().__init__(parent)
        self.parent = parent
        _, self.target_member_id = find_input_key(self)

        from src.gui.config import CVBoxLayout
        self.layout = CVBoxLayout(self)
        self.main_combo = self.TargetComboBox(self)
        self.layout.addWidget(self.main_combo)

        self.main_combo.currentIndexChanged.connect(self.on_main_combo_index_changed)

        self.load()

    def on_main_combo_index_changed(self, index):
        # Emit our own signal when the main_combo's index changes
        self.currentIndexChanged.emit(index)
        self.update_visibility()

    def load(self):
        with block_signals(self):
            self.main_combo.load()
        self.update_visibility()
        self.currentIndexChanged.emit(self.currentIndex())

    def update_visibility(self):
        pass

    def setCurrentIndex(self, index):
        self.main_combo.setCurrentIndex(index)

    def currentIndex(self):
        return self.main_combo.currentIndex()

    def currentData(self):
        return self.main_combo.currentText()

    def itemData(self, index):
        return self.main_combo.itemData(index)

    def findData(self, data):
        return self.main_combo.findData(data)

    def current_options(self):
        return None

    class TargetComboBox(BaseComboBox):
        def __init__(self, parent):
            super().__init__(parent)
            self.parent = parent
            self.load()

        def showPopup(self):
            # self.load()
            super().showPopup()

        def load(self):
            workflow = find_workflow_widget(self)
            target_member = workflow.members_in_view[self.parent.target_member_id]
            target_member_config = target_member.member_config
            target_member_type = target_member_config.get('_TYPE', 'agent')

            allowed_inputs = []
            if target_member_type == 'workflow':
                target_workflow_first_member = next(iter(sorted(target_member_config.get('members', []),
                                                 key=lambda x: x['loc_x'])),
                                               None)
                if target_workflow_first_member:
                    first_member_is_user = target_workflow_first_member['config'].get('_TYPE', 'agent') == 'user'
                    if first_member_is_user:  # todo de-dupe
                        allowed_inputs = ['Message']

            elif target_member_type == 'agent' or target_member_type == 'user':
                allowed_inputs = ['Message']

            with block_signals(self):
                self.clear()
                for inp in allowed_inputs:
                    if inp not in [self.itemText(i) for i in range(self.count())]:
                        self.addItem(inp, inp)


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


class ModuleComboBox(BaseComboBox):
    def __init__(self, *args, **kwargs):
        self.first_item = kwargs.pop('first_item', None)
        super().__init__(*args, **kwargs)
        self.load()

    def load(self):
        with block_signals(self):
            pages_module_folder_id = sql.get_scalar("""
                SELECT id
                FROM folders
                WHERE name = 'Pages'
                    AND type = 'modules'
            """)  # todo de-deupe
            self.clear()
            if pages_module_folder_id:
                models = sql.get_results("SELECT name, id FROM modules ORDER BY name")
                for model in models:
                    self.addItem(model[0], model[1])
            self.addItem('< New Module >', '<NEW>')


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


class TreeDialog(QDialog):
    def __init__(self, parent, *args, **kwargs):
        super().__init__(parent=parent)
        self.parent = parent
        self.setWindowFlag(Qt.WindowMinimizeButtonHint, False)
        self.setWindowFlag(Qt.WindowMaximizeButtonHint, False)

        self.setWindowTitle(kwargs.get('title', ''))
        self.list_type = kwargs.get('list_type')
        self.callback = kwargs.get('callback', None)
        multiselect = kwargs.get('multiselect', False)
        show_blank = kwargs.get('show_blank', False)

        layout = QVBoxLayout(self)
        self.tree_widget = BaseTreeWidget(self)
        self.tree_widget.setDragDropMode(QAbstractItemView.NoDragDrop)
        self.tree_widget.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        layout.addWidget(self.tree_widget)

        if self.list_type == 'AGENT' or self.list_type == 'USER':
            def_avatar = ':/resources/icon-agent-solid.png' if self.list_type == 'AGENT' else ':/resources/icon-user.png'
            col_name_list = ['name', 'id', 'config']
            empty_member_label = 'Empty agent' if self.list_type == 'AGENT' else 'You'
            folder_key = 'agents' if self.list_type == 'AGENT' else 'users'
            query = f"""
                SELECT 
                    name, 
                    uuid, 
                    config,
                    folder_id
                FROM (
                    SELECT
                        e.id,
                        e.name,
                        e.uuid,
                        e.config,
                        e.folder_id
                    FROM entities e
                    WHERE kind = '{self.list_type}'
                )
                ORDER BY id DESC"""
        elif self.list_type == 'TOOL':
            def_avatar = ':/resources/icon-tool.png'
            col_name_list = ['name', 'id', 'config']
            empty_member_label = None
            folder_key = 'tools'
            query = """
                SELECT
                    name,
                    uuid as id,
                    '{}' as config,
                    folder_id
                FROM tools
                ORDER BY name"""

        elif self.list_type == 'MODULE':
            def_avatar = ':/resources/icon-jigsaw-solid.png'
            col_name_list = ['name', 'id', 'config']
            empty_member_label = None
            folder_key = 'modules'
            query = """
                SELECT
                    name,
                    uuid as id,
                    '{}' as config,
                    folder_id
                FROM modules
                ORDER BY name"""

        elif self.list_type == 'BLOCK':
            def_avatar = ':/resources/icon-blocks.png'
            col_name_list = ['block', 'id', 'config']
            empty_member_label = None
            folder_key = 'blocks'
            query = f"""
                SELECT
                    name,
                    uuid,
                    COALESCE(json_extract(config, '$.members[0].config'), config) as config,
                    folder_id
                FROM blocks
                WHERE (json_array_length(json_extract(config, '$.members')) = 1
                    OR json_type(json_extract(config, '$.members')) IS NULL)
                ORDER BY name"""

        elif self.list_type == 'TEXT':
            def_avatar = ':/resources/icon-blocks.png'
            col_name_list = ['block', 'id', 'config']
            empty_member_label = 'Empty text block'
            folder_key = 'blocks'
            query = f"""
                SELECT
                    name,
                    id,
                    COALESCE(json_extract(config, '$.members[0].config'), config) as config,
                    folder_id
                FROM blocks
                WHERE (json_array_length(json_extract(config, '$.members')) = 1
                    OR json_type(json_extract(config, '$.members')) IS NULL)
                    AND COALESCE(json_extract(config, '$.block_type'), 'Text') = 'Text'
                ORDER BY name"""

        elif self.list_type == 'PROMPT':
            def_avatar = ':/resources/icon-brain.png'
            col_name_list = ['block', 'id', 'config']
            empty_member_label = 'Empty prompt block'
            folder_key = 'blocks'
            # extract members[0] of workflow `block_type` when `members` is not null
            query = f"""
                SELECT
                    name,
                    id,
                    COALESCE(json_extract(config, '$.members[0].config'), config) as config,
                    folder_id
                FROM blocks
                WHERE (json_array_length(json_extract(config, '$.members')) = 1
                    OR json_type(json_extract(config, '$.members')) IS NULL)
                    AND json_extract(config, '$.block_type') = 'Prompt'
                ORDER BY name"""

        elif self.list_type == 'CODE':
            def_avatar = ':/resources/icon-code.png'
            col_name_list = ['block', 'id', 'config']
            empty_member_label = 'Empty code block'
            folder_key = 'blocks'
            query = f"""
                SELECT
                    name,
                    id,
                    COALESCE(json_extract(config, '$.members[0].config'), config) as config,
                    folder_id
                FROM blocks
                WHERE (json_array_length(json_extract(config, '$.members')) = 1
                    OR json_type(json_extract(config, '$.members')) IS NULL)
                    AND json_extract(config, '$.block_type') = 'Code'
                ORDER BY name"""
        else:
            raise NotImplementedError(f'List type {self.list_type} not implemented')

        column_schema = [
            {
                'text': 'Name',
                'key': 'name',
                'type': str,
                'stretch': True,
                'image_key': 'config' if self.list_type == 'AGENT' else None,
            },
            {
                'text': 'id',
                'key': 'id',
                'type': int,
                'visible': False,
            },
            {
                'text': 'config',
                'type': str,
                'visible': False,
            },
        ]
        self.tree_widget.build_columns_from_schema(column_schema)
        self.tree_widget.setHeaderHidden(True)

        data = sql.get_results(query)
        if empty_member_label is not None and show_blank:
            if self.list_type == 'WORKFLOW':
                pass
            if self.list_type in ['CODE', 'TEXT', 'PROMPT', 'MODULE']:
                empty_config_str = f"""{{"_TYPE": "block", "block_type": "{self.list_type.capitalize()}"}}"""
            elif self.list_type == 'AGENT':
                empty_config_str = "{}"
            else:
                empty_config_str = f"""{{"_TYPE": "{self.list_type.lower()}"}}"""

            data.insert(0, (empty_member_label, '', empty_config_str, None))

        self.tree_widget.load(
            data=data,
            folder_key=folder_key,
            schema=column_schema,
            readonly=True,
            default_item_icon=def_avatar,
        )

        # if self.list_type == 'MODULE':
        #
        #     pd = get_page_definitions(with_ids=True)
        #     pages_module_folder_id = sql.get_scalar("""
        #         SELECT id
        #         FROM folders
        #         WHERE name = 'Pages'
        #             AND type = 'modules'
        #     """)  # todo de-deupe
        #
        #     # extra_data = [('jj', 'dhs787dhus', int(pages_module_folder_id))]
        #     extra_data = [(name, id, int(pages_module_folder_id)) for id, name in pd.keys() if id is None]
        #
        #     with block_signals(self):
        #         for r, row_data in enumerate(extra_data):
        #             parent_item = self
        #             if folder_key is not None:
        #                 folder_id = row_data[-1]
        #                 parent_item = self.tree_widget.folder_items_mapping.get(folder_id) if folder_id else self
        #
        #             if len(row_data) > len(column_schema):
        #                 row_data = row_data[:-1]  # remove folder_id
        #
        #             item = QTreeWidgetItem(parent_item, [str(v) for v in row_data])
        #             field_dict = {col_name_list[i]: row_data[i] for i in range(len(row_data))}
        #             item.setData(0, Qt.UserRole, field_dict)
        #
        #             item.setFlags(item.flags() & ~Qt.ItemIsEditable)
        #
        #             if def_avatar:
        #                 pixmap = colorize_pixmap(QPixmap(def_avatar))
        #                 item.setIcon(0, QIcon(pixmap))

        if self.callback:
            self.tree_widget.itemDoubleClicked.connect(self.itemSelected)

    class TreeWidget(BaseTreeWidget):
        def __init__(self, *args, **kwargs):
            super().__init__(*args, **kwargs)

        def load(self, data, **kwargs):
            super().load(data, **kwargs)

    def open(self):
        with block_pin_mode():
            self.exec_()

    def itemSelected(self, item):
        is_folder = item.data(0, Qt.UserRole) == 'folder'
        if is_folder:
            return
        self.callback(item)
        self.close()

    def keyPressEvent(self, event):
        super().keyPressEvent(event)
        if event.key() != Qt.Key_Return:
            return
        item = self.tree_widget.currentItem()
        self.itemSelected(item)


class HelpIcon(QLabel):
    def __init__(self, parent, tooltip):
        super().__init__(parent=parent)
        self.parent = parent
        pixmap = colorize_pixmap(QPixmap(':/resources/icon-info.png'), opacity=0.5)
        pixmap = pixmap.scaled(12, 12, Qt.KeepAspectRatio, Qt.SmoothTransformation)
        self.setPixmap(pixmap)
        self.setToolTip(tooltip)


class AlignDelegate(QStyledItemDelegate):
    def paint(self, painter, option, index):
        option.displayAlignment = Qt.AlignCenter
        super(AlignDelegate, self).paint(painter, option, index)


class XMLHighlighter(QSyntaxHighlighter):
    def __init__(self, parent=None, workflow_settings=None):
        super().__init__(parent)
        self.workflow_settings = workflow_settings  # todo link classes
        self.tag_format = QTextCharFormat()
        self.tag_format.setForeground(QColor('#438BB9'))

    def highlightBlock(self, text):
        pattern = QRegularExpression(r"<[^>]*>")
        match = pattern.match(text)
        while match.hasMatch():
            start = match.capturedStart()
            length = match.capturedLength()
            self.setFormat(start, length, self.tag_format)
            match = pattern.match(text, start + length)


class PythonHighlighter(QSyntaxHighlighter):
    def __init__(self, parent=None, workflow_settings=None):
        super().__init__(parent)

        self.keywordFormat = QTextCharFormat()
        self.keywordFormat.setForeground(QColor('#c78953'))
        # self.keywordFormat.setFontWeight(QTextCharFormat.Bold)

        self.blueKeywordFormat = QTextCharFormat()
        self.blueKeywordFormat.setForeground(QColor('#438BB9'))

        self.purpleKeywordFormat = QTextCharFormat()
        self.purpleKeywordFormat.setForeground(QColor('#9B859D'))

        self.pinkKeywordFormat = QTextCharFormat()
        self.pinkKeywordFormat.setForeground(QColor('#FF6B81'))

        self.stringFormat = QTextCharFormat()
        self.stringFormat.setForeground(QColor('#6aab73'))

        self.commentFormat = QTextCharFormat()
        self.commentFormat.setForeground(QColor('#808080'))  # Grey color for comments

        self.decoratorFormat = QTextCharFormat()
        self.decoratorFormat.setForeground(QColor('#AA6D91'))  # Choose a color for decorators

        self.parameterFormat = QTextCharFormat()
        self.parameterFormat.setForeground(QColor('#B94343'))  # Red color for parameters

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

        self.purple_keywords = [
            'self', 'cls', 'super'
        ]

        self.pink_keywords = [
            '__init__', '__str__', '__repr__', '__len__', '__getitem__', '__setitem__',
            '__delitem__', '__iter__', '__next__', '__contains__',
        ]

        # Regular expressions for python's syntax
        self.tri_single_quote = QRegularExpression("f?'''([^'\\\\]|\\\\.|'{1,2}(?!'))*(''')?")
        self.tri_double_quote = QRegularExpression('f?"""([^"\\\\]|\\\\.|"{1,2}(?!"))*(""")?')
        self.single_quote = QRegularExpression(r"'([^'\\]|\\.)*(')?")
        self.double_quote = QRegularExpression(r'"([^"\\]|\\.)*(")?')
        self.comment = QRegularExpression(r'#.*')  # Regular expression for comments
        self.decorator = QRegularExpression(r'@\w+(\.\w+)*')
        # Regular expression for parameter names in method calls
        self.parameter = QRegularExpression(r'\b\w+(?=\s*=(?!=)\s*[^,\)]*(?:[,\)]|$))')

        self.multi_line_comment_start = QRegularExpression(r'^\s*"""(?!")')
        self.multi_line_comment_end = QRegularExpression(r'"""')

    def highlightBlock(self, text):
        # Keyword matching
        for keyword in self.keywords:
            expression = QRegularExpression('\\b' + keyword + '\\b')
            match_iterator = expression.globalMatch(text)
            while match_iterator.hasNext():
                match = match_iterator.next()
                self.setFormat(match.capturedStart(), match.capturedLength(), self.keywordFormat)
        pass
        for keyword in self.blue_keywords:
            expression = QRegularExpression('\\b' + keyword + '\\b')
            match_iterator = expression.globalMatch(text)
            while match_iterator.hasNext():
                match = match_iterator.next()
                self.setFormat(match.capturedStart(), match.capturedLength(), self.blueKeywordFormat)
        pass
        for keyword in self.purple_keywords:
            expression = QRegularExpression('\\b' + keyword + '\\b')
            match_iterator = expression.globalMatch(text)
            while match_iterator.hasNext():
                match = match_iterator.next()
                self.setFormat(match.capturedStart(), match.capturedLength(), self.purpleKeywordFormat)
        pass
        for keyword in self.pink_keywords:
            expression = QRegularExpression('\\b' + keyword + '\\b')
            match_iterator = expression.globalMatch(text)
            while match_iterator.hasNext():
                match = match_iterator.next()
                self.setFormat(match.capturedStart(), match.capturedLength(), self.pinkKeywordFormat)
        pass
        # Decorator matching
        self.match_decorator(text, self.decorator, self.decoratorFormat)

        # Comment matching
        self.match_inline_comment(text, self.comment, self.commentFormat)

        # Parameter name matching
        self.match_parameter(text, self.parameter, self.parameterFormat)

        # String matching
        self.match_inline_string(text, self.single_quote, self.stringFormat)
        self.match_inline_string(text, self.double_quote, self.stringFormat)
        # self.match_multiline(text, self.tri_single_quote, 1, self.stringFormat)
        # self.match_multiline(text, self.tri_double_quote, 2, self.stringFormat)
        self.match_multiline_comment(text, self.stringFormat)
        pass

    def match_multiline_comment(self, text, format):
        start_index = 0
        if self.previousBlockState() == 1:
            # Inside a multi-line comment
            end_match = self.multi_line_comment_end.match(text)
            if end_match.hasMatch():
                length = end_match.capturedEnd() - start_index
                self.setFormat(start_index, length, format)
                start_index = end_match.capturedEnd()
                self.setCurrentBlockState(0)
            else:
                self.setFormat(start_index, len(text), format)
                self.setCurrentBlockState(1)
                return

        start_match = self.multi_line_comment_start.match(text, start_index)
        while start_match.hasMatch():
            end_match = self.multi_line_comment_end.match(text, start_match.capturedEnd())
            if end_match.hasMatch():
                length = end_match.capturedEnd() - start_match.capturedStart()
                self.setFormat(start_match.capturedStart(), length, format)
                start_index = end_match.capturedEnd()
            else:
                self.setFormat(start_match.capturedStart(), len(text) - start_match.capturedStart(), format)
                self.setCurrentBlockState(1)
                return
            start_match = self.multi_line_comment_start.match(text, start_index)

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

    def match_decorator(self, text, expression, format):
        match_iterator = expression.globalMatch(text)
        while match_iterator.hasNext():
            match = match_iterator.next()
            self.setFormat(match.capturedStart(), match.capturedLength(), format)

    def match_parameter(self, text, expression, format):
        match_iterator = expression.globalMatch(text)
        while match_iterator.hasNext():
            match = match_iterator.next()
            start = match.capturedStart()
            length = match.capturedLength()

            # Check if we're inside parentheses and not in a function definition
            open_paren = text.rfind('(', 0, start)
            if open_paren != -1 and not text[:open_paren].strip().endswith('def'):
                # Check if there's an unmatched closing parenthesis before this point
                if text.count(')', 0, start) < text.count('(', 0, start):
                    self.setFormat(start, length, format)

def clear_layout(layout, skip_count=0):
    """Clear all layouts and widgets from the given layout"""
    while layout.count() > skip_count:
        item = layout.itemAt(skip_count)
        widget = item.widget()
        if isinstance(widget, BreadcrumbWidget):
            skip_count += 1
            continue
        item = layout.takeAt(skip_count)
        if widget is not None:
            widget.deleteLater()
        else:
            child_layout = item.layout()
            if child_layout is not None:
                clear_layout(child_layout)
