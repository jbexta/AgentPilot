from plugins.projects.core.web_stacks.base import BundledStack
from utils.helpers import set_module_type


@set_module_type(module_type='Web_stacks')
class XamppStack(BundledStack):
    display_name = 'XAMPP'
    priority = 20

    roots = (
        '/opt/lampp',
        'C:/xampp',
        '/Applications/XAMPP/xamppfiles',
    )
    php_globs = ('bin/php', 'php/php.exe')
    mysql_globs = ('bin/mysqld', 'mysql/bin/mysqld.exe')
    mysql_conf_globs = ('etc/my.cnf', 'mysql/bin/my.ini')