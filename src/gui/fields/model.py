"""
Model selection field widget for configurable AI model choices.

This module provides a ModelComboBox field widget that extends BaseCombo to create
a sophisticated dropdown for selecting AI models from various providers. It includes
an integrated options button for model parameter configuration, supports model
filtering by kind (chat, completion, etc.), and provides a popup interface for
advanced model settings. The widget automatically organizes models by provider
and handles model configuration persistence.
"""  # unchecked

import json

from PySide6.QtCore import QPoint, QTimer
from PySide6.QtGui import QPainter, QStandardItemModel, QStandardItem, Qt, QColor
from PySide6.QtWidgets import (
    QLabel, QScrollArea, QSizePolicy, QStyleOptionComboBox, QStylePainter, QStyle, QWidget,
)

from gui import system
from gui.fields.combo import BaseCombo
from gui.util import CVBoxLayout, IconButton, CHBoxLayout, clear_layout
from gui.popup import PopupModel
from gui.widgets.config_fields import ConfigFields
from utils import sql
from utils.helpers import convert_model_json_to_obj, block_signals


class ModelComboBox(QWidget):
    """
    BE CAREFUL SETTING BREAKPOINTS DUE TO PYSIDE COMBOBOX BUG
    """
    def __init__(self, parent, **kwargs):
        super().__init__(parent=parent)
        self.parent = parent
        self.first_item = kwargs.pop('first_item', None)
        self.model_kind = kwargs.pop('model_kind', 'ALL')

        popup_params = kwargs.pop('popup_params', False)
        self.popup_params = popup_params

        self.combo_box = self.ModelCombo(parent=self, **kwargs)
        self.combo_box.currentIndexChanged.connect(self.on_index_changed_lag)

        self.layout = CVBoxLayout(self)
        h_layout = CHBoxLayout()
        h_layout.addWidget(self.combo_box)
        h_layout.addStretch(1)
        self.layout.addLayout(h_layout)

        if self.model_kind == 'CHAT':
            self.config_widget = PopupModel(self, is_popup=popup_params)
        else:
            self.config_widget = ConfigFields(parent=self)
            self.config_widget.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        if popup_params:
            self.options_btn = self.OptionsButton(
                parent=self,
                icon_path=':/resources/icon-settings-solid.png',
                tooltip='Options',
                size=18,
            )
            self.options_btn.setFixedSize(18, 18)
            if self.model_kind != 'CHAT':  # PopupModel handles its own flags
                self.config_widget.setWindowFlags(
                    Qt.Popup | Qt.FramelessWindowHint
                )
                self.config_widget.setFixedWidth(350)

        else:
            self.DISABLE_DEFAULT_LABEL = True
            self.combo_label = QLabel('Model')
            h_layout.insertWidget(0, self.combo_label)

            self.scroll_area = QScrollArea(self)
            self.scroll_area.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
            self.scroll_area.setWidgetResizable(True)
            # self.scroll_area.setMaximumHeight(400)
            self.scroll_area.setWidget(self.config_widget)
            self.scroll_area.setFrameShape(QScrollArea.NoFrame)
            
            self.layout.addWidget(self.scroll_area, 1)

        self.load()
    
    def on_index_changed_lag(self):  # todo temp clean
        QTimer.singleShot(100, self.refresh_and_update_config)

    def refresh_and_update_config(self):
        self.refresh_fields()
        self.parent.update_config()
        
    def refresh_scroll_height(self):
        """Show or hide the scroll area based on whether there are fields."""
        if not hasattr(self, 'scroll_area'):
            return
        has_content = self.config_widget.sizeHint().height() > 0
        self.scroll_area.setVisible(has_content)

    def refresh_fields(self):
        model_opts = convert_model_json_to_obj(self.combo_box.get_value())
        model_id = sql.get_scalar("""
            SELECT id
            FROM models
            WHERE COALESCE(json_extract(config, '$._model_name'), json_extract(config, '$.model_name')) = ?
                AND kind = ?
                AND provider_plugin = ?
        """, (model_opts['_model_name'], model_opts['kind'], model_opts['provider']))  # todo temp clean

        if not model_id:
            if self.model_kind == 'CHAT':
                self.config_widget.hide()
            else:
                clear_layout(self.config_widget.layout)
            self.refresh_scroll_height()
            return

        if self.model_kind == 'CHAT':
            if not self.popup_params:
                self.config_widget.show()
            model_config = sql.get_scalar("""
                SELECT config FROM models WHERE id = ?
            """, (model_id,), load_json=True)
            if model_config:
                self.config_widget.load_config(model_config)
                self.config_widget.load()
        else:
            # Dynamic schema from DB metadata
            # todo clean & dedupe
            model_metadata = sql.get_scalar("""
                SELECT metadata
                FROM models
                WHERE id = ?
            """, (model_id,), load_json=True)

            model_input_schema = model_metadata.get('input_schema', [])

            self.config_widget.schema = model_input_schema
            self.config_widget.build_schema()

            model_config = sql.get_scalar("""
                SELECT config FROM models WHERE id = ?
            """, (model_id,), load_json=True)
            if model_config:
                self.config_widget.load_config(model_config)
                self.config_widget.load()

        self.refresh_scroll_height()
        # self.parent.update_config()
        # # # super().on_item_selected()

    def load(self):
        #
        # matched_provider_ids = sql.get_results(f"""
        #     SELECT DISTINCT a.id
        #     FROM apis a
        #     JOIN models m
        #         ON a.id = m.api_id
        #     WHERE m.kind = ? OR ? = 'ALL'
        #     ORDER BY a.pinned DESC, a.name
        # """, (self.model_kind, self.model_kind), return_type='list')  # todo clean
        with block_signals(self), block_signals(self.combo_box):
            self.combo_box.clear()

            model = QStandardItemModel()
            self.combo_box.setModel(model)

            # api_models = {}

            models = sql.get_results("""
                SELECT
                    m.name,
                    m.kind,
                    a.name AS api_name,
                    m.provider_plugin,
                    m.config,
                    a.api_key
                FROM models m
                LEFT JOIN apis a
                    ON m.api_id = a.id
                ORDER BY m.api_id, m.name""")
            
            last_api_name = None
            for display_name, model_kind, api_name, provider_plugin, model_config, api_key in models:
                if self.model_kind not in ('ALL', model_kind):
                    continue

                if self.model_kind == 'CHAT' and api_key == '':
                    continue

                if api_name != last_api_name:
                    header_item = QStandardItem(api_name)
                    header_item.setData('header', Qt.UserRole)
                    header_item.setEnabled(False)
                    font = header_item.font()
                    font.setBold(True)
                    header_item.setFont(font)
                    model.appendRow(header_item)
                    last_api_name = api_name

                data = convert_model_json_to_obj(model_config)
                data.update({
                    'kind': model_kind,
                    'provider': provider_plugin,
                })
                    # 'model_name': model_name,  #  or '',  # todo
                    # 'model_params': model_config,  purposefully exclude params
                item = QStandardItem(display_name)
                item.setData(json.dumps(data), Qt.UserRole)
                model.appendRow(item)

    def update_config(self):
        """Implements same method as ConfigWidget, as a workaround to avoid inheriting from it"""
        if hasattr(self.parent, 'update_config'):
            self.parent.update_config()

        if hasattr(self, 'save_config'):
            self.save_config()

        if self.popup_params:
            self.refresh_options_button_visibility()

    def refresh_options_button_visibility(self):
        if not self.popup_params:
            return
        has_config = len(self.config_widget.get_config()) > 0
        has_items = self.combo_box.model().rowCount() > 0
        self.options_btn.setVisible(has_config and has_items)

    def get_value(self):
        """
        DO NOT PUT A BREAKPOINT IN HERE BECAUSE IT WILL FREEZE YOUR PC (LINUX, PYCHARM & VSCODE) ISSUE WITH PYSIDE COMBOBOX
        """
        # from utils.helpers import convert_model_json_to_obj
        model_json = self.combo_box.currentData()
        model_obj = convert_model_json_to_obj(model_json)
        # cnf = self.config_widget.get_config()
        # pretty_printed_cnf = json.dumps(cnf, indent=4, ensure_ascii=False)
        # print(f'Config for model {model_obj["model_name"]}:\n{pretty_printed_cnf}')
        model_obj['model_params'] = self.config_widget.get_config()  #!88!#
        return model_obj

    def set_value(self, value):
        if value is None or value == '':
            default_key = f'system.default_{self.model_kind.lower()}_model'
            value = system.manager.config.get(default_key, '')
        if not value:
            return
        value = convert_model_json_to_obj(value)

        value_copy = value.copy()
        model_params = value_copy.pop('model_params', {})

        value_copy = json.dumps(value_copy)
        # widget.set_key(value_copy)
        with block_signals(self.combo_box):
            self.combo_box.set_value(value_copy)

        if self.model_kind == 'CHAT':
            if not self.popup_params:
                self.config_widget.show()
            self.config_widget.load_config(model_params)
            self.config_widget.load()
        else:
            self.refresh_fields()
            self.config_widget.load_config(model_params)
            self.config_widget.load()

        if self.popup_params:
            self.refresh_options_button_visibility()
        # model_obj = convert_model_json_to_obj(key)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if self.popup_params:
            self.options_btn.move(
                self.combo_box.x() + self.combo_box.width() - 40, 0
            )

    # only show options button when the mouse is over the combobox
    def enterEvent(self, event):
        if self.popup_params:
            has_schema = bool(
                self.config_widget.schema
                or getattr(self.config_widget, 'widgets', None)
            )
            has_items = self.combo_box.model().rowCount() > 0
            if has_schema and has_items:
                self.options_btn.show()
        super().enterEvent(event)

    def leaveEvent(self, event):
        if self.popup_params:
            self.refresh_options_button_visibility()
        super().leaveEvent(event)

    # def mousePressEvent(self, event):
    #     if self.options_btn.geometry().contains(event.pos()):
    #         self.options_btn.show_options()
    #     else:
    #         super().mousePressEvent(event)

    class ModelCombo(BaseCombo):
        def __init__(self, parent, **kwargs):
            super().__init__(parent=parent, **kwargs)
            self.parent = parent
            # self.setMaximumHeight(30)

        def paintEvent(self, event):
            current_item = self.model().item(self.currentIndex())
            if current_item:
                # Check if the selected item's text color is red
                if current_item.foreground().color() == QColor('red'):
                    # Set the text color to red when
                    # painter = QPainter(self)
                    option = QStyleOptionComboBox()
                    self.initStyleOption(option)

                    painter = QStylePainter(self)
                    try:
                        painter.setPen(QColor('red'))
                        painter.drawComplexControl(QStyle.CC_ComboBox, option)

                        # Get the text rectangle
                        text_rect = self.style().subControlRect(QStyle.CC_ComboBox, option, QStyle.SC_ComboBoxEditField)
                        text_rect.adjust(2, 0, -2, 0)  # Adjust the rectangle to provide some padding

                        # Draw the text with red color
                        current_text = self.currentText()
                        painter.drawText(text_rect, Qt.AlignLeft, current_text)
                    finally:
                        painter.end()
                    return

            if self.model().rowCount() == 0:
                painter = QPainter()
                if not painter.begin(self):
                    super().paintEvent(event)
                    return
                try:
                    # painter.setPen(QColor('red'))
                    painter.drawText(self.rect(), Qt.AlignLeft, 'No models found')
                finally:
                    painter.end()
                return

            super().paintEvent(event)

    class OptionsButton(IconButton):
        def __init__(self, parent, *args, **kwargs):
            super().__init__(parent=parent, *args, **kwargs)
            self.clicked.connect(self.show_options)
            self.hide()
            # self.config_widget = CustomDropdown(self)

        def showEvent(self, event):
            super().showEvent(event)
            combo = self.parent.combo_box
            self.move(combo.x() + combo.width() - 40, 0)

        def show_options(self):
            model_combo_box = self.parent
            config_widget = model_combo_box.config_widget
            if config_widget.isVisible():
                config_widget.hide()
            else:
                config_widget.adjustSize()
                btm_right = model_combo_box.rect().bottomRight()
                global_pos = model_combo_box.mapToGlobal(btm_right)
                config_widget.move(
                    global_pos - QPoint(config_widget.width(), 0)
                )
                config_widget.show()
