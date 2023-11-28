from pynput.keyboard import Key, Controller


def press_keys(keys):
    keyboard = Controller()
    for key in keys:
        keyboard.press(key)
    for key in keys:
        keyboard.release(key)


def type_string(string):
    keyboard = Controller()
    keyboard.type(string)
