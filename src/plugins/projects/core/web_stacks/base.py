"""Base class for the runtimes that serve a Website project."""

import glob
import os
from pathlib import Path


class WebStack:
    """A runtime that can serve a Website project.

    Subclasses declare how to recognise a project, what to run for it, and
    where the preview should point. Everything is classmethod-only; stacks
    hold no state.
    """

    display_name = ''
    priority = 50  # lowest priority that detects a project wins

    @classmethod
    def detect(cls, path):
        """Whether this stack can serve the project at *path*."""
        return False

    @classmethod
    def services(cls, path, port):
        """The processes to run, as ``{name, command, env}`` dicts."""
        return []

    @classmethod
    def requirement(cls, path):
        """What is missing before this stack can run, if anything."""
        return ''

    @classmethod
    def url(cls, path, port):
        """Where the preview should point once the services are up."""
        return f'http://127.0.0.1:{port}/'

    @classmethod
    def web_root(cls, path):
        """The directory actually served, honouring common conventions."""
        for name in ('public_html', 'public', 'web', 'www', 'htdocs',
                     'dist'):
            candidate = os.path.join(path, name)
            if os.path.isdir(candidate):
                return candidate
        return path

    @classmethod
    def has_files(cls, path, pattern):
        """Whether *pattern* matches anything in the project, one level deep."""
        return bool(glob.glob(os.path.join(path, pattern))
                    or glob.glob(os.path.join(path, '*', pattern)))

    @classmethod
    def first_install(cls, candidates):
        """The first install directory that exists, else an empty string."""
        for candidate in candidates:
            for match in sorted(glob.glob(candidate), reverse=True):
                if os.path.isdir(match):
                    return match
        return ''

    @classmethod
    def first_file(cls, patterns):
        """The first file matching any of *patterns*, else an empty string."""
        for pattern in patterns:
            for match in sorted(glob.glob(pattern), reverse=True):
                if os.path.isfile(match):
                    return match
        return ''

    @classmethod
    def index_page(cls, path):
        """The site's index page under the web root, one level deep."""
        root = cls.web_root(path)
        for folder in ('', '*'):
            for name in ('index.php', 'index.html'):
                matches = sorted(glob.glob(os.path.join(root, folder, name)))
                if matches:
                    return Path(matches[0])
        return None

    @classmethod
    def site_url(cls, path, port):
        """The served url of the folder holding the index page."""
        page = cls.index_page(path)
        folder = page.parent.relative_to(cls.web_root(path)) if page else Path()
        return f'http://127.0.0.1:{port}/' + ''.join(
            f'{part}/' for part in folder.parts
        )

    @classmethod
    def file_url(cls, path):
        """A ``file://`` url for the project's index page, if it has one."""
        page = cls.index_page(path)
        return page.as_uri() if page and page.suffix == '.html' else ''


class BundledStack(WebStack):
    """A WAMP-style bundle shipping PHP and MySQL together.

    The bundle's own PHP binary serves the project where it already lives,
    so nothing has to be moved into a document root and nothing needs root
    privileges. Apache itself is not started, so ``.htaccess`` rules and
    Apache modules do not apply.
    """

    roots = ()
    php_globs = ()
    mysql_globs = ()
    mysql_conf_globs = ()

    @classmethod
    def root(cls):
        return cls.first_install(cls.roots)

    @classmethod
    def bundled(cls, patterns):
        root = cls.root()
        if not root:
            return ''
        return cls.first_file(
            [os.path.join(root, pattern) for pattern in patterns]
        )

    @classmethod
    def detect(cls, path):
        return bool(cls.bundled(cls.php_globs)) and cls.has_files(path, '*.php')

    @classmethod
    def url(cls, path, port):
        return cls.site_url(path, port)

    @classmethod
    def services(cls, path, port):
        php = cls.bundled(cls.php_globs)
        if not php:
            return []

        services = [{
            'name': 'php',
            'command': f'"{php}" -S 127.0.0.1:{port} -t "{cls.web_root(path)}"',
        }]

        mysqld = cls.bundled(cls.mysql_globs)
        if mysqld:
            conf = cls.bundled(cls.mysql_conf_globs)
            command = f'"{mysqld}"'
            if conf:
                command += f' --defaults-file="{conf}"'
            services.append({'name': 'mysql', 'command': command})

        return services
