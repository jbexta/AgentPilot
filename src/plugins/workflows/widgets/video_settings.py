from plugins.workflows.widgets.media_settings import MediaSettings, DownloadUrlSettings
from utils.helpers import set_module_type


@set_module_type(module_type='Widgets')
class VideoSettings(MediaSettings):
    file_filter = 'Video Files (*.mp4 *.avi *.mov *.mkv *.webm *.wmv *.flv);;All Files (*)'
    model_kind = 'VIDEO'

    def build_url_settings(self, parent):
        return self.VideoUrlSettings(parent=parent)

    class VideoUrlSettings(DownloadUrlSettings):
        ydl_format = 'bestvideo+bestaudio/best'
        merge_output_format = 'mp4'
