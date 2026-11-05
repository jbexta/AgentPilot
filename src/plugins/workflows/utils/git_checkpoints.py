"""Git helpers for the checkpoint members."""

import asyncio
import os
import re
import shutil
import tempfile
from datetime import datetime


def checkpoint_ref(name):
    name = re.sub(r'[^\w.-]', '_', name.strip()) or 'default'
    return f'refs/agentpilot/checkpoints/{name}'


async def git(cwd, *args, env=None):
    if not cwd:
        raise ValueError('No repository set. Pick one in the Repository field.')
    proc = await asyncio.create_subprocess_exec(
        'git', *args,
        cwd=cwd,
        env=env,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    out, err = await proc.communicate()
    if proc.returncode:
        raise RuntimeError(err.decode().strip())
    return out.decode().strip()


async def resolve_commit(cwd, name):
    """The commit of checkpoint `name`, else of any commit-ish `name`,
    or None."""
    for ref in (checkpoint_ref(name), name):
        try:
            return await git(cwd, 'rev-parse', '--verify', '--quiet', f'{ref}^{{commit}}')
        except RuntimeError:
            pass
    return None


async def diff(cwd, base, target, max_chars=100_000):
    """The diff from `base` to `target`, or a per-file summary when the
    diff is longer than `max_chars`."""
    content = await git(cwd, 'diff', base, target)
    if len(content) <= max_chars:
        return content
    stat = await git(cwd, 'diff', '--stat', base, target)
    return (
        f'The diff is too large to show ({len(content):,} characters).\n'
        f'Run `git diff {base} {target} -- <path>` for specific files.\n\n'
        f'{stat}'
    )


async def save_checkpoint(cwd, ref, commit, expire=''):
    """Point `ref` at `commit`. The reflog keeps older checkpoints from
    being garbage collected until they are older than `expire`."""
    await git(cwd, 'update-ref', '--create-reflog', ref, commit)
    if expire:
        await git(cwd, 'reflog', 'expire', f'--expire={expire}', ref)


async def snapshot(cwd, include_untracked=True, exclude=''):
    """Commit the working tree without touching the branch or the
    real index. Files matching the `exclude` patterns are skipped,
    tracked ones keep their committed version."""
    index = await git(cwd, 'rev-parse', '--path-format=absolute', '--git-path', 'index')
    excludes = [f':(top,exclude){p}' for p in re.split(r'[,\s]+', exclude) if p]
    with tempfile.TemporaryDirectory() as tmp:
        env = {**os.environ, 'GIT_INDEX_FILE': os.path.join(tmp, 'index')}
        shutil.copy(index, env['GIT_INDEX_FILE'])
        await git(cwd, 'add', '-A' if include_untracked else '-u',
                  '--', ':/', *excludes, env=env)
        tree = await git(cwd, 'write-tree', env=env)
    message = f"Checkpoint {datetime.now().isoformat(timespec='seconds')}"
    return await git(cwd, 'commit-tree', tree, '-p', 'HEAD', '-m', message)
