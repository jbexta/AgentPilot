
"""
Notification Settings Widget for Agent Pilot.

This module provides a specialized configuration widget for managing notification settings
and visual notification properties within the Agent Pilot application. It enables users
to customize notification appearance, behavior, and styling preferences.

Key Features:
• Color customization for notification display and theming
• Notification field configuration through ConfigFields integration
• Support for visual notification styling and appearance settings
• Integration with the Agent Pilot notification system
• Real-time notification preview and configuration updates
• Support for mini avatar display in notifications
• Dynamic notification behavior configuration
• Seamless integration with the parent widget architecture

The NotifSettings widget extends ConfigJoined to provide a unified interface for
configuring notification appearance and behavior. It serves as a key component in the
Agent Pilot user interface for customizing the notification experience, allowing users
to personalize how notifications are displayed and interact with the application.
"""  # unchecked

from gui.widgets.config_fields import ConfigFields
from gui.widgets.config_joined import ConfigJoined
from utils.helpers import set_module_type


@set_module_type(module_type='Widgets')
class NotifSettings(ConfigJoined):
    def __init__(self, parent):
        super().__init__(parent=parent)
        self.widgets = [
            self.NotifFields(self),
        ]

    class NotifFields(ConfigFields):
        def __init__(self, parent):
            super().__init__(parent=parent)
            self.schema = [
                {
                    'text': 'Icon',
                    'type': ('NoIcon', 'Information', 'Warning', 'Critical'),
                    'default': 'Information',
                    'row_key': 0,
                },
                {
                    'text': 'Duration (ms)',
                    'key': 'duration',
                    'type': int,
                    'default': 5000,
                    'row_key': 0,
                },
                {
                    'text': 'Title',
                    'type': str,
                    'has_toggle': True,
                    'default': '',
                    'row_key': 1,
                },
                {
                    'text': 'Color',
                    'type': 'color_picker',
                    'default': '#438BB9',
                    'row_key': 1,
                },
                {
                    'text': 'Text',
                    'type': str,
                    'default': '',
                    'num_lines': 4,
                    'stretch_x': True,
                    'stretch_y': True,
                    'label_position': 'top',
                },
            ]
            