import os
from pathlib import Path

import qasync
from PySide6.QtCore import QUrl
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import QMessageBox

from gui import system
from gui.widgets.config_fields import ConfigFields
from plugins.workflows.utils.workflows import blocks_instant_runnable
from utils.helpers import (
    block_signals, display_message, display_message_box, set_module_type)

CONTEXT_FILES = {'claude_md': 'CLAUDE', 'agents_md': 'AGENTS'}
EXPENSIVE_MSG = ("Auto-write is off: the template uses a block that can't "
                 'be instantly run. Click Write to render it.')


def find_context_files(directory, stem):
    """Existing ``<stem>.md``/``.MD`` files in *directory*, then in its
    ``.claude`` folder, matched by real entries so case-insensitive
    filesystems don't yield one file twice."""
    folders = (Path(directory), Path(directory) / '.claude')
    return [f / n for f in folders if f.is_dir()
            for n in (f'{stem}.md', f'{stem}.MD') if n in os.listdir(f)]


@set_module_type(module_type='Widgets')
class ClaudeContext(ConfigFields):
    """Edits the CLAUDE.md and AGENTS.md files of a directory as one text.

    *directory* is a callable returning the directory, or a falsy value
    to disable the widget. The text is a jinja template stored in the
    config, written to the files rendered; the checkboxes reflect the
    files on disk. Auto-write needs every referenced block to be instant
    runnable.
    """

    def __init__(self, parent, directory, conf_namespace):
        super().__init__(parent=parent, conf_namespace=conf_namespace)
        self.propagate_config = True
        self.directory = directory
        self.checked = {}
        self.suspended = False
        self.cheap = self.last_cheap = True
        row = {'type': bool, 'row_key': 0}
        open_btn = {**row, 'text': '', 'type': 'button',
                    'label_position': None, 'size': 20,
                    'icon_path': ':/resources/icon-files.png'}
        self.schema = [
            {**row, 'text': 'CLAUDE.md', 'key': 'claude_md', 'default': True},
            {**open_btn, 'key': 'open_claude_md', 'tooltip': 'Open CLAUDE.md',
             'target': lambda: self.open_file('CLAUDE'),
             'visibility_predicate': lambda: bool(self.context_file('CLAUDE'))},
            {**row, 'text': 'AGENTS.md', 'key': 'agents_md', 'default': False},
            {**open_btn, 'key': 'open_agents_md', 'tooltip': 'Open AGENTS.md',
             'target': lambda: self.open_file('AGENTS'),
             'visibility_predicate': lambda: bool(self.context_file('AGENTS'))},
            {**row, 'type': 'stretch'},
            {**row, 'text': 'Auto-write', 'key': 'auto_write',
             'default': True},
            {**row, 'text': 'Write', 'key': 'write_btn', 'type': 'button',
             'target': lambda: self.write_files(notify=True),
             'label_position': None,
             'visibility_predicate': lambda: self.suspended or not (
                 self.cheap and self.auto_write_wgt.get_value())},
            {'text': 'Text', 'key': 'text', 'type': str, 'num_lines': 20,
             'stretch_x': True, 'stretch_y': True, 'wrap_text': True,
             'label_position': None},
            {'text': 'Rendered', 'key': 'rendered', 'type': str,
             'visible': False},
        ]

    def context_file(self, stem):
        directory = self.directory()
        return directory and next(
            iter(find_context_files(directory, stem)), None)

    def open_file(self, stem):
        QDesktopServices.openUrl(
            QUrl.fromLocalFile(str(self.context_file(stem))))

    def get_config(self):
        return {k: v for k, v in super().get_config().items()
                if not k.endswith('_md')}

    def set_cheap(self, template, notify=True):
        """Allow auto-write only while every block is instant runnable,
        telling the user when a parseable template stops being so."""
        self.cheap = blocks_instant_runnable(template)
        if self.cheap is None:
            return
        if (notify and self.last_cheap and not self.cheap
                and self.auto_write_wgt.get_value()):
            display_message(EXPENSIVE_MSG, title='Auto-write paused',
                            icon=QMessageBox.Warning)
        self.last_cheap = self.cheap
        self.auto_write_wgt.setEnabled(self.cheap)
        self.auto_write_wgt.setToolTip('' if self.cheap else EXPENSIVE_MSG)

    def load(self):
        super().load()
        directory = self.directory()
        self.setEnabled(bool(directory))
        found = {key: find_context_files(directory, stem)
                 for key, stem in CONTEXT_FILES.items()} if directory else {}
        paths = {key: files[0] for key, files in found.items() if files}
        contents = {k: p.read_text('utf-8') for k, p in paths.items()}
        self.checked = {k: k in (paths or ['claude_md'])
                        for k in CONTEXT_FILES}
        first = next(iter(paths.values()), None)
        first_text = next(iter(contents.values()), '')
        template = self.config.get(f'{self.conf_namespace}.text')
        self.written_text = first_text if template is None else template
        self.set_cheap(self.written_text, notify=False)
        warnings = [
            'Multiple copies, delete all but the first:\n'
            + '\n'.join(str(f.relative_to(directory)) for f in files)
            for files in found.values() if len(files) > 1
        ]
        if len(set(contents.values())) > 1:
            warnings.append(' and '.join(
                str(p.relative_to(directory)) for p in paths.values())
                + ' differ, showing the first.')
        if (template is not None and first
                and first_text != self.rendered_wgt.get_value()):
            warnings.append(f'{first.relative_to(directory)} was edited '
                            'outside the app, showing the template.')
        self.suspended = bool(warnings)

        with block_signals(self):
            for key, checked in self.checked.items():
                getattr(self, f'{key}_wgt').set_value(checked)
            self.text_wgt.set_value(self.written_text)
        self.refresh_visibility()

        if warnings:
            display_message_box(
                icon=QMessageBox.Warning,
                title='Context file conflict',
                text=f'In {directory}:\n\n' + '\n\n'.join(warnings)
                     + '\n\nAuto-write is paused. Click Write to overwrite '
                       'the first copy of each checked file with the text '
                       'shown.',
            )

    def update_config(self):
        newly_checked = False
        for key, stem in CONTEXT_FILES.items():
            checked = getattr(self, f'{key}_wgt').get_value()
            if checked == self.checked.get(key):
                continue
            self.checked[key] = checked
            newly_checked |= checked
            path = next(iter(find_context_files(self.directory(), stem)), None)
            if not checked and path and display_message_box(
                icon=QMessageBox.Question, title='Delete file',
                text=f'Delete {path}?',
                buttons=QMessageBox.Yes | QMessageBox.No,
            ) == QMessageBox.Yes:
                path.unlink()
        text = self.text_wgt.get_value()
        self.set_cheap(text)
        if (self.cheap and self.auto_write_wgt.get_value()
                and not self.suspended
                and (text != self.written_text or newly_checked)):
            self.write_files()
        super().update_config()

    @qasync.asyncSlot()
    async def write_files(self, notify=False):
        """Render the template into the checked files, then save it.
        Render errors are always shown, success only if *notify*."""
        template = self.text_wgt.get_value()
        try:
            rendered = await system.manager.blocks.format_string(
                template, raise_errors=True)
        except Exception as e:
            display_message(f'Nothing was written: {e}', title='Write failed',
                            icon=QMessageBox.Warning)
            return
        directory = Path(self.directory())
        directory.mkdir(parents=True, exist_ok=True)
        written = []
        for key, stem in CONTEXT_FILES.items():
            if self.checked.get(key):
                path = next(iter(find_context_files(directory, stem)),
                            directory / f'{stem}.md')
                path.write_text(rendered, encoding='utf-8')
                written.append(str(path))
        if notify:
            display_message('Wrote ' + ', '.join(written),
                            title='Write succeeded',
                            icon=QMessageBox.Information)
        self.written_text = template
        self.rendered_wgt.set_value(rendered)
        self.suspended = False
        self.update_config()
