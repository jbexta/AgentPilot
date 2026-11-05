
from plugins.studio.studios.image_studio import ImageStudio
# from plugins.studio.studios.video_studio import VideoStudio
from utils.helpers import set_module_type


@set_module_type('Pages')
class Page_Images(ImageStudio):
    display_name = 'Images'
    icon_path = ":/resources/icon-image.png"
    page_type = 'any'

    def __init__(self, parent):
        super().__init__(parent=parent, full_screen=False)
