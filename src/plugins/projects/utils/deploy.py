"""Push a repo's committed files to a web server and pull server files
into its working tree. See DEPLOY_SPEC.md."""

import asyncio
import fnmatch
import hashlib
import json
import os
import posixpath
import tarfile
import tempfile
from dataclasses import dataclass, field

import keyring
from keyring.errors import KeyringError, PasswordDeleteError

from plugins.projects.utils import vcs
from plugins.projects.utils.deploy_transport import transport

KEYRING_SERVICE = 'agentpilot'
MARKER = '.deploy-rev'
LIST_KEYS = ('map', 'include', 'post')
MODE_KEYS = ('dir-mode', 'file-mode')


@dataclass
class Target:
    name: str
    protocol: str = 'ssh'
    host: str = ''
    port: int = None
    user: str = ''
    identity: str = ''
    maps: list = field(default_factory=list)
    include: list = field(default_factory=list)
    dir_mode: int = None
    file_mode: int = None
    marker: str = ''
    post: list = field(default_factory=list)

    @property
    def marker_path(self):
        return posixpath.join(self.marker or self.maps[0][1], MARKER)

    @property
    def keyring_user(self):
        return f'deploy:{self.protocol}:{self.user}@{self.host}'


@dataclass
class Item:
    pair: int
    path: str
    action: str
    label: str
    ticked: bool
    digest: str = ''
    blocked: bool = False


@dataclass
class Plan:
    target: Target
    commit: str
    first_sync: bool
    items: list
    marker: dict
    dirty: bool = False


async def targets(root):
    """The deploy targets in the repo's .git/config, by name."""
    output = await vcs.git(
        root, 'config', '--local', '--null', '--get-regexp', r'^deploy\.',
        ok_codes=(0, 1))
    found = {}
    for entry in filter(None, output.split('\0')):
        key, _, value = entry.partition('\n')
        name, key = key[len('deploy.'):].rsplit('.', 1)
        target = found.setdefault(name, Target(name))
        if key == 'map':
            local, _, remote = value.partition(':')
            target.maps.append((local.strip('/') or '.', remote))
        elif key in LIST_KEYS:
            getattr(target, key).append(value)
        elif key in MODE_KEYS:
            setattr(target, key.replace('-', '_'), int(value, 8))
        elif key == 'port':
            target.port = int(value)
        elif hasattr(target, key):
            setattr(target, key, value)
    return found


async def save_target(root, target, old_name=None):
    old_name = old_name or target.name
    if old_name in await targets(root):
        await vcs.git(root, 'config', '--remove-section', f'deploy.{old_name}')
    if old_name != target.name:
        commit = await deployed_commit(root, old_name)
        if commit:
            await vcs.git(
                root, 'update-ref', f'refs/deploy/{target.name}', commit)
            await vcs.git(root, 'update-ref', '-d', f'refs/deploy/{old_name}')
    values = [
        ('protocol', target.protocol),
        ('host', target.host),
        ('port', target.port),
        ('user', target.user),
        ('identity', target.identity),
        *(('map', f'{local}:{remote}') for local, remote in target.maps),
        *(('include', pattern) for pattern in target.include),
        ('dir-mode', target.dir_mode and f'{target.dir_mode:o}'),
        ('file-mode', target.file_mode and f'{target.file_mode:o}'),
        ('marker', target.marker),
        *(('post', command) for command in target.post),
    ]
    for key, value in values:
        if value:
            await vcs.git(
                root, 'config', '--local', '--add',
                f'deploy.{target.name}.{key}', str(value))


async def delete_target(root, name):
    await vcs.git(root, 'config', '--remove-section', f'deploy.{name}')
    if await deployed_commit(root, name):
        await vcs.git(root, 'update-ref', '-d', f'refs/deploy/{name}')


async def deployed_commit(root, name):
    """The commit last deployed to target `name` from this repo."""
    output = await vcs.git(
        root, 'rev-parse', '--verify', '-q', f'refs/deploy/{name}',
        ok_codes=(0, 1))
    return output.strip() or None


async def get_password(target):
    try:
        return await asyncio.to_thread(
            keyring.get_password, KEYRING_SERVICE, target.keyring_user)
    except KeyringError:
        return None


async def set_password(target, password):
    if password:
        await asyncio.to_thread(
            keyring.set_password, KEYRING_SERVICE, target.keyring_user,
            password)
        return
    try:
        await asyncio.to_thread(
            keyring.delete_password, KEYRING_SERVICE, target.keyring_user)
    except PasswordDeleteError:
        pass


async def connect(target):
    return transport(
        target.protocol, target.host, target.port, target.user,
        target.identity, await get_password(target))


def repo_path(local, path):
    return path if local == '.' else f'{local}/{path}'


def pair_path(local, path):
    return path if local == '.' else path[len(local) + 1:]


async def tree_sizes(root, commit, local):
    """Map each file under `local` in `commit` to its size, relative to
    `local`."""
    output = await vcs.git(root, 'ls-tree', '-r', '-l', '-z', commit, '--', local)
    sizes = {}
    for entry in filter(None, output.split('\0')):
        meta, path = entry.split('\t', 1)
        mode, kind, _, size = meta.split()
        if kind == 'blob' and mode != '120000':
            sizes[pair_path(local, path)] = int(size)
    return sizes


async def changed(root, old, new, local):
    """(status letter, path relative to `local`) between two commits."""
    output = await vcs.git(
        root, 'diff', '--name-status', '--no-renames', '-z', old, new,
        '--', local)
    parts = output.split('\0')
    return [
        (status, pair_path(local, path))
        for status, path in zip(parts[::2], parts[1::2]) if path
    ]


async def ignored(root, paths):
    """The subset of repo-relative `paths` that git ignores."""
    if not paths:
        return set()
    output = await vcs.git(
        root, 'check-ignore', '-z', '--stdin', ok_codes=(0, 1),
        input='\0'.join(paths))
    return set(filter(None, output.split('\0')))


def file_digest(path):
    with open(path, 'rb') as f:
        return hashlib.file_digest(f, 'sha1').hexdigest()


async def included_files(root, target, local):
    """Map each gitignored file under `local` that matches an include
    pattern, relative to `local`, to its (sha1, size)."""
    if not target.include:
        return {}
    output = await vcs.git(
        root, 'ls-files', '-z', '--others', '--ignored', '--exclude-standard',
        '--', local)
    files = {}
    for path in filter(None, output.split('\0')):
        if any(fnmatch.fnmatch(path, p) for p in target.include):
            full = os.path.join(root, path)
            files[pair_path(local, path)] = (
                await asyncio.to_thread(file_digest, full),
                os.path.getsize(full),
            )
    return files


async def read_marker(root, connection, target):
    data = await connection.read(target.marker_path)
    marker = json.loads(data) if data else {}
    commit = marker.get('commit')
    if commit:
        try:
            await vcs.git(root, 'cat-file', '-e', f'{commit}^{{commit}}')
        except RuntimeError:
            raise RuntimeError(
                f'The server is at commit {commit[:7]}, which this repo '
                'does not have. Fetch or pull it first.')
    return marker


def is_marker(target, remote, path):
    return posixpath.join(remote, path) == target.marker_path


async def push_plan(root, target):
    """What a push of HEAD to `target` would upload and delete."""
    if not target.maps:
        raise RuntimeError(f'Target "{target.name}" has no folders to deploy')
    if not await vcs.has_commits(root):
        raise RuntimeError('Nothing to deploy yet. Commit your changes first.')
    commit = (await vcs.git(root, 'rev-parse', 'HEAD')).strip()
    connection = await connect(target)
    marker = await read_marker(root, connection, target)
    baseline = marker.get('commit')
    deployed_includes = marker.get('includes', {})
    items = []
    for i, (local, remote) in enumerate(target.maps):
        listing = await connection.list(remote)
        new_sizes = await tree_sizes(root, commit, local)
        if baseline:
            old_sizes = await tree_sizes(root, baseline, local)
            diff = await changed(root, baseline, commit, local)
            for status, path in diff:
                drifted = (
                    path in old_sizes and listing.get(path) != old_sizes[path])
                if status == 'D':
                    if path in listing:
                        items.append(Item(
                            i, path, 'delete',
                            'changed on server' if drifted else 'deleted',
                            not drifted))
                    continue
                label = {'A': 'added'}.get(status, 'modified')
                items.append(Item(
                    i, path, 'upload',
                    'changed on server' if drifted else label, not drifted))
            diffed = {path for _, path in diff}
            for path, size in old_sizes.items():
                if (path not in diffed and path in new_sizes
                        and listing.get(path) != size):
                    items.append(Item(
                        i, path, 'upload',
                        'changed on server' if path in listing
                        else 'missing on server', False))
        else:
            for path, size in new_sizes.items():
                if listing.get(path) != size:
                    items.append(Item(
                        i, path, 'upload',
                        'missing on server' if path not in listing
                        else 'differs', True))
        for path, (digest, size) in (
                await included_files(root, target, local)).items():
            if baseline:
                unchanged = deployed_includes.get(
                    repo_path(local, path)) == digest
            else:
                unchanged = listing.get(path) == size
            if not unchanged:
                items.append(Item(
                    i, path, 'upload', 'included', True, digest=digest))
    return Plan(
        target, commit, not baseline, items, marker,
        dirty=bool(await vcs.status(root)))


async def pull_plan(root, target):
    """What a pull from `target` would download and delete locally."""
    if not target.maps:
        raise RuntimeError(f'Target "{target.name}" has no folders to deploy')
    connection = await connect(target)
    marker = await read_marker(root, connection, target)
    deployed = marker.get('commit')
    baseline = deployed
    if not baseline and await vcs.has_commits(root):
        baseline = (await vcs.git(root, 'rev-parse', 'HEAD')).strip()
    entries = await vcs.status(root)
    items = []
    for i, (local, remote) in enumerate(target.maps):
        listing = {
            path: size for path, size in (await connection.list(remote)).items()
            if not is_marker(target, remote, path)
        }
        base_sizes = (
            await tree_sizes(root, baseline, local) if baseline else {})
        skipped = await ignored(root, [
            repo_path(local, path) for path in listing
            if path not in base_sizes])

        def item(path, action, label, ticked):
            blocked = vcs.state(
                entries, repo_path(local, path), False) is not None
            return Item(i, path, action, label, ticked, blocked=blocked)

        for path, size in listing.items():
            if path in base_sizes:
                if size != base_sizes[path]:
                    items.append(
                        item(path, 'download', 'changed on server', True))
            elif repo_path(local, path) not in skipped:
                items.append(item(
                    path, 'download', 'new on server', not deployed))
        for path in base_sizes.keys() - listing.keys():
            items.append(
                item(path, 'delete_local', 'missing on server', False))
    return Plan(target, baseline, not deployed, items, marker)


def write_archive(raw, out, wanted, included, dir_mode, file_mode):
    """Write `out` from the `wanted` members of git archive `raw` plus the
    `included` files ({name: path on disk}), with deploy file modes."""

    def mode(info):
        if file_mode:
            return file_mode
        return 0o755 if info.mode & 0o111 else 0o644

    with tarfile.open(out, 'w') as dst:
        if dir_mode:
            folders = {
                posixpath.dirname(name)
                for name in (*wanted, *included)
            }
            for folder in sorted(
                    {'/'.join(f.split('/')[:i + 1])
                     for f in folders if f
                     for i in range(f.count('/') + 1)}):
                info = tarfile.TarInfo(folder)
                info.type = tarfile.DIRTYPE
                info.mode = dir_mode
                dst.addfile(info)
        if raw:
            with tarfile.open(raw) as src:
                for info in src:
                    if info.name in wanted and not info.isdir():
                        if info.isfile():
                            info.mode = mode(info)
                        dst.addfile(
                            info,
                            src.extractfile(info) if info.isfile() else None)
        for name, path in included.items():
            info = dst.gettarinfo(path, name)
            info.mode = mode(info)
            info.uid = info.gid = 0
            info.uname = info.gname = ''
            with open(path, 'rb') as f:
                dst.addfile(info, f)


async def push(root, plan, on_output=print):
    """Upload and delete the ticked items, record the deploy, then run
    the post-deploy commands."""
    target = plan.target
    selected = [item for item in plan.items if item.ticked]
    connection = await connect(target)
    includes = dict(plan.marker.get('includes', {}))
    for i, (local, remote) in enumerate(target.maps):
        uploads = [
            item for item in selected
            if item.pair == i and item.action == 'upload']
        deletes = [
            item.path for item in selected
            if item.pair == i and item.action == 'delete']
        if uploads:
            wanted = {item.path for item in uploads if not item.digest}
            included = {
                item.path: os.path.join(root, repo_path(local, item.path))
                for item in uploads if item.digest}
            with tempfile.TemporaryDirectory() as folder:
                raw = os.path.join(folder, 'git.tar') if wanted else None
                if raw:
                    tree = plan.commit if local == '.' else (
                        f'{plan.commit}:{local}')
                    await vcs.git(
                        root, 'archive', '--format=tar', '-o', raw, tree)
                archive = os.path.join(folder, 'deploy.tar')
                await asyncio.to_thread(
                    write_archive, raw, archive, wanted, included,
                    target.dir_mode, target.file_mode)
                await connection.upload(remote, archive)
            includes.update({
                repo_path(local, item.path): item.digest
                for item in uploads if item.digest})
        if deletes:
            await connection.delete(remote, deletes)
        on_output(
            f'{local} → {remote}: {len(uploads)} uploaded, '
            f'{len(deletes)} deleted')
    marker = {'commit': plan.commit, 'includes': includes}
    await connection.write(
        target.marker_path, json.dumps(marker, indent=1).encode())
    await vcs.git(root, 'update-ref', f'refs/deploy/{target.name}', plan.commit)
    on_output(f'Deployed {plan.commit[:7]} to {target.name}')
    for number, command in enumerate(target.post, 1):
        on_output(f'$ {command}')
        try:
            await connection.run(command, on_output)
        except RuntimeError as e:
            raise RuntimeError(
                f'Deployed {plan.commit[:7]}, but post-deploy step '
                f'{number} failed:\n{e}')


async def pull(root, plan, on_output=print):
    """Download and delete the ticked items in the working tree."""
    selected = [item for item in plan.items if item.ticked]
    blocked = [item.path for item in selected if item.blocked]
    if blocked:
        raise RuntimeError(
            'Commit or discard your local changes to these files first:\n'
            + '\n'.join(blocked[:20]))
    connection = await connect(plan.target)
    for i, (local, remote) in enumerate(plan.target.maps):
        folder = os.path.join(root, local)
        downloads = {
            item.path for item in selected
            if item.pair == i and item.action == 'download'}
        deletes = [
            item.path for item in selected
            if item.pair == i and item.action == 'delete_local']
        if downloads:
            with tempfile.TemporaryDirectory() as tmp:
                archive = os.path.join(tmp, 'pull.tar')
                await connection.download(remote, sorted(downloads), archive)
                await asyncio.to_thread(
                    extract, archive, folder, downloads)
        for path in deletes:
            os.remove(os.path.join(folder, path))
        on_output(
            f'{remote} → {local}: {len(downloads)} downloaded, '
            f'{len(deletes)} deleted')


def extract(archive, folder, names):
    """Extract only the regular files in `names`, whatever else the server
    put in the archive."""
    with tarfile.open(archive) as tar:
        members = [
            info for info in tar
            if info.isfile() and info.name in names]
        tar.extractall(folder, members=members, filter='data')
