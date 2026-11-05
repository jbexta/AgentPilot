import asyncio
import os
import shutil
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

import qasync
from PySide6.QtCore import QFileSystemWatcher, QResource, QTimer
from PySide6.QtWidgets import QFileDialog

from plugins.files.widgets.file_tree import FileTree
from utils.helpers import RESOURCES_RCC, display_message, set_module_type

RESOURCES_DIR = Path(RESOURCES_RCC).parent / 'resources'
QRC_PATH = Path(RESOURCES_RCC).with_suffix('.qrc')


@set_module_type('Pages')
class Page_Icons(FileTree):
    display_name = 'Icons'
    icon_path = ':/resources/icon-image.png'
    page_type = 'settings'

    def __init__(self, parent):
        super().__init__(
            parent=parent,
            root_directory=RESOURCES_DIR,
            files_in_tree=True,
            fixed_directory=True,
            media_thumbnails=True,
        )
        self.rebuild_timer = QTimer(self)
        self.rebuild_timer.setSingleShot(True)
        self.rebuild_timer.setInterval(500)
        self.rebuild_timer.timeout.connect(self.rebuild_resources)

        self.watcher = QFileSystemWatcher([str(RESOURCES_DIR)], self)
        self.watcher.directoryChanged.connect(self.rebuild_timer.start)

    def _add_extra_file_actions(self, menu, file_path):
        action = menu.addAction('Replace...')
        action.triggered.connect(lambda: self.replace_icon(file_path))

    def replace_icon(self, file_path):
        source, _ = QFileDialog.getOpenFileName(
            self, f'Replace {file_path.name}'
        )
        if source:
            shutil.copyfile(source, file_path)
            self.rebuild_timer.start()

    @qasync.asyncSlot()
    async def rebuild_resources(self):
        self.write_qrc()
        tmp_rcc = f'{RESOURCES_RCC}.tmp'
        proc = await asyncio.create_subprocess_exec(
            str(Path(sys.executable).with_name('pyside6-rcc')),
            '--binary', str(QRC_PATH), '-o', tmp_rcc,
            stderr=asyncio.subprocess.PIPE,
        )
        _, stderr = await proc.communicate()
        if proc.returncode != 0:
            display_message(
                f'Failed to compile resources:\n{stderr.decode()}', 'Error'
            )
            return

        os.replace(tmp_rcc, RESOURCES_RCC)
        QResource.unregisterResource(RESOURCES_RCC)
        QResource.registerResource(RESOURCES_RCC)
        self.file_view.refresh()

    def write_qrc(self):
        tree = ET.parse(QRC_PATH)
        qresource = tree.find('qresource')
        for entry in qresource.findall('file'):
            if entry.text.startswith('resources/'):
                qresource.remove(entry)
        for path in sorted(RESOURCES_DIR.iterdir()):
            if path.is_file():
                ET.SubElement(qresource, 'file').text = f'resources/{path.name}'
        ET.indent(tree, space='    ')
        tree.write(QRC_PATH)
