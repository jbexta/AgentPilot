from src.gui.util import IconButton


class MemberPopupButton(IconButton):
    def __init__(self, parent, **kwargs):
        super().__init__(
            parent=parent,
            icon_path=':/resources/icon-agent-group.png',
            size=24,
        )
        self.member_type = kwargs.get('member_type', 'member')
        self.use_namespace = kwargs.get('use_namespace', None)
        from src.gui.popup import PopupMember
        self.config_widget = PopupMember(self, use_namespace=self.use_namespace, member_type=self.member_type)
        self.clicked.connect(self.show_popup)

    def update_config(self):
        """Implements same method as ConfigWidget, as a workaround to avoid inheriting from it"""
        if hasattr(self.parent, 'update_config'):
            self.parent.update_config()

        if hasattr(self, 'save_config'):
            self.save_config()

    def show_popup(self):
        if self.config_widget.isVisible():
            self.config_widget.hide()
        else:
            self.config_widget.show()