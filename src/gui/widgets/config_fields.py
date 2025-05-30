import json
from functools import partial

from PySide6.QtWidgets import *
from PySide6.QtGui import Qt, QFontDatabase
from typing_extensions import override

from src.utils.helpers import block_signals, convert_to_safe_case, convert_model_json_to_obj, convert_json_to_obj, \
    display_message

from src.gui.util import find_attribute, clear_layout, XMLHighlighter, DockerfileHighlighter, PythonHighlighter, \
    CVBoxLayout, CHBoxLayout, get_widget_value, ModelComboBox, MemberPopupButton  # XML used dynamically todo
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

        for param_dict in schema:
            key = convert_to_safe_case(param_dict.get('key', param_dict['text']))
            row_key = param_dict.get('row_key', None)
            label_position = param_dict.get('label_position', 'left')
            label_width = param_dict.get('label_width', None) or self.label_width
            has_toggle = param_dict.get('has_toggle', False)
            tooltip = param_dict.get('tooltip', None)
            visible = param_dict.get('visible', True)
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

            widget = self.create_widget(**param_dict)
            setattr(self, key, widget)
            self.connect_signal(widget)

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
                    self.connect_signal(toggle)
                    toggle.stateChanged.connect(partial(self.toggle_widget, toggle, key))
                    self.toggle_widget(toggle, key, None)
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
        with block_signals(self):
            for param_dict in self.schema:
                # if self.__class__.__name__ == 'Module_Config_Fields':  # and key == 'load_on_startup':
                #     print('load prompt_model: ', config_value)
                key = convert_to_safe_case(param_dict.get('key', param_dict['text']))

                widget = getattr(self, key)
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
                    self.set_widget_value(widget, config_value)
                else:
                    self.set_widget_value(widget, param_dict.get('default', ''))

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

            widget = getattr(self, param_key)
            widget_value = get_widget_value(widget)
            if getattr(widget, 'use_namespace', None):
                config.update(widget_value)
            else:
                config[config_key] = widget_value

        self.config = config
        super().update_config()

    def create_widget(self, **kwargs):
        from src.gui.util import BaseComboBox, CircularImageLabel, ColorPickerWidget, RoleComboBox, \
            PluginComboBox, EnvironmentComboBox, FontComboBox, LanguageComboBox, APIComboBox, \
            CTextEdit, VenvComboBox, ModuleComboBox
        param_type = kwargs['type']
        default_value = kwargs.get('default', '')
        param_width = kwargs.get('width', None)
        num_lines = kwargs.get('num_lines', 1)
        text_size = kwargs.get('text_size', None)
        text_align = kwargs.get('text_alignment', Qt.AlignLeft)  # only works for single line
        highlighter = kwargs.get('highlighter', None)
        highlighter_field = kwargs.get('highlighter_field', None)
        monospaced = kwargs.get('monospaced', False)
        # expandable = kwargs.get('expandable', False)
        transparent = kwargs.get('transparent', False)
        minimum = kwargs.get('minimum', 0)
        maximum = kwargs.get('maximum', 1)
        step = kwargs.get('step', 1)
        stretch_x = kwargs.get('stretch_x', False)
        stretch_y = kwargs.get('stretch_y', False)
        placeholder_text = kwargs.get('placeholder_text', None)
        # wrap_text = kwargs.get('wrap_text', False)

        set_width = param_width or 50
        if param_type == bool:
            widget = QCheckBox()
        elif param_type == int:
            widget = QSpinBox()
            widget.setMinimum(minimum)
            widget.setMaximum(maximum)
            widget.setSingleStep(step)
        elif param_type == float:
            widget = QDoubleSpinBox()
            widget.setMinimum(minimum)
            widget.setMaximum(maximum)
            widget.setSingleStep(step)
        elif param_type == str:
            enhancement_key = kwargs.get('enhancement_key', None)
            fold_mode = kwargs.get('fold_mode', 'xml')
            widget = QLineEdit() if num_lines == 1 else CTextEdit(enhancement_key=enhancement_key, fold_mode=fold_mode)

            transparency = 'background-color: transparent;' if transparent else ''
            widget.setStyleSheet(f"border-radius: 6px;" + transparency)

            if isinstance(widget, CTextEdit):
                widget.setTabStopDistance(widget.fontMetrics().horizontalAdvance(' ') * 4)
            elif isinstance(widget, QLineEdit):
                widget.setAlignment(text_align)

            font = widget.font()
            if monospaced:
                font = QFontDatabase.systemFont(QFontDatabase.FixedFont)
            if text_size:
                font.setPointSize(text_size)
            widget.setFont(font)

            if highlighter:
                try:
                    # highlighter is a string name of the highlighter class, imported in this file
                    # reassign highlighter to the highlighter class
                    highlighter = globals()[highlighter]
                    widget.highlighter = highlighter(widget.document(), self.parent)
                    if isinstance(highlighter, PythonHighlighter) or isinstance(highlighter, DockerfileHighlighter):
                        widget.setLineWrapMode(QPlainTextEdit.NoWrap)
                except Exception as e:
                    pass
            elif highlighter_field:
                widget.highlighter_field = highlighter_field

            if placeholder_text:
                widget.setPlaceholderText(placeholder_text)

            if not stretch_y:
                font_metrics = widget.fontMetrics()
                height = (font_metrics.lineSpacing() + 2) * num_lines + widget.contentsMargins().top() + widget.contentsMargins().bottom()
                widget.setFixedHeight(height)

            set_width = param_width or 150
        elif isinstance(param_type, tuple):
            widget = BaseComboBox()
            widget.addItems(param_type)
            set_width = param_width or 150
        elif param_type == 'CircularImageLabel':
            diameter = kwargs.get('diameter', 50)
            widget = CircularImageLabel(diameter=diameter)
            set_width = widget.width()
        elif param_type == 'PluginComboBox':
            plugin_type = kwargs.get('plugin_type', 'AGENT')
            centered = kwargs.get('centered', False)
            allow_none = kwargs.get('allow_none', True)
            none_text = None if not allow_none else kwargs.get('none_text', 'Choose Plugin')
            widget = PluginComboBox(plugin_type=plugin_type, centered=centered, none_text=none_text)
            set_width = param_width or 150
        elif param_type == 'ModelComboBox':
            model_kind = kwargs.get('model_kind', 'ALL')
            widget = ModelComboBox(parent=self, model_kind=model_kind)
            set_width = param_width or 150
        elif param_type == 'MemberPopupButton':
            use_namespace = kwargs.get('use_namespace', None)
            member_type = kwargs.get('member_type', 'agent')
            widget = MemberPopupButton(parent=self, use_namespace=use_namespace, member_type=member_type)
            set_width = param_width or 24
        elif param_type == 'EnvironmentComboBox':
            widget = EnvironmentComboBox()
            set_width = param_width or 150
        elif param_type == 'VenvComboBox':
            widget = VenvComboBox(parent=self)
            set_width = param_width or 150
        elif param_type == 'FontComboBox':
            widget = FontComboBox()
            set_width = param_width or 150
        elif param_type == 'APIComboBox':
            with_model_kind = kwargs.get('with_model_kind', None)
            widget = APIComboBox(self, with_model_kind=with_model_kind)
            set_width = param_width or 150
        elif param_type == 'RoleComboBox':
            widget = RoleComboBox()
            set_width = param_width or 150
        elif param_type == 'ModuleComboBox':
            module_type = kwargs.get('module_type', None)
            widget = ModuleComboBox(module_type=module_type)
            set_width = param_width or 150
        elif param_type == 'LanguageComboBox':
            widget = LanguageComboBox()
            set_width = param_width or 150
        elif param_type == 'ColorPickerWidget':
            widget = ColorPickerWidget()
            set_width = param_width or 25
        else:
            raise ValueError(f'Unknown param type: {param_type}')

        self.set_widget_value(widget, default_value)

        if stretch_x or stretch_y:
            x_pol = QSizePolicy.Expanding if stretch_x else QSizePolicy.Fixed
            y_pol = QSizePolicy.Expanding if stretch_y else QSizePolicy.Fixed
            widget.setSizePolicy(x_pol, y_pol)

        elif set_width:
            widget.setFixedWidth(set_width)

        return widget

    def connect_signal(self, widget):
        from src.gui.util import CircularImageLabel, ColorPickerWidget, CTextEdit
        if isinstance(widget, CircularImageLabel):
            widget.avatarChanged.connect(self.update_config)
        elif isinstance(widget, ColorPickerWidget):
            widget.colorChanged.connect(self.update_config)
        elif isinstance(widget, ModelComboBox):
            widget.currentIndexChanged.connect(self.update_config)
        elif isinstance(widget, MemberPopupButton):
            pass  # do nothing
        elif isinstance(widget, QCheckBox):
            widget.stateChanged.connect(self.update_config)
        elif isinstance(widget, QLineEdit):
            widget.textChanged.connect(self.update_config)
        elif isinstance(widget, QComboBox):
            widget.currentIndexChanged.connect(self.update_config)
        elif isinstance(widget, QSpinBox):
            widget.valueChanged.connect(self.update_config)
        elif isinstance(widget, QDoubleSpinBox):
            widget.valueChanged.connect(self.update_config)
        elif isinstance(widget, CTextEdit):
            widget.textChanged.connect(self.update_config)
        else:
            raise Exception(f'Widget not implemented: {type(widget)}')

    def set_widget_value(self, widget, value):
        from src.gui.util import CircularImageLabel, ColorPickerWidget, RoleComboBox, \
            PluginComboBox, EnvironmentComboBox, CTextEdit, VenvComboBox, ModuleComboBox
        try:
            if isinstance(widget, CircularImageLabel):
                widget.setImagePath(value)
            elif isinstance(widget, ColorPickerWidget):
                widget.setColor(value)
            elif isinstance(widget, PluginComboBox):
                widget.set_key(value)
            elif isinstance(widget, ModelComboBox):
                from src.system import manager
                if value == '':
                    value = manager.config.get('system.default_chat_model', 'mistral/mistral-large-latest')
                value = convert_model_json_to_obj(value)

                value_copy = value.copy()
                model_params = value_copy.pop('model_params', {})

                widget.config_widget.load_config(model_params)
                widget.config_widget.load()

                value_copy = json.dumps(value_copy)
                widget.set_key(value_copy)
                widget.refresh_options_button_visibility()
            elif isinstance(widget, MemberPopupButton):
                value = convert_json_to_obj(value)
                use_namespace = getattr(widget, 'use_namespace', None)
                if use_namespace:
                    use_config = {k: v for k, v in self.config.items() if k.startswith(f'{widget.use_namespace}.')}
                    widget.config_widget.load_config(use_config)
                else:
                    widget.config_widget.load_config(value)
                widget.config_widget.load()
            elif isinstance(widget, EnvironmentComboBox):
                widget.set_key(value)
            elif isinstance(widget, VenvComboBox):
                widget.set_key(value)
            elif isinstance(widget, RoleComboBox):
                widget.set_key(value)
            elif isinstance(widget, ModuleComboBox):
                widget.set_key(value)
            elif isinstance(widget, QCheckBox):
                widget.setChecked(value)
            elif isinstance(widget, QLineEdit):
                widget.setText(value)
            elif isinstance(widget, QComboBox):
                widget.setCurrentText(str(value))
            elif isinstance(widget, QSpinBox):
                widget.setValue(int(value))
            elif isinstance(widget, QDoubleSpinBox):
                widget.setValue(float(value))
            elif isinstance(widget, CTextEdit):
                widget.setPlainText(value)
            else:
                raise Exception(f'Widget not implemented: {type(widget)}')
        except Exception as e:
            print('Error setting widget value: ', e)

    def toggle_widget(self, toggle, key, _):
        widget = getattr(self, key)
        widget.setVisible(toggle.isChecked())

    def clear_fields(self):
        from src.gui.util import CTextEdit
        for param_dict in self.schema:
            key = convert_to_safe_case(param_dict.get('key', param_dict['text']))
            widget = getattr(self, key)
            if isinstance(widget, QLineEdit):
                widget.clear()
            elif isinstance(widget, QCheckBox):
                widget.setChecked(False)
            elif isinstance(widget, QSpinBox):
                widget.setValue(0)
            elif isinstance(widget, QDoubleSpinBox):
                widget.setValue(0.0)
            elif isinstance(widget, QComboBox):
                widget.setCurrentIndex(0)
            elif isinstance(widget, CTextEdit):
                widget.clear()

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

            field_name = get_widget_value(self.tb_name).strip()
            field_type = get_widget_value(self.cb_type)

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