import threading
import time
import yaml
config = None
async_lock = threading.Lock()

yaml_file = 'configuration.yaml'  # os.path.join(project_root, 'configuration.yaml')


def load_config():
    global config
    try:
        for i in range(10):
            time.sleep(0.1)
            with open(yaml_file, 'r') as f:
                d = yaml.safe_load(f)
                if d is not None:
                    config = d
                    return
        raise Exception('Could not load config')
    except Exception as e:
        print(e)


load_config()


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
    with async_lock:
        with open(yaml_file, 'w') as f:
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
