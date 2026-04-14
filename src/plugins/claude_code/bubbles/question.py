import json

from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import (
    QFrame, QHBoxLayout, QLabel, QLineEdit, QVBoxLayout, QWidget,
)

from plugins.workflows.bubbles import MessageBubble
from utils.helpers import set_module_type


@set_module_type(module_type='Bubbles')
class QuestionBubble(MessageBubble):
    """Bubble for interactive AskUserQuestion prompts."""

    bubble_bg_color = '#1e2a2d'
    bubble_text_color = '#44d4c8'

    def __init__(self, parent, message):
        self._questions = None
        self._q_index = 0
        self._answers = {}
        self._picker = None
        self._below_layout = None
        super().__init__(parent=parent, message=message)

    def _ensure_parsed(self, text):
        """Parse the stored JSON payload into self._questions on first use."""
        if self._questions is not None:
            return True
        try:
            parsed = json.loads(text)
        except (ValueError, TypeError):
            return False
        questions = parsed.get('questions') if isinstance(parsed, dict) else None
        if not questions:
            return False
        self._questions = questions
        self._q_index = 0
        self._answers = {}
        return True

    def setMarkdownText(self, text, display_text=None):
        if display_text is None and self._ensure_parsed(text):
            q = self._questions[self._q_index]
            display_text = q.get('question', '')
        super().setMarkdownText(text, display_text=display_text)

    def install_below_bubble(self, bubble_v_layout):
        self._below_layout = bubble_v_layout
        content = getattr(self.parent.message, 'content', '') or ''
        if not self._ensure_parsed(content):
            return
        self._build_picker()

    def _build_picker(self):
        if self._below_layout is None or self._questions is None:
            return
        if self._picker is not None:
            self._below_layout.removeWidget(self._picker)
            self._picker.deleteLater()
            self._picker = None
        q = self._questions[self._q_index]
        self._picker = OptionsPicker(self, q)
        self._below_layout.addWidget(self._picker)
        QTimer.singleShot(0, self._picker.setFocus)

    def _on_answer(self, answer_str):
        q = self._questions[self._q_index]
        self._answers[q.get('question', '')] = answer_str

        if self._q_index + 1 < len(self._questions):
            self._q_index += 1
            next_q = self._questions[self._q_index]
            super().setMarkdownText(self.text, display_text=next_q.get('question', ''))
            self._build_picker()
            return

        self._resolve_future(dict(self._answers))

    def _resolve_future(self, answers):
        member_id = self.member_id
        workflow = self.parent.parent.workflow
        member = workflow.members.get(member_id)
        if member and hasattr(member, '_question_future'):
            future = member._question_future
            if future and not future.done():
                future.set_result(answers)

        msg_collection = self.parent.parent
        msg_collection.last_member_bubbles.pop(('question', member_id), None)

        if self._picker is not None:
            self._picker.setDisabled(True)


class OptionsPicker(QWidget):
    """Keyboard-driven numbered list of options plus a free-text row."""

    def __init__(self, bubble, question_obj):
        super().__init__(parent=bubble.parent)
        self.bubble = bubble
        self.question_obj = question_obj
        self.multi_select = bool(question_obj.get('multiSelect', False))
        self.options = list(question_obj.get('options', []))
        self._rows = []
        self._focus_idx = 0
        self._selected = set()
        self.setFocusPolicy(Qt.StrongFocus)
        self._build()

    def _build(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 4, 8, 4)
        layout.setSpacing(2)

        for idx, opt in enumerate(self.options):
            row = OptionRow(
                picker=self,
                number=idx + 1,
                label=opt.get('label', ''),
                description=opt.get('description', ''),
            )
            layout.addWidget(row)
            self._rows.append(row)

        free_row = FreeTextRow(picker=self, number=len(self.options) + 1)
        layout.addWidget(free_row)
        self._rows.append(free_row)

        self._refresh()

    def _refresh(self):
        for idx, row in enumerate(self._rows):
            row.set_focused(idx == self._focus_idx)
            if isinstance(row, OptionRow):
                row.set_selected(self.multi_select and idx in self._selected)
        focused_row = self._rows[self._focus_idx]
        if isinstance(focused_row, FreeTextRow):
            focused_row.line_edit.setFocus()
        else:
            self.setFocus()

    def mouse_select(self, row):
        if row not in self._rows:
            return
        self._focus_idx = self._rows.index(row)
        self._refresh()

    def keyPressEvent(self, event):
        key = event.key()
        if key in (Qt.Key_Down, Qt.Key_Tab):
            self._focus_idx = (self._focus_idx + 1) % len(self._rows)
            self._refresh()
            return
        if key in (Qt.Key_Up, Qt.Key_Backtab):
            self._focus_idx = (self._focus_idx - 1) % len(self._rows)
            self._refresh()
            return
        if key == Qt.Key_Space and self.multi_select:
            focused_row = self._rows[self._focus_idx]
            if isinstance(focused_row, OptionRow):
                if self._focus_idx in self._selected:
                    self._selected.remove(self._focus_idx)
                else:
                    self._selected.add(self._focus_idx)
                self._refresh()
                return
        if key in (Qt.Key_Return, Qt.Key_Enter):
            self._submit()
            return
        super().keyPressEvent(event)

    def _submit(self):
        focused_row = self._rows[self._focus_idx]

        if isinstance(focused_row, FreeTextRow):
            text = focused_row.line_edit.text().strip()
            if not text:
                return
            self._deliver(text)
            return

        if self.multi_select:
            if not self._selected:
                return
            labels = [
                self.options[i].get('label', '')
                for i in sorted(self._selected)
            ]
            self._deliver(', '.join(labels))
            return

        self._deliver(self.options[self._focus_idx].get('label', ''))

    def _deliver(self, answer_str):
        self.setDisabled(True)
        self.bubble._on_answer(answer_str)


class OptionRow(QFrame):
    """Single numbered option row."""

    def __init__(self, picker, number, label, description):
        super().__init__(parent=picker)
        self.picker = picker
        self.number = number
        self.label_text = label
        self.description = description
        self._focused = False
        self._selected = False
        self.setFocusPolicy(Qt.NoFocus)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(6, 3, 6, 3)
        layout.setSpacing(6)

        self.marker = QLabel(self._marker_text())
        self.marker.setFixedWidth(28)
        layout.addWidget(self.marker)

        text = label
        if description:
            text = f"{label}  —  {description}"
        self.text_label = QLabel(text)
        self.text_label.setWordWrap(True)
        layout.addWidget(self.text_label, 1)

        self._apply_style()

    def _marker_text(self):
        prefix = '●' if self._selected else ' '
        return f"{prefix} {self.number}."

    def set_focused(self, focused):
        self._focused = focused
        self._apply_style()

    def set_selected(self, selected):
        self._selected = selected
        self.marker.setText(self._marker_text())
        self._apply_style()

    def _apply_style(self):
        bg = '#2a3a3d' if self._focused else 'transparent'
        color = '#44d4c8' if self._focused else '#9fb8b5'
        weight = '600' if self._selected else '400'
        self.setStyleSheet(
            f"QFrame {{ background-color: {bg}; border-radius: 3px; }}"
            f"QLabel {{ color: {color}; font-weight: {weight}; background: transparent; }}"
        )

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self.picker.mouse_select(self)
        super().mousePressEvent(event)

    def mouseDoubleClickEvent(self, event):
        if event.button() == Qt.LeftButton:
            self.picker.mouse_select(self)
            self.picker._submit()
        super().mouseDoubleClickEvent(event)


class FreeTextRow(QFrame):
    """Trailing row with an inline text input for custom answers."""

    def __init__(self, picker, number):
        super().__init__(parent=picker)
        self.picker = picker
        self.number = number
        self._focused = False
        self.setFocusPolicy(Qt.NoFocus)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(6, 3, 6, 3)
        layout.setSpacing(6)

        self.marker = QLabel(f"  {self.number}.")
        self.marker.setFixedWidth(28)
        layout.addWidget(self.marker)

        self.line_edit = QLineEdit()
        self.line_edit.setPlaceholderText('Type a custom answer and press Enter…')
        self.line_edit.returnPressed.connect(self.picker._submit)
        layout.addWidget(self.line_edit, 1)

        self._apply_style()

    def set_focused(self, focused):
        self._focused = focused
        self._apply_style()

    def set_selected(self, selected):  # noqa: D401 — parity with OptionRow
        pass

    def _apply_style(self):
        bg = '#2a3a3d' if self._focused else 'transparent'
        color = '#44d4c8' if self._focused else '#9fb8b5'
        self.setStyleSheet(
            f"QFrame {{ background-color: {bg}; border-radius: 3px; }}"
            f"QLabel {{ color: {color}; background: transparent; }}"
            f"QLineEdit {{ background-color: #141c1e; color: #d1e8e5; "
            f"border: 1px solid #2a3a3d; border-radius: 3px; padding: 2px 4px; }}"
        )

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self.picker.mouse_select(self)
        super().mousePressEvent(event)