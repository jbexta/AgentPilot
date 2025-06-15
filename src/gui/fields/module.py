from PySide6.QtWidgets import QInputDialog

from src.gui.fields.combo import BaseCombo
from src.utils.helpers import block_signals


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
            from src.system import manager
            modules = manager.modules.get_modules_in_folder(
                module_type=self.module_type,
                fetch_keys=('name',)
            )

            self.clear()
            for module_name in modules:
                self.addItem(module_name)  # , module_id)
            self.addItem('< New Module >', '<NEW>')

    def on_index_changed(self, index):
        if self.itemData(index) == '<NEW>':
            # module_type_folder_id = None
            # if self.module_type:
            #     module_type_folder_id = get_module_type_folder_id(module_type=self.module_type)

            module_label = 'module' if not self.module_type else f'{self.module_type} module'
            new_module_name, ok = QInputDialog.getText(self, f"New {module_label.title()}", f"Enter the name for the new {module_label}:")
            if ok and new_module_name:
                from src.system import manager
                manager.modules.add(new_module_name, module_type=self.module_type)

                self.load()

                new_index = self.findText(new_module_name)
                if new_index != -1:
                    self.setCurrentIndex(new_index)
            else:
                # If dialog was cancelled or empty input, revert to previous selection
                self.setCurrentText('Default')