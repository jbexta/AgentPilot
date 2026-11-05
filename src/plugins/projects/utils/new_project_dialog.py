import os
import re

import qasync
from PySide6.QtCore import QProcess, QProcessEnvironment, Qt
from PySide6.QtGui import QIcon, QPixmap
from PySide6.QtWidgets import (
    QButtonGroup, QComboBox, QDialog, QLabel, QLineEdit, QProgressBar,
    QPushButton, QWidget,
)

from gui.gui_utils.helpers import colorize_pixmap
from gui.gui_utils.layouts import CHBoxLayout, CVBoxLayout
from plugins.projects.utils import github, vcs


class NewProjectDialog(QDialog):
    """Creates a project folder in `projects_dir`, empty or cloned from git.
    On accept, `name`, `path` and `project_type` describe the new project."""

    def __init__(self, parent, projects_dir, project_types):
        super().__init__(parent)
        self.projects_dir = projects_dir
        self.name = ''
        self.path = ''
        self.project_type = ''
        self.name_edited = False
        self.clone_output = ''

        self.setObjectName('newProjectDialog')
        self.setWindowTitle('New Project')
        self.setAttribute(Qt.WA_DeleteOnClose)
        self.setFixedWidth(520)

        title = QLabel('Create a new project')
        title.setObjectName('newProjectTitle')

        self.empty_btn = self.mode_button('Empty project', ':/resources/icon-new.png')
        self.clone_btn = self.mode_button('Clone repository', ':/resources/icon-import.png')
        self.empty_btn.setChecked(True)
        mode_group = QButtonGroup(self)
        mode_group.addButton(self.empty_btn)
        mode_group.addButton(self.clone_btn)
        mode_group.buttonClicked.connect(self.on_mode_clicked)
        mode_row = CHBoxLayout()
        mode_row.setSpacing(8)
        mode_row.addWidget(self.empty_btn)
        mode_row.addWidget(self.clone_btn)

        self.url_edit = QLineEdit()
        self.url_edit.setPlaceholderText('https://github.com/owner/repo.git')
        self.url_edit.textChanged.connect(self.on_url_changed)
        self.url_field = self.field('Repository URL', self.url_edit)

        self.name_edit = QLineEdit()
        self.name_edit.setPlaceholderText('my-project')
        self.name_edit.textEdited.connect(self.on_name_edited)
        self.name_edit.textChanged.connect(lambda _: self.refresh())

        self.type_combo = QComboBox()
        for project_type in project_types:
            self.type_combo.addItem(project_type.capitalize(), project_type)
        self.type_combo.setCurrentIndex(max(self.type_combo.findData('general'), 0))
        self.type_combo.setFixedWidth(150)
        name_row = CHBoxLayout()
        name_row.setSpacing(12)
        name_row.addWidget(self.field('Project name', self.name_edit), 1)
        name_row.addWidget(self.field('Project type', self.type_combo))

        self.location_lbl = QLabel()
        self.location_lbl.setObjectName('newProjectLocation')
        self.location_lbl.setTextInteractionFlags(Qt.TextSelectableByMouse)
        self.location_lbl.setWordWrap(True)

        self.error_lbl = QLabel()
        self.error_lbl.setObjectName('newProjectError')
        self.error_lbl.setWordWrap(True)

        self.progress_bar = QProgressBar()
        self.progress_bar.setObjectName('newProjectProgress')
        self.progress_bar.setTextVisible(False)
        self.progress_bar.setFixedHeight(4)
        self.status_lbl = QLabel()
        self.status_lbl.setObjectName('newProjectStatus')

        self.cancel_btn = QPushButton('Cancel')
        self.cancel_btn.setProperty('class', 'dialog-button')
        self.cancel_btn.setAutoDefault(False)
        self.cancel_btn.clicked.connect(self.reject)
        self.create_btn = QPushButton()
        self.create_btn.setProperty('class', 'dialog-button')
        self.create_btn.setProperty('primary', True)
        self.create_btn.setDefault(True)
        self.create_btn.clicked.connect(self.on_create)
        button_row = CHBoxLayout()
        button_row.setSpacing(8)
        button_row.addStretch(1)
        button_row.addWidget(self.cancel_btn)
        button_row.addWidget(self.create_btn)

        self.layout = CVBoxLayout(self)
        self.layout.setContentsMargins(24, 20, 24, 20)
        self.layout.addWidget(title)
        self.layout.addSpacing(16)
        self.layout.addLayout(mode_row)
        self.layout.addSpacing(18)
        self.layout.addWidget(self.url_field)
        self.layout.addLayout(name_row)
        self.layout.addWidget(self.location_lbl)
        self.layout.addSpacing(6)
        self.layout.addWidget(self.error_lbl)
        self.layout.addWidget(self.progress_bar)
        self.layout.addSpacing(4)
        self.layout.addWidget(self.status_lbl)
        self.layout.addSpacing(18)
        self.layout.addLayout(button_row)

        self.cancelled = False
        self.process = QProcess(self)
        env = QProcessEnvironment.systemEnvironment()
        env.insert('GIT_TERMINAL_PROMPT', '0')
        self.process.setProcessEnvironment(env)
        self.process.setProcessChannelMode(QProcess.MergedChannels)
        self.process.readyReadStandardOutput.connect(self.on_clone_output)
        self.process.finished.connect(self.on_clone_finished)
        self.process.errorOccurred.connect(self.on_clone_error)

        self.set_busy(False)
        self.name_edit.setFocus()

    def mode_button(self, text, icon_path):
        btn = QPushButton(text)
        btn.setProperty('class', 'new-project-mode')
        btn.setIcon(QIcon(colorize_pixmap(QPixmap(icon_path))))
        btn.setCheckable(True)
        btn.setCursor(Qt.PointingHandCursor)
        return btn

    def field(self, label_text, input_widget):
        label = QLabel(label_text)
        label.setProperty('class', 'new-project-label')
        widget = QWidget()
        layout = CVBoxLayout(widget)
        layout.setSpacing(6)
        layout.setContentsMargins(0, 0, 0, 14)
        layout.addWidget(label)
        layout.addWidget(input_widget)
        return widget

    def is_clone(self):
        return self.clone_btn.isChecked()

    def target_path(self):
        return os.path.join(self.projects_dir, self.name_edit.text().strip())

    def on_mode_clicked(self):
        self.refresh()
        (self.url_edit if self.is_clone() else self.name_edit).setFocus()

    def on_url_changed(self, url):
        if not self.name_edited:
            repo = re.split(r'[/:]', url.strip().rstrip('/'))[-1]
            self.name_edit.setText(repo.removesuffix('.git'))
        self.refresh()

    def on_name_edited(self, text):
        self.name_edited = bool(text)

    def validation_error(self):
        name = self.name_edit.text().strip()
        if self.is_clone() and not self.url_edit.text().strip():
            return ''
        if not name:
            return ''
        if '/' in name or '\\' in name or name in ('.', '..'):
            return 'The name can\'t contain slashes.'
        if os.path.exists(self.target_path()):
            return 'A folder with this name already exists.'
        return ''

    def refresh(self):
        clone = self.is_clone()
        self.url_field.setVisible(clone)
        self.create_btn.setText('Clone' if clone else 'Create')

        name = self.name_edit.text().strip()
        location = self.target_path() if name else self.projects_dir + os.sep
        home = os.path.expanduser('~')
        if location.startswith(home + os.sep):
            location = '~' + location[len(home):]
        self.location_lbl.setText(f'Location: {location}')

        error = self.validation_error()
        self.show_error(error)
        self.create_btn.setEnabled(
            bool(name) and not error
            and (not clone or bool(self.url_edit.text().strip()))
        )
        self.layout.activate()
        self.adjustSize()

    def show_error(self, text):
        self.error_lbl.setText(text)
        self.error_lbl.setVisible(bool(text))

    def set_busy(self, busy):
        for widget in (self.empty_btn, self.clone_btn, self.url_edit, self.name_edit, self.type_combo):
            widget.setEnabled(not busy)
        self.progress_bar.setVisible(busy)
        self.status_lbl.setVisible(busy)
        if busy:
            self.create_btn.setEnabled(False)
            self.progress_bar.setRange(0, 0)
            self.status_lbl.setText('Starting clone...')
        else:
            self.refresh()

    @qasync.asyncSlot()
    async def on_create(self):
        self.name = self.name_edit.text().strip()
        self.path = self.target_path()
        self.project_type = self.type_combo.currentData()
        if not self.is_clone():
            os.makedirs(self.path)
            self.accept()
            return

        self.clone_output = ''
        self.show_error('')
        self.set_busy(True)
        token = await github.get_token()
        auth_args = []
        if token:
            env = self.process.processEnvironment()
            env.insert('AP_GITHUB_TOKEN', token)
            self.process.setProcessEnvironment(env)
            auth_args = vcs.github_auth_args()
        self.process.start(
            'git',
            [*auth_args, 'clone', '--progress', self.url_edit.text().strip(), self.path],
        )

    def on_clone_output(self):
        text = self.process.readAllStandardOutput().data().decode(errors='replace')
        self.clone_output += text
        lines = [ln.strip() for ln in re.split(r'[\r\n]', text) if ln.strip()]
        if not lines:
            return
        status = lines[-1].removeprefix('remote: ')
        self.status_lbl.setText(status)
        percent = re.search(r'(\d+)%', status)
        if percent:
            self.progress_bar.setRange(0, 100)
            self.progress_bar.setValue(int(percent.group(1)))
        else:
            self.progress_bar.setRange(0, 0)

    def on_clone_finished(self, exit_code, exit_status):
        if self.cancelled:
            super().reject()
            return
        if exit_status == QProcess.NormalExit and exit_code == 0:
            self.accept()
            return
        self.set_busy(False)
        lines = [ln.strip() for ln in re.split(r'[\r\n]', self.clone_output) if ln.strip()]
        fatal = [ln for ln in lines if ln.startswith(('fatal:', 'error:'))]
        message = (fatal or lines or ['git clone failed'])[-1]
        if 'terminal prompts disabled' in message:
            message = ('Repository not found, or it is private and git has '
                       'no credentials for it.')
        message = message.removeprefix('fatal: ').removeprefix('error: ')
        self.show_error(message[:1].upper() + message[1:])

    def on_clone_error(self, error):
        if error == QProcess.FailedToStart:
            self.set_busy(False)
            self.show_error('Git is not installed or not on your PATH.')

    def reject(self):
        if self.process.state() != QProcess.NotRunning:
            self.cancelled = True
            self.status_lbl.setText('Cancelling...')
            self.process.terminate()
            return
        super().reject()
