import os
import re
import sys
import time

from PySide6.QtCore import QSize, Qt
from PySide6.QtGui import QPixmap, QPainter, QPainterPath

from agentpilot.utils.apis import llm
from agentpilot.toolkits import lists
from agentpilot.utils import filesystem, resources_rc
from utils.filesystem import unsimplify_path


# def simplify_path(path):
#     abs_path = os.path.abspath(path)
#     exe_dir = filesystem.get_application_path()
#
#     if abs_path.startswith(exe_dir):
#         rel_path = os.path.relpath(abs_path, exe_dir)
#         return '.' + os.sep + rel_path
#     else:
#         return abs_path
#
#
# def unsimplify_path(path):
#     exe_dir = filesystem.get_application_path()
#
#     # Handle path starting with './'
#     if path.startswith('./'):
#         rel_path = path[2:]  # remove the './' at the beginning
#         abs_path = os.path.join(exe_dir, rel_path)
#     # Handle path starting with '../'
#     elif path.startswith('../'):
#         parts = path.split('/')
#         num_up = parts.count('..')
#         rel_path = '/'.join(parts[num_up:])
#         abs_path = exe_dir
#         for _ in range(num_up):
#             abs_path = os.path.dirname(abs_path)
#         abs_path = os.path.join(abs_path, rel_path)
#     # Handle path starting with '.'
#     elif path.startswith('.'):
#         rel_path = path[1:]
#         abs_path = os.path.join(exe_dir, rel_path)
#     else:
#         abs_path = path
#
#     return os.path.abspath(abs_path)  # return absolute path


class SafeDict(dict):
    """A custom dictionary that returns the key wrapped in curly braces
       when the key is missing."""
    def __missing__(self, key):
        return '{' + key + '}'


def categorize_item(item_list, item, can_make_new=False):
    # if cats is a list
    if isinstance(item_list, list):
        items = ['   ' + s for s in item_list]
        cat_str = '\n'.join(items)
    elif isinstance(item_list, str):
        items = lists.get_list_items(item_list).values()
        cat_str = '\n'.join([f'   {s}' for s in items])
    else:
        raise ValueError('cats must be a list or str')

    cat = llm.get_scalar(f"""
categories [
{cat_str}
]
What_To_Categorize: `{item}`
{"Please either" if can_make_new else "You must"} choose one of the above categories{" or return a new one that it can be classified under." if can_make_new else ""}.
Category: """).lower()
    cat = re.sub(r'\([^)]*\)', '', cat).strip()

    if isinstance(item_list, str) and can_make_new:
        if cat not in items:
            lists.add_list_item(item_list, cat)
    return cat


# def answer_questions


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


def path_to_pixmap(path, use_default_image=True, circular=True, diameter=30, opacity=1):
    path = unsimplify_path(path)
    try:
        if path == '':
            raise Exception('Empty path')
        pic = QPixmap(path)
    except Exception as e:
        default_img_path = ":/resources/icon-agent.png" if use_default_image else ''
        pic = QPixmap(default_img_path)

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
