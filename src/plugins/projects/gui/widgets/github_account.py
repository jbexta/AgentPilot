import qasync
import shiboken6
from PySide6.QtWidgets import QLabel, QPushButton

from gui.gui_utils.layouts import CHBoxLayout
from gui.widgets.config_widget import ConfigWidget
from plugins.projects.gui.gui_utils.github_sign_in import GitHubSignInDialog
from plugins.projects.utils import github
from utils.helpers import set_module_type


@set_module_type('Widgets')
class GitHubAccount(ConfigWidget):
    def __init__(self, parent):
        super().__init__(parent=parent)
        self.propagate_config = False
        self.login = None

        self.status_lbl = QLabel()
        self.status_lbl.setObjectName('dialogDetail')
        self.button = QPushButton()
        self.button.setProperty('class', 'dialog-button')
        self.button.clicked.connect(self.on_button_clicked)

        self.layout = CHBoxLayout(self)
        self.layout.setContentsMargins(20, 10, 20, 10)
        self.layout.setSpacing(12)
        self.layout.addWidget(QLabel('GitHub'))
        self.layout.addWidget(self.status_lbl)
        self.layout.addStretch(1)
        self.layout.addWidget(self.button)

    @qasync.asyncSlot()
    async def load(self):
        account = await github.get_account()
        if not shiboken6.isValid(self):
            return
        self.login = account['login'] if account else None
        self.status_lbl.setText(
            f'Signed in as {self.login}' if self.login else 'Not signed in')
        self.button.setText('Sign Out' if self.login else 'Sign In')

    @qasync.asyncSlot()
    async def on_button_clicked(self):
        if self.login:
            await github.sign_out()
            self.load()
            return
        dialog = GitHubSignInDialog(self)
        dialog.accepted.connect(self.load)
        dialog.open()
