from PySide6.QtCore import Signal, QDate
from PySide6.QtGui import QColor
from PySide6.QtWidgets import QWidget, QCalendarWidget

from src.gui.config import ConfigDBTree, ConfigWidget, CVBoxLayout, ConfigJoined
from src.members.workflow import WorkflowSettings
from src.utils.helpers import block_signals


class Page_Tasks_Settings(ConfigJoined):
    def __init__(self, parent):
        super().__init__(parent=parent, layout_type='vertical')

        self.widgets = [
            self.Page_Tasks_Settings_Widget(parent=self),
            self.Task_Config_Widget(parent=self),
        ]

        self.icon_path = ":/resources/icon-tasks.png"
        self.try_add_breadcrumb_widget(root_title='Tasks')

        self.widgets[0].widgets[0].config_widget = self.widgets[1]
        self.widgets[0].widgets[1].config_widget = self.widgets[1]


    class Task_Config_Widget(WorkflowSettings):
        def __init__(self, parent):
            super().__init__(parent=parent, table_name='tasks')

    class Page_Tasks_Settings_Widget(ConfigJoined):
        def __init__(self, parent):
            super().__init__(parent=parent, layout_type='horizontal')

            self.widgets = [
                self.Page_Scheduled_Tasks(parent=self),
                self.Page_Triggered_Tasks(parent=self),
            ]

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
                            folder_id
                        FROM tasks
                        WHERE kind = 'SCHEDULED'
                        ORDER BY pinned DESC, ordr, name""",
                    schema=[
                        {
                            'text': 'Scheduled',
                            'key': 'name',
                            'type': str,
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
                            'width': 125,
                        },
                    ],
                    add_item_prompt=('Add Task', 'Enter a name for the task:'),
                    del_item_prompt=('Delete Task', 'Are you sure you want to delete this task?'),
                    folder_key='tasks_scheduled',
                    kind='SCHEDULED',
                    readonly=False,
                    layout_type='horizontal',
                    # config_widget=self.parent.parent.widgets[1],
                    searchable=True,
                    default_item_icon=':/resources/icon-tasks-small.png',
                )
                self.splitter.setSizes([400, 1000])

            def on_item_selected(self):
                current_parent = self.config_widget.parent
                if isinstance(current_parent, ConfigDBTree) and current_parent != self:
                    with block_signals(current_parent.tree):
                        current_parent.tree.clearSelection()
                self.config_widget.parent = self
                super().on_item_selected()

            # def on_edited(self):
            #     self.parent.main.system.blocks.load()

        class Page_Triggered_Tasks(ConfigDBTree):
            def __init__(self, parent):
                super().__init__(
                    parent=parent,
                    table_name='tasks',
                    query="""
                        SELECT
                            name,
                            id,
                            COALESCE(json_extract(config, '$.trigger'), ''),
                            folder_id
                        FROM tasks
                        WHERE kind = 'TRIGGERED'
                        ORDER BY pinned DESC, ordr, name""",
                    schema=[
                        {
                            'text': 'Triggered',
                            'key': 'name',
                            'type': str,
                            'stretch': True,
                        },
                        {
                            'text': 'id',
                            'key': 'id',
                            'type': int,
                            'visible': False,
                        },
                        {
                            'text': 'Event',
                            'key': 'trigger_event',
                            'type': str,
                            'is_config_field': True,
                            'width': 125,
                        },
                    ],
                    add_item_prompt=('Add Task', 'Enter a name for the task:'),
                    del_item_prompt=('Delete Task', 'Are you sure you want to delete this task?'),
                    folder_key='tasks_triggered',
                    kind='TRIGGERED',
                    readonly=False,
                    layout_type='horizontal',
                    # config_widget=self.parent.parent.widgets[1],
                    searchable=True,
                    default_item_icon=':/resources/icon-tasks-small.png',
                )
                self.splitter.setSizes([400, 1000])

            def on_item_selected(self):
                current_parent = self.config_widget.parent
                if isinstance(current_parent, ConfigDBTree) and current_parent != self:
                    with block_signals(current_parent.tree):
                        current_parent.tree.clearSelection()
                self.config_widget.parent = self
                super().on_item_selected()

            # def on_edited(self):
            #     self.parent.main.system.blocks.load()

# class zzPage_Schedule_Settings(ConfigWidget):
#     def __init__(self, parent):
#         self.IS_DEV_MODE = True
#         super().__init__(parent=parent)
#         self.propagate = False
#         self.layout = CVBoxLayout(self)
#         self.calendar = CustomCalendarWidget()
#         self.layout.addWidget(self.calendar)
#         self.layout.addStretch()

class CustomCalendarWidget(QWidget):
    # Custom signal to emit when a date is selected
    dateSelected = Signal(QDate)

    def __init__(self):
        super().__init__()
        self.layout = CVBoxLayout(self)
        self.calendar = CustomCalendar()
        self.layout.addWidget(self.calendar)
        self.layout.addStretch()

        # Connect the selectionChanged signal to our custom slot
        self.calendar.selectionChanged.connect(self.on_date_selected)

        # Set the default view to today's date
        self.set_today()

    def set_today(self):
        """Set the calendar view to today's date and select it"""
        today = QDate.currentDate()
        self.calendar.setSelectedDate(today)

    def on_date_selected(self):
        """Handle the date selection event"""
        selected_date = self.calendar.selectedDate()
        print(f"Selected date: {selected_date.toString()}")
        # Emit our custom signal with the selected date
        self.dateSelected.emit(selected_date)

class CustomCalendar(QCalendarWidget):
    def __init__(self):
        super().__init__()
        # self.setFixedSize(400, 250)
        self.setVerticalHeaderFormat(QCalendarWidget.NoVerticalHeader)  # Hide week numbers

    def paintCell(self, painter, rect, date):
        """Customize the appearance of individual day cells"""
        super().paintCell(painter, rect, date)

        # Mark today's date with a red circle
        if date == QDate.currentDate():
            painter.save()
            painter.setPen(QColor(255, 0, 0))
            painter.drawEllipse(rect.adjusted(2, 2, -2, -2))
            painter.restore()

# class Page_Tasks_Settings(ConfigDBTree):
#     def __init__(self, parent):
#         super().__init__(
#             parent=parent,
#             table_name='tasks',
#             query="""
#                 SELECT
#                     name,
#                     id,
#                     COALESCE(json_extract(config, '$.time_expression'), ''),
#                     folder_id
#                 FROM tasks
#                 ORDER BY pinned DESC, ordr, name""",
#             schema=[
#                 {
#                     'text': 'Name',
#                     'key': 'name',
#                     'type': str,
#                     'stretch': True,
#                 },
#                 {
#                     'text': 'id',
#                     'key': 'id',
#                     'type': int,
#                     'visible': False,
#                 },
#                 {
#                     'text': 'When',
#                     'key': 'time_expression',
#                     'type': str,
#                     'is_config_field': True,
#                     'width': 125,
#                 },
#             ],
#             add_item_prompt=('Add Task', 'Enter a name for the task:'),
#             del_item_prompt=('Delete Task', 'Are you sure you want to delete this task?'),
#             folder_key='tasks',
#             readonly=False,
#             layout_type='horizontal',
#             config_widget=self.Task_Config_Widget(parent=self),
#             searchable=True,
#             default_item_icon=':/resources/icon-tasks-small.png',
#         )
#         self.icon_path = ":/resources/icon-tasks.png"
#         self.try_add_breadcrumb_widget(root_title='Tasks')
#         self.splitter.setSizes([400, 1000])
#
#     def on_edited(self):
#         self.parent.main.system.blocks.load()
#
#     class Task_Config_Widget(WorkflowSettings):
#         def __init__(self, parent):
#             super().__init__(parent=parent, table_name='tasks')
#
# class zzPage_Schedule_Settings(ConfigWidget):
#     def __init__(self, parent):
#         self.IS_DEV_MODE = True
#         super().__init__(parent=parent)
#         self.propagate = False
#         self.layout = CVBoxLayout(self)
#         self.calendar = CustomCalendarWidget()
#         self.layout.addWidget(self.calendar)
#         self.layout.addStretch()
#
#
# class CustomCalendarWidget(QWidget):
#     # Custom signal to emit when a date is selected
#     dateSelected = Signal(QDate)
#
#     def __init__(self):
#         super().__init__()
#         self.layout = CVBoxLayout(self)
#         self.calendar = CustomCalendar()
#         self.layout.addWidget(self.calendar)
#         self.layout.addStretch()
#
#         # Connect the selectionChanged signal to our custom slot
#         self.calendar.selectionChanged.connect(self.on_date_selected)
#
#         # Set the default view to today's date
#         self.set_today()
#
#     def set_today(self):
#         """Set the calendar view to today's date and select it"""
#         today = QDate.currentDate()
#         self.calendar.setSelectedDate(today)
#
#     def on_date_selected(self):
#         """Handle the date selection event"""
#         selected_date = self.calendar.selectedDate()
#         print(f"Selected date: {selected_date.toString()}")
#         # Emit our custom signal with the selected date
#         self.dateSelected.emit(selected_date)
#
#
# class CustomCalendar(QCalendarWidget):
#     def __init__(self):
#         super().__init__()
#         # self.setFixedSize(400, 250)
#         self.setVerticalHeaderFormat(QCalendarWidget.NoVerticalHeader)  # Hide week numbers
#
#     def paintCell(self, painter, rect, date):
#         """Customize the appearance of individual day cells"""
#         super().paintCell(painter, rect, date)
#
#         # Mark today's date with a red circle
#         if date == QDate.currentDate():
#             painter.save()
#             painter.setPen(QColor(255, 0, 0))
#             painter.drawEllipse(rect.adjusted(2, 2, -2, -2))
#             painter.restore()
