from plugins.studio.studios.video_studio import VideoStudio
from utils.helpers import set_module_type


@set_module_type('Pages')
class Page_Videos(VideoStudio):
    display_name = 'Videos'
    icon_path = ":/resources/icon-video.png"
    page_type = 'any'

    def __init__(self, parent):
        super().__init__(parent=parent, full_screen=False)
        self.recent_file_restored = False

    def load(self):
        if not self.recent_file_restored:
            self.recent_file_restored = True
            recent_files = self._get_recent_files()
            if recent_files:
                self._open_file_path(recent_files[0], only_load_config=True)
        super().load()
