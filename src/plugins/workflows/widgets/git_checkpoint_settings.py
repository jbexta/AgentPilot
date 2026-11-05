from gui.widgets.config_fields import ConfigFields
from utils.helpers import set_module_type


@set_module_type(module_type='Widgets')
class GitCheckpointSettings(ConfigFields):
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
                'text': 'Checkpoint name',
                'key': 'checkpoint_name',
                'type': str,
                'default': '{{ project_name }}_snapshot',
                'width': 250,
            },
            {
                'text': 'Expire after',
                'key': 'expire',
                'type': str,
                'default': '30 days',
                'width': 120,
                'tooltip': 'Forget older checkpoints after this long, '
                           'e.g. 2 weeks, or never to keep them all',
            },
            {
                'text': 'Exclude',
                'key': 'exclude',
                'type': str,
                'default': '*.db',
                'width': 150,
                'tooltip': 'Patterns to skip, separated by spaces or '
                           'commas, e.g. *.db *.zip',
            },
            {
                'text': 'Include untracked',
                'key': 'include_untracked',
                'type': bool,
                'default': True,
            },
        ]
