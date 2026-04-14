import os
import subprocess

from PySide6.QtCore import QTimer

from src.plugins.projects.gui.project_types.general import GeneralProject
from plugins.projects.utils.sync import sync_file_to_db
from utils.helpers import set_module_type


@set_module_type(module_type='Project_types')
class ApplicationProject(GeneralProject):
    def __init__(self, parent):
        super().__init__(parent=parent)
        self._file_mtimes = {}
        self._poll_timer = QTimer(self)
        self._poll_timer.timeout.connect(self._poll_files)

    def load_config(self, json_config=None):
        super().load_config(json_config)
        config = self.get_config()
        working_dir = config.get('working_dir', '')
        if working_dir and not os.path.isdir(working_dir):
            subprocess.run(
                ['git', 'clone',
                 'https://github.com/jbexta/AgentPilot.git',
                 working_dir],
                check=True,
            )
        self._poll_timer.stop()
        self._file_mtimes.clear()
        src_dir = os.path.join(working_dir, 'src') if working_dir else ''
        if src_dir and os.path.isdir(src_dir):
            self._src_base = working_dir
            self._seed_mtimes(src_dir)
            self._poll_timer.start(2000)

    def _seed_mtimes(self, src_dir):
        """Record current mtimes for all ``.py`` files under *src_dir*."""
        for dirpath, dirnames, filenames in os.walk(src_dir):
            dirnames[:] = [d for d in dirnames if d != '__pycache__']
            for fn in filenames:
                if fn.endswith('.py'):
                    fp = os.path.join(dirpath, fn)
                    try:
                        self._file_mtimes[fp] = os.path.getmtime(fp)
                    except OSError:
                        pass

    def _poll_files(self):
        """Detect modified ``.py`` files and sync changes to the DB."""
        src_dir = os.path.join(self._src_base, 'src')
        for dirpath, dirnames, filenames in os.walk(src_dir):
            dirnames[:] = [d for d in dirnames if d != '__pycache__']
            for fn in filenames:
                if not fn.endswith('.py'):
                    continue
                fp = os.path.join(dirpath, fn)
                try:
                    mtime = os.path.getmtime(fp)
                except OSError:
                    continue
                prev = self._file_mtimes.get(fp)
                if prev is not None and mtime != prev:
                    sync_file_to_db(fp, src_base=self._src_base)
                self._file_mtimes[fp] = mtime
                