"""Resolving the working dir of a Claude Code session."""

import os

from utils.filesystem import get_application_path

DEFAULT_CWD = os.path.join(get_application_path(), 'claude')


def get_default_cwd():
    """The working dir of chats outside a project."""
    from gui import system

    return system.manager.config.get(
        'claude.default_working_dir', '') or DEFAULT_CWD


def resolve_cwd(member_cwd=None):
    """The member's working dir, else the default, which is created if
    missing."""
    cwd = member_cwd
    if not cwd:
        cwd = get_default_cwd()
        os.makedirs(cwd, exist_ok=True)
    return cwd
