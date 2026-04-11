from PySide6.QtCore import QTimer

from gui.widgets.config_fields import ConfigFields
from plugins.workflows.widgets.media_settings import MediaSettings
from utils.helpers import set_module_type


@set_module_type(module_type='Widgets')
class ImageSettings(MediaSettings):
    file_filter = 'Image Files (*.png *.jpg *.jpeg *.gif *.bmp *.webp *.svg *.tiff);;All Files (*)'
    model_kind = 'IMAGE'

    def build_url_settings(self, parent):
        return self.ImageUrlSettings(parent=parent)

    class ImageUrlSettings(ConfigFields):
        def __init__(self, parent):
            super().__init__(parent=parent)
            self.schema = [
                {
                    'text': 'URL',
                    'key': 'url',
                    'type': str,
                    'placeholder_text': 'Enter image URL...',
                    'label_position': None,
                    'stretch_x': True,
                    'default': '',
                },
                {
                    'text': 'Use URL',
                    'type': 'button',
                    'clicked': '_on_use_url_clicked',
                    'label_position': None,
                },
            ]

        def _on_use_url_clicked(self):
            """Use the URL directly as the browse path."""
            url = self.url_wgt.get_value()
            if not url:
                return
            settings = self.parent.parent  # ImageSettings
            QTimer.singleShot(
                50,
                lambda: settings.multi_preview.set_results(
                    [{'url': url}]
                ),
            )
