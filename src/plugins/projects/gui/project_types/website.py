import asyncio
import os
import re
import socket

import qasync
from PySide6.QtCore import QUrl
from PySide6.QtWebEngineWidgets import QWebEngineView
from PySide6.QtWidgets import QLineEdit, QMessageBox, QPlainTextEdit

from gui import system
from gui.gui_utils.layouts import CHBoxLayout, CVBoxLayout
from gui.gui_utils.icon_button import IconButton
from gui.widgets.config_widget import ConfigWidget
from plugins.projects.gui.project_types.general import GeneralProject
from plugins.projects.utils.services import runner
from plugins.projects.utils.tls_proxy import LOCAL_HOSTS, free_port
from utils.helpers import display_message, path_to_pixmap, set_module_type

PLAY_ICON = ':/resources/icon-play.png'
STOP_ICON = ':/resources/icon-stop.png'


def get_stacks():
    """Every web stack module, best match first."""
    modules = system.manager.modules.get_modules_in_folder(
        module_type='Web_stacks', fetch_keys=('name', 'class',),
    )
    return sorted(
        (stack for _, stack in modules if stack),
        key=lambda stack: stack.priority,
    )


def resolve_stack(name, path):
    """The stack for *path*, honouring a manual choice over detection."""
    stacks = get_stacks()
    if name and name != 'Auto':
        return next((s for s in stacks if s.display_name == name), None)
    return next((s for s in stacks if s.detect(path)), None)


def preview_url(stack, config):
    """Where the preview points, over HTTPS when the project asks for it."""
    url = stack.url(config.get('working_dir', ''),
                    int(config.get('web_port') or 8080))
    if config.get('web_https') and url.startswith('http://'):
        return 'https://' + url.removeprefix('http://')
    return url


@set_module_type(module_type='Project_types')
class WebsiteProject(GeneralProject):
    def __init__(self, parent):
        super().__init__(parent=parent)
        self._project_dir = None

        self.widgets[0] = self.Website_Fields(parent=self)

        side_tabs = self.widgets[1]
        side_tabs.pages['Preview'] = self.Website_Preview(parent=side_tabs)
        side_tabs.pages['Context'] = side_tabs.pages.pop('Context')
        tabs = self.widgets[2]
        tabs.pages['Output'] = self.Website_Output(parent=tabs)

    def load_config(self, json_config=None):
        super().load_config(json_config)
        working_dir = self.get_config().get('working_dir', '')
        if self._project_dir is not None and working_dir != self._project_dir:
            runner.stop()
        self._project_dir = working_dir
        self.widgets[0].refresh_run_icon()

    class Website_Fields(GeneralProject.Project_Fields):
        """The project header, with the stack picker and the run control."""

        def __init__(self, parent):
            super().__init__(parent=parent)
            stack_names = ('Auto',) + tuple(
                stack.display_name for stack in get_stacks()
            )
            self.schema = self.schema + [
                {
                    'text': 'Stack',
                    'key': 'web_stack',
                    'type': stack_names,
                    'default': 'Auto',
                    'width': 90,
                    'row_key': 0,
                },
                {
                    'text': 'Port',
                    'key': 'web_port',
                    'type': int,
                    'default': 8080,
                    'minimum': 1,
                    'maximum': 65535,
                    'width': 70,
                    'row_key': 0,
                },
                {
                    'text': 'HTTPS',
                    'key': 'web_https',
                    'type': bool,
                    'default': False,
                    'row_key': 0,
                },
                {
                    'text': '',
                    'key': 'web_run',
                    'type': 'button',
                    'icon_path': PLAY_ICON,
                    'target': self.toggle_run,
                    'tooltip': 'Run this project',
                    'row_key': 0,
                },
            ]

        @qasync.asyncSlot()
        async def toggle_run(self):
            if runner.running():
                runner.stop()
                self.refresh_run_icon()
                return

            config = self.parent.get_config()
            path = config.get('working_dir', '')
            port = int(config.get('web_port') or 8080)
            stack = resolve_stack(config.get('web_stack', 'Auto'), path)

            if not os.path.isdir(path):
                runner.output.emit('Set a project path first')
                return
            if not stack:
                runner.output.emit('No stack matched this project')
                return

            missing = stack.requirement(path)
            if missing:
                runner.output.emit(f'[{stack.display_name}] {missing}')
                display_message(
                    message=missing,
                    title=f'{stack.display_name} unavailable',
                    icon=QMessageBox.Warning,
                )
                return

            address = preview_url(stack, config)
            internal_port = address.startswith('https:') and free_port()

            runner.output.emit(f'[{stack.display_name}] starting')
            await runner.start(
                stack.services(path, internal_port or port), path, force=True,
                proxy=internal_port and (port, internal_port),
            )
            self.refresh_run_icon()
            if runner.running():
                preview = self.parent.widgets[1].pages['Preview']
                await preview.open_when_ready(address, internal_port)

        def refresh_run_icon(self):
            button = getattr(self, 'web_run_wgt', None)
            if not button:
                return
            is_running = runner.running()
            button.setIconPixmap(path_to_pixmap(
                STOP_ICON if is_running else PLAY_ICON, diameter=25,
            ))
            button.setToolTip('Stop' if is_running else 'Run this project')

    class Website_Preview(ConfigWidget):
        """The rendered site, following whatever the stack is serving."""

        def __init__(self, parent):
            super().__init__(parent=parent)
            self.propagate_config = False
            self._loaded_dir = None
            self._awaiting = None
            self._probe = None

            self.address_bar = QLineEdit(self)
            self.address_bar.setPlaceholderText('Preview url')
            self.address_bar.returnPressed.connect(self.navigate)
            self.reload_btn = IconButton(
                parent=self,
                icon_path=':/resources/icon-refresh.png',
                target=self.navigate,
                tooltip='Reload preview',
            )
            self.web_view = QWebEngineView(self)
            self.web_view.page().certificateError.connect(
                self.accept_local_certificate
            )

            toolbar = CHBoxLayout()
            toolbar.addWidget(self.address_bar)
            toolbar.addWidget(self.reload_btn)

            self.layout = CVBoxLayout(self)
            self.layout.addLayout(toolbar)
            self.layout.addWidget(self.web_view)

            runner.output.connect(self.follow_printed_url)

        def load(self):
            config = self.parent.parent.get_config()
            working_dir = config.get('working_dir', '')
            if working_dir == self._loaded_dir:
                return
            self._loaded_dir = working_dir

            stack = resolve_stack(config.get('web_stack', 'Auto'), working_dir)
            address = (
                preview_url(stack, config) if stack and working_dir else ''
            )

            self.address_bar.setText(address)
            if address.startswith('file:') or self.port_open(address):
                self.navigate()
            else:
                self.web_view.setUrl(QUrl('about:blank'))

        async def open_when_ready(self, address, internal_port=None):
            """Show *address* once whatever serves it is accepting requests.

            Behind the HTTPS proxy, *internal_port* is where the server
            itself listens: wait on that, and ignore the urls it prints.
            """
            self._awaiting = address
            self._probe = internal_port and f'http://127.0.0.1:{internal_port}'
            self.address_bar.setText(address)
            for _ in range(40):
                if not self._awaiting:
                    return  # a newer run took over
                if (self._awaiting.startswith('file:')
                        or self.port_open(self._probe or self._awaiting)):
                    self.address_bar.setText(self._awaiting)
                    self._awaiting = None
                    self.navigate()
                    return
                await asyncio.sleep(0.5)
            self._awaiting = None
            runner.output.emit('Gave up waiting for the server to start')

        def follow_printed_url(self, line):
            """Track a dev server that chose a port of its own."""
            if not self._awaiting or self._probe:
                return
            match = re.search(
                r'https?://(?:localhost|127\.0\.0\.1):(\d+)[^\s)\]\'"<>]*',
                line,
            )
            awaited_port = QUrl.fromUserInput(self._awaiting).port()
            if match and int(match.group(1)) != awaited_port:
                self._awaiting = match.group(0).rstrip('.,')

        def navigate(self):
            address = self.address_bar.text().strip()
            if not address:
                self.web_view.setUrl(QUrl('about:blank'))
                return

            url = QUrl.fromUserInput(address)
            if url == self.web_view.url():
                self.web_view.reload()
            else:
                self.web_view.setUrl(url)

        @staticmethod
        def accept_local_certificate(error):
            """Trust the proxy's self-signed certificate on local hosts."""
            if error.url().host() in LOCAL_HOSTS:
                error.acceptCertificate()

        @staticmethod
        def port_open(address):
            url = QUrl.fromUserInput(address)
            if url.scheme() not in ('http', 'https'):
                return False
            with socket.socket() as sock:
                sock.settimeout(0.2)
                host = url.host() or '127.0.0.1'
                return sock.connect_ex((host, url.port(80))) == 0

    class Website_Output(ConfigWidget):
        """What the running services are printing."""

        def __init__(self, parent):
            super().__init__(parent=parent)
            self.propagate_config = False

            self.view = QPlainTextEdit(self)
            self.view.setReadOnly(True)
            self.view.setMaximumBlockCount(1000)

            self.layout = CVBoxLayout(self)
            self.layout.addWidget(self.view)

            runner.output.connect(self.view.appendPlainText)
