
from functools import partial
from PySide6.QtWidgets import QMenu
from PySide6.QtGui import QAction, QFont

from gui import system
from gui.gui_utils.icon_button import IconButton


class ProjectTypeMenu(IconButton):  # todo dedupe
    def __init__(self, parent, **kwargs):
        super().__init__(
            parent=parent,
            icon_path=':/resources/icon-refresh.png',
            size=24,
        )
        self.current_value = None
        self.menu = QMenu(self)
        self.clicked.connect(self.show_menu)

    def select_item(self, value):
        """Handle menu item selection"""
        self.current_value = value
        self.update_config()

    def get_value(self):
        """Get the currently selected value"""
        return self.current_value

    def set_value(self, value):
        self.current_value = value

    def set_member_type(self, value):
        self.current_value = value
        self.update_config()

    def add_contxt_menu_header(self, menu, title):  # todo dedupe
        section = QAction(title, self)
        section.setEnabled(False)
        font = QFont()
        font.setPointSize(8)
        section.setFont(font)
        menu.addAction(section)

    def update_config(self):
        """Implements same method as ConfigWidget, as a workaround to avoid inheriting from it"""
        if hasattr(self.parent, 'update_config'):
            self.parent.update_config()

        if hasattr(self, 'save_config'):
            self.save_config()

    def show_menu(self):
        """Show the dropdown menu"""
        # clear the menu
        self.menu.clear()

        # populate the menu
        member_modules = system.manager.modules.get_modules_in_folder(
            module_type='Project_types',
            fetch_keys=('name', 'kind_folder', 'class',)
        )

        value_kind = next((kind_folder for name, kind_folder, module_class in member_modules if name == self.current_value), None)

        type_dict = {}
        for module_name, kind_folder, module_class in member_modules:
            if kind_folder not in type_dict:
                type_dict[kind_folder] = []
            type_dict[kind_folder].append((module_name, module_class))

        for module_kind, kind_modules in type_dict.items():
            # if not module_kind:
            #     continue
            if value_kind:
                if value_kind != module_kind:
                    continue
            elif module_kind:
                self.add_contxt_menu_header(self.menu, module_kind.capitalize())

            for module_name, module_class in kind_modules:
                if value_kind and module_name == self.current_value:
                    continue
                self.menu.addAction(module_name.capitalize(), partial(
                    self.set_member_type,
                    module_name
                ))
                # elif workflow_insert_mode == 'list':
                #     self.menu.addAction(module_name.capitalize(), partial(self.choose_member, 'AGENT'))
                # else:
                #     continue

        # set_kind = next((kind_folder for name, kind_folder in module_type_modules if name == value), None)

        # for module_name, module_class, baked, kind_folder in module_type_modules:

        button_rect = self.rect()
        menu_pos = self.mapToGlobal(button_rect.bottomLeft())
        self.menu.exec(menu_pos)