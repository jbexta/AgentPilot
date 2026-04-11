"""
Input Settings Widget for Agent Pilot.

This module provides a comprehensive configuration widget for managing input field settings
and conditional logic within the Agent Pilot application. It combines multiple configuration
interfaces to create a unified input configuration experience.

Key Features:
• Composite widget combining input fields and conditional logic settings
• Vertical layout organization for optimal user experience
• Integration with ConfigFields for basic input configuration
• Support for conditional input behavior and validation rules
• Dynamic configuration updates with real-time validation
• Error handling and user feedback through message dialogs
• JSON tree configuration for complex input structures
• Seamless integration with the parent widget architecture

The InputSettings widget extends ConfigJoined to provide a unified interface for
configuring input field behavior and conditional logic. It serves as a central component
in the Agent Pilot system for managing user input configurations, enabling flexible
and dynamic input handling throughout the application.
"""  # unchecked

from PySide6.QtWidgets import QMessageBox

from gui.widgets.config_fields import ConfigFields
from gui.widgets.config_joined import ConfigJoined
from gui.widgets.config_json_tree import ConfigJsonTree
from utils.helpers import display_message


class InputSettings(ConfigJoined):
    def __init__(self, parent):
        super().__init__(parent, layout_type='vertical')
        self.input_key = None
        self.widgets = [
            self.InputFields(self),
            self.InputConditional(self),
        ]

    def update_config(self):
        self.save_config()

    def save_config(self):
        conf = self.get_config()
        is_looper = conf.get('looper', False)
        reload = False
        if not is_looper:
            # check circular references #(member_id, [input_member_id])
            target_member_id = self.input_key[1]
            source_member_id = self.input_key[0]
            cr_check = self.parent.check_for_circular_references(target_member_id, [source_member_id])
            if cr_check:
                display_message(
                    message='Circular reference detected',
                    icon=QMessageBox.Warning,
                )
                conf['looper'] = True
                self.parent.inputs_in_view[self.input_key].config = conf
                self.widgets[0].widgets[0].looper.setChecked(True)
                return

        self.parent.inputs_in_view[self.input_key].config = conf
        self.parent.update_config()
        # repaint all lines
        graphics_item = self.parent.inputs_in_view[self.input_key]
        graphics_item.updatePosition()
        if reload:  # temp
            self.load()

    class InputConditional(ConfigFields):
        def __init__(self, parent):
            super().__init__(parent, add_stretch_to_end=True)
            self.schema = [
                {
                    'text': 'Conditional',
                    'type': bool,
                    'default': False,
                },
                {
                    'text': 'Condition',
                    'type': str,
                    'num_lines': 2,
                    'stretch_x': True,
                    'stretch_y': True,
                    'highlighter': 'cel',
                    'monospaced': True,
                    'label_position': None,
                    'visibility_predicate': lambda fields: fields.config.get('conditional', False),
                    'default': 'true',
                },
            ]

    class InputFields(ConfigJoined):
        def __init__(self, parent):
            super().__init__(parent, add_stretch_to_end=True)
            self.widgets = [
                self.InputLooper(self),
                self.InputMappings(self),
            ]

        class InputLooper(ConfigFields):
            def __init__(self, parent):
                super().__init__(parent)
                self.schema = [
                    {
                        'text': 'Looper',
                        'type': bool,
                        'row_key': 0,
                        'default': False,
                    },
                    {
                        'text': 'Max loops',
                        'type': int,
                        'minimum': 1,
                        'maximum': 9999,
                        'step': 1,
                        'row_key': 0,
                        'visibility_predicate': lambda fields: fields.config.get('looper', False),
                        'has_toggle': True,
                        'default': 10,
                    },
                ]

        class InputMappings(ConfigJsonTree):
            def __init__(self, parent):
                super().__init__(
                    parent=parent,
                    add_item_options={'title': 'NA', 'prompt': 'NA'},
                    del_item_options={'title': 'NA', 'prompt': 'NA'},
                    tree_header_resizable=False,
                )
                self.tree.setObjectName('input_items')
                self.conf_namespace = 'mappings'
                self.schema = [
                    {
                        'text': 'Source',
                        'type': 'input_source',
                        'stretch': True,
                        'default': None,
                    },
                    {
                        'text': 'Target',
                        'type': 'input_target',
                        'width': 150,
                        'default': None,
                    },
                ]