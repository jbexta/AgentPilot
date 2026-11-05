import asyncio
import os
import shutil
from pathlib import Path

from plugins.projects.utils import github

GITHUB_HELPER = (
    '!f() { test "$1" = get || return; '
    'echo username=x-access-token; echo "password=$AP_GITHUB_TOKEN"; }; f'
)


def github_auth_args():
    """Git options that answer github.com logins with $AP_GITHUB_TOKEN."""
    return [
        '-c', 'credential.https://github.com.helper=',
        '-c', f'credential.https://github.com.helper={GITHUB_HELPER}',
    ]


async def git(cwd, *args, auth=False, ok_codes=(0,), input=None):
    """Run a git command in `cwd` and return its stdout, raise on failure.
    With `auth`, the GitHub sign-in is given to git for github.com.
    `input` is a str written to its stdin."""
    env = {**os.environ, 'GIT_TERMINAL_PROMPT': '0'}
    config = []
    token = await github.get_token() if auth else None
    if token:
        env['AP_GITHUB_TOKEN'] = token
        config = github_auth_args()
    process = await asyncio.create_subprocess_exec(
        'git', '--no-optional-locks', *config, *args,
        cwd=str(cwd),
        env=env,
        stdin=asyncio.subprocess.PIPE if input is not None else None,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    stdout, stderr = await process.communicate(
        input.encode() if input is not None else None)
    if process.returncode not in ok_codes:
        raise RuntimeError(stderr.decode(errors='replace').strip())
    return stdout.decode(errors='replace')


async def repo_root(path):
    """The root of the repo containing `path`, or None if there isn't one."""
    path = Path(path)
    if not shutil.which('git') or not any(
        (p / '.git').exists() for p in (path, *path.parents)
    ):
        return None
    return Path((await git(path, 'rev-parse', '--show-toplevel')).strip())


async def untrusted_root(path):
    """The root of the repo containing `path` if git only refuses it
    because the folder belongs to another user, else None."""
    try:
        output = await git(
            path, '-c', 'safe.directory=*', 'rev-parse', '--show-toplevel')
    except (RuntimeError, OSError):
        return None
    return Path(output.strip())


async def trust(root):
    await git(
        root, 'config', '--global', '--add',
        'safe.directory', Path(root).as_posix(),
    )


async def init(path):
    await git(path, 'init')


async def status(root):
    """Map each changed path, relative to `root`, to its porcelain XY code."""
    output = await git(root, 'status', '--porcelain=v1', '-z')
    entries = {}
    parts = iter(output.split('\0'))
    for part in parts:
        if not part:
            continue
        code, path = part[:2], part[3:]
        entries[path] = code
        if 'R' in code or 'C' in code:
            next(parts)  # the original path of a rename or copy
    return entries


async def branches(root):
    """(current branch, all local branches)."""
    current = (await git(root, 'branch', '--show-current')).strip()
    names = (await git(
        root, 'for-each-ref', '--format=%(refname:short)', 'refs/heads',
    )).split()
    return current, names


async def checkout(root, branch):
    await git(root, 'switch', branch)


async def create_branch(root, branch):
    await git(root, 'switch', '-c', branch)


async def stage(root, paths):
    await git(root, 'add', '--', *map(str, paths))


async def unstage(root, paths):
    await git(root, 'reset', '-q', '--', *map(str, paths))


async def stage_all(root):
    await git(root, 'add', '-A')


async def commit(root, message):
    await git(root, 'commit', '-m', message)


async def identity(root):
    """The (name, email) git labels commits with, or None if unset."""
    try:
        name = (await git(root, 'config', 'user.name')).strip()
        email = (await git(root, 'config', 'user.email')).strip()
    except RuntimeError:
        return None
    return name, email


async def set_identity(name, email):
    await git(Path.home(), 'config', '--global', 'user.name', name)
    await git(Path.home(), 'config', '--global', 'user.email', email)


async def diff(root, rel, code, staged):
    """The diff of one `status` entry, staged or not."""
    if code == '??':
        if rel.endswith('/'):
            files = await git(
                root, 'ls-files', '--others', '--exclude-standard', '--', rel)
            return 'New folder:\n\n' + files
        return await git(
            root, 'diff', '--no-index', '--', '/dev/null', rel, ok_codes=(0, 1))
    return await git(root, 'diff', *(['--cached'] if staged else []), '--', rel)


async def log(root, rel=None, limit=200):
    """Recent commits as dicts of sha, short, author, date and subject."""
    if not await has_commits(root):
        return []
    output = await git(
        root, 'log', f'-n{limit}', '--format=%H%x1f%h%x1f%an%x1f%ar%x1f%s',
        *(['--', rel] if rel else []),
    )
    keys = ('sha', 'short', 'author', 'date', 'subject')
    return [dict(zip(keys, line.split('\x1f'))) for line in output.splitlines()]


async def show(root, sha):
    return await git(root, 'show', '--stat', '--patch', sha)


async def revert(root, paths):
    await git(
        root, 'restore', '--source=HEAD', '--staged', '--worktree',
        '--', *map(str, paths),
    )


async def revert_commit(root, sha):
    """Add a commit that undoes `sha`."""
    await git(root, 'revert', '--no-edit', sha)


async def reset_to(root, sha):
    """Move the branch back to `sha`, keeping later changes staged."""
    await git(root, 'reset', '--soft', sha)


async def fetch(root):
    await git(root, 'fetch', auth=True)


async def pull(root):
    await git(root, 'pull', auth=True)


async def push(root):
    if not await has_commits(root):
        raise RuntimeError('Nothing to push yet. Commit your changes first.')
    try:
        await git(root, 'rev-parse', '--abbrev-ref', '@{upstream}')
    except RuntimeError:
        remote = (await remotes(root))[0]
        await git(root, 'push', '-u', remote, 'HEAD', auth=True)
        return
    await git(root, 'push', auth=True)


async def remotes(root):
    return (await git(root, 'remote')).split()


async def remote_url(root):
    return (await git(root, 'remote', 'get-url', (await remotes(root))[0])).strip()


async def add_remote(root, url, name='origin'):
    await git(root, 'remote', 'add', name, url)


async def check_remote(root, url):
    """Raise if `url` isn't a repo git can reach."""
    await git(root, 'ls-remote', url, 'HEAD', auth=True)


async def has_commits(root):
    try:
        await git(root, 'rev-parse', '--verify', '-q', 'HEAD')
    except RuntimeError:
        return False
    return True


def state(entries, rel, is_dir):
    """The display state of a path from `status` entries, or None."""
    code = entries.get(rel, entries.get(rel + '/'))
    if code is None:
        for path, path_code in entries.items():
            if path_code == '??' and path.endswith('/') and rel.startswith(path):
                return 'untracked'
            if is_dir and path.startswith(rel + '/'):
                return 'changed'
        return None
    if code == '??':
        return 'untracked'
    if 'U' in code or code in ('AA', 'DD'):
        return 'conflict'
    if 'A' in code:
        return 'added'
    if 'D' in code:
        return 'deleted'
    return 'modified'


def rel_path(root, path):
    return Path(os.path.relpath(path, root)).as_posix()
