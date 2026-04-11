import asyncio
import json
import re
from datetime import datetime, timezone

from PySide6.QtCore import QDate, Slot, QPointF, QTime, QTimer, QRect, Signal
from PySide6.QtGui import Qt, QColor, QTextCharFormat, QFont, QPainter, QPen, QPainterPath
from PySide6.QtWidgets import (
    QCalendarWidget, QVBoxLayout, QLabel,
    QDialog, QFormLayout, QLineEdit, QTimeEdit, QComboBox,
    QDialogButtonBox, QHBoxLayout, QMenu, QScrollArea, QWidget,
    QSpinBox,
)

from plugins.workflows.widgets.workflow_settings import WorkflowSettings

from gui.widgets.config_db_tree import ConfigDBTree
from gui.widgets.config_joined import ConfigJoined
from gui.widgets.config_widget import ConfigWidget
from gui.util import IconButton
from utils import sql
from utils.helpers import block_signals, apply_alpha_to_hex, set_module_type
from gui import system


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
    icon_path = ":/resources/icon-tasks.png"
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
                self.label.setStyleSheet(
                    'font-size: 10pt; font-weight: bold;'
                )
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

                sql.execute(
                    "UPDATE tasks SET config = json_set("
                    "config, '$.rrule', ?, "
                    "'$.time_expression', ?, "
                    "'$.duration', ?) "
                    "WHERE id = ?",
                    (rrule, time_expr, duration, task_id),
                )

                scheduled_tasks = self.parent.parent.widgets[1]
                scheduled_tasks.load()
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
                scheduled_tasks.manager.add(
                    name=name, kind='SCHEDULED',
                )
                last_id = scheduled_tasks.db_connector.get_scalar(
                    "SELECT seq FROM sqlite_sequence WHERE name=?",
                    (scheduled_tasks.table_name,),
                )

                sql.execute(
                    "UPDATE tasks SET config = json_set("
                    "config, '$.rrule', ?, "
                    "'$.time_expression', ?, "
                    "'$.duration', ?"
                    ") WHERE id = ?",
                    (rrule_str, time_expression, duration, last_id),
                )

                scheduled_tasks.load(select_id=last_id)
                scheduled_tasks.on_edited()

    class Page_Scheduled_Tasks(ConfigDBTree):
        def __init__(self, parent):
            super().__init__(
                parent=parent,
                table_name='tasks',
                query="""
                    SELECT
                        name,
                        id,
                        COALESCE(json_extract(config, '$.time_expression'), ''),
                        COALESCE(json_extract(config, '$.rrule'), ''),
                        -- COALESCE(json_extract(config, '$.enabled'), 1),
                        folder_id
                    FROM tasks
                    WHERE kind = 'SCHEDULED'
                    ORDER BY pinned DESC, ordr, name COLLATE NOCASE""",
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
                        'text': 'When',
                        'key': 'time_expression',
                        'type': str,
                        'is_config_field': True,
                        'stretch': True,
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
                folder_key='tasks_scheduled',
                kind='SCHEDULED',
                readonly=False,
                layout_type='horizontal',
                config_widget=self.Task_Config_Widget(self),
                default_item_icon=':/resources/icon-tasks-small.png',
            )
            self.splitter.setSizes([400, 1000])

        def on_edited(self):
            daemon = system.manager.daemons.running_daemons.get('tasks')
            if daemon:
                asyncio.ensure_future(daemon.load())
            self.parent.widgets[0].load()

        def on_item_selected(self):
            current_parent = self.config_widget.parent
            if isinstance(current_parent, ConfigDBTree) and current_parent != self:
                with block_signals(current_parent.tree):
                    current_parent.tree.clearSelection()
            self.config_widget.parent = self
            super().on_item_selected()

        def on_cell_edited(self, item):
            col_indx = self.tree.currentColumn()
            if col_indx != 2:
                super().on_cell_edited(item)
                return

            item_id = self.get_selected_item_id()
            if item_id is None:
                return
            time_expression = item.text(col_indx)

            if time_expression.strip() == '':
                self.handle_result('', '', item_id)
                return

            asyncio.ensure_future(
                self._process_time_expression(time_expression, item_id)
            )

        async def _process_time_expression(self, time_expression, item_id):
            try:
                result = await system.manager.blocks.compute_block_async(
                    'expression_to_time', {'expression': time_expression}
                )
                match = re.search(r'<answer>(.*?)</answer>', result, re.DOTALL)
                result = match.group(1).strip() if match else result.strip()

                clean_time_expression = await system.manager.blocks.compute_block_async(
                    'time_to_expression', {'time': result}
                )
                match = re.search(r'<answer>(.*?)</answer>', clean_time_expression, re.DOTALL)
                clean_time_expression = match.group(1).strip() if match else clean_time_expression.strip()
                self.handle_result(result, clean_time_expression, item_id)
            except Exception as e:
                print(f"Error processing time expression: {e}")

        @Slot(str, str, int)
        def handle_result(self, result, time_expression, item_id):
            result = result.strip()
            if 'DTSTART' not in result and result != '':
                now = datetime.now(timezone.utc)
                result = f"DTSTART:{now.strftime('%Y%m%dT%H%M%SZ')}\n{result}"

            sql.execute(f"""
                UPDATE tasks
                SET config = json_set(config, '$.rrule', ?)
                WHERE id = ?
            """ , (result.strip(), item_id))
            sql.execute(f"""
                UPDATE tasks
                SET config = json_set(config, '$.time_expression', ?)
                WHERE id = ?
            """ , (time_expression.strip(), item_id))

            daemon = system.manager.daemons.running_daemons.get('tasks')
            if daemon:
                asyncio.ensure_future(daemon.load())
            self.reload_current_row()
            self.parent.calendar.load()

        class Task_Config_Widget(WorkflowSettings):
            def __init__(self, parent):
                super().__init__(parent=parent, compact_mode=True)

            def get_config(self):
                config = super().get_config()
                for key in ('rrule', 'time_expression'):
                    if key in self.config and key not in config:
                        config[key] = self.config[key]
                return config

            def load_config(self, json_config=None):
                if json_config is None:
                    parent_config = getattr(self.parent, 'config', {})

                    if self.conf_namespace is None and not isinstance(self, ConfigDBTree):
                        json_config = parent_config
                    else:
                        json_config = {k: v for k, v in parent_config.items() if k.startswith(f'{self.conf_namespace}.')}
                super().load_config(json_config)

            def update_config(self):
                self.save_config()

            def save_config(self):
                self.parent.update_config()