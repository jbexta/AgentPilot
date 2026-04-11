"""Standalone video preview widget.

Provides a video player with play/pause button, position slider,
and duration label using QMediaPlayer + QVideoWidget.
"""

from PySide6.QtCore import QUrl, Qt
from PySide6.QtMultimedia import QMediaPlayer, QAudioOutput
from PySide6.QtMultimediaWidgets import QVideoWidget
from PySide6.QtWidgets import (
    QWidget, QHBoxLayout, QPushButton,
    QSlider, QLabel, QSizePolicy,
)

from gui.util import CVBoxLayout

_POPUP_MAX = 500


class VideoPreview(QWidget):
    """Reusable video player widget with playback controls."""

    def __init__(self, parent=None):
        super().__init__(parent=parent)
        self.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Expanding)

        self.video_widget = None
        self.media_player = None
        self.audio_output = None
        self.play_button = None
        self.position_slider = None
        self.duration_label = None
        self.controls_widget = None

        self.main_layout = CVBoxLayout(self)

    def set_filepath(self, filepath):
        """Set up the player and load *filepath*.

        Parameters
        ----------
        filepath : str
            Absolute path to a video file.
        """
        self._setup_player(filepath=filepath, url=None)

    def set_url(self, url):
        """Set up the player and load a remote *url*."""
        self._setup_player(filepath=None, url=url)

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _setup_player(self, filepath, url):
        # Video widget
        self.video_widget = QVideoWidget(self)
        self.video_widget.setSizePolicy(
            QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.video_widget.setMinimumSize(0, 0)
        self.video_widget.setStyleSheet("background-color: black;")
        self.video_widget.mousePressEvent = (
            lambda event: self._toggle_playback()
            if event.button() == Qt.LeftButton else None
        )
        self.main_layout.addWidget(self.video_widget)

        # Controls
        self._create_controls()
        self.main_layout.addWidget(self.controls_widget)

        # Media player
        self.media_player = QMediaPlayer(self)
        self.audio_output = QAudioOutput(self)
        self.media_player.setAudioOutput(self.audio_output)
        self.media_player.setVideoOutput(self.video_widget)

        self.media_player.durationChanged.connect(self._update_duration)
        self.media_player.positionChanged.connect(self._update_position)
        self.media_player.errorOccurred.connect(self._handle_error)
        self.media_player.mediaStatusChanged.connect(
            self._on_media_status_changed)

        if filepath:
            self.media_player.setSource(
                QUrl.fromLocalFile(filepath))
        elif url:
            self.media_player.setSource(QUrl(url))

    def _create_controls(self):
        self.controls_widget = QWidget()
        layout = QHBoxLayout()
        layout.setContentsMargins(0, 0, 0, 0)

        self.play_button = QPushButton("\u25b6")
        self.play_button.setFixedSize(30, 30)
        self.play_button.clicked.connect(self._toggle_playback)
        layout.addWidget(self.play_button)

        self.position_slider = QSlider(Qt.Horizontal)
        self.position_slider.sliderMoved.connect(self._set_position)
        layout.addWidget(self.position_slider)

        self.duration_label = QLabel("00:00 / 00:00")
        self.duration_label.setFixedWidth(80)
        layout.addWidget(self.duration_label)

        self.controls_widget.setLayout(layout)

    def _toggle_playback(self):
        if self.media_player.playbackState() == \
                QMediaPlayer.PlayingState:
            self.media_player.pause()
            self.play_button.setText("\u25b6")
        else:
            self.media_player.play()
            self.play_button.setText("\u23f8")

    def _set_position(self, position):
        self.media_player.setPosition(position)

    def _update_duration(self, duration):
        self.position_slider.setRange(0, duration)
        self.duration_label.setText(
            f"00:00 / {self._format_time(duration)}")

    def _update_position(self, position):
        if not self.position_slider.isSliderDown():
            self.position_slider.setValue(position)
        duration = self.media_player.duration()
        self.duration_label.setText(
            f"{self._format_time(position)} / "
            f"{self._format_time(duration)}")

    @staticmethod
    def _format_time(ms):
        seconds = ms // 1000
        minutes = seconds // 60
        seconds = seconds % 60
        return f"{minutes:02d}:{seconds:02d}"

    def _handle_error(self, error, error_string):
        print(f"Media player error: {error} - {error_string}")

    def _on_media_status_changed(self, status):
        if status == QMediaPlayer.LoadedMedia:
            self.media_player.play()
            self.media_player.pause()
            self.play_button.setText("\u25b6")

    def cleanup(self):
        """Stop the player and release resources."""
        if self.media_player:
            self.media_player.stop()
