from gui.widgets.config_fields import ConfigFields
from utils.helpers import set_module_type


@set_module_type(module_type='Widgets')
class GitDiffSettings(ConfigFields):
    def __init__(self, parent):
        super().__init__(parent=parent)
        self.schema = [
            {
                'text': 'Repository',
                'key': 'directory',
                'type': 'file_picker',
                'mode': 'directory',
                'default': '{{ cwd }}',
                'stretch_x': True,
            },
            {
                'text': 'From',
                'key': 'from',
                'type': str,
                'default': '',
                'stretch_x': True,
                'tooltip': 'A checkpoint name or a commit',
            },
            {
                'text': 'To',
                'key': 'to',
                'type': str,
                'default': '',
                'stretch_x': True,
                'tooltip': 'A checkpoint name or a commit, or empty for the working tree',
            },
            {
                'text': 'Exclude',
                'key': 'exclude',
                'type': str,
                'default': '*.db',
                'width': 150,
                'tooltip': 'Patterns to skip when To is the working tree, '
                           'separated by spaces or commas, e.g. *.db *.zip',
            },
        ]
