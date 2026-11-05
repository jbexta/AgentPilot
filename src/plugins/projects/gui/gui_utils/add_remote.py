import qasync
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QDialog, QLabel, QLineEdit, QPushButton

from gui.gui_utils.layouts import CHBoxLayout, CVBoxLayout
from plugins.projects.utils import github, vcs


class AddRemoteDialog(QDialog):
    """Adds a remote to the repo at `root`, once git can reach it."""

    def __init__(self, parent, root):
        super().__init__(parent)
        self.root = root
        self.setObjectName('addRemoteDialog')
        self.setWindowTitle('Add Remote')
        self.setAttribute(Qt.WA_DeleteOnClose)
        self.setFixedWidth(440)
        self.busy = False

        title = QLabel('Add a remote')
        title.setObjectName('dialogTitle')

        self.name_edit = QLineEdit('origin')
        self.url_edit = QLineEdit()
        self.url_edit.setPlaceholderText('https://github.com/owner/repo.git')
        for edit in (self.name_edit, self.url_edit):
            edit.textChanged.connect(self.refresh)

        self.status_lbl = QLabel('Checking repository...')
        self.status_lbl.setObjectName('dialogDetail')
        self.status_lbl.hide()
        self.error_lbl = QLabel()
        self.error_lbl.setObjectName('dialogError')
        self.error_lbl.setWordWrap(True)
        self.error_lbl.hide()

        self.cancel_btn = QPushButton('Cancel')
        self.cancel_btn.setProperty('class', 'dialog-button')
        self.cancel_btn.setAutoDefault(False)
        self.cancel_btn.clicked.connect(self.reject)
        self.add_btn = QPushButton('Add')
        self.add_btn.setProperty('class', 'dialog-button')
        self.add_btn.setProperty('primary', True)
        self.add_btn.setDefault(True)
        self.add_btn.clicked.connect(self.add)
        button_row = CHBoxLayout()
        button_row.setSpacing(8)
        button_row.addStretch(1)
        button_row.addWidget(self.cancel_btn)
        button_row.addWidget(self.add_btn)

        self.layout = CVBoxLayout(self)
        self.layout.setContentsMargins(24, 20, 24, 20)
        self.layout.addWidget(title)
        self.layout.addSpacing(16)
        for text, widget in (('Name', self.name_edit), ('URL', self.url_edit)):
            label = QLabel(text)
            label.setProperty('class', 'dialog-label')
            self.layout.addWidget(label)
            self.layout.addSpacing(4)
            self.layout.addWidget(widget)
            self.layout.addSpacing(12)
        self.layout.addWidget(self.status_lbl)
        self.layout.addWidget(self.error_lbl)
        self.layout.addSpacing(18)
        self.layout.addLayout(button_row)

        self.refresh()
        self.url_edit.setFocus()

    def refresh(self):
        ready = bool(self.name_edit.text().strip() and self.url_edit.text().strip())
        self.add_btn.setEnabled(ready and not self.busy)

    def set_busy(self, busy):
        self.busy = busy
        for widget in (self.name_edit, self.url_edit, self.cancel_btn):
            widget.setEnabled(not busy)
        self.status_lbl.setVisible(busy)
        self.refresh()

    def reject(self):
        if not self.busy:
            super().reject()

    def add(self):
        self.error_lbl.hide()
        self.set_busy(True)
        self.check_and_add(
            self.url_edit.text().strip(), self.name_edit.text().strip())

    @qasync.asyncSlot()
    async def check_and_add(self, url, name):
        try:
            await vcs.check_remote(self.root, url)
            await vcs.add_remote(self.root, url, name)
        except RuntimeError as e:
            if url.startswith('https://github.com/') and not await github.get_token():
                message = ('Repository not found, or it is private. Sign in '
                           'to GitHub in Settings to use private repositories.')
            else:
                message = str(e).splitlines()[0].removeprefix('fatal: ')
            self.set_busy(False)
            self.error_lbl.setText(message)
            self.error_lbl.show()
            return
        self.accept()
