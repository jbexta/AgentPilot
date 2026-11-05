from plugins.projects.core.web_stacks.base import WebStack
from utils.helpers import set_module_type


@set_module_type(module_type='Web_stacks')
class StaticStack(WebStack):
    display_name = 'Static'
    priority = 99  # the fallback when nothing else recognises the project

    @classmethod
    def detect(cls, path):
        return True

    @classmethod
    def url(cls, path, port):
        return cls.file_url(path)