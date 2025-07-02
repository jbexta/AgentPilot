from PySide6.QtWidgets import QMessageBox, QInputDialog

from gui.fields.combo import BaseCombo
from gui.util import CHBoxLayout, IconButton
from utils.helpers import display_message_box, block_signals, display_message


class VenvComboBox(BaseCombo):
    def __init__(self, parent, **kwargs):
        self.parent = parent
        self.first_item = kwargs.pop('first_item', None)
        super().__init__(parent, **kwargs)
        self.current_key = None
        self.currentIndexChanged.connect(self.on_current_index_changed)

        self.btn_delete = self.DeleteButton(
            parent=self,
            icon_path=':/resources/icon-minus.png',
            tooltip='Delete Venv',
            size=20,
        )
        self.layout = CHBoxLayout(self)
        self.layout.addWidget(self.btn_delete)
        self.btn_delete.move(-20, 0)

        self.load()

    class DeleteButton(IconButton):
        def __init__(self, parent, *args, **kwargs):
            super().__init__(parent=parent, *args, **kwargs)
            self.clicked.connect(self.delete_venv)
            self.hide()

        def showEvent(self, event):
            super().showEvent(event)
            self.parent.btn_delete.move(self.parent.width() - 40, 0)

        def delete_venv(self):
            ok = display_message_box(
                icon=QMessageBox.Warning,
                title='Delete Virtual Environment',
                text=f'Are you sure you want to delete the venv `{self.parent.current_key}`?',
                buttons=QMessageBox.Yes | QMessageBox.No
            )
            if ok != QMessageBox.Yes:
                return

            from system import manager
            manager.venvs.delete(self.parent.current_key)
            self.parent.load()
            self.parent.reset_index()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self.btn_delete.move(self.width() - 40, 0)

    # only show options button when the mouse is over the combobox
    def enterEvent(self, event):
        self.btn_delete.show()
        super().enterEvent(event)

    def leaveEvent(self, event):
        self.btn_delete.hide()
        super().leaveEvent(event)

    def mouseMoveEvent(self, event):
        self.btn_delete.show()
        super().mouseMoveEvent(event)

    def load(self):
        from system import manager
        with block_signals(self):
            self.clear()
            for venv_name, venv in manager.venvs:
                item_user_data = f"{venv_name} ({venv.path})"
                self.addItem(item_user_data, venv_name)
            # add create new venv option
            self.addItem('< Create New Venv >', '<NEW>')

    def set_value(self, key):
        super().set_value(key)
        self.current_key = key

    def on_current_index_changed(self):
        from system import manager
        key = self.itemData(self.currentIndex())
        if key == '<NEW>':
            dlg_title, dlg_prompt = ('Enter Name', 'Enter a name for the new virtual environment')
            text, ok = QInputDialog.getText(self, dlg_title, dlg_prompt)
            if not ok or not text:
                self.reset_index()
                return
            if text == 'default':
                display_message(
                    self,
                    message='The name `default` is reserved and cannot be used.',
                    icon=QMessageBox.Warning,
                )
                self.reset_index()
                return
            manager.venvs.add(text)
            self.load()
            self.set_key(text)
        else:
            self.current_key = key

    def reset_index(self):
        current_key_index = self.findData(self.current_key)
        has_items = self.count() - 1 > 0  # -1 for <new> item
        if current_key_index >= 0 and has_items:
            self.setCurrentIndex(current_key_index)
        else:
            self.set_value(self.current_key)
