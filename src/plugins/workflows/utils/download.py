"""Async URL-to-file download helper.

Moved out of ``src/utils/helpers.py`` so the ``aiofiles`` dep stays with the
workflows plugin instead of polluting root deps. Callers in other plugins
(e.g. slopify) re-import from here directly.
"""

import os

from utils.media import AUDIO_EXTS, VIDEO_EXTS
from utils.filesystem import get_application_path


async def download_url_to_file(url, base_dir=None, filename_without_ext=None):
    """Download a URL to a local file and return the path.

    Parameters
    ----------
    url : str
        Remote URL to download.

    Returns
    -------
    str or None
        Local file path, or ``None`` on failure.
    """
    import aiofiles
    import aiohttp

    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(url) as response:
                response.raise_for_status()
                content = await response.read()
    except Exception as e:
        print(f"Download error: {e}")
        return None

    remote_filename = os.path.basename(url.split('?')[0])
    remote_filename_without_ext, remote_fileext = os.path.splitext(remote_filename)

    if not filename_without_ext:
        filename_without_ext = remote_filename_without_ext or 'download'
    else:
        # Guard against callers accidentally passing a filename with extension.
        filename_without_ext = os.path.splitext(filename_without_ext)[0]
    if not base_dir:
        ext = remote_fileext.lower()
        if ext in VIDEO_EXTS:
            subdir = 'videos'
        elif ext in AUDIO_EXTS:
            subdir = 'music'
        else:
            subdir = 'images'
        base_dir = os.path.join(get_application_path(), subdir)
    os.makedirs(base_dir, exist_ok=True)

    local_path = os.path.join(
        base_dir, f"{filename_without_ext}{remote_fileext}")
    suffix = 1
    while os.path.exists(local_path):
        local_path = os.path.join(
            base_dir, f"{filename_without_ext}_{suffix}{remote_fileext}")
        suffix += 1

    async with aiofiles.open(local_path, 'wb') as f:
        await f.write(content)
    return local_path
