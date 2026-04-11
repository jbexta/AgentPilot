"""
File picker field widget for configurable file selection.

This module provides a FilePicker field widget that extends QWidget to create
an interactive file selection interface. It includes a text input for manual entry
and a browse button for file dialogs. Integrates with the configuration system for file path settings.
"""

from PySide6.QtWidgets import QSizePolicy, QWidget, QLineEdit, QFileDialog, QHBoxLayout

from gui.util import IconButton


class FilePicker(QWidget):
    def __init__(self, parent, **kwargs):
        super().__init__(parent)
        self.parent = parent
        width = kwargs.get('width', None)
        placeholder = kwargs.get('placeholder', 'Select or enter path...')
        self.file_filter = kwargs.get('file_filter', 'All Files (*)')
        self.mode = kwargs.get('mode', 'open')

        # Create layout
        self.layout = QHBoxLayout(self)
        self.layout.setContentsMargins(0, 0, 0, 0)
        self.layout.setSpacing(4)

        # Create path input
        self.path_input = QLineEdit(self)
        self.path_input.setPlaceholderText(placeholder)
        self.path_input.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
        
        # Create browse button
        self.browse_button = IconButton(self, icon_path=':/resources/icon-folder.png')
        self.browse_button.setMaximumWidth(60)
        self.browse_button.clicked.connect(self.browse_path)
        
        # Add widgets to layout
        self.layout.addWidget(self.path_input)
        self.layout.addWidget(self.browse_button)
        
        # Set fixed width if specified
        if width:
            self.setFixedWidth(width)
            # Adjust path input width to fill remaining space
            button_width = self.browse_button.maximumWidth()
            spacing = self.layout.spacing()
            path_width = width - button_width - spacing - 10
            self.path_input.setFixedWidth(max(path_width, 100))
        
        # Connect signals
        self.path_input.textChanged.connect(parent.update_config)

    def get_value(self):
        return self.path_input.text()

    def set_value(self, value):
        if value:
            self.path_input.setText(str(value))

    def clear_value(self):
        self.path_input.clear()

    def browse_path(self):
        current_path = self.path_input.text()

        if self.mode == 'directory':
            path = QFileDialog.getExistingDirectory(
                self,
                'Select Directory',
                current_path
            )
        elif self.mode == 'save':
            path, _ = QFileDialog.getSaveFileName(
                self,
                'Save File',
                current_path,
                self.file_filter
            )
        else:
            path, _ = QFileDialog.getOpenFileName(
                self,
                'Select File',
                current_path,
                self.file_filter
            )

        if path:
            self.path_input.setText(path)