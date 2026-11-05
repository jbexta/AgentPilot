import asyncio

import aiohttp
from keyring.errors import KeyringError, NoKeyringError
from PySide6.QtCore import Qt, QUrl
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import QApplication, QDialog, QLabel, QPushButton

from gui.gui_utils.layouts import CHBoxLayout, CVBoxLayout
from plugins.projects.utils import github


class GitHubSignInDialog(QDialog):
    """Signs in to GitHub with a device code, accepted once signed in."""

    def __init__(self, parent):
        super().__init__(parent)
        self.setObjectName('githubSignInDialog')
        self.setWindowTitle('Sign in to GitHub')
        self.setAttribute(Qt.WA_DeleteOnClose)
        self.setFixedWidth(440)
        self.verification_uri = ''

        title = QLabel('Sign in to GitHub')
        title.setObjectName('dialogTitle')

        message = QLabel(
            'Enter this code on GitHub to let AgentPilot push and pull '
            'your repositories.')
        message.setWordWrap(True)

        self.code_lbl = QLabel('····-····')
        self.code_lbl.setObjectName('githubCode')
        self.code_lbl.setAlignment(Qt.AlignCenter)
        self.code_lbl.setTextInteractionFlags(Qt.TextSelectableByMouse)

        hint = QLabel('Only enter codes that AgentPilot shows you.')
        hint.setObjectName('dialogDetail')

        self.status_lbl = QLabel('Requesting a code...')
        self.status_lbl.setObjectName('dialogDetail')
        self.status_lbl.setWordWrap(True)

        self.error_lbl = QLabel()
        self.error_lbl.setObjectName('dialogError')
        self.error_lbl.setWordWrap(True)
        self.error_lbl.hide()

        cancel_btn = QPushButton('Cancel')
        cancel_btn.setProperty('class', 'dialog-button')
        cancel_btn.setAutoDefault(False)
        cancel_btn.clicked.connect(self.reject)
        self.open_btn = QPushButton('Copy Code && Open GitHub')
        self.open_btn.setProperty('class', 'dialog-button')
        self.open_btn.setProperty('primary', True)
        self.open_btn.setDefault(True)
        self.open_btn.setEnabled(False)
        self.open_btn.clicked.connect(self.open_github)
        button_row = CHBoxLayout()
        button_row.setSpacing(8)
        button_row.addStretch(1)
        button_row.addWidget(cancel_btn)
        button_row.addWidget(self.open_btn)

        self.layout = CVBoxLayout(self)
        self.layout.setContentsMargins(24, 20, 24, 20)
        self.layout.addWidget(title)
        self.layout.addSpacing(12)
        self.layout.addWidget(message)
        self.layout.addSpacing(16)
        self.layout.addWidget(self.code_lbl)
        self.layout.addSpacing(16)
        self.layout.addWidget(hint)
        self.layout.addSpacing(4)
        self.layout.addWidget(self.status_lbl)
        self.layout.addWidget(self.error_lbl)
        self.layout.addSpacing(18)
        self.layout.addLayout(button_row)

        self.task = asyncio.ensure_future(self.sign_in())

    async def sign_in(self):
        try:
            code = await github.request_device_code()
            self.code_lbl.setText(code['user_code'])
            self.verification_uri = code['verification_uri']
            self.open_btn.setEnabled(True)
            self.status_lbl.setText('Waiting for you to approve on GitHub...')
            token = await github.poll_token(code['device_code'], code['interval'])
            self.status_lbl.setText('Signing in...')
            await github.sign_in(token)
        except NoKeyringError:
            self.show_error(
                "No system keyring is available, so the sign-in can't be saved.")
        except KeyringError:
            self.show_error("Couldn't save the sign-in to the system keyring.")
        except aiohttp.ClientError:
            self.show_error("Couldn't reach GitHub. Check your connection.")
        except RuntimeError as e:
            self.show_error(str(e))
        else:
            self.accept()

    def show_error(self, text):
        self.status_lbl.hide()
        self.open_btn.setEnabled(False)
        self.error_lbl.setText(text)
        self.error_lbl.show()

    def open_github(self):
        QApplication.clipboard().setText(self.code_lbl.text())
        QDesktopServices.openUrl(QUrl(self.verification_uri))

    def done(self, result):
        self.task.cancel()
        super().done(result)
