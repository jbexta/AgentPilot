from PySide6.QtWidgets import QMessageBox

from src.gui.widgets.config_fields import ConfigFields
from src.gui.widgets.config_joined import ConfigJoined
from src.gui.widgets.config_json_tree import ConfigJsonTree
from src.utils.helpers import display_message


class InputSettings(ConfigJoined):
    def __init__(self, parent):
        super().__init__(parent, add_stretch_to_end=True)
        self.input_key = None
        self.widgets = [
            self.InputFields(self),
            self.InputMappings(self),
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
                display_message(self,
                                message='Circular reference detected',
                                icon=QMessageBox.Warning,
                                )
                conf['looper'] = True  # todo bug
                self.parent.inputs_in_view[self.input_key].config = conf
                self.widgets[0].looper.setChecked(True)
                return

        self.parent.inputs_in_view[self.input_key].config = conf
        self.parent.update_config()
        # repaint all lines
        graphics_item = self.parent.inputs_in_view[self.input_key]
        graphics_item.updatePosition()
        if reload:  # temp
            self.load()

    class InputFields(ConfigFields):
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
                    'text': 'Condition',
                    'type': bool,
                    'row_key': 0,
                    'default': False,
                },
            ]

    class InputMappings(ConfigJsonTree):
        def __init__(self, parent):
            super().__init__(parent=parent,
                             add_item_options={'title': 'NA', 'prompt': 'NA'},
                             del_item_options={'title': 'NA', 'prompt': 'NA'},
                             tree_header_resizable=False ,)
            self.tree.setObjectName('input_items')
            self.conf_namespace = 'mappings'
            self.schema = [
                {
                    'text': 'Source',
                    'type': 'InputSourceComboBox',
                    'width': 175,
                    'default': None,
                },
                {
                    'text': 'Target',
                    'type': 'InputTargetComboBox',
                    'width': 175,
                    'default': None,
                },
            ]