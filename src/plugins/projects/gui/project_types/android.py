import asyncio
import glob
import os
import re
import shlex
import shutil
import time
import xml.etree.ElementTree as ET

import qasync
from PySide6.QtCore import QProcess, Qt
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import (
    QCheckBox, QComboBox, QLabel, QPlainTextEdit, QPushButton, QRadioButton,
    QSizePolicy,
)

from gui.gui_utils.icon_button import IconButton
from gui.gui_utils.layouts import CHBoxLayout, CVBoxLayout
from gui.widgets.config_widget import ConfigWidget
from plugins.projects.gui.project_types.general import GeneralProject
from utils.helpers import llm_tool, set_module_type

GRADLE_WRAPPER = 'gradlew.bat' if os.name == 'nt' else 'gradlew'
NAV_KEYS = {
    'back': 'KEYCODE_BACK',
    'home': 'KEYCODE_HOME',
    'recents': 'KEYCODE_APP_SWITCH',
    'enter': 'KEYCODE_ENTER',
    'delete': 'KEYCODE_DEL',
}
QT_KEYS = {
    Qt.Key_Backspace: 'KEYCODE_DEL',
    Qt.Key_Delete: 'KEYCODE_FORWARD_DEL',
    Qt.Key_Return: 'KEYCODE_ENTER',
    Qt.Key_Enter: 'KEYCODE_ENTER',
    Qt.Key_Escape: 'KEYCODE_BACK',
    Qt.Key_Tab: 'KEYCODE_TAB',
    Qt.Key_Up: 'KEYCODE_DPAD_UP',
    Qt.Key_Down: 'KEYCODE_DPAD_DOWN',
    Qt.Key_Left: 'KEYCODE_DPAD_LEFT',
    Qt.Key_Right: 'KEYCODE_DPAD_RIGHT',
}


def sdk_tool(subdir, name):
    """The path of an Android SDK executable, or None if it's missing."""
    exe = name + ('.exe' if os.name == 'nt' else '')
    roots = [
        os.environ.get('ANDROID_HOME'),
        os.environ.get('ANDROID_SDK_ROOT'),
        os.path.expanduser('~/Android/Sdk'),
        os.path.expanduser('~/Library/Android/sdk'),
        os.path.expanduser('~/AppData/Local/Android/Sdk'),
    ]
    for root in filter(None, roots):
        path = os.path.join(root, subdir, exe)
        if os.path.isfile(path):
            return path
    return shutil.which(name)


async def run_tool(program, *args):
    proc = await asyncio.create_subprocess_exec(
        program, *args,
        stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE,
    )
    out, err = await proc.communicate()
    if proc.returncode:
        raise RuntimeError(
            err.decode(errors='replace').strip()
            or f'{os.path.basename(program)} exited with {proc.returncode}'
        )
    return out


async def adb(serial, *args):
    program = sdk_tool('platform-tools', 'adb')
    if not program:
        raise RuntimeError(
            'adb not found, install the Android SDK platform-tools '
            'or set ANDROID_HOME'
        )
    return await run_tool(
        program, *(('-s', serial) if serial else ()), *args
    )


def app_package(working_dir):
    """The applicationId of the project's app module."""
    for path in sorted(glob.glob(
            os.path.join(working_dir, '*', 'build.gradle*'))):
        with open(path, encoding='utf-8') as f:
            match = re.search(
                r'applicationId\s*=?\s*["\']([\w.]+)["\']', f.read()
            )
        if match:
            return match.group(1)
    for path in glob.glob(os.path.join(
            working_dir, '*', 'src', 'main', 'AndroidManifest.xml')):
        with open(path, encoding='utf-8') as f:
            match = re.search(r'\bpackage="([\w.]+)"', f.read())
        if match:
            return match.group(1)
    return None


@set_module_type(module_type='Project_types')
class AndroidProject(GeneralProject):
    def __init__(self, parent):
        super().__init__(parent=parent)

        self.widgets[0] = self.Android_Fields(parent=self)

        side_tabs = self.widgets[1]
        side_tabs.pages['Preview'] = self.Android_Preview(parent=side_tabs)
        side_tabs.pages['Context'] = side_tabs.pages.pop('Context')
        tabs = self.widgets[2]
        tabs.pages['Logcat'] = self.Android_Logcat(parent=tabs)
        tabs.pages['Output'] = self.Android_Output(parent=tabs)

    class Android_Fields(GeneralProject.Project_Fields):
        """The project header, with buttons to run and stop the app."""

        def __init__(self, parent):
            super().__init__(parent=parent)
            self.schema = self.schema + [
                {
                    'text': '',
                    'key': 'android_run',
                    'type': 'button',
                    'icon_path': ':/resources/icon-play.png',
                    'target': self.run,
                    'tooltip': 'Build, install and launch on the device',
                    'row_key': 0,
                },
                {
                    'text': '',
                    'key': 'android_stop',
                    'type': 'button',
                    'icon_path': ':/resources/icon-stop.png',
                    'target': self.stop_app,
                    'tooltip': 'Stop the app',
                    'row_key': 0,
                },
            ]

        @qasync.asyncSlot()
        async def run(self):
            working_dir = self.parent.get_config().get('working_dir', '')
            side_tabs = self.parent.widgets[1]
            tabs = self.parent.widgets[2]
            preview = side_tabs.pages['Preview']
            output = tabs.pages['Output']

            tabs.goto_page('Output')
            installed = await output.run_gradle(
                working_dir, 'installDebug', preview.serial(),
            )
            if not installed:
                return
            package = app_package(working_dir)
            if not package:
                output.view.appendPlainText('No applicationId found')
                return
            try:
                await preview.adb(
                    'shell', 'monkey', '-p', package,
                    '-c', 'android.intent.category.LAUNCHER', '1',
                )
            except RuntimeError as e:
                output.view.appendPlainText(str(e))
                return
            side_tabs.goto_page('Preview')
            await tabs.pages['Logcat'].follow()

        @qasync.asyncSlot()
        async def stop_app(self):
            working_dir = self.parent.get_config().get('working_dir', '')
            package = app_package(working_dir)
            if package:
                preview = self.parent.widgets[1].pages['Preview']
                await preview.adb('shell', 'am', 'force-stop', package)

    class Android_Preview(ConfigWidget):
        """The device screen, mirrored and controllable with the mouse."""

        def __init__(self, parent):
            super().__init__(parent=parent)
            self.propagate_config = False
            self.stream = None
            self.status = ''

            self.emulator_radio = QRadioButton('Emulator', self)
            self.emulator_radio.setChecked(True)
            self.emulator_radio.toggled.connect(
                lambda: self.refresh_devices()
            )
            device_radio = QRadioButton('Device', self)

            self.device_combo = QComboBox(self)
            self.device_combo.setMinimumWidth(200)
            self.device_combo.activated.connect(self.on_device_chosen)
            refresh_btn = IconButton(
                parent=self,
                icon_path=':/resources/icon-refresh.png',
                target=self.refresh_devices,
                tooltip='Refresh devices',
            )

            toolbar = CHBoxLayout()
            toolbar.addWidget(self.emulator_radio)
            toolbar.addWidget(device_radio)
            toolbar.addWidget(self.device_combo)
            toolbar.addWidget(refresh_btn)
            toolbar.addStretch(1)
            for text, key in (('◁', 'back'), ('○', 'home'), ('□', 'recents')):
                btn = QPushButton(text, self)
                btn.setToolTip(key.capitalize())
                btn.clicked.connect(lambda _=None, k=key: self.press_key(k))
                toolbar.addWidget(btn)

            self.screen = self.Device_Screen(parent=self)

            self.layout = CVBoxLayout(self)
            self.layout.addLayout(toolbar)
            self.layout.addWidget(self.screen, stretch=1)

        def showEvent(self, event):
            super().showEvent(event)
            self.refresh_devices()
            if not self.stream:
                self.stream = asyncio.ensure_future(self.stream_screen())

        def hideEvent(self, event):
            super().hideEvent(event)
            if self.stream:
                self.stream.cancel()
                self.stream = None

        def agent_visualisation(self):
            return f'Android device: {self.serial() or "none"}'

        def serial(self):
            data = self.device_combo.currentData()
            return data.get('serial') if data else None

        async def adb(self, *args):
            serial = self.serial()
            if not serial:
                raise RuntimeError('No Android device connected')
            return await adb(serial, *args)

        async def stream_screen(self):
            while True:
                if not self.serial():
                    self.screen.show_message(self.status)
                    await asyncio.sleep(1)
                    continue
                try:
                    png = await self.adb('exec-out', 'screencap', '-p')
                except RuntimeError as e:
                    self.screen.show_message(str(e))
                    await asyncio.sleep(2)
                    continue
                self.screen.show_frame(png)
                await asyncio.sleep(0.05)

        @qasync.asyncSlot()
        async def refresh_devices(self, select=None):
            current = select or self.serial()
            self.device_combo.clear()
            try:
                serials = await self.connected_serials()
            except RuntimeError as e:
                self.status = str(e)
                return

            emulator_mode = self.emulator_radio.isChecked()
            for serial in serials:
                if serial.startswith('emulator-') == emulator_mode:
                    self.device_combo.addItem(serial, {'serial': serial})

            if emulator_mode:
                emulator = sdk_tool('emulator', 'emulator')
                avds = (
                    (await run_tool(emulator, '-list-avds')).decode().split()
                    if emulator else []
                )
                for avd in avds:
                    self.device_combo.addItem(
                        f'Start emulator: {avd}', {'avd': avd}
                    )
                if not emulator:
                    self.status = (
                        'emulator not found, install the Android SDK '
                        'emulator or set ANDROID_HOME'
                    )
                elif not avds:
                    self.status = (
                        'No emulators found, create one in the Android '
                        'Studio Device Manager'
                    )
                else:
                    self.status = 'Choose an emulator to start'
            else:
                self.status = (
                    'No device found, connect one with USB debugging on'
                )

            index = self.device_combo.findText(current) if current else -1
            self.device_combo.setCurrentIndex(max(index, 0))

        @qasync.asyncSlot()
        async def on_device_chosen(self, index):
            avd = self.device_combo.itemData(index).get('avd')
            if not avd:
                return
            emulator = sdk_tool('emulator', 'emulator')
            before = set(await self.connected_serials())
            QProcess.startDetached(emulator, ['-avd', avd])
            self.status = f'Starting {avd}...'
            for _ in range(60):
                await asyncio.sleep(2)
                started = set(await self.connected_serials()) - before
                if started:
                    await self.refresh_devices(select=started.pop())
                    return
            self.status = f'{avd} did not start'

        async def connected_serials(self):
            out = await adb(None, 'devices')
            return [
                line.split('\t')[0]
                for line in out.decode().splitlines()[1:]
                if line.endswith('\tdevice')
            ]

        @llm_tool(
            description='Tap the Android device screen at pixel x, y',
            params={'x': 'Pixels from the left', 'y': 'Pixels from the top'},
        )
        @qasync.asyncSlot()
        async def tap(self, x: int, y: int):
            await self.adb('shell', 'input', 'tap', str(x), str(y))

        @llm_tool(
            description='Swipe on the Android device screen',
            params={
                'x1': 'Start x', 'y1': 'Start y',
                'x2': 'End x', 'y2': 'End y',
                'duration_ms': 'How long the swipe takes',
            },
        )
        @qasync.asyncSlot()
        async def swipe(self, x1: int, y1: int, x2: int, y2: int,
                        duration_ms: int = 300):
            await self.adb(
                'shell', 'input', 'swipe',
                *map(str, (x1, y1, x2, y2, duration_ms)),
            )

        @llm_tool(
            description='Type text into the focused field on the device',
            params={'text': 'The text to type'},
        )
        @qasync.asyncSlot()
        async def type_text(self, text: str):
            await self.adb(
                'shell', 'input', 'text',
                shlex.quote(text.replace(' ', '%s')),
            )

        @llm_tool(
            description='Press a key on the device',
            params={'key': f'One of: {", ".join(NAV_KEYS)}'},
        )
        @qasync.asyncSlot()
        async def press_key(self, key: str):
            await self.adb(
                'shell', 'input', 'keyevent', NAV_KEYS.get(key, key),
            )

        @llm_tool(
            description='List the elements on the device screen, with '
                        'their text and the coordinates to tap them',
            params={},
        )
        @qasync.asyncSlot()
        async def dump_ui(self):
            out = await self.adb(
                'exec-out', 'uiautomator', 'dump', '/dev/tty',
            )
            xml = out.decode(errors='replace')
            root = ET.fromstring(xml[:xml.rfind('>') + 1])
            lines = []
            for node in root.iter('node'):
                label = node.get('text') or node.get('content-desc')
                clickable = node.get('clickable') == 'true'
                if not label and not clickable:
                    continue
                x1, y1, x2, y2 = map(
                    int, re.findall(r'\d+', node.get('bounds'))
                )
                resource = node.get('resource-id', '').split('/')[-1]
                lines.append(
                    f'"{label or ""}" {node.get("class", "").split(".")[-1]}'
                    f'{f" #{resource}" if resource else ""}'
                    f' at ({(x1 + x2) // 2}, {(y1 + y2) // 2})'
                    f'{" clickable" if clickable else ""}'
                )
            return '\n'.join(lines) or 'No elements on screen'

        class Device_Screen(QLabel):
            def __init__(self, parent):
                super().__init__(parent)
                self.preview = parent
                self.frame = QPixmap()
                self.press_pos = None
                self.press_time = 0
                self.setAlignment(Qt.AlignCenter)
                self.setFocusPolicy(Qt.StrongFocus)
                self.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Ignored)

            def show_message(self, text):
                self.frame = QPixmap()
                self.setText(text)

            def show_frame(self, png):
                if self.frame.loadFromData(png, 'PNG'):
                    self.rescale()

            def rescale(self):
                if not self.frame.isNull():
                    self.setPixmap(self.frame.scaled(
                        self.size(), Qt.KeepAspectRatio,
                        Qt.SmoothTransformation,
                    ))

            def resizeEvent(self, event):
                super().resizeEvent(event)
                self.rescale()

            def to_device(self, pos):
                if self.frame.isNull():
                    return None
                shown = self.frame.size().scaled(
                    self.size(), Qt.KeepAspectRatio
                )
                scale = self.frame.width() / shown.width()
                x = (pos.x() - (self.width() - shown.width()) / 2) * scale
                y = (pos.y() - (self.height() - shown.height()) / 2) * scale
                if 0 <= x < self.frame.width() and 0 <= y < self.frame.height():
                    return int(x), int(y)
                return None

            def mousePressEvent(self, event):
                self.setFocus()
                self.press_pos = self.to_device(event.position())
                self.press_time = time.monotonic()

            def mouseReleaseEvent(self, event):
                start, end = self.press_pos, self.to_device(event.position())
                self.press_pos = None
                if not start or not end:
                    return
                if abs(end[0] - start[0]) + abs(end[1] - start[1]) < 20:
                    self.preview.tap(*start)
                    return
                duration = int((time.monotonic() - self.press_time) * 1000)
                self.preview.swipe(*start, *end, max(duration, 100))

            def keyPressEvent(self, event):
                key = QT_KEYS.get(event.key())
                if key:
                    self.preview.press_key(key)
                elif event.text().isprintable() and event.text():
                    self.preview.type_text(event.text())
                else:
                    super().keyPressEvent(event)

    class Android_Logcat(ConfigWidget):
        """The device log, optionally just the app's."""

        def __init__(self, parent):
            super().__init__(parent=parent)
            self.propagate_config = False

            self.app_only = QCheckBox('App only', self)
            self.app_only.setChecked(True)
            self.app_only.toggled.connect(lambda: self.follow())
            clear_btn = IconButton(
                parent=self,
                icon_path=':/resources/icon-clear.png',
                target=self.clear,
                tooltip='Clear the log',
            )
            self.view = QPlainTextEdit(self)
            self.view.setReadOnly(True)
            self.view.setMaximumBlockCount(5000)

            self.process = QProcess(self)
            self.process.setProcessChannelMode(QProcess.MergedChannels)
            self.process.readyReadStandardOutput.connect(self.read_output)

            toolbar = CHBoxLayout()
            toolbar.addWidget(self.app_only)
            toolbar.addStretch(1)
            toolbar.addWidget(clear_btn)

            self.layout = CVBoxLayout(self)
            self.layout.addLayout(toolbar)
            self.layout.addWidget(self.view)

        def showEvent(self, event):
            super().showEvent(event)
            if self.process.state() == QProcess.NotRunning:
                self.follow()

        @qasync.asyncSlot()
        async def follow(self):
            self.process.kill()
            self.process.waitForFinished(1000)
            serial = self.parent.parent.widgets[1].pages['Preview'].serial()
            if not serial:
                self.view.appendPlainText('No Android device connected')
                return
            args = ['-s', serial, 'logcat', '-v', 'time']
            if self.app_only.isChecked():
                working_dir = self.parent.parent.get_config().get(
                    'working_dir', ''
                )
                package = app_package(working_dir)
                if not package:
                    self.view.appendPlainText('No applicationId found')
                    return
                try:
                    pid = await adb(serial, 'shell', 'pidof', '-s', package)
                except RuntimeError:
                    self.view.appendPlainText('The app is not running')
                    return
                args += ['--pid', pid.decode().strip()]
            self.process.start(sdk_tool('platform-tools', 'adb'), args)

        @qasync.asyncSlot()
        async def clear(self):
            self.view.clear()
            await self.parent.parent.widgets[1].pages['Preview'].adb(
                'logcat', '-c',
            )

        def read_output(self):
            text = bytes(self.process.readAllStandardOutput())
            self.view.appendPlainText(
                text.decode(errors='replace').rstrip('\n')
            )

    class Android_Output(ConfigWidget):
        """What Gradle is printing."""

        def __init__(self, parent):
            super().__init__(parent=parent)
            self.propagate_config = False
            self.busy = False

            self.view = QPlainTextEdit(self)
            self.view.setReadOnly(True)
            self.view.setMaximumBlockCount(1000)

            self.layout = CVBoxLayout(self)
            self.layout.addWidget(self.view)

        async def run_gradle(self, working_dir, task, serial):
            """Run a Gradle task on the device, returning if it succeeded."""
            if self.busy:
                self.view.appendPlainText('Gradle is already running')
                return False
            if not os.path.isdir(working_dir):
                self.view.appendPlainText('Set a project path first')
                return False

            wrapper = os.path.join(working_dir, GRADLE_WRAPPER)
            program = wrapper if os.path.isfile(wrapper) else 'gradle'
            env = dict(os.environ, ANDROID_SERIAL=serial) if serial else None
            self.view.appendPlainText(f'$ {program} {task}')
            self.busy = True
            try:
                proc = await asyncio.create_subprocess_exec(
                    program, task, cwd=working_dir, env=env,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.STDOUT,
                )
                async for line in proc.stdout:
                    self.view.appendPlainText(
                        line.decode(errors='replace').rstrip('\n')
                    )
                code = await proc.wait()
            except OSError as e:
                self.view.appendPlainText(str(e))
                return False
            finally:
                self.busy = False
            self.view.appendPlainText(f'Exited with {code}')
            return code == 0
