from PySide6.QtCore import QPoint, QSize
from PySide6.QtGui import QStandardItem, QStandardItemModel, Qt
from PySide6.QtWidgets import QHBoxLayout, QWidget

from gui import system
from gui.gui_utils.helpers import find_attribute
from gui.gui_utils.icon_button import IconButton
from utils import sql


class EditBar(QWidget):
    def __init__(self, editing_widget):
        super().__init__(parent=None)
        self.editing_widget = editing_widget
        self.editing_module_id = find_attribute(editing_widget, 'module_id')
        self.class_name = editing_widget.__class__.__name__
        module_name = sql.get_scalar(
            "SELECT name FROM modules WHERE id = ?",
            (self.editing_module_id,)
        )
        controller = system.manager.modules.type_controllers.get('pages')
        loaded_module = None
        if controller and module_name:
            module_path = controller.get_module_path(module_name)
            import sys as _sys
            loaded_module = _sys.modules.get(module_path)
        from gui.builder import get_class_path
        class_tup = get_class_path(loaded_module, self.class_name)
        self.class_map = None
        if class_tup:
            self.class_map, _ = class_tup

        # Detect current superclass via MRO against registered Widget modules
        widget_modules = system.manager.modules.get_modules_in_folder(
            'Widgets', fetch_keys=('name', 'class'))
        self.current_superclass = None
        current_mod_name = None
        for base in type(editing_widget).__mro__:
            for mod_name, mod_cls in widget_modules:
                if base is mod_cls:
                    self.current_superclass = base
                    current_mod_name = mod_name
                    break
            if self.current_superclass:
                break

        self.page_editor = find_attribute(editing_widget, 'module_popup')

        self.setWindowFlags(Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint)
        self.setProperty('class', 'edit-bar')

        self.layout = QHBoxLayout(self)

        from gui.fields.combo import BaseCombo
        self.type_combo = BaseCombo()
        self.type_combo.setFixedWidth(150)

        # Group modules by origin (Core vs plugin name)
        def _get_group(cls):
            mod = getattr(cls, '__module__', '')
            if mod.startswith('plugins.'):
                return mod.split('.')[1]
            return 'Core'

        grouped = {}
        for mod_name, mod_cls in widget_modules:
            group = _get_group(mod_cls)
            grouped.setdefault(group, []).append(mod_name)

        combo_model = QStandardItemModel()
        for group in sorted(
            grouped.keys(), key=lambda g: (g != 'Core', g)
        ):
            header = QStandardItem(group)
            header.setData('header', Qt.UserRole)
            header.setEnabled(False)
            font = header.font()
            font.setBold(True)
            header.setFont(font)
            combo_model.appendRow(header)
            for mod_name in grouped[group]:
                combo_model.appendRow(QStandardItem(mod_name))
        self.type_combo.setModel(combo_model)

        if current_mod_name:
            self.type_combo.setCurrentText(current_mod_name)
        self.type_combo.currentIndexChanged.connect(self.on_type_combo_changed)

        # self.btn_add_widget_left = IconButton(
        #     parent=self,
        #     icon_path=':/resources/icon-new.png',
        #     tooltip='Add Widget Left',
        #     size=20,
        # )

        self.layout.addWidget(self.type_combo)

        self.options_btn = IconButton(
            parent=self,
            icon_path=':/resources/icon-settings-solid.png',
            tooltip='Options',
            size=20,
        )
        self.options_btn.setProperty('class', 'send')
        self.options_btn.clicked.connect(self.show_options)
        self.layout.addWidget(self.options_btn)
        from gui.popup import PopupFields
        self.config_widget = PopupFields(self)
        self.rebuild_config_widget()

    def show_options(self):
        if self.config_widget.isVisible():
            self.config_widget.hide()
        else:
            self.config_widget.show()

    def rebuild_config_widget(self):
        new_superclass = self.type_combo.currentText()

        widget_class = system.manager.modules.get_module_class(
            module_type='Widgets',
            module_name=new_superclass,
        )
        self.config_widget.schema = getattr(widget_class, 'param_schema', [])
        self.config_widget.build_schema()

    def on_type_combo_changed(self, index):
        # Skip header items
        model = self.type_combo.model()
        if model and model.item(index):
            if model.item(index).data(Qt.UserRole) == 'header':
                return
        if not self.page_editor:
            return
        if not hasattr(self.page_editor, 'module_id'):
            pass
        if self.editing_module_id != self.page_editor.module_id:
            return
        from gui.builder import modify_class_base
        new_superclass = self.type_combo.currentText()
        new_class = modify_class_base(self.editing_module_id, self.class_map, new_superclass)
        if new_class:
            # `config` is a table json column (a dict)
            # the code needs to go in the 'data' key
            sql.execute("""
                UPDATE modules
                SET config = json_set(config, '$.data', ?)
                WHERE id = ?
            """, (new_class, self.editing_module_id))

            system.manager.load()  # _manager('modules')
            self.page_editor.load()
            self.page_editor.config_widget.widgets[0].reimport()
            self.rebuild_config_widget()

    def leaveEvent(self, event):
        type_combo_is_expanded = self.type_combo.view().isVisible()
        config_widget_shown = self.config_widget.isVisible()
        if not (type_combo_is_expanded or config_widget_shown):
            self.hide()

    def sizeHint(self):
        # size of contents
        width = self.layout.sizeHint().width()
        return QSize(width, 25)

    def showEvent(self, event):
        # move to top left of editing widget
        try:
            if self.editing_widget and not self.editing_widget.isVisible():
                return
            self.move(self.editing_widget.mapToGlobal(
            QPoint(0, -self.sizeHint().height())))
        except RuntimeError:
            pass
