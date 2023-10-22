from utils import sql


def get_all_lists():
    return sql.get_results(f"SELECT id, list_name FROM `lists`", return_type='dict')


def get_list_items(list_name):
    return sql.get_results(f"SELECT id, item_name FROM `lists_items` WHERE `list_id` = (SELECT `id` FROM `lists` WHERE `list_name` = '{list_name}')",
                           return_type='dict')


def add_list_item(list_name, item_name, item_data=''):
    sql.execute(f"INSERT INTO `lists_items` (`list_id`, `item_name`, `item_data`) VALUES ((SELECT `id` FROM `lists` WHERE `list_name` = '{list_name}'), '{item_name}', '{item_data}')")


def add_list(list_name):
    sql.execute(f"INSERT INTO `lists` (`list_name`) VALUES ('{list_name}')")
