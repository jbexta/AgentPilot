import os
import sys
import threading

import yaml


config = None
async_lock = threading.Lock()


def get_config_path():
    from agentpilot.utils.filesystem import get_application_path
    # Check if we're running as a script or a frozen exe
    if getattr(sys, 'frozen', False):
        application_path = get_application_path()  # os.path.dirname(sys.executable)
    else:
        # config_file = os.path.join(cwd, '..', '..', 'configuration.yaml')
        application_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '..')

    ret = os.path.join(application_path, 'configuration.yaml')
    print(ret)
    return ret


def load_config():
    global config
    config_file = get_config_path()

    with open(config_file, 'r') as stream:
        try:
            config = yaml.safe_load(stream)
            # return config
        except yaml.YAMLError as exc:
            print(exc)


# import os
# import threading
# import time
# import yaml
# async_lock = threading.Lock()
# config = None
#
#
# # Get the directory of the current script
# # script_dir = os.path.dirname(os.path.realpath(__file__))
# #
# # # Get the parent directory
# # parent_dir = os.path.dirname(script_dir)
# #
# # # Construct the path to 'configuration.yaml'
# # yaml_file = os.path.join(parent_dir, 'configuration.yaml')
# yaml_file = 'configuration.yaml'
#
# def load_config():
#     global config
#     try:
#         for i in range(10):
#             time.sleep(0.1)
#             with open(yaml_file, 'r') as f:
#                 d = yaml.safe_load(f)
#                 if d is not None:
#                     config = d
#                     return
#         raise Exception('Could not load config')
#     except Exception as e:
#         print(e)

# yaml_file = 'configuration.yaml'  # os.path.join(project_root, 'configuration.yaml')
#
# def load_config():
#     global config
#     try:
#         for i in range(10):
#             time.sleep(0.1)
#             full_config_path = os.path.join(os.getcwd(), yaml_file)
#             with open(full_config_path, 'r') as f:
#                 d = yaml.safe_load(f)
#                 if d is not None:
#                     config = d
#                     return
#         raise Exception('Could not load config')
#     except Exception as e:
#         print(e)


load_config()
# print(script_dir)
# print(yaml_file)


def get_value(key):
    global config
    with async_lock:
        try:
            keys = key.split('.')
            value = config
            for k in keys:
                if k not in value:
                    raise KeyError(f'Could not find key `{k}` in config')
                value = value[k]
            return value
        except Exception as e:
            print(e)


def save_config():
    global config
    config_file = get_config_path()
    with async_lock:
        with open(config_file, 'w') as f:
            yaml.safe_dump(config, f, default_flow_style=False)


def set_value(key_path, value):
    global config
    keys = key_path.split('.')
    d = config
    for k in keys[:-1]:
        d = d.get(k)
        if d is None:
            raise KeyError(f'Could not find key `{k}` in config')
    d[keys[-1]] = value
    save_config()


override_map = {
    'code-interpreter.forced': {
        True: {
            'context.model': 'gpt-4'
        }
    }
}
