"""Move files between the local machine and a deploy target's server.

Files travel as uncompressed tar archives in both directions, so the deploy
logic builds and unpacks one archive whatever the protocol. File modes are
taken from the archive.
"""

import asyncio
import ftplib
import io
import os
import posixpath
import shlex
import ssl
import stat
import tarfile
import tempfile

MISSING = 3
_askpass = None


def transport(protocol, host, port=None, user=None, identity=None,
              password=None):
    if protocol == 'ssh':
        return SshTransport(host, port, user, identity, password)
    if protocol in ('ftps', 'ftp'):
        return FtpTransport(host, port, user, password, protocol == 'ftps')
    raise ValueError(f'Unknown protocol: {protocol}')


def shell_path(path):
    """Quote a remote path for sh, keeping a leading ~ expandable."""
    if path == '~' or path.startswith('~/'):
        return '"$HOME"' + shlex.quote(path[1:]) if path[1:] else '"$HOME"'
    return shlex.quote(path)


def askpass_script():
    """A script that answers ssh's password prompt from $AP_SSH_PASSWORD."""
    global _askpass
    if _askpass is None:
        fd, _askpass = tempfile.mkstemp(prefix='ap-askpass-', suffix='.sh')
        with os.fdopen(fd, 'w') as f:
            f.write('#!/bin/sh\nprintf \'%s\\n\' "$AP_SSH_PASSWORD"\n')
        os.chmod(_askpass, stat.S_IRWXU)
    return _askpass


class SshTransport:
    """Runs the system `ssh`. Needs a shell and GNU find/tar on the server."""

    def __init__(self, host, port=None, user=None, identity=None,
                 password=None):
        self.destination = f'{user}@{host}' if user else host
        self.password = password
        self.options = [
            '-C',
            '-o', 'ConnectTimeout=15',
            '-o', 'StrictHostKeyChecking=accept-new',
        ]
        if port:
            self.options += ['-p', str(port)]
        if identity:
            self.options += ['-i', os.path.expanduser(identity)]
        if not password:
            self.options += ['-o', 'BatchMode=yes']

    async def _spawn(self, command, **kwargs):
        env = os.environ.copy()
        if self.password:
            env.update(
                SSH_ASKPASS=askpass_script(),
                SSH_ASKPASS_REQUIRE='force',
                AP_SSH_PASSWORD=self.password,
            )
        return await asyncio.create_subprocess_exec(
            'ssh', *self.options, self.destination, command, env=env,
            **kwargs,
        )

    async def _ssh(self, command, data=None, stdin=None,
                   stdout=asyncio.subprocess.PIPE, ok_codes=(0,)):
        """Run `command` on the server, return (exit code, stdout)."""
        if data is not None:
            stdin = asyncio.subprocess.PIPE
        process = await self._spawn(
            command,
            stdin=stdin or asyncio.subprocess.DEVNULL,
            stdout=stdout,
            stderr=asyncio.subprocess.PIPE,
        )
        out, err = await process.communicate(data)
        if process.returncode not in ok_codes:
            raise RuntimeError(
                err.decode(errors='replace').strip()
                or f'ssh exited with code {process.returncode}')
        return process.returncode, out

    async def list(self, remote_dir):
        """Map each file under `remote_dir` to its size. {} if missing."""
        d = shell_path(remote_dir)
        _, out = await self._ssh(
            f'[ -d {d} ] || exit 0; cd {d} && '
            'find . -type f -printf "%P\\t%s\\0"')
        files = {}
        for entry in out.decode(errors='surrogateescape').split('\0'):
            if entry:
                rel, size = entry.rsplit('\t', 1)
                files[rel] = int(size)
        return files

    async def upload(self, remote_dir, archive):
        d = shell_path(remote_dir)
        with open(archive, 'rb') as f:
            await self._ssh(f'mkdir -p {d} && tar -xpf - -C {d}', stdin=f)

    async def download(self, remote_dir, rels, archive):
        d = shell_path(remote_dir)
        names = '\0'.join(rels).encode(errors='surrogateescape')
        with open(archive, 'wb') as f:
            await self._ssh(
                f'cd {d} && tar --null -T - -cf -', data=names, stdout=f)

    async def delete(self, remote_dir, rels):
        if not rels:
            return
        d = shell_path(remote_dir)
        names = '\0'.join(rels).encode(errors='surrogateescape')
        await self._ssh(f'cd {d} && xargs -0 rm -f --', data=names)

    async def read(self, path):
        """The file's bytes, or None if it doesn't exist."""
        p = shell_path(path)
        code, out = await self._ssh(
            f'[ -f {p} ] || exit {MISSING}; cat -- {p}',
            ok_codes=(0, MISSING))
        return out if code == 0 else None

    async def write(self, path, data):
        p = shell_path(path)
        await self._ssh(
            f'mkdir -p -- "$(dirname -- {p})" && cat > {p}', data=data)

    async def run(self, command, on_output=None):
        """Run a shell command on the server, passing each output line to
        `on_output`. Raises with the output if it fails."""
        process = await self._spawn(
            command,
            stdin=asyncio.subprocess.DEVNULL,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.STDOUT,
        )
        lines = []
        async for raw in process.stdout:
            line = raw.decode(errors='replace').rstrip('\n')
            lines.append(line)
            if on_output:
                on_output(line)
        if await process.wait() != 0:
            raise RuntimeError('\n'.join(lines[-20:]) or
                               f'Command exited with code {process.returncode}')
        return '\n'.join(lines)


def ftp_path(path):
    """FTP has no ~, paths starting with it are relative to the login
    folder."""
    if path == '~':
        return '.'
    return path[2:] if path.startswith('~/') else path


def parse_list_line(line):
    """(name, is_dir, size) from a Unix-style LIST line, or None."""
    parts = line.split(None, 8)
    if len(parts) < 9 or parts[0][0] not in 'd-' or parts[8] in ('.', '..'):
        return None
    return parts[8], parts[0][0] == 'd', int(parts[4])


class FtpTransport:
    """ftplib in a thread, FTPS unless `tls` is False."""

    def __init__(self, host, port=None, user=None, password=None, tls=True):
        self.host = host
        self.port = port or 21
        self.user = user or 'anonymous'
        self.password = password or ''
        self.tls = tls
        self.use_mlsd = True

    def _connect(self):
        ftp = (ftplib.FTP_TLS(context=ssl.create_default_context())
               if self.tls else ftplib.FTP())
        ftp.connect(self.host, self.port, timeout=15)
        ftp.login(self.user, self.password)
        if self.tls:
            ftp.prot_p()
        return ftp

    def _entries(self, ftp, path):
        if self.use_mlsd:
            try:
                return [
                    (name, facts['type'] == 'dir', int(facts.get('size', 0)))
                    for name, facts in ftp.mlsd(path, facts=['type', 'size'])
                    if facts.get('type') in ('dir', 'file')
                ]
            except ftplib.error_perm as e:
                if not str(e).startswith(('500', '501', '502')):
                    raise
                self.use_mlsd = False
        lines = []
        ftp.cwd(path)
        ftp.retrlines('LIST -a', lines.append)
        return [entry for line in lines if (entry := parse_list_line(line))]

    def _list(self, remote_dir):
        with self._connect() as ftp:
            try:
                ftp.cwd(ftp_path(remote_dir))
            except ftplib.error_perm:
                return {}
            base = ftp.pwd()
            files = {}
            folders = ['']
            while folders:
                rel = folders.pop()
                for name, is_dir, size in self._entries(
                        ftp, posixpath.join(base, rel)):
                    path = posixpath.join(rel, name)
                    if is_dir:
                        folders.append(path)
                    else:
                        files[path] = size
            return files

    @staticmethod
    def _makedirs(ftp, path, made):
        parts = path.split('/')
        for i in range(1, len(parts) + 1):
            folder = '/'.join(parts[:i])
            if not folder or folder in made:
                continue
            try:
                ftp.mkd(folder)
            except ftplib.error_perm:
                pass
            made.add(folder)

    def _enter(self, ftp, remote_dir, create=False):
        """cd into `remote_dir` and return its absolute path."""
        path = ftp_path(remote_dir)
        if create:
            self._makedirs(ftp, path, set())
        ftp.cwd(path)
        return ftp.pwd()

    def _upload(self, remote_dir, archive):
        with self._connect() as ftp, tarfile.open(archive) as tar:
            base = self._enter(ftp, remote_dir, create=True)
            made = set()
            for member in tar:
                path = posixpath.join(base, posixpath.normpath(member.name))
                if member.isdir():
                    self._makedirs(ftp, path, made)
                elif member.isfile():
                    self._makedirs(ftp, posixpath.dirname(path), made)
                    ftp.storbinary(f'STOR {path}', tar.extractfile(member))

    def _download(self, remote_dir, rels, archive):
        with self._connect() as ftp, tarfile.open(archive, 'w') as tar:
            base = self._enter(ftp, remote_dir)
            for rel in rels:
                buffer = io.BytesIO()
                ftp.retrbinary(
                    f'RETR {posixpath.join(base, rel)}', buffer.write)
                info = tarfile.TarInfo(rel)
                info.size = buffer.tell()
                buffer.seek(0)
                tar.addfile(info, buffer)

    def _delete(self, remote_dir, rels):
        with self._connect() as ftp:
            base = self._enter(ftp, remote_dir)
            for rel in rels:
                ftp.delete(posixpath.join(base, rel))

    def _read(self, path):
        buffer = io.BytesIO()
        with self._connect() as ftp:
            try:
                ftp.retrbinary(f'RETR {ftp_path(path)}', buffer.write)
            except ftplib.error_perm as e:
                if str(e).startswith('550'):
                    return None
                raise
        return buffer.getvalue()

    def _write(self, path, data):
        path = ftp_path(path)
        with self._connect() as ftp:
            self._makedirs(ftp, posixpath.dirname(path), set())
            ftp.storbinary(f'STOR {path}', io.BytesIO(data))

    async def list(self, remote_dir):
        return await asyncio.to_thread(self._list, remote_dir)

    async def upload(self, remote_dir, archive):
        await asyncio.to_thread(self._upload, remote_dir, archive)

    async def download(self, remote_dir, rels, archive):
        await asyncio.to_thread(self._download, remote_dir, rels, archive)

    async def delete(self, remote_dir, rels):
        await asyncio.to_thread(self._delete, remote_dir, rels)

    async def read(self, path):
        return await asyncio.to_thread(self._read, path)

    async def write(self, path, data):
        await asyncio.to_thread(self._write, path, data)

    async def run(self, command, on_output=None):
        raise RuntimeError('FTP targets cannot run commands')
