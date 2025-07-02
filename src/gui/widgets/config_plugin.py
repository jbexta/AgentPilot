
from PySide6.QtWidgets import *
from typing_extensions import override

from gui.util import CVBoxLayout, CHBoxLayout

from gui.widgets.config_widget import ConfigWidget


class ConfigPlugin(ConfigWidget):
    def __init__(self, parent, **kwargs):
        super().__init__(parent=parent)

        self.layout = CVBoxLayout(self)
        self.layout.setContentsMargins(0, 5, 0, 0)

        self.plugin_type = kwargs.get('plugin_type', 'AGENT')
        self.plugin_json_key = kwargs.get('plugin_json_key', 'use_plugin')
        none_text = kwargs.get('none_text', None)
        plugin_label_text = kwargs.get('plugin_label_text', None)
        plugin_label_width = kwargs.get('plugin_label_width', None)

        h_layout = CHBoxLayout()
        from gui.util import PluginComboBox
        self.plugin_combo = PluginComboBox(plugin_type=self.plugin_type, none_text=none_text)
        self.plugin_combo.setFixedWidth(90)
        self.plugin_combo.currentIndexChanged.connect(self.plugin_changed)
        self.default_class = kwargs.get('default_class', None)
        self.config_widget = None

        if plugin_label_text:
            label = QLabel(plugin_label_text)
            if plugin_label_width is not None:
                label.setFixedWidth(plugin_label_width)
            h_layout.addWidget(label)
        h_layout.addWidget(self.plugin_combo)
        h_layout.addStretch(1)
        self.layout.addLayout(h_layout)

    @override
    def get_config(self):
        config = self.config_widget.get_config()
        config[self.plugin_json_key] = self.plugin_combo.currentData()
        return config

    def plugin_changed(self):
        self.build_plugin_config()
        self.update_config()

    def build_plugin_config(self):
        # self.layout.takeAt(self.layout.count() - 1)  # remove last stretch
        if self.config_widget is not None:
            self.layout.takeAt(self.layout.count() - 1)  # remove config widget
            self.config_widget.deleteLater()
            self.config_widget = None

        from system import manager
        plugin = self.plugin_combo.currentData()
        plugin_class = manager.modules.get_module_class(
            module_type='Modules',
            module_name=plugin,
            # plugin_type=self.plugin_type,
            default=self.default_class
        )
        if not plugin_class:
            return

        #     self.plugin_type, plugin, default_class=self.default_class)
        # pass

        self.config_widget = plugin_class(parent=self)
        self.layout.addWidget(self.config_widget)
        # self.layout.addStretch(1)

        self.config_widget.build_schema()
        self.config_widget.load_config()

    @override
    def load(self):
        plugin_value = self.config.get(self.plugin_json_key, '')
        index = self.plugin_combo.findData(plugin_value)
        if index == -1:
            index = 0

        self.plugin_combo.setCurrentIndex(index)  # p

        self.build_plugin_config()

        if self.config_widget:
            self.config_widget.load()