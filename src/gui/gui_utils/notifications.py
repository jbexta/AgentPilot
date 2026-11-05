import json
import sys
import traceback

import qasync
from PySide6.QtCore import QEasingCurve, QObject, QPropertyAnimation, QTimer, Signal
from PySide6.QtGui import QTextDocument, Qt
from PySide6.QtWidgets import QLabel, QPushButton, QSizePolicy, QSystemTrayIcon, QVBoxLayout, QWidget

from gui import system
from gui.gui_utils.layouts import CVBoxLayout


class NotificationWidget(QWidget):
    closed = Signal(QObject)

    def __init__(self, parent=None, color=None, fix_task=None):
        super().__init__(parent)
        self.fix_task = fix_task
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.main = parent.main
        # Handle color defaults and conversions
        if not color:
            color = '#ff6464'
        elif color == 'blue':
            color = '#438BB9'
        elif color == 'red':
            color = '#ff6464'
        elif not color.startswith('#'):
            color = '#ff6464'

        # Create the main layout
        self.outer_layout = QVBoxLayout(self)
        self.outer_layout.setContentsMargins(0, 0, 0, 0)
        self.outer_layout.setSpacing(0)

        # Create the content container
        self.content = QWidget(self)
        self.content.setStyleSheet(f"""
            background-color: {color};
            border-radius: 10px;
            color: white;
        """)

        # Inner layout for the content
        self.content_layout = QVBoxLayout(self.content)
        self.content_layout.setContentsMargins(12, 10, 12, 10)
        self.content_layout.setSpacing(0)

        # Create text label with proper wrapping
        self.label = QLabel()
        self.label.setWordWrap(True)
        self.label.setObjectName('notificationLabel')
        self.label.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Minimum)
        self.content_layout.addWidget(self.label)

        self.fix_button = None
        if fix_task:
            self.content_layout.setSpacing(6)
            self.fix_button = QPushButton('Fix')
            self.fix_button.setToolTip('Create a task for an agent to fix this error')
            self.fix_button.setStyleSheet('border: 1px solid white; border-radius: 5px; padding: 2px 12px;')
            self.fix_button.clicked.connect(self.on_fix_clicked)
            self.content_layout.addWidget(self.fix_button, alignment=Qt.AlignRight)

        # Add content to outer layout
        self.outer_layout.addWidget(self.content)

        # Set size policies
        self.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Minimum)
        self.setMaximumWidth(300)

        # Initialize with zero height
        self.content.setMinimumHeight(0)
        self.content.setMaximumHeight(0)

        # Setup timer for auto-hide
        self.timer = QTimer(self)
        self.timer.setSingleShot(True)
        self.timer.timeout.connect(self.hide_animation)

        # Setup animation
        self.animation = QPropertyAnimation(self.content, b"maximumHeight")
        self.animation.setEasingCurve(QEasingCurve.InOutCubic)
        self.animation.finished.connect(self.on_animation_finished)

    def show_message(self, message, duration=5000):
        # Set the message
        self.label.setText(message)

        # Calculate proper size based on text
        self.label.adjustSize()
        text_width = min(self.label.sizeHint().width(), 280)  # Account for padding

        # Create a temporary document to calculate proper text height
        doc = QTextDocument()
        doc.setDefaultFont(self.label.font())
        doc.setHtml(message)
        doc.setTextWidth(text_width)

        # Calculate target height with margins
        target_height = doc.size().height() + 20  # Add some padding
        if self.fix_button:
            target_height += self.fix_button.sizeHint().height() + self.content_layout.spacing()

        # Reset animation and height
        self.animation.stop()
        self.content.setMaximumHeight(0)

        # Start show animation
        self.animation.setStartValue(0)
        self.animation.setEndValue(target_height)
        self.animation.setDuration(250)
        self.animation.start()

        if not self.main.isMinimized():
            # Start timer for auto-hide
            self.timer.start(duration)

    @qasync.asyncSlot()
    async def on_fix_clicked(self):
        self.fix_button.setEnabled(False)
        self.hide_animation()
        tasks = system.manager.tasks
        result = await tasks.add_item(**self.fix_task)
        task_id = json.loads(result)['id']
        await tasks.run_scheduled(task_id)

    def hide_animation(self):
        # Start hide animation
        current_height = self.content.height()
        self.animation.stop()
        self.animation.setStartValue(current_height)
        self.animation.setEndValue(0)
        self.animation.setDuration(250)
        self.animation.start()

    def on_animation_finished(self):
        if self.content.maximumHeight() == 0:
            self.hide()
            self.closed.emit(self)

    def enterEvent(self, event):
        self.timer.stop()
        event.accept()

    def leaveEvent(self, event):
        self.timer.start(3000)
        event.accept()


class NotificationManager(QWidget):
    def __init__(self, parent):
        super().__init__(parent=parent)
        self.main = parent
        self.setFixedWidth(300)
        self.setWindowFlags(Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.Tool)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setAttribute(Qt.WA_ShowWithoutActivating)
        self.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Preferred)

        # Main layout for stacking notifications
        self.layout = CVBoxLayout(self)
        self.layout.setSpacing(6)
        self.layout.setContentsMargins(0, 0, 0, 0)
        self.layout.setAlignment(Qt.AlignTop)

        self.notifications = []

    def show_notification(self, message, title, icon='Information', color=None, duration=5000):
        is_minimized = self.main.isMinimized()
        if is_minimized:
            icon = getattr(QSystemTrayIcon, icon, QSystemTrayIcon.Information)
            self.main.tray.showMessage(
                title,
                message,
                icon,
                duration  # duration in ms
            )
            # self.tray.showMessage(message, color)
            return

        fix_task = None
        icon_name = icon if isinstance(icon, str) else icon.name
        if icon_name in ('Warning', 'Critical') and getattr(system.manager, 'tasks', None):
            description = f'Fix the cause of this error popup.\n\n{title}: {message}'
            if sys.exc_info()[1] is not None:
                description += f'\n\n{traceback.format_exc()}'
            fix_task = {'name': f'Fix: {title}', 'description': description}

        # Create new notification
        notification = NotificationWidget(self, color=color, fix_task=fix_task)
        notification.closed.connect(self.remove_notification)

        # Add to layout
        self.layout.addWidget(notification)
        self.notifications.append(notification)

        # Display the notification
        notification.show_message(message, duration)
        # self.setVisible(True)
        self.update_position()

        print(message)

    def remove_notification(self, notification):
        if notification in self.notifications:
            self.notifications.remove(notification)
            self.layout.removeWidget(notification)
            notification.deleteLater()

        # if not self.notifications:
        #     self.hide()
        # else:
        # if self.notifications:
        self.update_position()

    def update_position(self):
        # Position in top right corner of main window with padding
        # visible = self.notifications is not None and not self.main.isMinimized()
        # self.setVisible(visible)
        # if not visible:
        #     return
        self.move(self.main.x() + self.main.width() - self.width() - 90,
                 self.main.y() + 50)
        self.adjustSize()
