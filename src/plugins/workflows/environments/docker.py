"""Docker Environment Module.

Provides a Docker-based code execution environment using the Docker SDK.
Manages a long-running container per environment instance and executes
code inside it via ``docker exec``.
"""

import logging

import docker
from docker.errors import NotFound, ImageNotFound, APIError

logger = logging.getLogger(__name__)

LANG_INTERPRETERS = {
    'python': ['python3', '-c'],
    'javascript': ['node', '-e'],
    'bash': ['bash', '-c'],
    'sh': ['sh', '-c'],
    'ruby': ['ruby', '-e'],
    'perl': ['perl', '-e'],
}


class Docker:
    """Docker-based code execution environment.

    Maintains a long-running container named ``agentpilot_env_{id}``
    and executes code inside it via ``container.exec_run()``.

    Parameters
    ----------
    config : dict
        Environment configuration from the database.
    """

    def __init__(self, config):
        self.config = config
        self._client = None
        self._container = None

    @property
    def client(self):
        """Lazy-initialised Docker client."""
        if self._client is None:
            self._client = docker.from_env()
        return self._client

    def _container_name(self):
        """Deterministic container name from config."""
        env_id = self.config.get('_env_id', 'default')
        return f"agentpilot_env_{env_id}"

    # ------------------------------------------------------------------
    # Image management
    # ------------------------------------------------------------------

    def _get_or_pull_image(self):
        """Get the Docker image, pulling or building as needed.

        Returns
        -------
        docker.models.images.Image
        """
        source = self.config.get('docker.image_source', 'pull')

        if source == 'dockerfile':
            path = self.config.get('docker.dockerfile_path', '')
            if not path:
                raise ValueError(
                    "Dockerfile path not configured for this environment."
                )
            logger.info("Building image from Dockerfile at %s", path)
            image, _ = self.client.images.build(
                path=path, tag=self._container_name(), rm=True
            )
            return image

        # Default: pull
        image_name = self.config.get(
            'docker.image_name', 'python:3.12-slim'
        )
        try:
            return self.client.images.get(image_name)
        except ImageNotFound:
            logger.info("Pulling image %s ...", image_name)
            return self.client.images.pull(image_name)

    # ------------------------------------------------------------------
    # Container lifecycle
    # ------------------------------------------------------------------

    def _ensure_container(self):
        """Start or reconnect to the long-running container."""
        if self._container is not None:
            try:
                self._container.reload()
                if self._container.status == 'running':
                    return
                if self._container.status in ('created', 'exited'):
                    self._container.start()
                    return
            except NotFound:
                self._container = None

        name = self._container_name()

        # Try to find an existing container by name
        try:
            self._container = self.client.containers.get(name)
            if self._container.status != 'running':
                self._container.start()
            return
        except NotFound:
            pass

        # Create a new container
        image = self._get_or_pull_image()
        kwargs = self._build_container_kwargs(image, name)
        self._container = self.client.containers.run(**kwargs)

    def _build_container_kwargs(self, image, name):
        """Build kwargs dict for ``client.containers.run()``.

        Parameters
        ----------
        image : docker.models.images.Image or str
        name : str

        Returns
        -------
        dict
        """
        ports = {}
        for mapping in self.config.get('docker.ports.data', []):
            host_port = mapping.get('host_port', '')
            container_port = mapping.get('container_port', '')
            if host_port and container_port:
                ports[f"{container_port}/tcp"] = int(host_port)

        volumes = {}
        for vol in self.config.get('docker.volumes.data', []):
            host_path = vol.get('host_path', '')
            container_path = vol.get('container_path', '')
            mode = vol.get('mode', 'rw')
            if host_path and container_path:
                volumes[host_path] = {
                    'bind': container_path, 'mode': mode
                }

        environment = {}
        for ev in self.config.get('docker.env_vars.data', []):
            var_name = ev.get('variable', '')
            var_value = ev.get('value', '')
            if var_name:
                environment[var_name] = var_value

        working_dir = self.config.get('docker.working_dir', '/app')
        network_mode = self.config.get('docker.network_mode', 'bridge')

        return {
            'image': image,
            'name': name,
            'detach': True,
            'tty': True,
            'stdin_open': True,
            'ports': ports or None,
            'volumes': volumes or None,
            'environment': environment or None,
            'working_dir': working_dir,
            'network_mode': network_mode,
        }

    def start(self):
        """Explicitly start the container (called from UI)."""
        self._ensure_container()

    def stop(self):
        """Stop the container (called from UI)."""
        if self._container is not None:
            try:
                self._container.stop(timeout=10)
            except Exception as e:
                logger.error("Error stopping container: %s", e)

    def is_running(self):
        """Check if the container is currently running.

        Returns
        -------
        bool
        """
        if self._container is None:
            name = self._container_name()
            try:
                self._container = self.client.containers.get(name)
            except (NotFound, APIError):
                return False

        try:
            self._container.reload()
            return self._container.status == 'running'
        except (NotFound, APIError):
            self._container = None
            return False

    def get_logs(self, tail=100):
        """Retrieve recent container logs.

        Parameters
        ----------
        tail : int
            Number of log lines to retrieve.

        Returns
        -------
        str
        """
        if self._container is None:
            return ''
        try:
            return self._container.logs(tail=tail).decode('utf-8')
        except Exception:
            return ''

    # ------------------------------------------------------------------
    # Code execution
    # ------------------------------------------------------------------

    def run_code(self, lang, code, venv_path=None):
        """Execute code inside the running container.

        Parameters
        ----------
        lang : str
            Programming language (e.g. 'Python', 'JavaScript').
        code : str
            Source code to execute.
        venv_path : str, optional
            Ignored for Docker environments.

        Returns
        -------
        str
            Combined stdout and stderr from the execution.
        """
        self._ensure_container()

        interpreter = LANG_INTERPRETERS.get(lang.lower())
        if interpreter is None:
            # Fallback: try using the language name as the command
            cmd = [lang.lower(), '-c', code]
        else:
            cmd = interpreter + [code]

        exit_code, output = self._container.exec_run(
            cmd, demux=False, workdir=self.config.get(
                'docker.working_dir', '/app'
            )
        )
        return output.decode('utf-8') if output else ''

    # ------------------------------------------------------------------
    # Config / lifecycle
    # ------------------------------------------------------------------

    def update(self, config):
        """Update config. If image changed, the container will be
        recreated on next ``run_code()`` or ``start()`` call."""
        old_image = self.config.get('docker.image_name')
        self.config = config
        new_image = config.get('docker.image_name')
        if old_image != new_image:
            self.cleanup()

    def set_env_vars(self):
        """No-op — env vars are passed at container creation."""

    def cleanup(self):
        """Remove the container entirely."""
        if self._container is not None:
            try:
                self._container.stop(timeout=5)
            except Exception:
                pass
            try:
                self._container.remove(force=True)
            except Exception:
                pass
            self._container = None
