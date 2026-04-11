"""Standalone audio preview widget.

Displays a filename label and a play button that uses
``utils.media.play_file()`` for playback.
"""

import os

from PySide6.QtWidgets import QWidget, QPushButton, QLabel, QSizePolicy

from gui.util import CHBoxLayout


class AudioPreview(QWidget):
    """Reusable audio preview with play button."""

    def __init__(self, parent=None):
        super().__init__(parent=parent)
        self.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Expanding)
        self.filepath = None

        self.layout = CHBoxLayout(self)
        self.layout.setSpacing(5)

        self.filename_label = QLabel(self)
        self.filename_label.setSizePolicy(
            QSizePolicy.Expanding, QSizePolicy.Preferred)
        self.layout.addWidget(self.filename_label)

        self.play_button = QPushButton("\u25b6")
        self.play_button.setFixedSize(30, 30)
        self.play_button.clicked.connect(self._play)
        self.layout.addWidget(self.play_button)

    def set_filepath(self, filepath):
        """Set the audio file to preview.

        Parameters
        ----------
        filepath : str
            Absolute path to an audio file.
        """
        self.filepath = filepath
        filename = os.path.basename(filepath)
        self.filename_label.setText(filename)

    def _play(self):
        if self.filepath:
            from utils.media import play_file
            play_file(self.filepath)
