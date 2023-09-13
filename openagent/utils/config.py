import time

import yaml

config = None


def load_config():
    global config
    # with open('config.yaml', 'r') as f:
    #     d = yaml.safe_load(f)
    #     if d is None:
    #         raise Exception('Could not load config')
    #     return d
    for i in range(10):
        time.sleep(0.1)
        with open('config.yaml', 'r') as f:
            d = yaml.safe_load(f)
            if d is not None:
                config = d
                return  # yaml.safe_load(f)
    raise Exception('Could not load config')


load_config()


def get_value(key):
    # config = load_config()
    global config
    keys = key.split('.')
    value = config
    for k in keys:
        value = value.get(k)
        if value is None:
            raise KeyError(f'Could not find key `{k}` in config')
    return value


# def save_config():
#     global config
#     with open('config.yaml', 'w') as f:
#         yaml.safe_dump(config, f, default_flow_style=False)


# def set_value(key, value):
#     # config = load_config()
#     global config
#     keys = key.split('.')
#     d = config
#     for k in keys[:-1]:
#         d = d.setdefault(k, {})
#     d[keys[-1]] = value
#     config = d
#     save_config()
#
#     # with open('config.yaml', 'w') as f:
#     #     yaml.dump(config, f)

