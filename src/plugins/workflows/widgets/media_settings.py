import asyncio
import os

from gui.widgets.config_fields import ConfigFields
from gui.widgets.config_joined import ConfigJoined
from gui.widgets.config_tabs import ConfigTabs
from gui.widgets.multi_preview import MultiPreview
from plugins.workflows.widgets.generate_widget import GenerateWidget
from utils.filesystem import get_application_path
from utils.helpers import display_message, set_module_type


@set_module_type(module_type="Widgets")
class MediaSettings(ConfigJoined):
    """Base class for media settings (Image, Video, Audio).

    Subclasses must define:
        file_filter: str - file dialog filter string
        model_kind: str - 'IMAGE', 'VIDEO', or 'AUDIO'
    """
    file_filter = 'All Files (*)'
    model_kind = 'IMAGE'

    def __init__(self, parent):
        super().__init__(parent=parent)
        self.multi_preview = MultiPreview(parent=self)
        self.widgets = [
            self.BrowseSettings(parent=self),
            self.MediaSettingsTabs(parent=self),
            self.multi_preview,
        ]

    def reload_predicates(self):
        model_settings = self.widgets[1].pages['Model']
        model_settings.widgets[1].refresh_visibility()

    class BrowseSettings(ConfigFields):
        def __init__(self, parent):
            super().__init__(parent=parent, conf_namespace='browse')
            self.schema = [
                {
                    'text': 'Path',
                    'key': 'path',
                    'type': 'file_picker',
                    'label_position': None,
                    'stretch_x': True,
                    'file_filter': parent.file_filter,
                },
            ]

    class MediaSettingsTabs(ConfigTabs):
        stretch = 1

        def __init__(self, parent):
            super().__init__(parent=parent)
            self.pages = {
                'Model': self.ModelSettings(parent=self),
                'URL': parent.build_url_settings(parent=self),
            }
            self.content.currentChanged.disconnect()
            self.content.currentChanged.connect(self.on_current_changed)

        def get_config(self):
            config = super().get_config()
            selected_page_key = list(self.pages.keys())[self.content.currentIndex()]
            config['mode'] = selected_page_key
            return config

        def on_current_changed(self, _):
            selected_page_key = list(self.pages.keys())[self.content.currentIndex()]
            self.config['mode'] = selected_page_key
            super().on_current_changed(_)

        def load(self):
            super().load()
            selected_page_key = self.config.get('mode', 'Model')
            self.goto_page(selected_page_key)

        class ModelSettings(ConfigJoined):
            def __init__(self, parent):
                super().__init__(parent=parent)
                self.widgets = [
                    self.ModelFields(parent=self),
                    self.GenerateFields(parent=self),
                ]

            class ModelFields(ConfigFields):
                def __init__(self, parent):
                    super().__init__(parent=parent)
                    # Walk up to find the MediaSettings to get model_kind
                    media_settings = parent.parent.parent
                    self.schema = [
                        {
                            'text': 'Model',
                            'type': 'model',
                            'model_kind': media_settings.model_kind,
                            'width': 200,
                            'stretch_y': True,
                        },
                    ]

            class GenerateFields(GenerateWidget):
                def get_current_model(self):
                    model_fields = self.parent.widgets[0]
                    return model_fields.model_wgt.get_value()

    def build_url_settings(self, parent):
        """Override in subclasses for custom URL tab behavior."""
        return None


class DownloadUrlSettings(ConfigFields):
    """URL settings with yt-dlp download support for Video and Audio."""
    ydl_format = 'bestvideo+bestaudio/best'
    merge_output_format = None

    def __init__(self, parent):
        super().__init__(parent=parent)
        self.schema = [
            {
                'text': 'URL',
                'key': 'url',
                'type': str,
                'placeholder_text': 'Enter URL...',
                'label_position': None,
                'stretch_x': True,
                'default': '',
            },
            {
                'text': 'Download',
                'type': 'button',
                'clicked': '_on_download_clicked',
                'label_position': None,
            },
        ]

    def _on_download_clicked(self):
        asyncio.ensure_future(self._do_download())

    async def _do_download(self):
        """Download media from URL using yt-dlp."""
        url = self.url_wgt.get_value()
        if not url:
            return

        output_dir = os.path.join(
            get_application_path(), 'videos'
        )
        os.makedirs(output_dir, exist_ok=True)

        self.download_wgt.setEnabled(False)
        self.download_wgt.setText("Downloading...")

        try:
            filepath = await asyncio.to_thread(
                self._run_ytdlp, url, output_dir
            )
            settings = self.parent.parent  # MediaSettings
            settings.multi_preview.set_results(
                [{'filepath': filepath}]
            )
        except Exception as e:
            display_message(
                f"Download failed: {e}"
            )
        finally:
            self.download_wgt.setText("Download")
            self.download_wgt.setEnabled(True)

    def _run_ytdlp(self, url, output_dir):
        """Run yt-dlp download synchronously."""
        import yt_dlp

        downloaded_files = []

        def progress_hook(d):
            if d['status'] == 'finished':
                filepath = d.get('filename', '')
                if filepath:
                    downloaded_files.append(filepath)

        ydl_opts = {
            'quiet': True,
            'no_warnings': True,
            'outtmpl': os.path.join(
                output_dir, '%(title)s.%(ext)s'
            ),
            'format': self.ydl_format,
            'extractor_args': {
                'youtube': {
                    'player_client': ['android', 'web'],
                },
            },
            'progress_hooks': [progress_hook],
        }
        if self.merge_output_format:
            ydl_opts['merge_output_format'] = self.merge_output_format

        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=True)
            filepath = ydl.prepare_filename(info)
            if not os.path.exists(filepath) \
                    and downloaded_files:
                filepath = downloaded_files[-1]
        return filepath