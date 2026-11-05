import aiohttp
import qasync
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QDialog, QLabel, QLineEdit, QPushButton

from gui.gui_utils.layouts import CHBoxLayout, CVBoxLayout
from plugins.projects.utils import github, vcs


class GitIdentityDialog(QDialog):
    """Asks for the name and email git labels commits with, and saves them
    to the global git config. Filled in from GitHub when signed in."""

    def __init__(self, parent):
        super().__init__(parent)
        self.setObjectName('gitIdentityDialog')
        self.setWindowTitle('Commit Identity')
        self.setAttribute(Qt.WA_DeleteOnClose)
        self.setFixedWidth(440)

        title = QLabel('Who is committing?')
        title.setObjectName('dialogTitle')
        message = QLabel(
            'Git labels each commit with a name and email. They are saved '
            'to your git config and used for all your repositories.')
        message.setWordWrap(True)

        self.name_edit = QLineEdit()
        self.email_edit = QLineEdit()
        for edit in (self.name_edit, self.email_edit):
            edit.textChanged.connect(self.refresh)

        self.hint_lbl = QLabel()
        self.hint_lbl.setObjectName('dialogDetail')
        self.hint_lbl.setWordWrap(True)
        self.hint_lbl.hide()
        self.error_lbl = QLabel()
        self.error_lbl.setObjectName('dialogError')
        self.error_lbl.setWordWrap(True)
        self.error_lbl.hide()

        cancel_btn = QPushButton('Cancel')
        cancel_btn.setProperty('class', 'dialog-button')
        cancel_btn.setAutoDefault(False)
        cancel_btn.clicked.connect(self.reject)
        self.save_btn = QPushButton('Save')
        self.save_btn.setProperty('class', 'dialog-button')
        self.save_btn.setProperty('primary', True)
        self.save_btn.setDefault(True)
        self.save_btn.clicked.connect(self.save)
        button_row = CHBoxLayout()
        button_row.setSpacing(8)
        button_row.addStretch(1)
        button_row.addWidget(cancel_btn)
        button_row.addWidget(self.save_btn)

        self.layout = CVBoxLayout(self)
        self.layout.setContentsMargins(24, 20, 24, 20)
        self.layout.addWidget(title)
        self.layout.addSpacing(12)
        self.layout.addWidget(message)
        self.layout.addSpacing(16)
        for text, widget in (('Name', self.name_edit), ('Email', self.email_edit)):
            label = QLabel(text)
            label.setProperty('class', 'dialog-label')
            self.layout.addWidget(label)
            self.layout.addSpacing(4)
            self.layout.addWidget(widget)
            self.layout.addSpacing(12)
        self.layout.addWidget(self.hint_lbl)
        self.layout.addWidget(self.error_lbl)
        self.layout.addSpacing(18)
        self.layout.addLayout(button_row)

        self.refresh()
        self.fill_from_github()

    def refresh(self):
        self.save_btn.setEnabled(bool(
            self.name_edit.text().strip() and self.email_edit.text().strip()))

    @qasync.asyncSlot()
    async def fill_from_github(self):
        token = await github.get_token()
        if not token:
            return
        try:
            name, email = await github.get_identity(token)
        except (RuntimeError, aiohttp.ClientError):
            return
        if not self.name_edit.text():
            self.name_edit.setText(name)
        if not self.email_edit.text():
            self.email_edit.setText(email)
        self.hint_lbl.setText(
            'Filled in from your GitHub account. The email is GitHub\'s '
            'private address, so your real email stays out of commits.')
        self.hint_lbl.show()

    @qasync.asyncSlot()
    async def save(self):
        try:
            await vcs.set_identity(
                self.name_edit.text().strip(), self.email_edit.text().strip())
        except RuntimeError as e:
            self.error_lbl.setText(str(e))
            self.error_lbl.show()
            return
        self.accept()
