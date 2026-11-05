import os
import shlex
import signal
import subprocess
import sys
import time

from utils.filesystem import get_application_path

_restarting = False


def _app_path():
    """The file that identifies a running copy of this app in a process list."""
    path = sys.executable if getattr(sys, 'frozen', False) else sys.argv[0]
    return os.path.normcase(os.path.abspath(path))


def _mac_cwd(pid):
    out = subprocess.run(
        ['lsof', '-a', '-d', 'cwd', '-p', str(pid), '-Fn'],
        capture_output=True, text=True,
    ).stdout
    return next((line[1:] for line in out.splitlines() if line.startswith('n')), None)


def _processes():
    """Yield (pid, cwd, args) for each process, cwd being None if unknown."""
    if sys.platform == 'win32':
        out = subprocess.run(
            ['powershell', '-NoProfile', '-Command',
             'Get-CimInstance Win32_Process | ForEach-Object '
             '{ "$($_.ProcessId)`t$($_.ExecutablePath)`t$($_.CommandLine)" }'],
            capture_output=True, text=True,
            creationflags=subprocess.CREATE_NO_WINDOW,
        ).stdout
        for line in out.splitlines():
            pid, exe, command = (line.split('\t') + ['', ''])[:3]
            if pid.isdigit():
                args = [a.strip('"') for a in shlex.split(command, posix=False)]
                yield int(pid), None, [exe, *args]

    elif os.path.isdir('/proc'):
        for entry in os.listdir('/proc'):
            if not entry.isdigit():
                continue
            try:
                with open(f'/proc/{entry}/cmdline', 'rb') as f:
                    args = f.read().decode(errors='replace').split('\0')[:-1]
                cwd = os.readlink(f'/proc/{entry}/cwd')
            except OSError:
                continue
            yield int(entry), cwd, args

    else:
        name = os.path.basename(_app_path())
        out = subprocess.run(
            ['ps', '-axo', 'pid=,command='], capture_output=True, text=True,
        ).stdout
        for line in out.splitlines():
            pid, _, command = line.strip().partition(' ')
            if name in command:
                yield int(pid), _mac_cwd(pid), command.split()


def find_other_instances():
    """PIDs of other running copies of this app.

    An instance being replaced by `restart_app` is excluded, as it may still
    be shutting down when its replacement starts.
    """
    target = _app_path()
    ignored = {os.getpid(), int(os.environ.get('AP_REPLACES_PID', 0))}
    pids = []
    for pid, cwd, args in _processes():
        if pid in ignored:
            continue
        for arg in args:
            if cwd is None and not os.path.isabs(arg):
                continue
            path = os.path.normcase(os.path.abspath(os.path.join(cwd or '', arg)))
            if path == target:
                pids.append(pid)
                break
    return pids


def kill_other_instances(timeout=5.0):
    """Kill other running copies of this app. False if any survive.

    Stopped processes ignore SIGTERM, so any left after the timeout get
    SIGKILL.
    """
    for sig in (signal.SIGTERM, getattr(signal, 'SIGKILL', signal.SIGTERM)):
        for pid in find_other_instances():
            try:
                os.kill(pid, sig)
            except ProcessLookupError:
                pass

        deadline = time.time() + timeout
        while find_other_instances():
            if time.time() > deadline:
                break
            time.sleep(0.1)
        else:
            return True
    return False


def _is_debugging():
    """Whether this process was started by a debugger (VS Code / debugpy, pydevd)."""
    return 'DEBUGPY_RUNNING' in os.environ or 'debugpy' in sys.modules or 'pydevd' in sys.modules


def get_relaunch_command():
    """Build the command that starts a fresh copy of this app.

    Covers the three ways the app can be running: from source (either
    ``python src/__main__.py`` or ``python -m src``), from a onefile binary
    (Linux/Windows), and from a macOS .app bundle.
    """
    if getattr(sys, 'frozen', False):
        if sys.platform == 'darwin':
            # sys.executable is <bundle>.app/Contents/MacOS/AgentPilot. Going
            # through `open` keeps the new instance a proper bundled app
            # (dock icon, LaunchServices registration) instead of a bare process.
            bundle = os.path.abspath(os.path.join(os.path.dirname(sys.executable), os.pardir, os.pardir))
            if bundle.endswith('.app'):
                return ['open', '-n', bundle, '--args', *sys.argv[1:]]

        # Frozen: the executable *is* the app, so argv[0] would be a duplicate.
        return [sys.executable, *sys.argv[1:]]

    if _is_debugging():
        # Under a debugger, orig_argv is the debugpy launcher's command line,
        # and its adapter port dies with this process, so replaying it would
        # exit immediately. sys.argv is the plain target argv, so the app
        # restarts normally, without the debugger attached.
        return [sys.executable, *sys.argv]

    # Source: orig_argv preserves how the interpreter was invoked, including
    # any -X / -m flags, which sys.argv alone would lose.
    return [sys.executable, *sys.orig_argv[1:]]


def get_relaunch_env():
    """Copy the environment, undoing what the PyInstaller bootloader changed.

    The bootloader points the dynamic loader at the bundle's libraries and
    stashes any pre-existing value in ``<VAR>_ORIG``. Passing our own values
    on would make the child load this instance's (about to be deleted)
    extraction dir, so restore the originals or drop the vars entirely.
    """
    env = os.environ.copy()

    for key in ('LD_LIBRARY_PATH', 'DYLD_LIBRARY_PATH', 'DYLD_FRAMEWORK_PATH', 'SSL_CERT_FILE'):
        original = env.pop(f'{key}_ORIG', None)
        if original is not None:
            env[key] = original
        elif getattr(sys, 'frozen', False):
            env.pop(key, None)

    env.pop('_MEIPASS2', None)

    if _is_debugging():
        # The restarted app isn't under the debugger, so don't let it inherit
        # the debug session's vars (subprocess auto-attach points at an
        # endpoint that dies with this process).
        for key in [k for k in env if k.startswith(('DEBUGPY_', 'PYDEVD_'))]:
            del env[key]

    return env


def _spawn():
    """Launch the replacement instance, detached from this process."""
    try:
        # debugpy's auto-attach monkey-patches subprocess so children re-launch
        # under pydevd, pointed at an adapter endpoint that dies with this
        # process. This opts the spawn below out of that rewriting.
        from _pydev_bundle.pydev_monkey import skip_subprocess_arg_patch as unpatched_spawn
    except ImportError:
        from contextlib import nullcontext as unpatched_spawn

    kwargs = {}
    if sys.platform == 'win32':
        # Detach from this process's console so the child outlives it. Windows
        # builds are console apps, so give it a console of its own when there's
        # one to inherit, otherwise its output would go nowhere.
        has_console = sys.stdout is not None and sys.stdout.isatty()
        kwargs['creationflags'] = subprocess.CREATE_NEW_PROCESS_GROUP | (
            subprocess.CREATE_NEW_CONSOLE if has_console else subprocess.DETACHED_PROCESS
        )
    else:
        kwargs['start_new_session'] = True

    env = get_relaunch_env()
    env['AP_REPLACES_PID'] = str(os.getpid())

    with unpatched_spawn():
        subprocess.Popen(
            get_relaunch_command(),
            cwd=get_application_path(),
            env=env,
            **kwargs
        )


def restart_app():
    """Quit the app and start a fresh instance in its place.

    The spawn is done by `launch()` once the daemons have stopped, so the new
    instance never contends with this one over the database or the files and
    ports the daemons hold open.
    """
    global _restarting
    if _restarting:
        return
    _restarting = True

    from PySide6.QtCore import QTimer
    from PySide6.QtWidgets import QApplication

    QTimer.singleShot(0, QApplication.quit)
