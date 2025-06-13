
from functools import partial

from PySide6.QtWidgets import *
from PySide6.QtGui import Qt
from typing_extensions import override

from src.utils.helpers import block_signals, convert_to_safe_case, display_message

from src.gui.util import find_attribute, clear_layout, CVBoxLayout, CHBoxLayout
from src.utils import sql

from src.gui.widgets.config_widget import ConfigWidget


class ConfigFields(ConfigWidget):
    def __init__(self, parent, *args, **kwargs):
        super().__init__(parent=parent)

        self.conf_namespace = kwargs.get('conf_namespace', None)
        self.field_alignment = kwargs.get('field_alignment', Qt.AlignLeft)
        self.layout = CVBoxLayout(self)
        self.label_width = kwargs.get('label_width', None)
        self.label_text_alignment = kwargs.get('label_text_alignment', Qt.AlignLeft)
        self.margin_left = kwargs.get('margin_left', 0)
        self.add_stretch_to_end = kwargs.get('add_stretch_to_end', True)
        self.schema = kwargs.get('schema', [])
        self.adding_field = None

    @override
    def build_schema(self):
        """Build the widgets from the schema list"""
        clear_layout(self.layout)
        schema = self.schema
        if not schema:
            self.adding_field = self.AddingField(self)
            if not find_attribute(self, 'user_editing'):
                self.adding_field.hide()
            self.layout.addWidget(self.adding_field)
            self.layout.addStretch(1)

            if hasattr(self, 'after_init'):  # todo clean
                self.after_init()
            return

        self.layout.setContentsMargins(self.margin_left, 0, 0, 5)
        row_layout = None
        last_row_key = None
        has_stretch_y = False

        from src.system import manager

        for param_dict in schema:
            key = convert_to_safe_case(param_dict.get('key', param_dict['text']))
            row_key = param_dict.get('row_key', None)
            label_position = param_dict.get('label_position', 'left')
            label_width = param_dict.get('label_width', None) or self.label_width
            has_toggle = param_dict.get('has_toggle', False)
            tooltip = param_dict.get('tooltip', None)
            visible = param_dict.get('visible', True)
            stretch_x = param_dict.get('stretch_x', False)
            stretch_y = param_dict.get('stretch_y', False)

            if row_key is not None and row_layout is None:
                row_layout = CHBoxLayout()
            elif row_key is not None and row_layout is not None and row_key != last_row_key:
                self.layout.addLayout(row_layout)
                row_layout = CHBoxLayout()
            elif row_key is None and row_layout is not None:
                self.layout.addLayout(row_layout)
                row_layout = None

            last_row_key = row_key

            current_value = self.config.get(f'{key}', None)
            if current_value is not None:
                param_dict['default'] = current_value

            param_type = param_dict['type']
            type_map = {  # todo temp map
                str: 'text',
                int: 'integer',
                float: 'float',
                bool: 'boolean',
                'CircularImageLabel': 'avatar',
                'ColorPickerWidget': 'color_picker',
                'ModelComboBox': 'model',
            }
            if param_type in type_map:
                param_type = type_map[param_type]
            elif isinstance(param_type, tuple):
                param_dict['items'] = param_type
                param_type = 'combo'

            widget_class = manager.modules.get_module_class(
                module_type='Fields',
                module_name=param_type,
            )
            widget = widget_class(parent=self, **param_dict) if widget_class else None
            if not widget:
                print(f'Widget type {param_type} not found in modules. Skipping field: {key}')
                continue

            setattr(self, key, widget)

            if stretch_x or stretch_y:
                x_pol = QSizePolicy.Expanding if stretch_x else QSizePolicy.Fixed
                y_pol = QSizePolicy.Expanding if stretch_y else QSizePolicy.Fixed
                widget.setSizePolicy(x_pol, y_pol)

            if hasattr(widget, 'build_schema'):
                widget.build_schema()

            param_layout = CHBoxLayout() if label_position == 'left' else CVBoxLayout()
            param_layout.setContentsMargins(2, 8, 2, 0)
            param_layout.setAlignment(self.field_alignment)
            if label_position is not None:
                label_layout = CHBoxLayout()
                label_layout.setAlignment(self.label_text_alignment)
                param_label = QLabel(param_dict['text'])
                param_label.setAlignment(self.label_text_alignment)
                if not visible:
                    param_label.setVisible(False)
                if label_width:
                    param_label.setFixedWidth(label_width)

                label_layout.addWidget(param_label)

                label_minus_width = 0
                if tooltip:
                    from src.gui.util import HelpIcon
                    info_label = HelpIcon(parent=self, tooltip=tooltip)
                    info_label.setAlignment(self.label_text_alignment)
                    label_minus_width += 22
                    label_layout.addWidget(info_label)

                if has_toggle:
                    toggle = QCheckBox()
                    toggle.setFixedWidth(20)
                    setattr(self, f'{key}_tgl', toggle)
                    # self.connect_signal(toggle)
                    toggle.stateChanged.connect(partial(self.toggle_widget, toggle, key))
                    # self.toggle_widget(toggle, key, None)
                    label_minus_width += 20
                    label_layout.addWidget(toggle)

                if has_toggle or tooltip:
                    label_layout.addStretch(1)

                if label_width:
                    param_label.setFixedWidth(label_width - label_minus_width)

                param_layout.addLayout(label_layout)

            param_layout.addWidget(widget)

            if getattr(self, 'user_editable', True):
                from src.gui.temp import OptionsButton
                param_layout.addSpacing(4)
                options_btn = OptionsButton(
                    self,
                    param_dict['type'],
                    icon_path=':/resources/icon-settings-solid.png',
                    tooltip='Options',
                    size=20,
                )
                # options_btn.setProperty('class', 'send')
                # options_btn.move(widget.x() + widget.width() - 20, widget.y())
                if not find_attribute(self, 'user_editing'):
                    options_btn.hide()
                param_layout.addWidget(options_btn)

            if isinstance(param_layout, CHBoxLayout):
                param_layout.addStretch(1)

            if stretch_y:
                has_stretch_y = True

            if row_layout:
                row_layout.addLayout(param_layout)
            else:
                self.layout.addLayout(param_layout)

            if not visible:
                widget.setVisible(False)

        if row_layout:
            self.layout.addLayout(row_layout)

        if getattr(self, 'user_editable', True):
            self.layout.addSpacing(7)
            self.adding_field = self.AddingField(self)
            if not find_attribute(self, 'user_editing'):
                self.adding_field.hide()
            self.layout.addWidget(self.adding_field)

        if self.add_stretch_to_end and not has_stretch_y:
            self.layout.addStretch(1)

        if hasattr(self, 'after_init'):
            self.after_init()

    @override
    def load(self):
        """Loads the widget values from the config dict"""
        # return
        with block_signals(self):
            for param_dict in self.schema:
                # if self.__class__.__name__ == 'Module_Config_Fields':  # and key == 'load_on_startup':
                #     print('load prompt_model: ', config_value)
                key = convert_to_safe_case(param_dict.get('key', param_dict['text']))

                widget = getattr(self, key, None)
                if not widget:
                    print(f'Widget `{key}` not found in config fields. Skipping.')
                    continue
                config_key = f"{self.conf_namespace}.{key}" if self.conf_namespace else key

                config_value = self.config.get(config_key, None)
                has_config_value = config_value is not None


                toggle = getattr(self, f'{key}_tgl', None)
                if toggle:
                    toggle.setChecked(has_config_value)
                    widget.setVisible(has_config_value)

                if has_config_value:
                    is_encrypted = param_dict.get('encrypt', False)
                    if is_encrypted:
                        # todo decrypt
                        pass
                    widget.set_value(config_value)
                else:
                    widget.set_value(param_dict.get('default', ''))

    def load_config(self, config=None):
        """Only accepts keys that are in the schema"""
        super().load_config(config)

        schema_keys = [convert_to_safe_case(param_dict.get('key', param_dict['text']))
                       for param_dict in self.schema]

        filtered_config = {}
        for key, value in self.config.items():
            if self.conf_namespace and key.startswith(f"{self.conf_namespace}."):
                schema_key = key[len(f"{self.conf_namespace}."): ]
            else:
                schema_key = key

            if schema_key in schema_keys:
                filtered_config[key] = value

        self.config = filtered_config

    @override
    def update_config(self):
        config = {}
        for param_dict in self.schema:
            param_key = convert_to_safe_case(param_dict.get('key', param_dict['text']))
            config_key = f"{self.conf_namespace}.{param_key}" if self.conf_namespace else param_key

            widget_toggle = getattr(self, f'{param_key}_tgl', None)
            if widget_toggle:
                if not widget_toggle.isChecked():
                    config.pop(config_key, None)
                    continue

            widget = getattr(self, param_key, None)
            if not widget:
                print(f'Widget `{param_key}` not found in config fields. Skipping.')
                continue

            widget_value = widget.get_value()
            if getattr(widget, 'use_namespace', None):
                config.update(widget_value)
            else:
                config[config_key] = widget_value

        self.config = config
        super().update_config()

    def toggle_widget(self, toggle, key, _):
        widget = getattr(self, key)
        widget.setVisible(toggle.isChecked())
        self.update_config()

    def clear_fields(self):
        """Clears all fields in the config widget"""
        for param_dict in self.schema:
            key = convert_to_safe_case(param_dict.get('key', param_dict['text']))
            widget = getattr(self, key, None)
            if widget and hasattr(widget, 'clear_value'):
                widget.clear_value()

    class AddingField(QWidget):
        def __init__(self, parent):
            super().__init__(parent)
            from src.gui.util import BaseComboBox
            self.parent = parent
            self.layout = CHBoxLayout(self)
            self.tb_name = QLineEdit()
            self.tb_name.setMaximumWidth(175)
            self.tb_name.setPlaceholderText('Field name')
            self.cb_type = BaseComboBox()
            self.cb_type.setMaximumWidth(125)
            from src.gui.builder import field_type_alias_map
            self.cb_type.addItems(list(field_type_alias_map.keys()))

            self.btn_add = QPushButton('Add')
            self.layout.addWidget(self.tb_name)
            self.layout.addWidget(self.cb_type)
            self.layout.addWidget(self.btn_add)
            self.layout.addStretch(1)
            self.btn_add.clicked.connect(self.add_field)

        def add_field(self):
            edit_bar = getattr(self.parent, 'edit_bar', None)
            if not edit_bar:
                return
            page_editor = edit_bar.page_editor
            if not page_editor:
                return
            if edit_bar.editing_module_id != page_editor.module_id:
                return

            field_name = self.tb_name.text().strip()
            field_type = self.cb_type.currentText().strip()

            if field_name == '':
                display_message(self,
                    message='Field name is required',
                    icon=QMessageBox.Warning,
                )
                return

            from src.gui.builder import modify_class_add_field
            new_class = modify_class_add_field(edit_bar.editing_module_id, edit_bar.class_map, field_name, field_type)
            if new_class:
                sql.execute("""
                    UPDATE modules
                    SET config = json_set(config, '$.data', ?)
                    WHERE id = ?
                """, (new_class, edit_bar.editing_module_id))

                from src.system import manager
                manager.load()  # _manager('modules')
                page_editor.load()
                page_editor.config_widget.widgets[0].reimport()