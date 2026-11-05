
from plugins.workflows.members import MediaMember
from utils.helpers import set_module_type


@set_module_type(module_type='Members', settings='video_settings')
class Video(MediaMember):
    default_role = 'video'
    default_avatar = ':/resources/icon-video.png'
    default_name = 'Video'
    OUTPUT = 'VIDEO'
