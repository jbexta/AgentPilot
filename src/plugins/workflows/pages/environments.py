from PySide6.QtWidgets import QLabel, QHBoxLayout, QWidget
from PySide6.QtGui import Qt

from gui import system
from gui.util import IconButton, find_attribute
from gui.widgets.config_db_tree import ConfigDBTree
from gui.widgets.config_joined import ConfigJoined
from gui.widgets.config_fields import ConfigFields
from gui.widgets.config_json_tree import ConfigJsonTree


class Page_Environments_Settings(ConfigDBTree):
    display_name = 'Envs'
    page_type = 'settings'

    def __init__(self, parent):
        super().__init__(
            parent=parent,
            table_name='environments',
            query="""
                SELECT
                    name,
                    id,
                    folder_id
                FROM environments
                ORDER BY pinned DESC, name COLLATE NOCASE""",
            schema=[
                {
                    'text': 'Name',
                    'key': 'name',
                    'type': str,
                    'stretch': True,
                },
                {
                    'text': 'id',
                    'key': 'id',
                    'type': int,
                    'visible': False,
                },
            ],
            add_item_options={
                'title': 'Add Environment',
                'prompt': 'Enter a name for the environment:',
            },
            del_item_options={
                'title': 'Delete Environment',
                'prompt': 'Are you sure you want to delete this environment?',
            },
            readonly=False,
            layout_type='horizontal',
            folder_key='environments',
            config_widget=self.EnvironmentConfig(parent=self),
        )

    def on_edited(self):
        system.manager.environments.load()

    class EnvironmentConfig(ConfigJoined):
        def __init__(self, parent):
            super().__init__(parent=parent, layout_type='vertical')
            self.widgets = [
                self.EnvironmentFields(parent=self),
                self.DockerSettings(parent=self),
            ]

        class EnvironmentFields(ConfigFields):
            def __init__(self, parent):
                super().__init__(
                    parent=parent,
                    schema=[
                        {
                            'text': 'Environment Type',
                            'key': 'environment_type',
                            'type': 'module',
                            'module_type': 'Environments',
                        },
                    ]
                )

            def load_config(self, json_config=None):
                super().load_config(json_config)
                env_type = self.config.get('environment_type', '')
                docker_widget = self.parent.widgets[1]
                docker_widget.setVisible(
                    env_type.lower() == 'docker'
                )

            def update_config(self):
                super().update_config()
                env_type = self.config.get('environment_type', '')
                docker_widget = self.parent.widgets[1]
                docker_widget.setVisible(
                    env_type.lower() == 'docker'
                )

        class DockerSettings(ConfigJoined):
            """Docker-specific settings, shown when type is Docker."""

            def __init__(self, parent):
                super().__init__(
                    parent=parent, layout_type='vertical'
                )
                self.widgets = [
                    self.ImageFields(parent=self),
                    self.ContainerFields(parent=self),
                    self.PortMappings(parent=self),
                    self.VolumeMounts(parent=self),
                    self.EnvVars(parent=self),
                ]
                self.hide()

            class ImageFields(ConfigFields):
                """Docker image source configuration."""

                def __init__(self, parent):
                    super().__init__(parent=parent)
                    self.add_stretch_to_end = False
                    self.conf_namespace = 'docker'
                    self.schema = [
                        {
                            'text': 'Image source',
                            'key': 'image_source',
                            'type': (
                                'Pull image',
                                'Build from Dockerfile',
                            ),
                            'default': 'Pull image',
                            'width': 180,
                        },
                        {
                            'text': 'Image name',
                            'key': 'image_name',
                            'type': str,
                            'default': 'python:3.12-slim',
                            'width': 250,
                            'tooltip': (
                                'Docker image to pull '
                                '(e.g. python:3.12-slim)'
                            ),
                            'visibility_predicate': lambda s: s.config.get(
                                'docker.image_source', 'Pull image'
                            ) == 'Pull image',
                        },
                        {
                            'text': 'Dockerfile path',
                            'key': 'dockerfile_path',
                            'type': 'file_picker',
                            'default': '',
                            'width': 250,
                            'visibility_predicate': lambda s: s.config.get(
                                'docker.image_source', 'Pull image'
                            ) != 'Pull image',
                        },
                    ]

            class ContainerFields(ConfigFields):
                """Container settings and lifecycle controls."""

                def __init__(self, parent):
                    super().__init__(parent=parent)
                    self.add_stretch_to_end = False
                    self.conf_namespace = 'docker'
                    self.schema = [
                        {
                            'text': 'Working dir',
                            'key': 'working_dir',
                            'type': str,
                            'default': '/app',
                            'width': 200,
                        },
                        {
                            'text': 'Network',
                            'key': 'network_mode',
                            'type': ('bridge', 'host', 'none'),
                            'default': 'bridge',
                            'width': 120,
                        },
                    ]

                def after_init(self):
                    controls = QWidget(self)
                    layout = QHBoxLayout(controls)
                    layout.setContentsMargins(0, 4, 0, 4)

                    self.status_label = QLabel('Stopped')
                    self.status_label.setStyleSheet(
                        'color: #888; font-weight: bold;'
                    )
                    layout.addWidget(self.status_label)
                    layout.addStretch(1)

                    self.btn_start = IconButton(
                        parent=controls,
                        icon_path=':/resources/icon-run.png',
                        tooltip='Start container',
                        size=18,
                    )
                    self.btn_start.clicked.connect(
                        self._start_container
                    )
                    layout.addWidget(self.btn_start)

                    self.btn_stop = IconButton(
                        parent=controls,
                        icon_path=':/resources/icon-stop.png',
                        tooltip='Stop container',
                        size=18,
                    )
                    self.btn_stop.clicked.connect(
                        self._stop_container
                    )
                    layout.addWidget(self.btn_stop)

                    self.layout.addWidget(controls)

                def _get_docker_env(self):
                    """Get the live Docker environment instance."""
                    if not hasattr(system.manager, 'environments'):
                        return None
                    tree = find_attribute(self, 'tree')
                    if tree is None:
                        return None
                    item_id = tree.get_selected_item_id()
                    if item_id is None:
                        return None
                    tup = system.manager.environments.get(item_id)
                    if tup is None:
                        return None
                    _, env = tup
                    return env

                def _start_container(self):
                    env = self._get_docker_env()
                    if env and hasattr(env, 'start'):
                        try:
                            env.start()
                        except Exception as e:
                            self.status_label.setText(f'Error: {e}')
                            return
                    self._refresh_status()

                def _stop_container(self):
                    env = self._get_docker_env()
                    if env and hasattr(env, 'stop'):
                        try:
                            env.stop()
                        except Exception as e:
                            self.status_label.setText(f'Error: {e}')
                            return
                    self._refresh_status()

                def _refresh_status(self):
                    if not hasattr(self, 'status_label'):
                        return
                    env = self._get_docker_env()
                    if env and hasattr(env, 'is_running'):
                        running = env.is_running()
                        if running:
                            self.status_label.setText('Running')
                            self.status_label.setStyleSheet(
                                'color: #4a4; font-weight: bold;'
                            )
                        else:
                            self.status_label.setText('Stopped')
                            self.status_label.setStyleSheet(
                                'color: #888; font-weight: bold;'
                            )
                    else:
                        self.status_label.setText('Stopped')
                        self.status_label.setStyleSheet(
                            'color: #888; font-weight: bold;'
                        )

                def load_config(self, json_config=None):
                    super().load_config(json_config)
                    self._refresh_status()

            class PortMappings(ConfigJsonTree):
                """Port mapping configuration."""

                def __init__(self, parent):
                    super().__init__(
                        parent=parent,
                        conf_namespace='docker.ports',
                        schema=[
                            {
                                'text': 'Host port',
                                'key': 'host_port',
                                'type': str,
                                'width': 100,
                                'default': '',
                            },
                            {
                                'text': 'Container port',
                                'key': 'container_port',
                                'type': str,
                                'width': 100,
                                'default': '',
                            },
                        ],
                        add_item_options={
                            'title': 'Add Port',
                            'prompt': 'NA',
                        },
                        del_item_options={
                            'title': 'Remove Port',
                            'prompt': 'Remove this port mapping?',
                        },
                    )

            class VolumeMounts(ConfigJsonTree):
                """Volume mount configuration."""

                def __init__(self, parent):
                    super().__init__(
                        parent=parent,
                        conf_namespace='docker.volumes',
                        schema=[
                            {
                                'text': 'Host path',
                                'key': 'host_path',
                                'type': str,
                                'width': 150,
                                'default': '',
                            },
                            {
                                'text': 'Container path',
                                'key': 'container_path',
                                'type': str,
                                'width': 150,
                                'default': '',
                            },
                            {
                                'text': 'Mode',
                                'key': 'mode',
                                'type': ('rw', 'ro'),
                                'width': 50,
                                'default': 'rw',
                            },
                        ],
                        add_item_options={
                            'title': 'Add Volume',
                            'prompt': 'NA',
                        },
                        del_item_options={
                            'title': 'Remove Volume',
                            'prompt': 'Remove this volume mount?',
                        },
                    )

            class EnvVars(ConfigJsonTree):
                """Container environment variables."""

                def __init__(self, parent):
                    super().__init__(
                        parent=parent,
                        conf_namespace='docker.env_vars',
                        schema=[
                            {
                                'text': 'Variable',
                                'key': 'variable',
                                'type': str,
                                'width': 150,
                                'default': '',
                            },
                            {
                                'text': 'Value',
                                'key': 'value',
                                'type': str,
                                'width': 200,
                                'stretch': True,
                                'default': '',
                            },
                        ],
                        add_item_options={
                            'title': 'Add Env Var',
                            'prompt': 'NA',
                        },
                        del_item_options={
                            'title': 'Remove Env Var',
                            'prompt': 'Remove this environment variable?',
                        },
                    )