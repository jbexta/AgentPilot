import ftplib

import qasync
import shiboken6
from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QLabel, QPlainTextEdit, QPushButton, QSplitter, QTreeWidget,
    QTreeWidgetItem, QWidget,
)

from gui.gui_utils.layouts import CHBoxLayout, CVBoxLayout
from plugins.projects.gui.gui_utils.git_identity import GitIdentityDialog
from plugins.projects.utils import deploy, vcs
from utils.helpers import display_message, get_text

ERRORS = (RuntimeError, OSError, ftplib.Error)


class DeployPanel(QWidget):
    """The preview and output of a push to, or pull from, a deploy target,
    shown as a preview tab."""

    def __init__(self, tree_deploy):
        super().__init__()
        self.tree_deploy = tree_deploy
        self.target = None
        self.kind = 'push'
        self.plan = None
        self.items = {}

        self.title_lbl = QLabel()
        self.title_lbl.setObjectName('dialogTitle')
        self.detail_lbl = QLabel()
        self.detail_lbl.setObjectName('dialogDetail')
        self.detail_lbl.setWordWrap(True)
        self.warning_lbl = QLabel()
        self.warning_lbl.setObjectName('dialogError')
        self.warning_lbl.setWordWrap(True)
        self.warning_lbl.hide()
        self.commit_btn = QPushButton('Commit...')
        self.commit_btn.setProperty('class', 'dialog-button')
        self.commit_btn.clicked.connect(self.commit)
        self.commit_btn.hide()

        self.file_tree = QTreeWidget()
        self.file_tree.setHeaderLabels(['File', 'Change'])
        self.file_tree.setColumnWidth(0, 360)
        self.output = QPlainTextEdit()
        self.output.setObjectName('vcsDiff')
        self.output.setReadOnly(True)
        splitter = QSplitter(Qt.Vertical)
        splitter.setChildrenCollapsible(False)
        splitter.addWidget(self.file_tree)
        splitter.addWidget(self.output)
        splitter.setSizes([400, 160])

        self.refresh_btn = QPushButton('Refresh')
        self.refresh_btn.setProperty('class', 'dialog-button')
        self.refresh_btn.clicked.connect(self.refresh)
        self.run_btn = QPushButton()
        self.run_btn.setProperty('class', 'dialog-button')
        self.run_btn.setProperty('primary', True)
        self.run_btn.clicked.connect(self.run)

        warning_row = CHBoxLayout()
        warning_row.setSpacing(8)
        warning_row.addWidget(self.warning_lbl, 1)
        warning_row.addWidget(self.commit_btn)
        button_row = CHBoxLayout()
        button_row.setSpacing(8)
        button_row.addStretch(1)
        button_row.addWidget(self.refresh_btn)
        button_row.addWidget(self.run_btn)

        self.layout = CVBoxLayout(self)
        self.layout.setContentsMargins(12, 12, 12, 12)
        self.layout.setSpacing(8)
        self.layout.addWidget(self.title_lbl)
        self.layout.addWidget(self.detail_lbl)
        self.layout.addLayout(warning_row)
        self.layout.addWidget(splitter, 1)
        self.layout.addLayout(button_row)

    @property
    def root(self):
        return self.tree_deploy.repo_root

    def load(self, target, kind):
        self.target, self.kind = target, kind
        direction = 'to' if kind == 'push' else 'from'
        self.title_lbl.setText(f'{kind.title()} {direction} {target.name}')
        self.run_btn.setText(kind.title())
        self.output.clear()
        self.refresh()

    def set_busy(self, busy, detail=None):
        self.refresh_btn.setEnabled(not busy)
        self.run_btn.setEnabled(
            not busy and bool(self.plan and self.plan.items))
        if detail is not None:
            self.detail_lbl.setText(detail)

    def append_output(self, line):
        if shiboken6.isValid(self):
            self.output.appendPlainText(line)

    @qasync.asyncSlot()
    async def refresh(self):
        self.plan = None
        self.file_tree.clear()
        self.warning_lbl.hide()
        self.commit_btn.hide()
        self.set_busy(True, 'Comparing with the server...')
        make_plan = deploy.push_plan if self.kind == 'push' else deploy.pull_plan
        try:
            plan = await make_plan(self.root, self.target)
        except ERRORS as e:
            if shiboken6.isValid(self):
                self.set_busy(False, '')
                self.warning_lbl.setText(str(e) or type(e).__name__)
                self.warning_lbl.show()
            return
        if shiboken6.isValid(self):
            self.show_plan(plan)

    def show_plan(self, plan):
        self.plan = plan
        self.items = {}
        details = []
        if plan.commit:
            prefix = 'Commit' if self.kind == 'push' else 'Compared with'
            details.append(f'{prefix} {plan.commit[:7]}')
        if plan.first_sync:
            details.append('First sync: compared by file size')
        if not plan.items:
            details.append(f'Nothing to {self.kind}')
        self.set_busy(False, '. '.join(details))
        if plan.dirty:
            self.warning_lbl.setText(
                'You have uncommitted changes. Only committed files are '
                'deployed.')
            self.warning_lbl.show()
            self.commit_btn.show()

        for index, (local, remote) in enumerate(plan.target.maps):
            items = [item for item in plan.items if item.pair == index]
            if not items:
                continue
            arrow = '→' if self.kind == 'push' else '←'
            group = QTreeWidgetItem(self.file_tree, [f'{local} {arrow} {remote}'])
            group.setFlags(
                group.flags() | Qt.ItemIsUserCheckable | Qt.ItemIsAutoTristate)
            for item in sorted(items, key=lambda i: i.path):
                label = item.label
                if item.action in ('delete', 'delete_local'):
                    label += ' (delete)'
                if item.blocked:
                    label += ' (local changes)'
                row = QTreeWidgetItem(group, [item.path, label])
                row.setFlags(row.flags() | Qt.ItemIsUserCheckable)
                row.setCheckState(
                    0, Qt.Checked if item.ticked and not item.blocked
                    else Qt.Unchecked)
                if item.blocked:
                    row.setDisabled(True)
                self.items[id(row)] = (row, item)
            group.setExpanded(True)

    @qasync.asyncSlot()
    async def run(self):
        for row, item in self.items.values():
            item.ticked = row.checkState(0) == Qt.Checked
        self.output.clear()
        self.set_busy(True)
        self.run_btn.setEnabled(False)
        run = deploy.push if self.kind == 'push' else deploy.pull
        try:
            await run(self.root, self.plan, self.append_output)
        except ERRORS as e:
            self.append_output(str(e))
            display_message(str(e), f'{self.kind.title()} failed')
        self.tree_deploy.tree.refresh_extensions()
        if shiboken6.isValid(self):
            self.refresh()

    @qasync.asyncSlot()
    async def commit(self):
        if not await vcs.identity(self.root):
            dialog = GitIdentityDialog(self)
            dialog.accepted.connect(self.commit)
            dialog.open()
            return
        message, ok = get_text(self, 'Commit', 'Commit message:')
        if not ok or not message.strip():
            return
        try:
            await vcs.stage_all(self.root)
            await vcs.commit(self.root, message.strip())
        except RuntimeError as e:
            display_message(str(e), 'Commit failed')
        self.tree_deploy.tree.refresh_extensions()
        if shiboken6.isValid(self):
            self.refresh()
