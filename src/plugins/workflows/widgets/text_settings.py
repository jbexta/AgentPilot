
"""
Text Block Settings Widget for Agent Pilot.

This module provides a specialized configuration widget for managing text block settings
within the Agent Pilot application. It enables users to configure text blocks, member
options, and various parameters for text processing and display within workflows.

Key Features:
• Block type selection through plugin-based dropdown interface
• Member options configuration for text block associations
• Integration with the Agent Pilot plugin system for block discovery
• Dynamic configuration fields based on selected block type
• Support for text processing and formatting options
• Real-time configuration updates and validation
• Seamless integration with the ConfigFields architecture
• Flexible text block parameter and member management

The TextBlockSettings widget extends ConfigFields to provide a specialized interface for
configuring text blocks and their associated member options. It serves as a key component
in the Agent Pilot workflow system, enabling users to set up and customize text processing
blocks that handle textual content within agent interactions and automated workflows.
"""  # unchecked

from gui.widgets.config_fields import ConfigFields


class TextSettings(ConfigFields):
    def __init__(self, parent):
        super().__init__(parent=parent)
        self.schema = [
            {
                'text': 'Data',
                'type': str,
                'default': '',
                'num_lines': 2,
                'stretch_x': True,
                'stretch_y': True,
                'wrap_text': True,
                'highlighter': 'xml',
                'fold_mode': 'xml',
                'format_blocks': True,
                'label_position': None,
            },
        ]
