"""Resolving the working dir of a Claude Code session."""

import os

from utils.filesystem import get_application_path

DEFAULT_CWD = os.path.join(get_application_path(), 'claude')


def get_default_cwd():
    """The working dir of chats outside a project."""
    from gui import system

    return system.manager.config.get(
        'claude.default_working_dir', '') or DEFAULT_CWD
