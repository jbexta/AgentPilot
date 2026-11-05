from PySide6.QtGui import QPixmap

from gui.gui_utils.helpers import colorize_pixmap
from gui.gui_utils.icon_button import IconButton


class ToggleIconButton(IconButton):
    def __init__(self, **kwargs):
        self.icon_path = kwargs.get('icon_path', None)
        self.ttip = kwargs.get('tooltip', '')
        self.icon_path_checked = kwargs.pop('icon_path_checked', self.icon_path)
        self.tooltip_checked = kwargs.pop('tooltip_checked', None)
        self.color_when_checked = kwargs.pop('color_when_checked', None)
        self.opacity = kwargs.pop('opacity', 1)
        self.opacity_when_checked = kwargs.pop('opacity_when_checked', 1)
        self.show_checked_background = kwargs.pop('show_checked_background', True)
        self.target_when_checked = kwargs.pop('target_when_checked', None)
        super().__init__(**kwargs)
        # checkable = kwargs.get('checkable', False)
        self.setCheckable(True)

        # connect signal to refresh icon when checked state changes
        self.toggled.connect(self.refresh_icon)

    def setChecked(self, state):
        super().setChecked(state)
        self.refresh_icon()

    def refresh_icon(self):
        path = self.icon_path
        opacity = self.opacity
        color = None

        is_checked = self.isChecked()
        if self.icon_path == ':/resources/icon-chat.png' and not is_checked:
            pass
        if is_checked:
            path = self.icon_path_checked if self.icon_path_checked else self.icon_path
            opacity = self.opacity_when_checked if self.opacity_when_checked else self.opacity
            color = self.color_when_checked if self.color_when_checked else None

        if self.icon_path == ':/resources/icon-link.png':
            pass
        pixmap = colorize_pixmap(
            QPixmap(path),
            opacity=opacity,
            color=color
        )
        self.setIconPixmap(pixmap, color=self.color_when_checked if is_checked else None)
        # else:

        if self.tooltip_checked:
            self.setToolTip(self.tooltip_checked if is_checked else self.ttip)

    # def paintEvent(self, event):
    #     if not self.show_checked_background and self.isChecked():
    #         # Custom painting to avoid showing the checked background
    #         option = QStyleOptionButton()
    #         option.initFrom(self)
    #         # Remove the checked state for painting purposes only
    #         option.state &= ~QStyle.State_On
    #         option.state &= ~QStyle.State_Sunken

    #         # Set icon and text properties
    #         option.icon = QIcon(colorize_pixmap(QPixmap(self.icon_path_checked)))  # clean
    #         option.iconSize = self.iconSize()
    #         option.text = self.text()

    #         painter = QPainter()
    #         if not painter.begin(self):
    #             super().paintEvent(event)
    #             return
    #         # Draw button background without checked state
    #         self.style().drawControl(QStyle.CE_PushButton, option, painter, self)
    #         # Draw button content (icon and text)
    #         self.style().drawControl(QStyle.CE_PushButtonLabel, option, painter, self)
    #         painter.end()
    #     else:
    #         # Use default painting behavior
    #         super().paintEvent(event)
