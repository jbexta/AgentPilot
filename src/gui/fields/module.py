"""
Module selection field widget for configurable module choices.

This module provides a ModuleComboBox field widget that extends BaseCombo to create
a dropdown for selecting and managing modules within specific module types. It supports
dynamic module loading from the module system, the ability to create new modules
through a dialog interface, and integration with the configuration system. The widget
automatically populates with available modules of the specified type.
"""  # unchecked

from PySide6.QtWidgets import QInputDialog

from gui import system
from gui.fields.combo import BaseCombo
from utils.helpers import block_signals


class ModuleComboBox(BaseCombo):
    def __init__(self, *args, **kwargs):
        self.first_item = kwargs.pop('first_item', None)
        self.module_type = kwargs.pop('module_type', None)
        super().__init__(*args, **kwargs)
        # self.items_have_keys = False
        self.currentIndexChanged.connect(self.on_index_changed)
        self.load()

    def load(self):
        with block_signals(self):
            modules = system.manager.modules.get_modules_in_folder(
                module_type=self.module_type,
                fetch_keys=('name',)
            )

            self.clear()
            for module_name in modules:
                self.addItem(module_name, module_name)
            self.addItem('< New Module >', '<NEW>')

    def on_index_changed(self, index):
        if self.itemData(index) == '<NEW>':
            # module_type_folder_id = None
            # if self.module_type:
            #     module_type_folder_id = get_module_type_folder_id(module_type=self.module_type)

            module_label = 'module' if not self.module_type else f'{self.module_type} module'
            new_module_name, ok = QInputDialog.getText(self, f"New {module_label.title()}", f"Enter the name for the new {module_label}:")
            if ok and new_module_name:
                system.manager.modules.add(new_module_name, module_type=self.module_type)

                self.load()

                new_index = self.findText(new_module_name)
                if new_index != -1:
                    self.setCurrentIndex(new_index)
            else:
                # If dialog was cancelled or empty input, revert to previous selection
                self.setCurrentText('Default')
        if self.parent:
            self.parent.update_config()