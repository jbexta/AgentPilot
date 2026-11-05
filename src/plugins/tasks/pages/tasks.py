import asyncio
import json
import re
from datetime import datetime, timezone

import qasync
from PySide6.QtCore import QDate, QPointF, QTime, QTimer, QRect, Signal
from PySide6.QtGui import Qt, QColor, QTextCharFormat, QFont, QIcon, QPainter, QPen, QPainterPath, QPixmap
from PySide6.QtWidgets import (
    QCalendarWidget, QVBoxLayout, QLabel,
    QDialog, QFormLayout, QLineEdit, QTimeEdit, QComboBox,
    QDialogButtonBox, QHBoxLayout, QMenu, QMessageBox, QScrollArea,
    QWidget, QSpinBox,
)

from plugins.tasks.managers.tasks import STATUSES
from plugins.workflows.utils.runs import get_run_manager
from plugins.workflows.widgets.chat_widget import ChattableWorkflowWidget

from gui.fields.text import CTextEdit
from gui.widgets.config_db_tree import ConfigDBTree
from gui.widgets.config_fields import ConfigFields
from gui.widgets.config_joined import ConfigJoined
from gui.widgets.config_widget import ConfigWidget
from gui.gui_utils.helpers import auto_bake_table_item, colorize_pixmap
from gui.gui_utils.icon_button import IconButton
from gui.gui_utils.layouts import CVBoxLayout
from utils import sql
from utils.helpers import block_signals, apply_alpha_to_hex, display_message_box, set_module_type, exec_non_modal
from gui import system

STATUS_ICONS = {
    'TODO': ':/resources/icon-dot.svg',
    'RUNNING': ':/resources/icon-run.png',
    'AWAITING_APPROVAL': ':/resources/icon-pause.png',
    'DONE': ':/resources/icon-tick.svg',
    'FAILED': ':/resources/icon-cross.png',
    'RECURRING': ':/resources/icon-refresh.png',
    'SCHEDULED': ':/resources/icon-clock.png',
}


def build_rrule(selected_date, selected_time, recurrence):
    """Build an rrule string and human-readable time expression.

    Parameters
    ----------
    selected_date : QDate
    selected_time : QTime
    recurrence : str
        One of 'Once', 'Daily', 'Weekly', 'Monthly', 'Yearly'.

    Returns
    -------
    tuple[str, str]
        (rrule_str, time_expression)
    """
    dt = datetime(
        selected_date.year(), selected_date.month(), selected_date.day(),
        selected_time.hour(), selected_time.minute(), 0,
        tzinfo=timezone.utc,
    )
    dtstart = f"DTSTART:{dt.strftime('%Y%m%dT%H%M%SZ')}"
    time_str = dt.strftime('%H:%M')

    freq_map = {
        'Once': 'RRULE:FREQ=DAILY;COUNT=1',
        'Daily': 'RRULE:FREQ=DAILY',
        'Weekly': 'RRULE:FREQ=WEEKLY',
        'Monthly': 'RRULE:FREQ=MONTHLY',
        'Yearly': 'RRULE:FREQ=YEARLY',
    }
    rrule_line = freq_map[recurrence]
    rrule_str = f"{dtstart}\n{rrule_line}"

    if recurrence == 'Once':
        date_str = dt.strftime('%d %b %Y')
        time_expression = f"Once on {date_str} at {time_str}"
    else:
        time_expression = f"{recurrence} at {time_str}"

    return rrule_str, time_expression


def extract_time_from_rrule(rrule_str):
    """Extract (hour, minute) from an rrule DTSTART string.

    Parameters
    ----------
    rrule_str : str
        An rrule string containing a DTSTART line.

    Returns
    -------
    tuple[int, int] or None
        (hour, minute) or None if not parseable.
    """
    match = re.search(r'DTSTART:\d{8}T(\d{2})(\d{2})\d{2}Z', rrule_str)
    if match:
        return int(match.group(1)), int(match.group(2))
    return None


class DayTimelineWidget(QWidget):
    """Custom-painted 24-hour diary timeline widget."""

    HOUR_HEIGHT = 40
    LABEL_WIDTH = 40

    task_clicked = Signal(int)
    task_modified = Signal(int, int, int, int)  # task_id, hour, minute, duration

    def __init__(self, parent=None):
        super().__init__(parent)
        self.tasks = []
        self.selected_date = None
        self._task_rects = []

        self.SNAP_MINUTES = 15
        self._drag_task = None
        self._drag_mode = None
        self._drag_start_y = 0
        self._drag_orig_hour = 0
        self._drag_orig_minute = 0
        self._drag_orig_duration = 60

        self.setMouseTracking(True)
        self.setMinimumHeight(self.HOUR_HEIGHT * 24)

        self._now_timer = QTimer(self)
        self._now_timer.timeout.connect(self.update)
        self._now_timer.start(60000)

    def set_tasks(self, tasks, selected_date):
        """Store task data and repaint.

        Parameters
        ----------
        tasks : list[dict]
            Each dict has keys: id, name, hour, minute, time_expression.
        selected_date : datetime.date
        """
        self.tasks = tasks
        self.selected_date = selected_date
        self.update()

    def paintEvent(self, event):
        from gui.style import (
            PRIMARY_COLOR, TEXT_COLOR, ACCENT_COLOR_1, ACCENT_COLOR_2,
        )

        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        w = self.width()
        h = self.HOUR_HEIGHT * 24

        # Background
        painter.fillRect(0, 0, w, h, QColor(PRIMARY_COLOR))

        # Hour grid lines and labels
        line_color = QColor(TEXT_COLOR)
        line_color.setAlphaF(0.15)
        label_color = QColor(TEXT_COLOR)
        label_color.setAlphaF(0.5)

        pen = QPen(line_color)
        pen.setWidth(1)
        painter.setPen(pen)

        for hour in range(24):
            y = hour * self.HOUR_HEIGHT
            painter.drawLine(self.LABEL_WIDTH, y, w, y)

            painter.setPen(label_color)
            painter.drawText(
                2, y, self.LABEL_WIDTH - 4, self.HOUR_HEIGHT,
                Qt.AlignRight | Qt.AlignTop,
                f'{hour:02d}:00',
            )
            painter.setPen(pen)

        # Task blocks
        self._task_rects = []
        block_left = self.LABEL_WIDTH + 4
        block_width = w - block_left - 4

        for task in self.tasks:
            duration = task.get('duration', 60)
            block_height = max(
                int(duration / 60.0 * self.HOUR_HEIGHT), 15,
            )
            y = (task['hour'] * self.HOUR_HEIGHT
                 + int(task['minute'] / 60.0 * self.HOUR_HEIGHT))
            rect = QRect(block_left, y + 2, block_width, block_height)
            self._task_rects.append((rect, task['id']))

            # Rounded rect fill
            fill_color = QColor(ACCENT_COLOR_1)
            fill_color.setAlphaF(0.3)
            path = QPainterPath()
            path.addRoundedRect(rect.x(), rect.y(),
                                rect.width(), rect.height(), 4, 4)
            painter.fillPath(path, fill_color)

            # Task name text
            painter.setPen(QColor(TEXT_COLOR))
            text_rect = rect.adjusted(6, 0, -4, 0)
            painter.drawText(
                text_rect, Qt.AlignLeft | Qt.AlignVCenter,
                task['name'],
            )

            # Resize grip at bottom
            grip_color = QColor(TEXT_COLOR)
            grip_color.setAlphaF(0.25)
            painter.setPen(QPen(grip_color, 1))
            grip_y = rect.bottom() - 3
            grip_x1 = rect.center().x() - 10
            grip_x2 = rect.center().x() + 10
            painter.drawLine(grip_x1, grip_y, grip_x2, grip_y)
            painter.drawLine(
                grip_x1, grip_y + 2, grip_x2, grip_y + 2,
            )

        # Now-line (only if viewing today)
        today = datetime.now().date()
        if self.selected_date == today:
            now = datetime.now()
            now_y = (now.hour * self.HOUR_HEIGHT
                     + int(now.minute / 60.0 * self.HOUR_HEIGHT))
            now_color = QColor(ACCENT_COLOR_2)
            painter.setPen(QPen(now_color, 2))
            painter.drawLine(self.LABEL_WIDTH, now_y, w, now_y)
            painter.setBrush(now_color)
            painter.drawEllipse(
                QPointF(self.LABEL_WIDTH, now_y), 4, 4,
            )

        painter.end()

    def _snap_to_grid(self, total_minutes):
        """Round to nearest SNAP_MINUTES interval, clamped 0–1425."""
        snapped = round(total_minutes / self.SNAP_MINUTES) * self.SNAP_MINUTES
        return max(0, min(snapped, 1425))

    def _hit_test(self, pos):
        """Return (task_dict, 'move'|'resize') or (None, None)."""
        for rect, task_id in self._task_rects:
            if rect.contains(pos):
                task = next(
                    (t for t in self.tasks if t['id'] == task_id),
                    None,
                )
                if task is None:
                    continue
                if pos.y() >= rect.bottom() - 6:
                    return task, 'resize'
                return task, 'move'
        return None, None

    def mousePressEvent(self, event):
        if event.button() != Qt.LeftButton:
            super().mousePressEvent(event)
            return

        task, mode = self._hit_test(event.pos())
        if task:
            self._drag_task = task
            self._drag_mode = mode
            self._drag_start_y = event.pos().y()
            self._drag_orig_hour = task['hour']
            self._drag_orig_minute = task['minute']
            self._drag_orig_duration = task.get('duration', 60)
            self.task_clicked.emit(task['id'])
            event.accept()
        else:
            super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if self._drag_task is None:
            # Just update cursor based on hover
            task, mode = self._hit_test(event.pos())
            if mode == 'resize':
                self.setCursor(Qt.SizeVerCursor)
            elif mode == 'move':
                self.setCursor(Qt.OpenHandCursor)
            else:
                self.unsetCursor()
            return

        dy = event.pos().y() - self._drag_start_y

        if self._drag_mode == 'move':
            orig_total = (
                self._drag_orig_hour * 60 + self._drag_orig_minute
            )
            delta_minutes = dy / self.HOUR_HEIGHT * 60
            new_total = self._snap_to_grid(
                orig_total + delta_minutes,
            )
            self._drag_task['hour'] = int(new_total // 60)
            self._drag_task['minute'] = int(new_total % 60)
        elif self._drag_mode == 'resize':
            delta_minutes = dy / self.HOUR_HEIGHT * 60
            new_duration = self._snap_to_grid(
                self._drag_orig_duration + delta_minutes,
            )
            new_duration = max(new_duration, 15)
            self._drag_task['duration'] = new_duration

        self.update()

    def mouseReleaseEvent(self, event):
        if self._drag_task is not None:
            task = self._drag_task
            hour = task['hour']
            minute = task['minute']
            duration = task.get('duration', 60)
            changed = (
                hour != self._drag_orig_hour
                or minute != self._drag_orig_minute
                or duration != self._drag_orig_duration
            )
            if changed:
                self.task_modified.emit(
                    task['id'], hour, minute, duration,
                )
            self._drag_task = None
            self._drag_mode = None
        super().mouseReleaseEvent(event)

    def contextMenuEvent(self, event):
        menu = QMenu(self)
        action = menu.addAction('Add task')
        # Walk up to find the calendar fields widget
        parent = self.parent()
        while parent and not hasattr(parent, 'add_task_for_date'):
            parent = parent.parent()
        if parent:
            action.triggered.connect(parent.add_task_for_date)
        menu.exec(event.globalPos())


class AddTaskDialog(QDialog):
    """Dialog for adding a new task on a specific date."""

    def __init__(self, parent, selected_date):
        super().__init__(parent)
        self.setWindowTitle('Add Task')

        layout = QFormLayout(self)

        self.name_edit = QLineEdit(self)
        layout.addRow('Name:', self.name_edit)

        # Round current time to nearest 5 minutes
        now = QTime.currentTime()
        rounded_min = (now.minute() + 2) // 5 * 5
        if rounded_min >= 60:
            rounded = QTime(now.hour() + 1, 0)
        else:
            rounded = QTime(now.hour(), rounded_min)
        self.time_edit = QTimeEdit(rounded, self)
        self.time_edit.setDisplayFormat('HH:mm')
        layout.addRow('Time:', self.time_edit)

        self.recurrence_combo = QComboBox(self)
        self.recurrence_combo.addItems(
            ['Once', 'Daily', 'Weekly', 'Monthly', 'Yearly']
        )
        layout.addRow('Repeat:', self.recurrence_combo)

        self.duration_spin = QSpinBox(self)
        self.duration_spin.setRange(15, 480)
        self.duration_spin.setSingleStep(15)
        self.duration_spin.setValue(60)
        self.duration_spin.setSuffix(' min')
        layout.addRow('Duration:', self.duration_spin)

        self.buttons = QDialogButtonBox(
            QDialogButtonBox.Ok | QDialogButtonBox.Cancel, self
        )
        self.buttons.button(QDialogButtonBox.Ok).setEnabled(False)
        self.buttons.accepted.connect(self.accept)
        self.buttons.rejected.connect(self.reject)
        layout.addRow(self.buttons)

        self.name_edit.textChanged.connect(
            lambda t: self.buttons.button(
                QDialogButtonBox.Ok
            ).setEnabled(bool(t.strip()))
        )

    def get_values(self):
        """Return (name, QTime, recurrence_str, duration_minutes)."""
        return (
            self.name_edit.text().strip(),
            self.time_edit.time(),
            self.recurrence_combo.currentText(),
            self.duration_spin.value(),
        )


class CustomCalendar(QCalendarWidget):
    def __init__(self, parent):
        super().__init__(parent)
        self.parent = parent
        self.setVerticalHeaderFormat(QCalendarWidget.NoVerticalHeader)
        self.setHorizontalHeaderFormat(QCalendarWidget.SingleLetterDayNames)

        self.task_occurrences = {}
        self.set_today()

        from gui.style import TEXT_COLOR
        header_format = QTextCharFormat()
        transparent = QColor('#00000000')
        header_format.setBackground(transparent)
        header_format.setFontWeight(QFont.Bold)
        self.setHeaderTextFormat(header_format)
        text_format = QTextCharFormat()
        text_format.setForeground(QColor(TEXT_COLOR))
        text_weekend_format = QTextCharFormat()
        text_weekend_format.setForeground(QColor(apply_alpha_to_hex(TEXT_COLOR, 0.6)))
        for day in (Qt.Monday, Qt.Tuesday, Qt.Wednesday, Qt.Thursday, Qt.Friday):
            self.setWeekdayTextFormat(day, text_format)
        for day in (Qt.Saturday, Qt.Sunday):
            self.setWeekdayTextFormat(day, text_weekend_format)

        palette = self.palette()
        palette.setColor(palette.ColorRole.HighlightedText, QColor(TEXT_COLOR))
        self.setPalette(palette)

    def load(self):
        self.update_task_occurrences()
        pass

    def set_today(self):
        """Set the calendar view to today's date and select it"""
        today = QDate.currentDate()
        self.setSelectedDate(today)

    def update_task_occurrences(self):
        daemon = system.manager.daemons.running_daemons.get('tasks')
        if not daemon:
            QTimer.singleShot(3000, self.update_task_occurrences)
            return
        self.task_occurrences = daemon.list_tasks_per_day()
        self.updateCells()
        # Refresh diary since selectionChanged won't fire
        calendar_fields = getattr(self.parent, 'widgets', [None, None])[1]
        if calendar_fields and hasattr(calendar_fields, 'load_date'):
            calendar_fields.load_date()

    def paintCell(self, painter, rect, date):
        """Customize the appearance of individual day cells"""
        from gui.style import ACCENT_COLOR_1, TEXT_COLOR

        is_selected = date == self.selectedDate()
        if is_selected:
            # Paint selected cell manually to control text color
            painter.save()
            painter.fillRect(rect, QColor(ACCENT_COLOR_1))
            painter.setPen(QColor(TEXT_COLOR))
            painter.drawText(rect, Qt.AlignCenter, str(date.day()))
            painter.restore()
        else:
            super().paintCell(painter, rect, date)

        # Mark today's date with a circle
        if date == QDate.currentDate():
            painter.save()
            painter.setPen(QColor(TEXT_COLOR))
            painter.drawEllipse(rect.adjusted(3, 0, -4, -1))
            painter.restore()

        n_date = datetime(date.year(), date.month(), date.day()).date()
        # Draw dots for task occurrences
        if n_date in self.task_occurrences:
            num_tasks = min(len(self.task_occurrences[n_date]), 4)  # Limit to 4 tasks
            painter.save()
            painter.setPen(Qt.NoPen)
            painter.setBrush(QColor(ACCENT_COLOR_1))

            dot_size = 3
            spacing = 2
            column_spacing = 5

            # Calculate the starting position for the dots
            start_x = rect.right() - dot_size / 2  # 10 pixels from the right side
            start_y = rect.center().y() - (dot_size + spacing) / 2

            for i in range(num_tasks):
                row = i % 2
                col = i // 2
                x = start_x - col * column_spacing
                y = start_y + row * (dot_size + spacing)
                painter.drawEllipse(QPointF(x, y), dot_size / 2, dot_size / 2)

            painter.restore()


@set_module_type('Pages')
class Page_Tasks_Settings(ConfigJoined):
    display_name = 'Tasks'
    icon_path = ":/resources/icon-schedule.png"
    page_type = 'main'  # either 'settings', 'main', or 'any' ('any' means it can be pinned between main and settings)

    def __init__(self, parent):
        super().__init__(parent=parent, layout_type='vertical', resizable=True, propagate_config=False)
        self.widgets = [
            self.Page_Tasks_Calendar(parent=self),
            self.Page_Scheduled_Tasks(parent=self),
        ]
        self.calendar = self.widgets[0].widgets[0]

    # class Page_Tasks_Diary(ConfigJoined):
    #     def __init__(self, parent):
    #         super().__init__(parent=parent, layout_type='vertical', propagate_config=False)
    #         self.widgets = [
    #             self.Page_Tasks_Calendar(parent=self),
    #             # self.Page_Scheduled_Tasks(parent=self),
    #         ]

    #         # self.calendar = self.widgets[0].widgets[0]
    #         # # self.icon_path = ":/resources/icon-tasks.png"
    #         # # self.try_add_breadcrumb_widget(root_title='Tasks')

    class Page_Tasks_Calendar(ConfigJoined):
        def __init__(self, parent):
            super().__init__(
                parent=parent,
                layout_type='horizontal',
                propagate_config=False,
            )

            self.widgets = [
                self.Page_Tasks_Calendar_Widget(parent=self),
                self.Page_Tasks_Calendar_Fields(parent=self),
            ]
            self.widgets[0].selectionChanged.connect(self.widgets[1].load)

        class Page_Tasks_Calendar_Widget(CustomCalendar):
            def __init__(self, parent):
                super().__init__(parent)

            def contextMenuEvent(self, event):
                menu = QMenu(self)
                action = menu.addAction('Add task')
                action.triggered.connect(
                    self.parent.widgets[1].add_task_for_date
                )
                menu.exec(event.globalPos())

        class Page_Tasks_Calendar_Fields(ConfigWidget):
            def __init__(self, parent):
                super().__init__(parent)
                self.layout = QVBoxLayout(self)

                header_layout = QHBoxLayout()
                self.label = QLabel('')
                self.label.setObjectName('calendarDayLabel')
                header_layout.addWidget(self.label)

                self.add_btn = IconButton(
                    parent=self,
                    icon_path=':/resources/icon-new.png',
                    size=22,
                    tooltip='Add task on this day',
                )
                self.add_btn.clicked.connect(self.add_task_for_date)
                header_layout.addWidget(self.add_btn)
                header_layout.addStretch(1)
                self.layout.addLayout(header_layout)

                self.timeline = DayTimelineWidget(self)
                self.timeline.task_clicked.connect(
                    self.on_task_clicked,
                )
                self.timeline.task_modified.connect(
                    self.on_task_modified,
                )
                self.scroll_area = QScrollArea(self)
                self.scroll_area.setWidgetResizable(True)
                self.scroll_area.setWidget(self.timeline)
                self.scroll_area.setHorizontalScrollBarPolicy(
                    Qt.ScrollBarAlwaysOff,
                )
                self.layout.addWidget(self.scroll_area)

            def load(self):
                self.load_date()

            def load_date(self):
                calendar_date = (
                    self.parent.widgets[0].selectedDate()
                )
                calendar_date = datetime(
                    calendar_date.year(),
                    calendar_date.month(),
                    calendar_date.day(),
                ).date()

                formatted_date = calendar_date.strftime(
                    '%d %B %Y, %A'
                )
                self.label.setText(formatted_date)

                task_ids_on_date = list(
                    self.parent.widgets[0]
                    .task_occurrences.get(calendar_date, [])
                )
                if not task_ids_on_date:
                    tasks_data = []
                else:
                    tasks_data = sql.get_results(f"""
                        SELECT
                            id,
                            name,
                            config
                        FROM tasks
                        WHERE uuid IN (
                            {','.join('?' * len(task_ids_on_date))}
                        )
                    """, task_ids_on_date)

                timeline_tasks = []
                for task_id, task_name, task_config in tasks_data:
                    task_config = json.loads(task_config)
                    rrule = task_config.get('rrule', '')
                    time_expr = task_config.get(
                        'time_expression', ''
                    )
                    parsed = extract_time_from_rrule(rrule)
                    hour, minute = parsed if parsed else (0, 0)
                    duration = task_config.get('duration', 60)
                    timeline_tasks.append({
                        'id': task_id,
                        'name': task_name,
                        'hour': hour,
                        'minute': minute,
                        'duration': duration,
                        'time_expression': time_expr,
                    })

                timeline_tasks.sort(
                    key=lambda t: (t['hour'], t['minute']),
                )
                self.timeline.set_tasks(
                    timeline_tasks, calendar_date,
                )

                # Auto-scroll
                today = datetime.now().date()
                if calendar_date == today:
                    scroll_hour = datetime.now().hour
                elif timeline_tasks:
                    scroll_hour = timeline_tasks[0]['hour']
                else:
                    scroll_hour = 8
                scroll_y = max(
                    0,
                    scroll_hour * DayTimelineWidget.HOUR_HEIGHT
                    - 20,
                )
                self.scroll_area.verticalScrollBar().setValue(
                    scroll_y,
                )

            def on_task_clicked(self, task_id):
                self.parent.parent.widgets[1]\
                    .tree.select_items_by_id(task_id)

            def on_task_modified(self, task_id, hour, minute, duration):
                """Persist drag/resize changes to the database."""
                config_json = sql.get_scalar(
                    "SELECT config FROM tasks WHERE id = ?",
                    (task_id,),
                )
                config = json.loads(config_json)
                rrule = config.get('rrule', '')

                new_time = f'{hour:02d}{minute:02d}00'
                rrule = re.sub(
                    r'(DTSTART:\d{8}T)\d{6}(Z)',
                    rf'\g<1>{new_time}\2',
                    rrule,
                )

                time_str = f'{hour:02d}:{minute:02d}'
                time_expr = config.get('time_expression', '')
                time_expr = re.sub(
                    r'\d{2}:\d{2}', time_str, time_expr,
                )

                system.manager.tasks.set_schedule(task_id, rrule, time_expr, duration)

                scheduled_tasks = self.parent.parent.widgets[1]
                scheduled_tasks.on_edited()

            def add_task_for_date(self):
                """Show dialog to add a task on the selected calendar date."""
                calendar = self.parent.widgets[0]
                selected_date = calendar.selectedDate()

                dlg = AddTaskDialog(self, selected_date)
                if dlg.exec() != QDialog.Accepted:
                    return

                name, selected_time, recurrence, duration = (
                    dlg.get_values()
                )
                rrule_str, time_expression = build_rrule(
                    selected_date, selected_time, recurrence,
                )

                scheduled_tasks = self.parent.parent.widgets[1]
                manager = system.manager.tasks
                task_id = manager.add(name=name)
                manager.set_schedule(task_id, rrule_str, time_expression, duration)

                scheduled_tasks.load(select_id=task_id)
                scheduled_tasks.on_edited()

    class Page_Scheduled_Tasks(ConfigDBTree):
        """Every task, those of other kinds (e.g. `PROJECT:1:Issues`) grouped
        under their kind; or, given another `kind`, just the tasks of it."""
        def __init__(self, parent, kind='SCHEDULED', folder_key='tasks_scheduled'):
            is_main = kind == 'SCHEDULED'
            super().__init__(
                parent=parent,
                manager='tasks',
                query=f"""
                    SELECT
                        name,
                        id,
                        status,
                        COALESCE(json_extract(config, '$.rrule'), ''),
                        folder_id,
                        parent_id
                        {", CASE WHEN kind = :kind THEN '' ELSE kind END" if is_main else ''}
                    FROM tasks
                    {'' if is_main else 'WHERE kind = :kind'}
                    ORDER BY
                        kind != :kind,
                        replace(replace(kind, ':Todo', ''), ':Issues', ''),
                        CASE WHEN kind LIKE '%:Todo' THEN 0 WHEN kind LIKE '%:Issues' THEN 1 ELSE 2 END,
                        CASE status
                            WHEN 'AWAITING_APPROVAL' THEN 0
                            WHEN 'RUNNING' THEN 1
                            WHEN 'FAILED' THEN 2
                            WHEN 'TODO' THEN 3
                            WHEN 'SCHEDULED' THEN 4
                            WHEN 'RECURRING' THEN 5
                            ELSE 6
                        END,
                        pinned DESC, ordr, name COLLATE NOCASE""",
                schema=[
                    {
                        'text': 'Tasks',
                        'key': 'name',
                        'type': str,
                        # 'width': 150,
                        'stretch': True,
                    },
                    {
                        'text': 'id',
                        'key': 'id',
                        'type': int,
                        'visible': False,
                    },
                    {
                        'text': 'Status',
                        'key': 'status',
                        'type': str,
                        'width': 120,
                    },
                    {
                        'text': 'RRule',
                        'key': 'rrule',
                        'type': str,
                        'is_config_field': True,
                        'visible': False,
                        'stretch': True,
                    },
                    # {
                    #     'text': '',
                    #     'key': 'enabled',
                    #     'type': bool,
                    #     'is_config_field': True,
                    # },
                ],
                add_item_options={'title': 'Add Task', 'prompt': 'Enter a name for the task:'},
                del_item_options={'title': 'Delete Task', 'prompt': 'Are you sure you want to delete this task?'},
                folder_key=folder_key,
                kind=kind,
                group_by_kind=is_main,
                kind_folder_key=lambda row_kind: f'{row_kind.lower()}:task',
                readonly=False,
                layout_type='horizontal',
                config_widget=self.Task_Config_Widget(self),
                default_item_icon=':/resources/icon-tasks-small.png',
                support_item_nesting=True,
                notify_unread=True,
            )
            self.splitter.setSizes([400, 1000])

        def load(self, *args, **kwargs):
            super().load(*args, **kwargs)
            self.apply_status_icons(self.tree.items_mapping.values())

        def reload_current_row(self):
            super().reload_current_row()
            if self.get_selected_item_id() is not None:
                self.apply_status_icons([self.tree.currentItem()])

        def apply_status_icons(self, items):
            done_ids = getattr(self.tree, '_disabled_ids', set())
            with block_signals(self.tree):  # setIcon emits itemChanged
                for item in items:
                    status = item.text(2)
                    icon_path = STATUS_ICONS.get(status)
                    if icon_path:
                        item.setIcon(0, QIcon(colorize_pixmap(QPixmap(icon_path))))
                    if status in ('TODO', 'DONE'):
                        item.setText(2, '')
                    item.setFirstColumnSpanned(status in ('TODO', 'DONE'))
                    item_id = item.data(0, Qt.UserRole)['id']
                    if status == 'DONE':
                        done_ids.add(item_id)
                    else:
                        done_ids.discard(item_id)
            self.tree._disabled_ids = done_ids  # painted dimmed

        def get_notify_ids(self, unread_context_ids):
            if not unread_context_ids:
                return set()
            placeholders = ','.join('?' * len(unread_context_ids))
            kinds = sql.get_results(
                f"SELECT kind FROM contexts WHERE id IN ({placeholders}) AND kind LIKE 'TASK:%'",
                tuple(unread_context_ids), return_type='list',
            )
            return {int(kind.partition(':')[2]) for kind in kinds}

        def on_edited(self):
            daemon = system.manager.daemons.running_daemons.get('tasks')
            if daemon:
                asyncio.ensure_future(daemon.load())
            self.reload_calendar()

        def reload_calendar(self):
            if isinstance(self.parent, Page_Tasks_Settings):
                self.parent.widgets[0].load()

        def on_manager_changed(self):
            super().on_manager_changed()
            self.reload_calendar()
            if self.get_selected_item_id():
                self.config_widget.refresh_from_db()

        def on_item_selected(self):
            current_parent = self.config_widget.parent
            if isinstance(current_parent, ConfigDBTree) and current_parent != self:
                with block_signals(current_parent.tree):
                    current_parent.tree.clearSelection()
            self.config_widget.parent = self
            super().on_item_selected()

        def get_new_item_values(self):
            title = self.add_item_options['title']
            dlg = QDialog(self)
            dlg.setObjectName('newTaskDialog')
            dlg.setWindowTitle(title)
            dlg.setFixedWidth(520)
            name_edit = QLineEdit(dlg)
            task_edit = CTextEdit(dlg, enhancement_key='task')
            task_edit.setPlaceholderText("What's the task?")
            buttons = QDialogButtonBox(
                QDialogButtonBox.Ok | QDialogButtonBox.Cancel, dlg,
            )
            ok_btn = buttons.button(QDialogButtonBox.Ok)
            ok_btn.setText('Create')
            for btn in buttons.buttons():
                btn.setIcon(QIcon())
            ok_btn.setEnabled(False)
            for edit in (name_edit, task_edit):
                edit.textChanged.connect(lambda *_: ok_btn.setEnabled(bool(
                    name_edit.text().strip()
                    or task_edit.toPlainText().strip()
                )))
            buttons.accepted.connect(dlg.accept)
            buttons.rejected.connect(dlg.reject)
            title_lbl = QLabel(title, dlg)
            title_lbl.setObjectName('newProjectTitle')
            layout = CVBoxLayout(dlg)
            layout.setContentsMargins(24, 20, 24, 20)
            layout.addWidget(title_lbl)
            layout.addSpacing(16)
            for text, edit in (('Name', name_edit), ('Task', task_edit)):
                label = QLabel(text, dlg)
                label.setProperty('class', 'new-project-label')
                layout.addWidget(label)
                layout.addSpacing(6)
                layout.addWidget(edit)
                layout.addSpacing(14)
            layout.addSpacing(4)
            layout.addWidget(buttons)
            if exec_non_modal(dlg) != QDialog.Accepted:
                return None
            task = task_edit.toPlainText().strip()
            name = name_edit.text().strip() or ' '.join(task.split())[:50]
            return {'name': name, 'task': task}

        def update_name(self):
            pass  # the task name is the chat title, not the workflow name

        def rename_item(self):
            super().rename_item()
            self.show_name_in_chat()

        def show_name_in_chat(self):
            item_id = self.get_selected_item_id()
            if item_id is None or not self.config_widget.chat_shows_task():
                return
            name = sql.get_scalar("SELECT name FROM tasks WHERE id = ?", (item_id,))
            self.config_widget.chat.set_chat_title(name)

        def on_context_menu(self, menu):
            task_id = self.get_selected_item_id()
            if task_id is None:
                return
            status_menu = menu.addMenu('Set Status')
            for status in STATUSES:
                action = status_menu.addAction(
                    QIcon(colorize_pixmap(QPixmap(STATUS_ICONS[status]))), status)
                action.triggered.connect(
                    lambda _, s=status: self.manager.set_item_status(task_id, s))

        def on_cell_edited(self, item):
            col_indx = self.tree.currentColumn()
            if col_indx == 2:  # status is set from the panel
                self.load(silent_select_id=self.get_selected_item_id())
                return
            super().on_cell_edited(item)
            if col_indx == 0:
                self.show_name_in_chat()

        async def _process_time_expression(self, time_expression, item_id):
            try:
                await system.manager.tasks.apply_time_expression(
                    item_id, time_expression,
                )
                auto_bake_table_item('tasks', item_id)
                self.reload_current_row()
                self.reload_calendar()
                if self.get_selected_item_id() == item_id:
                    self.config_widget.refresh_from_db()
            except Exception as e:
                print(f"Error processing time expression: {e}")

        def delete_item(self):
            item = self.tree.currentItem()
            if not item or not isinstance(item.data(0, Qt.UserRole), dict):
                return super().delete_item()
            retval = display_message_box(
                icon=QMessageBox.Warning,
                title='Delete Task',
                text='Delete this task, its sub-tasks and their chats?',
                buttons=QMessageBox.Yes | QMessageBox.No,
            )
            if retval == QMessageBox.Yes:
                self.manager.delete(self.get_selected_item_id())  # the tree reloads on its changed signal

        class Task_Config_Widget(ConfigJoined):
            """The task's text, and its workflow above the task's latest
            chat."""

            def __init__(self, parent):
                self.propagate_config = True  # inherited by the children built below
                self.task_id = None
                self.description = self.Task_Description(parent=self)
                self.chat = self.Task_Chat(parent=self)
                super().__init__(
                    parent=parent,
                    widgets=[self.description, self.chat],
                    layout_type='vertical',
                    resizable=True,
                    propagate_config=True,
                )

            def after_init(self):
                self.splitter.setSizes([120, 800])

            def maybe_rebuild_schema(self, schema_overrides, item_id):
                self.description.maybe_rebuild_schema(schema_overrides, item_id)

            def update_config(self):
                self.save_config()

            def save_config(self):
                # the chat saves through its parent, so route it to the tree
                self.parent.update_config()

            def chat_shows_task(self):
                """Whether the chat is on one of the selected task's chats
                (or its unsaved draft), so its workflow is the task's."""
                workflow = self.chat.workflow
                context_id = workflow.context_id
                kind = sql.get_scalar("SELECT kind FROM contexts WHERE id = ?", (context_id,)) if context_id else workflow._kind
                return kind == f'TASK:{self.task_id}'

            def get_config(self):
                stored = sql.get_scalar(
                    "SELECT config FROM tasks WHERE id = ?",
                    (self.parent.get_selected_item_id(),),
                    load_json=True,
                ) or {}
                if self.chat_shows_task():
                    config = super().get_config()
                else:  # keep the task's workflow, not the other chat's
                    config = {**stored, **self.description.get_config()}
                for key in ('rrule', 'time_expression', 'duration'):
                    if key in stored:
                        config[key] = stored[key]
                    else:
                        config.pop(key, None)
                return config

            def apply_time_expression(self):
                """Schedule the task from the `When` field, as typed."""
                text = self.description.time_expression_wgt.get_value().strip()
                stored = sql.get_scalar(
                    "SELECT json_extract(config, '$.time_expression') FROM tasks WHERE id = ?",
                    (self.task_id,),
                ) or ''
                if text == stored:
                    return
                asyncio.ensure_future(
                    self.parent._process_time_expression(text, self.task_id)
                )

            def load_config(self, json_config=None):
                self.task_id = self.parent.get_selected_item_id()
                self.load_task_text()
                self.chat.load_for_task(self.task_id, json_config)

            def load_task_text(self):
                # read from the row, `json_config` may be wrapped into a
                # workflow config without the `task` key
                stored = sql.get_scalar("SELECT config FROM tasks WHERE id = ?", (self.task_id,), load_json=True) or {}
                self.description.load_config({
                    'task': stored.get('task', ''),
                    'time_expression': stored.get('time_expression', ''),
                })

            def load(self):
                self.description.load()

            def refresh_from_db(self):
                """Show changes made outside the panel, e.g. by an agent,
                unless the user is typing in the description."""
                if self.description.task_wgt.hasFocus():
                    return
                self.load_task_text()
                self.description.load()

            class Task_Description(ConfigFields):
                def __init__(self, parent):
                    super().__init__(parent=parent)
                    self.schema = [
                        {
                            'text': 'When',
                            'key': 'time_expression',
                            'type': str,
                            'default': '',
                            'stretch_x': True,
                            'placeholder_text': 'When it runs, e.g. "every weekday at 9am"',
                            'label_position': None,
                        },
                        {
                            'text': 'Task',
                            'key': 'task',
                            'type': str,
                            'default': '',
                            'num_lines': 5,
                            'stretch_x': True,
                            'stretch_y': True,
                            'placeholder_text': 'What is the task?',
                            'label_position': None,
                            'wrap_text': True,
                        },
                    ]

                def build_schema(self):
                    super().build_schema()
                    self.time_expression_wgt.widget.editingFinished.connect(
                        self.parent.apply_time_expression
                    )

            class Task_Chat(ChattableWorkflowWidget):
                """The task's workflow above its latest chat. The task text is
                the user's first message, so an empty chat has no message
                input, only the run button."""

                def __init__(self, parent):
                    super().__init__(parent=parent, kind='TASK', workflow_editable=False)
                    self.is_minimal = None

                def new_chat(self):
                    if not self.workflow.message_history.messages:
                        return
                    context_id, _ = system.manager.tasks.prepare_context(
                        self.parent.task_id, new=True,
                    )
                    self.goto_context(context_id)

                def resize_for_context(self):
                    """Shrink to the header and input while the chat is
                    empty, giving the task text the space."""
                    super().resize_for_context()
                    self.set_minimal(not self.message_collection.chat_bubbles)

                def set_minimal(self, is_minimal):
                    if is_minimal == self.is_minimal:
                        return
                    self.is_minimal = is_minimal
                    self.parent.splitter.setSizes(
                        [10000, 0] if is_minimal else [120, 800]
                    )

                class ChatInputWidget(ChattableWorkflowWidget.ChatInputWidget):
                    def __init__(self, parent):
                        super().__init__(parent)
                        self.btn_new_chat = IconButton(
                            parent=self,
                            icon_path=':/resources/icon-new.png',
                            tooltip='New chat',
                        )
                        self.btn_new_chat.clicked.connect(parent.new_chat)
                        new_chat_layout = CVBoxLayout()
                        new_chat_layout.addStretch()
                        new_chat_layout.addWidget(self.btn_new_chat)
                        self.layout.insertLayout(2, new_chat_layout)  # after the run button

                    def update_for_next_member(self):
                        workflow = self.parent.workflow
                        has_messages = bool(workflow and workflow.message_history.messages)
                        self.btn_new_chat.setVisible(has_messages and workflow.context_id is not None)
                        if has_messages:
                            super().update_for_next_member()
                            return
                        self.set_non_user_mode()
                        self.send_button.set_style_mode(joined=False)
                        self.send_button.update_icon(is_generating=False)

                @qasync.asyncSlot()
                async def on_send_message(self, restore_scroll_pos=None):
                    if self.workflow.message_history.messages or get_run_manager().is_running(self.workflow.context_id):
                        super().on_send_message(restore_scroll_pos)
                        return
                    task_id = self.parent.task_id
                    manager = system.manager.tasks
                    context_id, continuing = manager.prepare_context(task_id)
                    self.goto_context(context_id)
                    self.set_minimal(False)
                    user_member_id = manager.first_user_member_id(self.workflow)
                    if user_member_id is None:
                        await self.run_workflow_async()
                    else:
                        message = await manager.run_message(task_id, continuing)
                        await self.workflow.send_message(message, as_member_id=user_member_id)

                def set_chat_title(self, text):
                    self.workflow_settings.header_widget.context_bar.title_label.setText(text)

                def on_chat_title_edited(self, text):
                    # the task name is the chat title
                    if not self.parent.chat_shows_task():
                        return
                    sql.execute("UPDATE tasks SET name = ? WHERE id = ?", (text, self.parent.task_id))
                    tree = self.parent.parent.tree
                    with block_signals(tree):
                        tree.currentItem().setText(0, text)

                def load_config(self, json_config=None):
                    pass  # driven by load_for_task()

                def load_for_task(self, task_id, task_config):
                    manager = system.manager.tasks
                    if manager.context_id(task_id) is None:
                        self.new_context(config=task_config, kind=f'TASK:{task_id}')
                    else:
                        context_id, _ = manager.prepare_context(task_id)
                        self.goto_context(context_id)
