
from plugins.workflows.members import MediaMember
from utils.helpers import set_module_type


@set_module_type(module_type='Members', settings='image_settings')
class Image(MediaMember):
    default_role = 'image'
    default_avatar = ':/resources/icon-image.png'
    default_name = 'Image'
    OUTPUT = 'IMAGE'
