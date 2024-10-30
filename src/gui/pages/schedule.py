from PySide6.QtCore import Signal, QDate
from PySide6.QtGui import QColor
from PySide6.QtWidgets import QHBoxLayout, QWidget, QVBoxLayout, QCalendarWidget

from src.gui.config import ConfigDBTree, ConfigWidget, CVBoxLayout


class Page_Schedule_Settings(ConfigWidget):
    def __init__(self, parent):
        self.IS_DEV_MODE = True
        super().__init__(parent=parent)
        self.propagate = False
        self.layout = CVBoxLayout(self)
        self.calendar = CustomCalendarWidget()
        self.layout.addWidget(self.calendar)
        self.layout.addStretch()


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
