import json
import re
import string
import time

from PySide6.QtCore import QSize, Qt
from PySide6.QtGui import QPixmap, QPainter, QPainterPath, QColor

from src.utils import resources_rc
from src.utils.filesystem import unsimplify_path
from contextlib import contextmanager
from PySide6.QtWidgets import QWidget, QMessageBox
import requests


def convert_model_json_to_obj(model_json):
    if model_json is None:
        return {
            'kind': 'CHAT',
            'model_name': 'mistral/mistral-large-latest',
            'model_params': {},
            'provider': 'litellm',
        }
    try:
        if isinstance(model_json, dict):
            return model_json
        return json.loads(model_json)
    except json.JSONDecodeError:  # temp patch until 0.4.0
        return {
            'kind': 'CHAT',
            'model_name': model_json,
            'model_params': {},
            'provider': 'litellm',
        }


def network_connected():
    try:
        response = requests.get("https://google.com", timeout=5)
        return True
    except requests.ConnectionError:
        return False


def convert_to_safe_case(text):
    """Use regex to return only a-z A-Z 0-9 and _"""
    text = text.replace(' ', '_').replace('-', '_').lower()
    return re.sub(r'[^a-zA-Z0-9_]', '_', text)


def get_avatar_paths_from_config(config):
    config_type = config.get('_TYPE', 'agent')
    if config_type == 'agent':
        return config.get('info.avatar_path', ':/resources/icon-agent-solid.png')
    elif config_type == 'workflow':
        paths = []
        members = config.get('members', [])
        for member_data in members:
            member_config = member_data.get('config', {})
            member_type = member_config.get('_TYPE', 'agent')
            if member_type == 'user':
                continue
            paths.append(get_avatar_paths_from_config(member_config))
        return paths
    elif config_type == 'user':
        return ':/resources/icon-user.png'
    elif config_type == 'tool':
        return ':/resources/icon-tool.png'
    elif config_type == 'block':
        return ':/resources/icon-tool.png'
    else:
        raise NotImplementedError(f'Unknown config type: {config_type}')


def get_member_name_from_config(config, default='Assistant', incl_types=('agent', 'workflow')):
    config_type = config.get('_TYPE', 'agent')
    if config_type == 'agent':
        return config.get('info.name', default)
    elif config_type == 'workflow':
        members = config.get('members', [])
        names = [get_member_name_from_config(member_data.get('config', {}))
                 for member_data in members
                 if member_data.get('config', {}).get('_TYPE', 'agent') in incl_types]
        return ', '.join(names)
    elif config_type == 'user':
        return config.get('info.name', 'You')
    elif config_type == 'tool':
        return config.get('name', 'Tool')
    else:
        raise NotImplementedError(f'Unknown config type: {config_type}')


def merge_config_into_workflow_config(config, entity_id=None):
    config_json = {
        '_TYPE': 'workflow',
        'members': [
            {'id': 1, 'agent_id': None, 'loc_x': -10, 'loc_y': 64, 'config': {"_TYPE": "user"}, 'del': 0},
            {'id': 2, 'agent_id': entity_id, 'loc_x': 37, 'loc_y': 30, 'config': config, 'del': 0}
        ],
        'inputs': [],
    }
    return config_json


def get_all_children(widget):
    """Recursive function to retrieve all child pages of a given widget."""
    children = []
    for child in widget.findChildren(QWidget):
        children.append(child)
        children.extend(get_all_children(child))
    return children


@contextmanager
def block_signals(*widgets):
    """Context manager to block signals for a widget and all its child pages."""
    all_widgets = []
    try:
        # Get all child pages
        for widget in widgets:
            all_widgets.append(widget)
            all_widgets.extend(get_all_children(widget))

        # Block signals
        for widget in all_widgets:
            widget.blockSignals(True)

        yield
    finally:
        # Unblock signals
        for widget in all_widgets:
            widget.blockSignals(False)


@contextmanager
def block_pin_mode():
    """Context manager to temporarily set pin mode to true, and then restore old state. A workaround for dialogs"""
    from src.gui import main
    try:
        old_pin_mode = main.PIN_MODE
        main.PIN_MODE = True
        yield
    finally:
        main.PIN_MODE = old_pin_mode


def display_messagebox(icon, text, title, buttons=(QMessageBox.Ok)):
    with block_pin_mode():
        msg = QMessageBox()
        msg.setIcon(icon)
        msg.setText(text)
        msg.setWindowTitle(title)
        msg.setStandardButtons(buttons)
        msg.setWindowFlags(msg.windowFlags() | Qt.WindowStaysOnTopHint)
        # msg.addButton('Archive', QMessageBox.ActionRole)
        return msg.exec_()


def apply_alpha_to_hex(hex_color, alpha):
    color = QColor(hex_color)
    color.setAlphaF(alpha)
    return color.name(QColor.HexArgb)


def replace_times_with_spoken(text):
    pattern = r"\b\d{1,2}:\d{2}\s?[ap]m\b"
    time_matches = re.findall(pattern, text)
    for time_match in time_matches:
        has_space = ' ' in time_match
        is_12hr = 'PM' in time_match.upper() and int(time_match.split(':')[0]) < 13
        h_symbol = '%I' if is_12hr else '%H'
        converted_time = time.strptime(time_match,
                                       f'{h_symbol}:%M %p' if has_space else f'{h_symbol}:%M%p')  # '%H = 24hr, %I = 12hr'
        spoken_time = time_to_human_spoken(converted_time)  # , include_timeframe=False)
        text = text.replace(time_match, f' {spoken_time} ')
    return text


def time_to_human_spoken(inp_time, include_timeframe=True):
    # inp_time += ' AM'
    hour_12h = int(time.strftime("%I", inp_time))
    hour_24h = int(time.strftime("%H", inp_time))
    minute = int(time.strftime("%M", inp_time))
    am_pm = time.strftime("%p", inp_time).upper()

    if am_pm == 'PM' and hour_24h < 12:
        hour_24h += 12

    hour_mapping = {
        0: "twelve",
        1: "one", 2: "two", 3: "three", 4: "four", 5: "five",
        6: "six", 7: "seven", 8: "eight", 9: "nine", 10: "ten",
        11: "eleven", 12: "twelve", 13: "thirteen", 14: "fourteen", 15: "fifteen",
        16: "sixteen", 17: "seventeen", 18: "eighteen", 19: "nineteen"
    }
    dec_mapping = {
        0: "oh",
        2: "twenty", 3: "thirty", 4: "forty", 5: "fifty",
        6: "sixty", 7: "seventy", 8: "eighty", 9: "ninety"
    }

    hour_map = hour_mapping[hour_12h]
    dec = minute // 10
    if 9 < minute < 20:
        min_map = hour_mapping[minute]
    elif minute == 0:
        min_map = 'oh clock'
    else:
        digits = hour_mapping[minute % 10] if minute % 10 != 0 else ''
        min_map = f'{dec_mapping[dec]} {digits}'

    timeframe = ' in the morning'
    if 12 <= hour_24h < 19:
        timeframe = ' in the afternoon'
    if 19 <= hour_24h < 22:
        timeframe = ' in the evening'
    if 22 <= hour_24h < 24:
        timeframe = ' at night'

    return f"{hour_map} {min_map}{timeframe if include_timeframe else ''}"


def is_url_valid(url):
    # regex to check if url is a valid url
    regex = r"^(?:http|ftp)s?://" \
            r"(?:(?:[A-Z0-9](?:[A-Z0-9-]{0,61}[A-Z0-9])?\.)" \
            r"+(?:[A-Z]{2,6}\.?|[A-Z0-9-]{2,}\.?)|" \
            r"localhost|" \
            r"\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3})" \
            r"(?::\d+)?" \
            r"(?:/?|[/?]\S+)$"
    return re.match(regex, url, re.IGNORECASE) is not None


def split_lang_and_code(text):
    if text.startswith('```') and text.endswith('```'):
        lang, code = text[3:-3].split('\n', 1)
        return lang, code
    return None, text


def extract_square_brackets(string):
    pattern = r"\[(.*?)\]$"
    matches = re.findall(pattern, string)
    if len(matches) == 0: return None
    return matches[0]


def extract_parentheses(string):
    pattern = r"\((.*?)\)$"
    matches = re.findall(pattern, string)
    if len(matches) == 0: return None
    return matches[0]


def remove_brackets(string, brackets_to_remove='[('):
    if '[' in brackets_to_remove:
        string = re.sub(r"\[.*?\]", "", string)
    if '(' in brackets_to_remove:
        string = re.sub(r"\(.*?\)", "", string)
    if '{' in brackets_to_remove:
        string = re.sub(r"\{.*?\}", "", string)
    if '*' in brackets_to_remove:
        string = re.sub(r"\*.*?\*", "", string)
    return string.strip()  # .upper()


def extract_list_from_string(string):
    # The regex pattern matches either a number followed by a dot or a hyphen,
    # followed by optional spaces, and then captures the remaining text until the end of the line.
    pattern = r'(?:\d+\.|-)\s*(.*)'
    matches = re.findall(pattern, string)
    return matches


def path_to_pixmap(paths, circular=True, diameter=30, opacity=1, def_avatar=None):
    if isinstance(paths, list):
        count = len(paths)
        dia_mult = 0.7 if count > 1 else 1  # 1 - (0.08 * min(count - 1, 8))
        small_diameter = int(diameter * dia_mult)

        pixmaps = []
        for path in paths:
            pixmaps.append(path_to_pixmap(path, diameter=small_diameter, def_avatar=def_avatar))

        # Create a new QPixmap to hold all the stacked pixmaps
        stacked_pixmap = QPixmap(diameter, diameter)
        stacked_pixmap.fill(Qt.transparent)

        painter = QPainter(stacked_pixmap)
        painter.setRenderHint(QPainter.Antialiasing)
        painter.setRenderHint(QPainter.SmoothPixmapTransform)

        only_two = count == 2
        only_one = count == 1

        offset = (diameter - small_diameter) // 2
        for i, pixmap in enumerate(pixmaps):
            # Calculate the shift for each pixmap
            # random either -1 or 1
            x_shift = (i % 2) * 2 - 1
            y_shift = ((i // 2) % 2) * 2 - 1
            x_shift *= 5
            y_shift *= 5
            if only_two and i == 1:
                y_shift *= -1
            if only_one:
                x_shift = 0
                y_shift = 0
            painter.drawPixmap(offset - x_shift, offset - y_shift, pixmap)
        painter.end()

        return stacked_pixmap

    else:
        from src.gui.widgets import colorize_pixmap
        colorize_paths = [
            ':/resources/icon-user.png',
            ':/resources/icon-tool.png',
            ':/resources/icon-agent-solid.png',
        ]
        try:
            path = unsimplify_path(paths)
            if path == '':
                raise Exception('Empty path')
            pic = QPixmap(path)
            if path in colorize_paths:
                pic = colorize_pixmap(pic)
        except Exception as e:
            default_img_path = def_avatar or ':/resources/icon-agent-solid.png'
            pic = colorize_pixmap(QPixmap(default_img_path))

        if circular:
            pic = create_circular_pixmap(pic, diameter=diameter)

        if opacity < 1:
            temp_pic = QPixmap(pic.size())
            temp_pic.fill(Qt.transparent)

            painter = QPainter(temp_pic)

            painter.setOpacity(opacity)
            painter.drawPixmap(0, 0, pic)
            painter.end()

            pic = temp_pic

        return pic


def create_circular_pixmap(src_pixmap, diameter=30):
    if src_pixmap.isNull():
        return QPixmap()

    # Desired size of the profile picture
    size = QSize(diameter, diameter)

    # Create a new QPixmap for our circular image with the same size as our QLabel
    circular_pixmap = QPixmap(size)
    circular_pixmap.fill(Qt.transparent)  # Ensure transparency for the background

    # Create a painter to draw on the pixmap
    painter = QPainter(circular_pixmap)
    painter.setRenderHint(QPainter.Antialiasing)  # For smooth rendering
    painter.setRenderHint(QPainter.SmoothPixmapTransform)

    # Draw the ellipse (circular mask) onto the pixmap
    path = QPainterPath()
    path.addEllipse(0, 0, size.width(), size.height())
    painter.setClipPath(path)

    # Scale the source pixmap while keeping its aspect ratio
    src_pixmap = src_pixmap.scaled(size, Qt.KeepAspectRatioByExpanding, Qt.SmoothTransformation)

    # Calculate the coordinates to ensure the pixmap is centered
    x = (size.width() - src_pixmap.width()) / 2
    y = (size.height() - src_pixmap.height()) / 2

    painter.drawPixmap(x, y, src_pixmap)
    painter.end()

    return circular_pixmap
