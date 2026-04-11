
"""
Prompt Block Settings Widget for Agent Pilot.

This module provides a specialized configuration widget for managing prompt block settings
within the Agent Pilot application. It enables users to configure prompt blocks, their
associated models, and various parameters for AI prompt processing and execution.

Key Features:
• Block type selection through plugin-based dropdown interface
• Model selection and configuration for prompt processing
• Integration with the Agent Pilot plugin system for block discovery
• Dynamic configuration fields based on selected block type
• Support for multiple prompt processing models and providers
• Real-time configuration updates and validation
• Seamless integration with the ConfigFields architecture
• Flexible prompt block parameter management

The PromptBlockSettings widget extends ConfigFields to provide a specialized interface for
configuring prompt blocks and their associated AI models. It serves as a fundamental component
in the Agent Pilot workflow system, enabling users to set up and customize prompt processing
blocks that form the core of AI agent interactions and automated workflows.
"""  # unchecked

from gui.widgets.config_fields import ConfigFields


class PromptSettings(ConfigFields):
    def __init__(self, parent):
        super().__init__(parent=parent)
        self.schema = [
            {
                'text': 'Model',
                'key': 'prompt_model',
                'type': 'model',
                'popup_params': True,
                'model_kind': 'CHAT',
                'label_position': None,
                'default': 'default',
            },
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
                'label_position': None,
            },
        ]