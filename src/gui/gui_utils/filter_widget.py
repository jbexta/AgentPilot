from PySide6.QtWidgets import QButtonGroup, QPushButton, QWidget

from gui.gui_utils.layouts import CHBoxLayout


class FilterWidget(QWidget):
    def __init__(self, parent, **kwargs):
        super().__init__(parent=parent)
        self.parent = parent
        self.layout = CHBoxLayout(self)

        self.button_group = QButtonGroup(self)
        self.button_group.buttonClicked.connect(self.on_button_clicked)

        self.kind_buttons = {kind: self.FilterButton(text=kind)
                             for kind in kwargs.get('kind_list', [])}

        for i, (key, btn) in enumerate(self.kind_buttons.items()):
            self.button_group.addButton(btn, i)
            self.layout.addWidget(btn)

        default_kind = kwargs.get('kind', None)
        if default_kind:
            default_btn = self.kind_buttons.get(default_kind)
            if default_btn:
                default_btn.setChecked(True)

        self.layout.addStretch(1)

    def on_button_clicked(self, button):
        self.parent.load()

    def get_kind(self):
        for kind, btn in self.kind_buttons.items():
            if btn.isChecked():
                return kind
        return self.parent.kind

    class FilterButton(QPushButton):
        def __init__(self, text):
            super().__init__()
            self.setCheckable(True)
            self.setText(text.title())
            self.setProperty('class', 'filter-button')
