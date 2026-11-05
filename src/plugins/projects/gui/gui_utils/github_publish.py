import aiohttp
import qasync
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QCheckBox, QDialog, QLabel, QLineEdit, QPushButton

from gui.gui_utils.layouts import CHBoxLayout, CVBoxLayout
from plugins.projects.utils import github, vcs
from utils.helpers import display_message


class GitHubPublishDialog(QDialog):
    """Creates a GitHub repo for `root`, adds it as origin and pushes."""

    def __init__(self, parent, root):
        super().__init__(parent)
        self.root = root
        self.setObjectName('githubPublishDialog')
        self.setWindowTitle('Publish to GitHub')
        self.setAttribute(Qt.WA_DeleteOnClose)
        self.setFixedWidth(440)
        self.busy = False

        title = QLabel('Publish to GitHub')
        title.setObjectName('dialogTitle')

        self.name_edit = QLineEdit(root.name)
        self.name_edit.textChanged.connect(
            lambda text: self.publish_btn.setEnabled(bool(text.strip())))
        self.description_edit = QLineEdit()
        self.description_edit.setPlaceholderText('Optional')
        self.private_check = QCheckBox('Private repository')
        self.private_check.setChecked(True)

        self.status_lbl = QLabel()
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
        self.publish_btn = QPushButton('Publish')
        self.publish_btn.setProperty('class', 'dialog-button')
        self.publish_btn.setProperty('primary', True)
        self.publish_btn.setDefault(True)
        self.publish_btn.clicked.connect(self.publish)
        button_row = CHBoxLayout()
        button_row.setSpacing(8)
        button_row.addStretch(1)
        button_row.addWidget(self.cancel_btn)
        button_row.addWidget(self.publish_btn)

        self.layout = CVBoxLayout(self)
        self.layout.setContentsMargins(24, 20, 24, 20)
        self.layout.addWidget(title)
        self.layout.addSpacing(16)
        for text, widget in (
            ('Repository name', self.name_edit),
            ('Description', self.description_edit),
        ):
            label = QLabel(text)
            label.setProperty('class', 'dialog-label')
            self.layout.addWidget(label)
            self.layout.addSpacing(4)
            self.layout.addWidget(widget)
            self.layout.addSpacing(12)
        self.layout.addWidget(self.private_check)
        self.layout.addSpacing(12)
        self.layout.addWidget(self.status_lbl)
        self.layout.addWidget(self.error_lbl)
        self.layout.addSpacing(18)
        self.layout.addLayout(button_row)

    def set_busy(self, status):
        self.busy = bool(status)
        for widget in (
            self.name_edit, self.description_edit, self.private_check,
            self.publish_btn, self.cancel_btn,
        ):
            widget.setEnabled(not self.busy)
        self.status_lbl.setText(status)
        self.status_lbl.setVisible(self.busy)

    def reject(self):
        if not self.busy:
            super().reject()

    def publish(self):
        self.error_lbl.hide()
        self.set_busy('Creating repository...')
        self.create_and_push(
            self.name_edit.text().strip(),
            self.description_edit.text().strip(),
            self.private_check.isChecked(),
        )

    @qasync.asyncSlot()
    async def create_and_push(self, name, description, private):
        try:
            url = await github.create_repo(
                await github.get_token(), name, description, private)
            self.set_busy('Adding remote...')
            await vcs.add_remote(self.root, url)
        except aiohttp.ClientError:
            self.show_error("Couldn't reach GitHub. Check your connection.")
            return
        except RuntimeError as e:
            self.show_error(str(e))
            return
        try:
            if await vcs.has_commits(self.root):
                self.set_busy('Pushing...')
                await vcs.push(self.root)
        except RuntimeError as e:
            display_message(f'Published to GitHub, but the push failed: {e}', 'GitHub')
        self.accept()

    def show_error(self, text):
        self.set_busy('')
        self.error_lbl.setText(text)
        self.error_lbl.show()
