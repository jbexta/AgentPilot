from plugins.projects.core.web_stacks.base import BundledStack
from utils.helpers import set_module_type


@set_module_type(module_type='Web_stacks')
class WampStack(BundledStack):
    display_name = 'WAMP'
    priority = 20

    roots = ('C:/wamp64', 'C:/wamp')
    php_globs = ('bin/php/php*/php.exe',)
    mysql_globs = (
        'bin/mysql/mysql*/bin/mysqld.exe',
        'bin/mariadb/mariadb*/bin/mysqld.exe',
    )
    mysql_conf_globs = (
        'bin/mysql/mysql*/my.ini',
        'bin/mariadb/mariadb*/my.ini',
    )