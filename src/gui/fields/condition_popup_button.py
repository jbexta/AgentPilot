from gui.util import IconButton


class ConditionPopupButton(IconButton):
    def __init__(self, parent, **kwargs):
        super().__init__(
            parent=parent,
            icon_path=':/resources/icon-condition.png',
            size=24,
        )
        self.use_namespace = kwargs.get('use_namespace', 'condition')
        from gui.popup import PopupCondition
        self.config_widget = PopupCondition(
            self, use_namespace=self.use_namespace,
        )
        self.clicked.connect(self.show_popup)

    def get_value(self):
        """Get the value from the config widget."""
        return self.config_widget.get_config()

    def update_config(self):
        """Propagate config changes upward."""
        if hasattr(self.parent, 'update_config'):
            self.parent.update_config()
        if hasattr(self, 'save_config'):
            self.save_config()

    def show_popup(self):
        if self.config_widget.isVisible():
            self.config_widget.hide()
        else:
            self.config_widget.show()