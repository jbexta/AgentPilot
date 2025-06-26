from PySide6.QtWidgets import QHBoxLayout, QLabel
from typing_extensions import override

from src.gui.util import IconButton  # , BaseComboBox
from src.gui.fields.combo import BaseCombo


class OptionsButton(IconButton):  # todo unify option popups to fix circular imports
    from src.gui.popup import PopupFields
    def __init__(self, parent, param_type, **kwargs):
        super().__init__(parent, **kwargs)
        from src.gui.builder import field_options_common_schema  # , field_option_schemas
        self.clicked.connect(self.show_options)
        self.config_widget = None
        self.config_widget_schema = field_options_common_schema #+ field_option_schemas.get(param_type, [])

    def show_options(self):
        if not self.config_widget:
            self.config_widget = self.PopupParams(self, schema=self.config_widget_schema)
            setattr(self.config_widget, 'user_editable', False)
            self.config_widget.build_schema()

        if self.config_widget.isVisible():
            self.config_widget.hide()
        else:
            self.config_widget.show()

    class PopupParams(PopupFields):
        def __init__(self, parent, schema=None):
            super().__init__(parent=parent, schema=schema)

        def after_init(self):
            super().after_init()

            from src.gui.builder import field_type_alias_map
            # from src.gui.util import BaseComboBox
            self.type_combo = BaseCombo(items=list(field_type_alias_map.keys()))
            self.type_combo.setMaximumWidth(160)
            h_layout = QHBoxLayout()
            h_layout.addWidget(QLabel('Type'))
            h_layout.addWidget(self.type_combo)
            self.layout.insertLayout(0, h_layout)