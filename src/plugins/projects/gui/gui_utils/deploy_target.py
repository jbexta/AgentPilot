import ftplib
import re

import qasync
from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QComboBox, QDialog, QFormLayout, QLabel, QLineEdit, QPlainTextEdit,
    QPushButton,
)

from gui.gui_utils.layouts import CHBoxLayout, CVBoxLayout
from plugins.projects.utils import deploy
from plugins.projects.utils.deploy_transport import transport

PROTOCOLS = [('SSH', 'ssh'), ('FTPS', 'ftps'), ('FTP (unencrypted)', 'ftp')]


class DeployTargetDialog(QDialog):
    """Adds a deploy target to the repo at `root`, or edits `target`."""

    def __init__(self, parent, root, target=None):
        super().__init__(parent)
        self.root = root
        self.old_name = target.name if target else None
        target = target or deploy.Target(
            'production', maps=[('.', '~/public_html')])
        self.setObjectName('deployTargetDialog')
        self.setWindowTitle('Deploy Target')
        self.setAttribute(Qt.WA_DeleteOnClose)
        self.setFixedWidth(520)
        self.busy = False

        title = QLabel('Edit deploy target' if self.old_name
                       else 'Add a deploy target')
        title.setObjectName('dialogTitle')

        self.name_edit = QLineEdit(target.name)
        self.protocol_combo = QComboBox()
        for text, protocol in PROTOCOLS:
            self.protocol_combo.addItem(text, protocol)
        self.protocol_combo.setCurrentIndex(
            self.protocol_combo.findData(target.protocol))
        self.protocol_combo.currentIndexChanged.connect(self.refresh)
        self.host_edit = QLineEdit(target.host)
        self.port_edit = QLineEdit(str(target.port or ''))
        self.port_edit.setPlaceholderText('Default')
        self.user_edit = QLineEdit(target.user)
        self.identity_edit = QLineEdit(target.identity)
        self.identity_edit.setPlaceholderText(
            'Optional, else ssh-agent and ~/.ssh/config')
        self.password_edit = QLineEdit()
        self.password_edit.setEchoMode(QLineEdit.Password)
        self.password_edit.setPlaceholderText('Saved in the system keyring')
        self.maps_edit = self.lines_edit(
            [f'{local}:{remote}' for local, remote in target.maps],
            'local/folder:~/remote/folder, one per line')
        self.include_edit = self.lines_edit(
            target.include, 'Gitignored files to upload, e.g. dist/*')
        self.file_mode_edit = QLineEdit(
            f'{target.file_mode:o}' if target.file_mode else '')
        self.file_mode_edit.setPlaceholderText('644, or 755 if executable')
        self.dir_mode_edit = QLineEdit(
            f'{target.dir_mode:o}' if target.dir_mode else '')
        self.dir_mode_edit.setPlaceholderText('Server default')
        self.marker_edit = QLineEdit(target.marker)
        self.marker_edit.setPlaceholderText(
            'Folder for .deploy-rev, else the first remote folder')
        self.post_edit = self.lines_edit(
            target.post, 'Commands run on the server after a push')
        for edit in (self.name_edit, self.host_edit):
            edit.textChanged.connect(self.refresh)
        self.maps_edit.textChanged.connect(self.refresh)

        self.form = QFormLayout()
        self.form.setSpacing(8)
        for text, widget in (
            ('Name', self.name_edit),
            ('Protocol', self.protocol_combo),
            ('Host', self.host_edit),
            ('Port', self.port_edit),
            ('User', self.user_edit),
            ('Key file', self.identity_edit),
            ('Password', self.password_edit),
            ('Folders', self.maps_edit),
            ('Include', self.include_edit),
            ('File mode', self.file_mode_edit),
            ('Folder mode', self.dir_mode_edit),
            ('Marker folder', self.marker_edit),
            ('After push', self.post_edit),
        ):
            label = QLabel(text)
            label.setProperty('class', 'dialog-label')
            self.form.addRow(label, widget)

        self.warning_lbl = QLabel(
            'Plain FTP sends your password and files unencrypted. Use FTPS '
            'if your host supports it.')
        self.warning_lbl.setObjectName('dialogError')
        self.warning_lbl.setWordWrap(True)
        self.status_lbl = QLabel()
        self.status_lbl.setObjectName('dialogDetail')
        self.status_lbl.setWordWrap(True)
        self.status_lbl.hide()
        self.error_lbl = QLabel()
        self.error_lbl.setObjectName('dialogError')
        self.error_lbl.setWordWrap(True)
        self.error_lbl.hide()

        self.test_btn = QPushButton('Test Connection')
        self.test_btn.setProperty('class', 'dialog-button')
        self.test_btn.setAutoDefault(False)
        self.test_btn.clicked.connect(self.test)
        self.cancel_btn = QPushButton('Cancel')
        self.cancel_btn.setProperty('class', 'dialog-button')
        self.cancel_btn.setAutoDefault(False)
        self.cancel_btn.clicked.connect(self.reject)
        self.save_btn = QPushButton('Save')
        self.save_btn.setProperty('class', 'dialog-button')
        self.save_btn.setProperty('primary', True)
        self.save_btn.setDefault(True)
        self.save_btn.clicked.connect(self.save)
        button_row = CHBoxLayout()
        button_row.setSpacing(8)
        button_row.addWidget(self.test_btn)
        button_row.addStretch(1)
        button_row.addWidget(self.cancel_btn)
        button_row.addWidget(self.save_btn)

        self.layout = CVBoxLayout(self)
        self.layout.setContentsMargins(24, 20, 24, 20)
        self.layout.addWidget(title)
        self.layout.addSpacing(16)
        self.layout.addLayout(self.form)
        self.layout.addSpacing(12)
        self.layout.addWidget(self.warning_lbl)
        self.layout.addWidget(self.status_lbl)
        self.layout.addWidget(self.error_lbl)
        self.layout.addSpacing(18)
        self.layout.addLayout(button_row)

        self.refresh()
        self.host_edit.setFocus()

    @staticmethod
    def lines_edit(lines, placeholder):
        edit = QPlainTextEdit('\n'.join(lines))
        edit.setPlaceholderText(placeholder)
        edit.setFixedHeight(64)
        return edit

    @staticmethod
    def lines(edit):
        return [
            line.strip() for line in edit.toPlainText().splitlines()
            if line.strip()]

    def refresh(self):
        protocol = self.protocol_combo.currentData()
        is_ssh = protocol == 'ssh'
        for widget in (self.identity_edit, self.file_mode_edit,
                       self.dir_mode_edit, self.post_edit):
            self.form.setRowVisible(widget, is_ssh)
        self.warning_lbl.setVisible(protocol == 'ftp')
        ready = bool(
            self.name_edit.text().strip() and self.host_edit.text().strip()
            and self.lines(self.maps_edit))
        self.save_btn.setEnabled(ready and not self.busy)
        self.test_btn.setEnabled(ready and not self.busy)

    def set_busy(self, busy, status=''):
        self.busy = busy
        self.cancel_btn.setEnabled(not busy)
        self.status_lbl.setText(status)
        self.status_lbl.setVisible(bool(status))
        self.refresh()

    def show_error(self, message):
        self.error_lbl.setText(message)
        self.error_lbl.setVisible(bool(message))

    def reject(self):
        if not self.busy:
            super().reject()

    def target(self):
        """The target from the fields. Raises ValueError if one is invalid."""
        name = self.name_edit.text().strip()
        if not re.fullmatch(r'[A-Za-z0-9_-]+', name):
            raise ValueError(
                'Use only letters, digits, - and _ in the name')
        maps = []
        for line in self.lines(self.maps_edit):
            local, sep, remote = line.partition(':')
            if not sep or not remote.strip():
                raise ValueError(f'Folders need local:remote, got "{line}"')
            maps.append((local.strip().strip('/') or '.', remote.strip()))
        is_ssh = self.protocol_combo.currentData() == 'ssh'

        def number(edit, base):
            text = edit.text().strip()
            try:
                return int(text, base) if text else None
            except ValueError:
                raise ValueError(f'"{text}" is not a valid number')

        return deploy.Target(
            name=name,
            protocol=self.protocol_combo.currentData(),
            host=self.host_edit.text().strip(),
            port=number(self.port_edit, 10),
            user=self.user_edit.text().strip(),
            identity=self.identity_edit.text().strip() if is_ssh else '',
            maps=maps,
            include=self.lines(self.include_edit),
            dir_mode=number(self.dir_mode_edit, 8) if is_ssh else None,
            file_mode=number(self.file_mode_edit, 8) if is_ssh else None,
            marker=self.marker_edit.text().strip(),
            post=self.lines(self.post_edit) if is_ssh else [],
        )

    @qasync.asyncSlot()
    async def test(self):
        self.show_error('')
        try:
            target = self.target()
        except ValueError as e:
            self.show_error(str(e))
            return
        self.set_busy(True, 'Connecting...')
        password = (
            self.password_edit.text() if self.password_edit.isModified()
            else await deploy.get_password(target))
        remote = target.maps[0][1]
        try:
            connection = transport(
                target.protocol, target.host, target.port, target.user,
                target.identity, password)
            files = await connection.list(remote)
        except (RuntimeError, OSError, ftplib.Error) as e:
            self.set_busy(False)
            self.show_error(str(e) or type(e).__name__)
            return
        self.set_busy(False, f'Connected. {len(files)} files in {remote}.')

    @qasync.asyncSlot()
    async def save(self):
        self.show_error('')
        try:
            target = self.target()
        except ValueError as e:
            self.show_error(str(e))
            return
        if (target.name != self.old_name
                and target.name in await deploy.targets(self.root)):
            self.show_error(f'There is already a target named {target.name}')
            return
        self.set_busy(True)
        try:
            await deploy.save_target(self.root, target, self.old_name)
            if self.password_edit.isModified():
                await deploy.set_password(target, self.password_edit.text())
        except RuntimeError as e:
            self.set_busy(False)
            self.show_error(str(e))
            return
        self.busy = False
        self.accept()
