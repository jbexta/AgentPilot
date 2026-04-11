from plugins.workflows.widgets.media_settings import MediaSettings, DownloadUrlSettings
from utils.helpers import set_module_type


@set_module_type(module_type='Widgets')
class AudioSettings(MediaSettings):
    file_filter = 'Audio Files (*.mp3 *.wav *.flac *.ogg *.m4a *.aac *.wma);;All Files (*)'
    model_kind = 'AUDIO'

    def build_url_settings(self, parent):
        return self.AudioUrlSettings(parent=parent)

    class AudioUrlSettings(DownloadUrlSettings):
        ydl_format = 'bestaudio/best'
