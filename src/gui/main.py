
import asyncio
from decimal import Decimal
import json
import os
import sys
import uuid

import PySide6
import qasync
from PySide6.QtWidgets import *
from PySide6.QtCore import Signal, QTimer, QThreadPool, QPropertyAnimation, QEasingCurve, QObject
from PySide6.QtGui import QIcon, QTextDocument, Qt
from typing_extensions import override

# from core.connectors.h5 import append_h5_dataset, create_h5_dataset, tea_kinds
from src.core.connectors.h5 import DATA_DIR, PriceFile, create_h5_file, get_h5_dataset_last_item_cell, get_h5_path, normalize_timestamp, sanitize_filename, sanitize_string
from src.core.connectors.mysql import MysqlConnector
from src.core.connectors.sqlite import SqliteConnector
from src.utils import sql
from src.utils.sql import get_db_path
from utils.sql_upgrade import upgrade_script
from utils import telemetry  # , sql
from utils.helpers import display_message_box, flatten_list, get_avatar_paths_from_config, display_message
from gui.style import ACCENT_COLOR_1, get_stylesheet
from gui.widgets.config_pages import ConfigPages
from gui.util import CustomMenu, IconButton, clear_layout, CVBoxLayout, safe_single_shot, set_selected_pages, FramelessResizeMixin
# from plugins.calligrapher.src.main import test_calligrapher

from gui import system

os.environ["QT_OPENGL"] = "software"

loop = None

BOTTOM_CORNER_X = 400
BOTTOM_CORNER_Y = 450

PIN_MODE = True


class SystemManager:
    def __init__(self):
        self._main_gui = None

        from core.managers.modules import ModuleManager
        self.modules = ModuleManager(system=self)
        # Managers will be populated here
        # self.apis = APIManager
        # self.agents = AgentManager
        # ....
    
    def reload_managers(self):
        self.modules.load()
        custom_managers = self.modules.get_modules_in_folder(
            module_type='Managers',
            fetch_keys=('name', 'class',)
        )
        for name, mgr in custom_managers:
            if name in self.__dict__:
                continue
            if mgr:
                setattr(self, name, mgr(self))

    def load(self):
        self.reload_managers()

        for name, mgr in self.__dict__.items():
            if name.startswith('_'):
                continue
            print(f'Loading manager: {name}')
            mgr.load()

    def load_manager(self, manager_name):
        mgr = getattr(self, manager_name, None)
        if mgr:
            mgr.load()


# class TutorialHighlightWidget(QWidget):
#     clicked_target = Signal()
#
#     def __init__(self, parent=None):
#         super().__init__(parent)
#         self.parent = parent
#         self.setAttribute(Qt.WA_TranslucentBackground)
#         self.setWindowFlags(Qt.Popup | Qt.FramelessWindowHint)
#
#         self.setStyleSheet("border-top-left-radius: 30px;")
#         self.target_pos = QPoint(90, 60)
#         self.target_radius = 50
#         self.message = ""
#
#         self.installEventFilter(self)
#
#     def eventFilter(self, obj, event):
#         if event.type() == QEvent.MouseButtonPress:
#             if (event.pos() - self.target_pos).manhattanLength() <= self.target_radius:
#                 self.clicked_target.emit()
#                 return True
#         return super().eventFilter(obj, event)
#
#     def mousePressEvent(self, event):
#         # call parent mousePressEvent
#         self.parent.mousePressEvent(event)
#
#     def mouseMoveEvent(self, event):
#         # event.ignore()
#         super().mouseMoveEvent(event)
#
#     def paintEvent(self, event):
#         painter = QPainter(self)
#         painter.setRenderHint(QPainter.Antialiasing)
#
#         # Create a path for the entire widget
#         full_path = QPainterPath()
#         full_path.addRect(self.rect())
#
#         # Create a path for the circular cutout
#         circle_path = QPainterPath()
#         circle_path.addEllipse(self.target_pos, self.target_radius, self.target_radius)
#
#         # Subtract the circle path from the full path
#         dimmed_path = full_path.subtracted(circle_path)
#
#         # Draw dimmed overlay
#         painter.setBrush(QColor(0, 0, 0, 128))
#         painter.setPen(Qt.NoPen)
#         painter.drawPath(dimmed_path)
#
#         # Draw circle border
#         painter.setBrush(Qt.NoBrush)
#         painter.setPen(QPen(Qt.white, 2))
#         painter.drawEllipse(self.target_pos, self.target_radius, self.target_radius)
#
#         # Draw message
#         if self.message:
#             painter.setPen(Qt.white)
#             painter.drawText(self.rect(), Qt.AlignBottom | Qt.AlignHCenter, self.message)
#
#     def set_target(self, pos, radius, message=""):
#         self.target_pos = pos
#         self.target_radius = radius
#         self.message = message
#         self.update()


class TOSDialog(QDialog):
    def __init__(self):
        super().__init__()

        self.setWindowTitle("Terms of Use")
        self.setWindowIcon(QIcon(':/resources/icon.png'))
        self.setMinimumSize(300, 350)
        self.resize(300, 350)

        self.setWindowFlags(
            Qt.Window
            | Qt.WindowTitleHint
            | Qt.WindowSystemMenuHint
            | Qt.WindowCloseButtonHint
            | Qt.WindowStaysOnTopHint
        )

        layout = QVBoxLayout(self)

        self.tos_label = QTextEdit("""
The material embodied in this software is provided to you "as-is" and without warranty of any kind, express, implied or otherwise, including without limitation, any warranty of fitness for a particular purpose. 
In no event shall Agent Pilot or it's creators be liable to you or anyone else for any direct, special, incidental, indirect or consequential damages of any kind, or any damages whatsoever, including but not limited to, loss of profit, loss of use, savings or revenue, or the claims of third parties, whether or not Agent Pilot creators have been advised of the possibility of such loss, however caused and on any theory of liability, arising out of or in connection with the possession, use or performance of this software.
"""
                                )
        self.tos_label.setReadOnly(True)
        self.tos_label.setFrameStyle(QFrame.NoFrame)

        layout.addWidget(self.tos_label)

        h_layout = QHBoxLayout()
        h_layout.addStretch(1)

        self.decline_button = QPushButton("Decline")
        self.decline_button.setFixedWidth(100)
        self.decline_button.clicked.connect(self.reject)
        h_layout.addWidget(self.decline_button)

        self.agree_button = QPushButton("Agree")
        self.agree_button.setFixedWidth(100)
        self.agree_button.clicked.connect(self.accept)
        h_layout.addWidget(self.agree_button)

        layout.addLayout(h_layout)


class TitleButtonBar(CustomMenu):
    def __init__(self, parent):
        super().__init__(parent=parent)
        self.icon_size = 12
        self.schema = [
            {
                'text': 'Minimize',
                'icon_path': ':/resources/icon-minimize.png',
                'target': self.minimizeApp,
            },
            {
                'text': 'Maximize',
                'icon_path': ':/resources/icon-maximize.png',
                'target': self.maximizeApp,
            },
            {
                'text': 'Close',
                'icon_path': ':/resources/close.png',
                'target': self.closeApp,
            },
        ]
        self.create_toolbar()

    def minimizeApp(self):
        self.window().showMinimized()

    def maximizeApp(self):
        if self.window().isMaximized():
            self.window().showNormal()
        else:
            self.window().showMaximized()

    def closeApp(self):
        self.window().close()


class MainPages(ConfigPages):
    def __init__(self, parent):
        super().__init__(
            parent=parent,
            default_page='chat',
            right_to_left=True,
            bottom_to_top=True,
            button_kwargs=dict(
                button_type='icon',
                icon_size=50
            ),
        )
        self.parent = parent
        self.main = parent
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)

        self.build_schema()

    @override
    def build_schema(self):
        from utils import sql
        pinned_pages: list = sql.get_scalar(
            "SELECT `value` FROM settings WHERE `field` = 'pinned_pages';",
            load_json=True
        )
        page_definitions = system.manager.modules.get_modules_in_folder(
            module_type='Pages',
            fetch_keys=('id', 'name', 'class',),
        )
        page_definitions = [  # filter out pages that are not main or pinned
            (module_id, module_name, page_class)
            for module_id, module_name, page_class in page_definitions
            if getattr(page_class, 'page_type', 'any') == 'main'
            or (getattr(page_class, 'page_type', 'any') == 'any' and module_name in pinned_pages)
        ]
        preferred_order = ['chat', 'contexts', 'agents', 'blocks', 'tools', 'modules']
        locked_below = ['settings']
        locked_above = ['chat', 'contexts', 'agents', 'blocks', 'tools', 'modules']
        order_column = 1
        if preferred_order:
            order_idx = {name: i for i, name in enumerate(preferred_order)}
            page_definitions.sort(key=lambda x: order_idx.get(x[order_column], len(preferred_order)))
        
        # sort so locked_below are at the bottom
        page_definitions.sort(key=lambda x: x[1] in locked_below)

        new_pages = {}
        for page_name in locked_above:
            if page_name in self.pages and page_name in [page[1] for page in page_definitions]:
                new_pages[page_name] = self.pages[page_name]
        for module_id, module_name, page_class in page_definitions:
            try:
                existing_page = self.pages.get(module_name, None)
                if existing_page and type(existing_page) is page_class:
                    new_pages[module_name] = existing_page
                    continue

                page = page_class(parent=self)
                setattr(page, 'module_id', module_id)
                if existing_page and getattr(existing_page, 'user_editing', False):
                    setattr(page, 'user_editing', True)

                if hasattr(page, 'add_breadcrumb_widget') and getattr(page, 'show_breadcrumbs', True):
                    page.add_breadcrumb_widget()

                new_pages[module_name] = page

            except Exception as e:
                display_message(f"Error loading page '{module_name}': {e}", 'Error', QMessageBox.Warning)

        for page_name in locked_below:
            if page_name in self.pages and page_name in [page[1] for page in page_definitions]:
                new_pages[page_name] = self.pages[page_name]

        self.pages = new_pages

        super().build_schema()

        self.settings_sidebar.setFixedWidth(70)

    def add_page(self):
        dlg_title, dlg_prompt = ('New page name', 'Enter a new name for the new page')
        text, ok = QInputDialog.getText(self, dlg_title, dlg_prompt)
        if not ok:
            return
    
        system.manager.modules.add(name=text, module_type='Pages')
    
        self.build_schema()
        # main.page_settings.build_schema()
        self.settings_sidebar.toggle_page_pin(text, True)
        page_btn = self.settings_sidebar.page_buttons.get(text, None)
        if page_btn:
            page_btn.click()
            self.edit_page(text)


class NotificationWidget(QWidget):
    closed = Signal(QObject)

    def __init__(self, parent=None, color=None):
        super().__init__(parent)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.main = parent.main
        # Handle color defaults and conversions
        if not color:
            color = '#ff6464'
        elif color == 'blue':
            color = '#438BB9'
        elif color == 'red':
            color = '#ff6464'
        elif not color.startswith('#'):
            color = '#ff6464'

        # Create the main layout
        self.outer_layout = QVBoxLayout(self)
        self.outer_layout.setContentsMargins(0, 0, 0, 0)
        self.outer_layout.setSpacing(0)

        # Create the content container
        self.content = QWidget(self)
        self.content.setStyleSheet(f"""
            background-color: {color};
            border-radius: 10px;
            color: white;
        """)

        # Inner layout for the content
        self.content_layout = QVBoxLayout(self.content)
        self.content_layout.setContentsMargins(12, 10, 12, 10)
        self.content_layout.setSpacing(0)

        # Create text label with proper wrapping
        self.label = QLabel()
        self.label.setWordWrap(True)
        self.label.setStyleSheet("color: white; font-size: 11pt;")
        self.label.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Minimum)
        self.content_layout.addWidget(self.label)

        # Add content to outer layout
        self.outer_layout.addWidget(self.content)

        # Set size policies
        self.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Minimum)
        self.setMaximumWidth(300)

        # Initialize with zero height
        self.content.setMinimumHeight(0)
        self.content.setMaximumHeight(0)

        # Setup timer for auto-hide
        self.timer = QTimer(self)
        self.timer.setSingleShot(True)
        self.timer.timeout.connect(self.hide_animation)

        # Setup animation
        self.animation = QPropertyAnimation(self.content, b"maximumHeight")
        self.animation.setEasingCurve(QEasingCurve.InOutCubic)
        self.animation.finished.connect(self.on_animation_finished)

    def show_message(self, message, duration=5000):
        # Set the message
        self.label.setText(message)

        # Calculate proper size based on text
        self.label.adjustSize()
        text_width = min(self.label.sizeHint().width(), 280)  # Account for padding

        # Create a temporary document to calculate proper text height
        doc = QTextDocument()
        doc.setDefaultFont(self.label.font())
        doc.setHtml(message)
        doc.setTextWidth(text_width)

        # Calculate target height with margins
        target_height = doc.size().height() + 20  # Add some padding

        # Reset animation and height
        self.animation.stop()
        self.content.setMaximumHeight(0)

        # Start show animation
        self.animation.setStartValue(0)
        self.animation.setEndValue(target_height)
        self.animation.setDuration(250)
        self.animation.start()

        if not self.main.isMinimized():
            # Start timer for auto-hide
            self.timer.start(duration)

    def hide_animation(self):
        # Start hide animation
        current_height = self.content.height()
        self.animation.stop()
        self.animation.setStartValue(current_height)
        self.animation.setEndValue(0)
        self.animation.setDuration(250)
        self.animation.start()

    def on_animation_finished(self):
        if self.content.maximumHeight() == 0:
            self.hide()
            self.closed.emit(self)

    def enterEvent(self, event):
        self.timer.stop()
        event.accept()

    def leaveEvent(self, event):
        self.timer.start(3000)
        event.accept()


class NotificationManager(QWidget):
    def __init__(self, parent):
        super().__init__(parent=parent)
        self.main = parent
        self.setFixedWidth(300)
        self.setWindowFlags(Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.Tool)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setAttribute(Qt.WA_ShowWithoutActivating)
        self.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Preferred)

        # Main layout for stacking notifications
        self.layout = CVBoxLayout(self)
        self.layout.setSpacing(6)
        self.layout.setContentsMargins(0, 0, 0, 0)
        self.layout.setAlignment(Qt.AlignTop)

        self.notifications = []

    def show_notification(self, message, title, icon='Information', color=None, duration=5000):
        is_minimized = self.main.isMinimized()
        if is_minimized:
            icon = getattr(QSystemTrayIcon, icon, QSystemTrayIcon.Information)
            self.main.tray.showMessage(
                title,
                message,
                icon,
                duration  # duration in ms
            )
            # self.tray.showMessage(message, color)
            return
        
        # Create new notification
        notification = NotificationWidget(self, color=color)
        notification.closed.connect(self.remove_notification)

        # Add to layout
        self.layout.addWidget(notification)
        self.notifications.append(notification)

        # Display the notification
        notification.show_message(message, duration)
        # self.setVisible(True)
        self.update_position()

        print(message)

    def remove_notification(self, notification):
        if notification in self.notifications:
            self.notifications.remove(notification)
            self.layout.removeWidget(notification)
            notification.deleteLater()

        # if not self.notifications:
        #     self.hide()
        # else:
        # if self.notifications:
        self.update_position()

    def update_position(self):
        # Position in top right corner of main window with padding
        # visible = self.notifications is not None and not self.main.isMinimized()
        # self.setVisible(visible)
        # if not visible:
        #     return
        self.move(self.main.x() + self.main.width() - self.width() - 90,
                 self.main.y() + 50)
        self.adjustSize()


# def convert_forex():
#     # Directory: `/home/jb/Downloads/fx_full_1min_6q0at16` contains .txt files with forex data
#     # Each file contains comma separated 1 minute data for a single forex pair
#     # The columns are: date, time, open, high, low, close, volume
#     # Convert the data to .h5 file
#     # Each file should not be loaded into memory, but rather processed line by line
#     for file in os.listdir('/home/jb/Downloads/fx_full_1min_6q0at16'):
#         if not file.endswith('.txt'):
#             continue

#         filename = file.split('.')[0]
#         market_id = filename.split('_')[0]
#         if len(market_id) != 6:
#             raise NotImplementedError(f"Market ID {market_id} is not 6 characters long")
#         tf_path = get_h5_path('FX', market_id)
#         if not os.path.exists(tf_path):
#             os.makedirs(os.path.dirname(tf_path), exist_ok=True)
#             create_h5_file(
#                 path=tf_path, 
#                 metadata={'api': 'FX', 'market': market_id},
#                 with_dataset='ohlc/60',
#             )

#         price_file = PriceFile(tf_path)
#         price_file.base_interval = 60
#         with price_file:

#             current_size = price_file.file['ohlc/60'].shape[0]

#             ohlc_batch = []
#             BATCH_SIZE = 60000
            
#             def write_batch():
#                 nonlocal current_size, ohlc_batch
#                 if ohlc_batch:
#                     price_file.append_batch(ohlc_batch)
#                     current_size = price_file.file['ohlc/60'].shape[0]
#                     print(f'FX: Wrote batch: {len(ohlc_batch)} ohlc, total size: {current_size}')
#                     ohlc_batch = []

#         # with h5py.File(tf_path, 'a') as f:
#             with open(os.path.join('/home/jb/Downloads/fx_full_1min_6q0at16', file), 'r') as f:
#                 for line in f:
#                     data = line.split(',')

#                     date = data[0]  # in the format YYYYMMDD
#                     year = int(date[:4])
#                     month = int(date[4:6])
#                     day = int(date[6:])
#                     time = data[1] # in the format HH:MM:SS, we only need HH:MM
#                     hour = int(time[:2])
#                     minute = int(time[3:5])
#                     unix = int(datetime(year, month, day, hour, minute).timestamp())
#                     opn = float(data[2])
#                     high = float(data[3])
#                     low = float(data[4])
#                     close = float(data[5])
#                     volume = float(data[6])

#                     ohlc_batch.append([unix, opn, high, low, close, volume, 0])
                    
#                     if len(ohlc_batch) >= BATCH_SIZE:
#                         write_batch()

#                 write_batch()
#                 # f['ohlc/60'].append([unix, opn, high, low, close, volume])

# def upsert_fx_assets():
#     fin_db = os.path.join(os.path.dirname(get_db_path()), 'finance.db')
#     connection = SqliteConnector(db_path=fin_db)
#     fx_api = FinanceAPI(connection, 1)
#     existing_assets = fx_api.get_existing_assets()
#     existing_markets = fx_api.get_existing_markets()

#     new_markets = {}
#     new_assets = set()
#     for file in os.listdir('/home/jb/Downloads/fx_full_1min_6q0at16'):
#         if not file.endswith('.txt'):
#             continue

#         filename = file.split('.')[0]
#         market_id = filename.split('_')[0]

#         base_asset = market_id[:3]
#         quote_asset = market_id[3:]

#         if base_asset not in existing_assets:
#             new_assets.add(base_asset)
#         if quote_asset not in existing_assets:
#             new_assets.add(quote_asset)

#         if market_id not in existing_markets:
#             new_markets[market_id] = (base_asset, quote_asset)
    
#     if new_assets:
#         values_clause = ', '.join(['(?, ?, ?, ?, ?)'] * len(new_assets))
#         query = f"INSERT INTO assets (api_id, name, symbol, api_asset_id, kind) VALUES {values_clause}"
#         params = []
#         for asset in new_assets:
#             params.extend([1, asset, asset, asset, 'FOREX'])
#         connection.execute(query, params)
#         # display_message(f"Binance: Added {len(new_assets)} assets")
#         print(f'FX: Added {len(new_assets)} assets')
    
#     new_asset_ids = connection.get_results(f"""
#         SELECT api_asset_id, id
#         FROM assets
#         WHERE api_id = ?
#     """, (1,), return_type='dict')

#     # new_markets = {symbol.symbol: (symbol.base_asset, symbol.quote_asset)
#     #             for symbol in data.symbols
#     #             if symbol.symbol not in existing_markets}

#     if new_markets:
#         # display_message(f"Binance: Adding {len(new_markets)} markets")
#         print(f'FX: Adding {len(new_markets)} markets')
#         items = list(new_markets.items())
#         batch_size = 499
#         for i in range(0, len(items), batch_size):
#             batch = items[i:i+batch_size]
#             values_clause = ', '.join(['(?, ?, ?, ?, ?, ?)'] * len(batch))
#             query = f"INSERT INTO api_markets (api_id, market_id, base_asset, quote_asset, base_symb, quote_symb) VALUES {values_clause}"
#             params = []
#             for market, (base, quote) in batch:
#                 base_asset_id = new_asset_ids.get(base, None)
#                 quote_asset_id = new_asset_ids.get(quote, None)
#                 params.extend([1, market, base_asset_id, quote_asset_id, base, quote])
#             connection.execute(query, params)

#     pass

# def convert_coingecko_files():
#     coingecko_dir = '/media/jb/DATA/PRICE/COINGECKO/14400'
#     for file in os.listdir(coingecko_dir):
#         # rename to remove `_usd_line.h5`
#         if not file.endswith('_line_14400.h5'):
#             continue
#         new_file = file.replace('_line_14400.h5', '.h5')
#         os.rename(os.path.join(coingecko_dir, file), os.path.join(coingecko_dir, new_file))

def get_total_at_unix(unix):
    asset_balances: dict[int, Decimal] = get_asset_balances_at_unix(unix)
    asset_prices: dict[int, Decimal] = get_asset_prices_at_unix(unix, asset_balances.keys())
    asset_totals: dict[int, Decimal] = {asset: asset_balances[asset] * asset_prices[asset] for asset in asset_balances.keys()}
    return sum(asset_totals.values())
    

def get_asset_balances_at_unix(unix):
    fin_db = os.path.join(os.path.dirname(get_db_path()), 'finance.db')
    connection = SqliteConnector(db_path=fin_db)
    result = connection.get_results(f"""
        SELECT 
            a.id,
            a.api_id,
            a.symbol,
            a.name,
            a.kind as asset_type,
            COALESCE(
                COALESCE(mf.depwith_amount, 0) + 
                COALESCE(t.trade_amount, 0), 0
            ) AS total_amount
            -- a.last_price,
            -- COALESCE(
            --    COALESCE(mf.depwith_amount, 0) + 
            --    COALESCE(t.trade_amount, 0), 0
            -- ) * a.last_price AS total_value
        FROM assets a
        LEFT JOIN (
            SELECT 
                asset_id,
                SUM(
                    CASE 
                        WHEN depwith = 0 THEN asset_amt 
                        WHEN depwith = 1 THEN -asset_amt 
                        ELSE 0 
                    END
                ) AS depwith_amount
            FROM depwiths 
            WHERE unix < ?
            GROUP BY asset_id
        ) mf ON a.id = mf.asset_id
        LEFT JOIN (
            SELECT 
                asset_id,
                SUM(amount) AS trade_amount
            FROM (
                SELECT asset_sold AS asset_id, -amt_sold AS amount
                FROM trades 
                WHERE ignored = 0 AND unix < ?
                UNION ALL
                SELECT asset_received AS asset_id, amt_received AS amount
                FROM trades 
                WHERE ignored = 0 AND unix < ?
                UNION ALL
                SELECT fee_asset AS asset_id, -fee_amt AS amount
                FROM trades 
                WHERE ignored = 0 AND fee_amt > 0 AND unix < ?
            ) trade_movements
            GROUP BY asset_id
        ) t ON a.id = t.asset_id
        WHERE total_amount != 0
    """, (unix,unix,unix,unix,))
    return {row[0]: Decimal(row[5]) for row in result}


def get_asset_prices_at_unix(unix, assets):
    prices = {}
    convert_to = 2
    for asset in assets:
        prices[asset] = convert_asset_price(asset, convert_to, unix)
    return prices


def find_linked_assets(asset_id):
    fin_db = os.path.join(os.path.dirname(get_db_path()), 'finance.db')
    connection = SqliteConnector(db_path=fin_db)
    return connection.get_results(f"""
        WITH RECURSIVE linked_assets AS (
            SELECT id, group_to FROM assets 
            WHERE id = ?

            UNION

            SELECT a.id, a.group_to
            FROM assets a
            INNER JOIN linked_assets la ON (a.id = la.group_to OR a.group_to = la.id)
        )
        SELECT DISTINCT id FROM linked_assets;
        """, (asset_id,), return_type='list')


def convert_asset_price(convert_asset_id, target_asset_id, unix):
    if convert_asset_id == target_asset_id:
        return 1.0

    fin_db = os.path.join(os.path.dirname(get_db_path()), 'finance.db')
    connection = SqliteConnector(db_path=fin_db)

    convert_links = find_linked_assets(convert_asset_id)
    target_links = find_linked_assets(target_asset_id)

    # Prepare placeholders for the IN clauses
    conv_placeholders = ', '.join(['?'] * len(convert_links))
    target_placeholders = ', '.join(['?'] * len(target_links))

    # Construct the query
    query = f"""
        SELECT a.name, am.market_id, am.base_asset, am.quote_asset 
        FROM api_markets am
        LEFT JOIN apis a ON am.api_id = a.id
        WHERE 
            (base_asset IN ({conv_placeholders}) AND quote_asset IN ({target_placeholders}))
            OR 
            (quote_asset IN ({conv_placeholders}) AND base_asset IN ({target_placeholders}))
    """

    params = convert_links + target_links + convert_links + target_links
    
    markets = connection.get_results(query, params)

    if len(markets) != 1:
        raise NotImplementedError(f"Multiple markets found for {convert_asset_id} to {target_asset_id}")

    market_file = get_market_price_file(markets[0][0], markets[0][1])
    pf = PriceFile(market_file)
    price = pf.binary_search_unix_price(unix)

    return price


def get_market_price_file(api, market):
    return f'/media/jb/DATA/PRICE/{api}/{api}_{market}.h5'


def upsert_coingecko_assets():
    fin_db = os.path.join(os.path.dirname(get_db_path()), 'finance.db')
    connection = SqliteConnector(db_path=fin_db)
    # cg_api = CoingeckoAPI(connection)

    existing_assets = connection.get_results("""
        SELECT 
            id, 
            api_asset_id
        FROM assets 
        WHERE api_id = ?
    """, (31,), return_type='dict')
    # existing_markets = cg_api.get_existing_markets()
    connection.execute("DELETE FROM api_markets WHERE api_id = 31")

    # new_assets = set()
    new_markets = {}

    for file in os.listdir('/media/jb/DATA/PRICE/COINGECKO'):
        # remove 'COINGECKO_' from the beginning ONLY
        market_id = file[len('COINGECKO_'):-3]
        base_asset = market_id[:-4]  # remove '_usd'
        quote_asset = 'USD'

        new_markets[market_id] = (base_asset, quote_asset)
    
    all_assets = connection.get_results("""
        SELECT 
            api_asset_id,
            id
        FROM assets 
        WHERE api_id = ?
    """, (31,), return_type='dict')
    
    if new_markets:
        # display_message(f"Binance: Adding {len(new_markets)} markets")
        print(f'FX: Adding {len(new_markets)} markets')
        items = list(new_markets.items())
        batch_size = 499
        for i in range(0, len(items), batch_size):
            batch = items[i:i+batch_size]
            values_clause = ', '.join(['(?, ?, ?, ?, ?, ?)'] * len(batch))
            query = f"INSERT INTO api_markets (api_id, market_id, base_asset, quote_asset, base_symb, quote_symb) VALUES {values_clause}"
            params = []
            for market, (base, quote) in batch:
                base_asset_id = all_assets[base]
                quote_asset_id = 53
                params.extend([31, market, base_asset_id, quote_asset_id, base, quote])
            connection.execute(query, params)


def insert_slopify_artists(artist_names):
    """Insert a list of artist names into slopify_artists.

    Parameters
    ----------
    artist_names : list[str]
        Artist names to insert.
    """
    existing_artists = sql.get_results("SELECT LOWER(name) FROM slopify_artists", return_type='list')
    existing_artists_count = len([name for name in artist_names if name.lower() in existing_artists])
    
    new_artists = [name for name in artist_names if name.lower() not in existing_artists]
    for name in new_artists:
        if not name:
            continue
        config = {
            'Info': {'name': name},
            'Generation': {},
        }
        sql.execute(
            "INSERT INTO slopify_artists (name, config)"
            " VALUES (?, ?)",
            (name, json.dumps(config)),
        )
    print(f'Inserted {len(new_artists)} artists')
    if existing_artists_count > 0:
        print(f'{existing_artists_count} artists already exist')



class Main(FramelessResizeMixin, QMainWindow):

    def __init__(self):
        super().__init__()


        # # # check_cg_filepaths()
        # # # sys.exit(0)

        # # # # # # use yt-dlp to download the following videos:
        # # # # # # https://www.youtube.com/watch?v=BEvt5dzxVW0
        # # # # # yt_manager = YouTubeManager()
        # # # # # yt_manager.download_video('https://www.youtube.com/watch?v=BEvt5dzxVW0', '/home/jb/Desktop/BEvt5dzxVW0.mp4')
        
        # # # # # convert_forex()
        # # # # # upsert_fx_assets()

        # # # totpot = get_total_at_unix(1635449600)
        # # # print(totpot)

        # # # # convert_coingecko_files()
        # # upsert_coingecko_assets()
        # # sys.exit(0)
        # # # # migrate_tables()
        # # # # # # sys.exit(0)

        # # # # # scan_file_ids()
        # # # # # sys.exit(0)

        # # return

        # from scrape_polo_depwiths import get_depwith
        # results = get_depwith()
        # for r in results:
        #     print(list(r.values()))
        # return

        self.init_frameless_resize(margin=10)

        self.setWindowTitle('AgentPilot')
        self.setWindowIcon(QIcon(':/resources/icon.png'))

        # self.main = self  # workaround for bubbling up

        self.threadpool = QThreadPool()

        self.central = QWidget()
        self.central.setProperty("class", "central")
        self.setCentralWidget(self.central)
        self.layout = QVBoxLayout(self.central)

        self.setMouseTracking(True)
        self.setAcceptDrops(True)

        self.title_bar = TitleButtonBar(parent=self)
        system.manager = SystemManager()
        system.manager._main_gui = self

        # Initialize the notification manager
        self.notification_manager = NotificationManager(self)
        self.notification_manager.show()

        self.init_app()

        # Create tray icon (required for notifications)
        self.tray = QSystemTrayIcon()
        self.tray.setIcon(QIcon(':/resources/icon.png'))
        self.tray.show()

        safe_single_shot(2000, system.manager.daemons.start_all_daemons)

    def init_app(self):
        clear_layout(self.layout)

        # migrate_old_format('/home/jb/Desktop/CRYP/PRICE/BINANCE/0/BINANCE_ETHBTC_raw.h5')
        # migrate_old_format('/home/jb/Desktop/CRYP/PRICE/BINANCE/0/BINANCE_LTCBTC_raw.h5')

        # self.check_if_app_already_running()
        telemetry.initialize()

        self.check_db()
        self.patch_db()

        # if not test_mode:  # workaround for dialog block todo
        self.check_tos()

        from utils.reset import ensure_system_folders
        ensure_system_folders()

        # system.manager = SystemManager()
        # system.manager._main_gui = self
        system.manager.load()

        if 'AP_DEV_MODE' in os.environ.keys():
            from utils.reset import bootstrap_app
            # reset_table(table_name='modules')
            bootstrap_app()

        get_stylesheet()  # init stylesheet

        # telemetry.set_uuid(self.get_uuid())
        # telemetry.send('user_login')
        self.test_running = False
        self.page_history = []

        always_on_top = system.manager.config.get('system.always_on_top', True)
        current_flags = self.windowFlags()
        new_flags = current_flags
        if always_on_top:
            new_flags |= Qt.WindowStaysOnTopHint
        else:
            new_flags &= ~Qt.WindowStaysOnTopHint
        self.setWindowFlags(new_flags)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setWindowFlags(self.windowFlags() | Qt.FramelessWindowHint)

        self.main_pages = MainPages(self)

        self.layout.addWidget(self.main_pages)

        self.side_bubbles = self.SideBubbles(self)
        # is_in_ide = 'AP_DEV_MODE' in os.environ
        # dev_mode_state = True if is_in_ide else None
        # self.main_menu.pages['Settings'].pages['System'].widgets[1].toggle_dev_mode(dev_mode_state)

        from utils import sql
        window_size = sql.get_scalar("SELECT value FROM settings WHERE `field` = 'window_size'", load_json=True)
        if not window_size:
            window_size = {}
        self.resize(window_size.get('width', 720), window_size.get('height', 900))

        # self.main_menu.settings_sidebar.btn_new_context.setFocus()
        self.apply_stylesheet()
        self.apply_margin()

        app_config = system.manager.config
        self.main_pages.pages['settings'].load_config(app_config)

        screen_geometry = QApplication.primaryScreen().availableGeometry()
        new_x = screen_geometry.x() + screen_geometry.width() - self.width()
        new_y = screen_geometry.y() + screen_geometry.height() - self.height()
        self.move(new_x, new_y)

        self.notification_manager.update_position()

        self.main_pages.build_schema()
        page_path = sql.get_scalar("SELECT value FROM settings WHERE `field` = 'page_path'", load_json=True)
        if page_path:
            set_selected_pages(self.main_pages, page_path)
        self.main_pages.load()


        # # system.manager.modules.test_modules()
        # QTimer.singleShot(100, system.manager.modules.test_modules)

    @property  # todo remove
    def page_chat(self):
        return self.main_pages.get('chat')

    def get_uuid(self):
        from utils import sql
        my_uuid = sql.get_scalar("SELECT value FROM settings WHERE `field` = 'my_uuid'")
        if my_uuid == '':
            my_uuid = str(uuid.uuid4())
            sql.execute("UPDATE settings SET value = ? WHERE `field` = 'my_uuid'", (my_uuid,))
        return my_uuid

    def check_tos(self):
        from utils import sql
        is_accepted = sql.get_scalar("SELECT value FROM settings WHERE `field` = 'accepted_tos'")
        if is_accepted == '1':
            return

        dialog = TOSDialog()
        if dialog.exec() == QDialog.Accepted:
            sql.execute("UPDATE settings SET value = '1' WHERE `field` = 'accepted_tos'")
            return
        else:
            sys.exit(0)

    def check_db(self):
        from utils import sql
        # Check if the database is up-to-date
        try:
            upgrade_db = sql.check_database_upgrade()
            if upgrade_db:
                # ask confirmation first
                if QMessageBox.question(None, "Database outdated",
                                        "Do you want to upgrade the database to the newer version?",
                                        QMessageBox.Yes | QMessageBox.No) != QMessageBox.Yes:
                    # exit the app
                    sys.exit(0)

                db_version = upgrade_db
                upgrade_script.upgrade(current_version=db_version)

        except Exception as e:
            display_message_box(icon=QMessageBox.Critical, title="Error", text=str(e), buttons=QMessageBox.Ok)
            sys.exit(0)

    def patch_db(self):
        from utils import sql

        # in `settings`.`app_config`, rename `display.parameter_color` to `display.accent_color_1` and `display.structure_color` to `display.accent_color_2`
        app_config = sql.get_scalar("SELECT value FROM settings WHERE `field` = 'app_config'", load_json=True)
        if app_config:
            if 'display.parameter_color' in app_config:
                app_config['display.accent_color_1'] = app_config.pop('display.parameter_color')
                app_config['display.accent_color_2'] = app_config.pop('display.structure_color')
                sql.execute("UPDATE settings SET value = ? WHERE `field` = 'app_config'", (json.dumps(app_config),))

        # add 'finance_config' to settings table
        if not sql.get_scalar("SELECT value FROM settings WHERE `field` = 'finance_config'"):
            sql.execute("INSERT INTO settings (field, value) VALUES ('finance_config', '{}')")

        # Roles table is deprecated — bubble styling lives on bubble module classes.
        # # update the json field  `roles`.`config`, set 'hide_bubbles' to
        # audio_config = json.dumps({"bubble_bg_color": "#003b3b3b", "bubble_text_color": "#ff818365"})
        # sql.execute("UPDATE roles SET config = ? WHERE name = 'audio'", (audio_config,))

        # add enhancement_blocks to settings table
        if not sql.get_scalar("SELECT value FROM settings WHERE `field` = 'enhancement_blocks'"):
            sql.execute("INSERT INTO settings (field, value) VALUES ('enhancement_blocks', '{}')")

        # # if 'modules' is in `roles`.`config` WHERE `name` = 'user'
        # has_module_field = sql.get_scalar("SELECT json_extract(config, '$.module') FROM roles WHERE name = 'user'")
        # if not has_module_field:
        #     sql.execute("UPDATE roles SET config = json_set(config, '$.module', ?) WHERE name = 'audio'", ('AudioBubble',))
        #     sql.execute("UPDATE roles SET config = json_set(config, '$.module', ?) WHERE name = 'code'", ('CodeBubble',))
        #     sql.execute("UPDATE roles SET config = json_set(config, '$.module', ?) WHERE name = 'tool'", ('ToolBubble',))
        #     sql.execute("UPDATE roles SET config = json_set(config, '$.module', ?) WHERE name = 'result'", ('ResultBubble',))
        #     sql.execute("UPDATE roles SET config = json_set(config, '$.module', ?) WHERE name = 'image'", ('ImageBubble',))
        #     sql.execute("UPDATE roles SET config = json_set(config, '$.module', ?) WHERE name = 'user'", ('UserBubble',))
        #     sql.execute("UPDATE roles SET config = json_set(config, '$.module', ?) WHERE name = 'assistant'", ('AssistantBubble',))

        sql.ensure_column_in_tables(
            tables=[
                'modules',
                'entities',
                'blocks',
                'tools',
                'environments',
            ],
            column_name='baked',
            column_type='INTEGER',
            default_value="0",
            not_null=True,
        )
        sql.ensure_column_in_tables(
            tables=[
                'folders',
            ],
            column_name='uuid',
            column_type='TEXT',
            default_value="""(
                lower(hex(randomblob(4))) || '-' ||
                lower(hex(randomblob(2))) || '-' ||
                '4' || substr(lower(hex(randomblob(2))), 2) || '-' ||
                substr('89ab', abs(random()) % 4 + 1, 1) || substr(lower(hex(randomblob(2))), 2) || '-' ||
                lower(hex(randomblob(6)))
            )""",
            not_null=True,
        )
        sql.ensure_column_in_tables(
            tables=[
                'blocks',
            ],
            column_name='parent_id',
            column_type='INTEGER',
            default_value='NULL',
            not_null=False,
        )

        # sql.execute("UPDATE folders SET name = 'Roles' WHERE name = 'Bubbles' and `type` = 'modules' and `locked` = 1")
        
        # add window_size to settings table
        if not sql.get_scalar("SELECT value FROM settings WHERE `field` = 'window_size'"):
            sql.execute("INSERT INTO settings (field, value) VALUES ('window_size', '{}')")
        # add page_path to settings table
        if not sql.get_scalar("SELECT value FROM settings WHERE `field` = 'page_path'"):
            sql.execute("INSERT INTO settings (field, value) VALUES ('page_path', '{}')")
        
        # rename block types: text_block -> text, code_block -> code, prompt_block -> prompt
        self.patch_config_recursive(
            tables=['contexts', 'entities', 'blocks', 'tools', 'tasks'],
            renames={'text_block': 'text', 'code_block': 'code', 'prompt_block': 'prompt'},
        )

        sql.ensure_column_in_tables(
            tables=['models'],
            column_name='metadata',
            column_type='TEXT',
            default_value='{}',
            not_null=True,
        )
        sql.ensure_column_in_tables(
            tables=['models'],
            column_name='provider_plugin',
            column_type='TEXT',
            default_value='litellm',
            not_null=True,
        )
        # # rename `entities` to `agents`
        # if sql.get_scalar("SELECT name FROM tables WHERE name = 'entities'"):
        #     sql.execute("ALTER TABLE entities RENAME TO agents")

            # ensure_column_in_tables(
        #     tables=['modules'],
        #     column_name='kind',
        #     column_type='TEXT',
        #     default_value='',  # todo - empty string default?
        #     not_null=True,
        # )
        # # if any items in `folders` table has `locked` = 1
        # locked_folders = sql.get_results("SELECT id, name FROM folders WHERE type = 'modules' AND locked = 1", return_type='dict')
        # if locked_folders:
        #     for folder_id, folder_name in locked_folders.items():
        #         folder_modules = sql.get_results(f"SELECT id FROM modules WHERE folder_id = ?",
        #                                          (folder_id,), return_type='list')
        #         for module_id in folder_modules:
        #             # set `kind` to folder_name
        #             sql.execute("UPDATE modules SET kind = ?, folder_id = NULL WHERE id = ?",
        #                         (folder_name.upper(), module_id))
        #     # delete locked folders
        #     sql.execute("DELETE FROM folders WHERE type = 'modules' and locked = 1")

    def patch_config_recursive(self, tables, renames):
        """Recursively rename `_TYPE` values in config JSON across tables.

        Parameters
        ----------
        tables : list[str]
            Database tables to patch.
        renames : dict[str, str]
            Mapping of old _TYPE values to new ones.
        """
        from utils import sql

        def _patch(config):
            if not isinstance(config, dict):
                return config
            if config.get('_TYPE') in renames:
                config['_TYPE'] = renames[config['_TYPE']]
            for member in config.get('members', []):
                if isinstance(member, dict):
                    _patch(member.get('config', {}))
            return config

        for table in tables:
            try:
                rows = sql.get_results(
                    f"SELECT id, config FROM {table} "
                    f"WHERE config IS NOT NULL"
                )
            except Exception:
                continue
            for row_id, config_str in rows:
                try:
                    config = json.loads(config_str)
                except (json.JSONDecodeError, TypeError):
                    continue
                patched = json.dumps(_patch(config))
                if patched != config_str:
                    sql.execute(
                        f"UPDATE {table} SET config = ? WHERE id = ?",
                        (patched, row_id),
                    )

    # def check_if_app_already_running(self):
    #     # if not getattr(sys, 'frozen', False):
    #     #     return  # Don't check if we are running in ide
    #
    #     current_pid = os.getpid()  # Get the current process ID
    #
    #     for proc in psutil.process_iter(['pid', 'name']):
    #         try:
    #             proc_info = proc.as_dict(attrs=['pid', 'name'])
    #             if proc_info['pid'] != current_pid and 'AgentPilot' in proc_info['name']:
    #                 raise Exception("Another instance of the application is already running.")
    #         except (psutil.NoSuchProcess, psutil.AccessDenied):
    #             # If the process no longer exists or there's no permission to access it, skip it
    #             continue

    def show_side_bubbles(self):
        self.side_bubbles.show()
        # move to top left of the main window
        self.side_bubbles.move(self.x() - self.side_bubbles.width(), self.y())

    # def hide_side_bubbles(self):
    #     print("hide side bubbles")
    #     self.side_bubbles.hide()

    class SideBubbles(QWidget):
        def __init__(self, main):
            super().__init__(parent=None)
            self.main = main
            self.setWindowFlags(Qt.Popup | Qt.FramelessWindowHint)
            self.setAttribute(Qt.WA_TranslucentBackground)
            self.setFixedWidth(50)

            # allow mouseMoveEvent
            self.setMouseTracking(True)

            # show 3 circles 50x50 px vertically
            self.layout = CVBoxLayout(self)

            self.load()

        def load(self):
            from utils import sql
            recent_chats = sql.get_results("""
                SELECT config
                FROM contexts
                WHERE kind = 'CHAT'
                ORDER BY id DESC
                LIMIT 3
            """, return_type='list')

            for config in recent_chats:
                row_layout = QHBoxLayout()
                config = json.loads(config)
                member_paths = get_avatar_paths_from_config(config)
                # member_pixmap = path_to_pixmap(member_paths, diameter=50)
                label = IconButton(  #) QLabel()
                    parent=self,
                    icon_path=member_paths,  # default icon
                    size=50,
                    opacity=0.75,
                    icon_size_percent=0.5,
                )

                # # when label is hovered, show a 1px border
                # # set transparent background
                # label.setStyleSheet("background-color: transparent;")
                # # set border radius to 25px
                #border-radius: 25px; border: 1px solid transparent; background-color: transparent;
                # label.setStyleSheet("""
                #     background-color: transparent;
                #     border-radius: 25px;
                #     border: 1px solid transparent;
                #     padding: 5px;
                # """)
                # set hovered background color to #ffffff20
                # label.setProperty("class", "bubble")
                # label.setPixmap(member_pixmap)
                row_layout.addWidget(label)
                self.layout.addLayout(row_layout)

        def mouseMoveEvent(self, event):
            # If the mouse is more than 50px away from any edge of side bubbles, hide it
            left_distance = event.globalX() - self.x()
            right_distance = self.x() + self.width() - event.globalX()
            top_distance = event.globalY() - self.y()
            bottom_distance = self.y() + self.height() - event.globalY()
            if left_distance < -50 or right_distance < -50 or \
               top_distance < -50 or bottom_distance < -50:
                self.hide()

    def position_title_bar(self):
        x = self.width() - self.title_bar.sizeHint().width()
        self.title_bar.move(x, 0)
        self.title_bar.raise_()

    def apply_stylesheet(self):
        old_text_color = getattr(self, '_cached_text_color', None)
        new_stylesheet = get_stylesheet()
        if getattr(self, '_cached_stylesheet', None) != new_stylesheet:
            self._cached_stylesheet = new_stylesheet
            QApplication.setOverrideCursor(Qt.WaitCursor)
            QApplication.instance().setStyleSheet(new_stylesheet)
            QApplication.restoreOverrideCursor()
        from gui.style import TEXT_COLOR as new_text_color
        self._cached_text_color = new_text_color
        text_color_changed = old_text_color != new_text_color

        if text_color_changed:
            # pixmaps
            for child in self.findChildren(IconButton):
                child.setIconPixmap()
            # trees
            for child in self.findChildren(QTreeWidget):
                if hasattr(child, 'apply_stylesheet'):
                    child.apply_stylesheet()
            # charts
            from gui.widgets.chart_widget import ChartWidget
            options = PySide6.QtCore.Qt.FindChildOptions.FindChildrenRecursively
            for child in self.findChildren(ChartWidget, options=options):
                child.apply_stylesheet()

        text_color = system.manager.config.get('display.text_color', '#c4c4c4')
        # if self.page_chat:
        #     self.page_chat.top_bar.title_label.setStyleSheet(f"QLineEdit {{ color: {apply_alpha_to_hex(text_color, 0.90)}; background-color: transparent; }}"
        #                                        f"QLineEdit:hover {{ color: {text_color}; }}")

    def apply_margin(self):
        margin = system.manager.config.get('display.window_margin', 6)
        self.layout.setContentsMargins(margin, margin, margin, margin)

    def toggle_always_on_top(self):
        always_on_top = system.manager.config.get('system.always_on_top', True)

        current_flags = self.windowFlags()
        new_flags = current_flags

        # Set or unset the always-on-top flag depending on the setting
        if always_on_top:
            new_flags |= Qt.WindowStaysOnTopHint
        else:
            new_flags &= ~Qt.WindowStaysOnTopHint

        # Hide the window before applying new flags
        self.hide()
        self.setWindowFlags(new_flags)

        # Ensuring window borders and transparency
        self.setAttribute(Qt.WA_TranslucentBackground)  # Maintain transparency
        self.setWindowFlags(self.windowFlags() | Qt.FramelessWindowHint)  # Keep it frameless
        self.show()

    def mouseReleaseEvent(self, event):
        if self._resizing:
            # save window state to database
            window_size = {
                'width': self.width(),
                'height': self.height(),
            }
            from utils import sql
            sql.execute("""
                UPDATE settings
                SET value = json(?)
                WHERE field = 'window_size'""", (json.dumps(window_size),))
        super().mouseReleaseEvent(event)

    def keyPressEvent(self, event):
        if event.key() == Qt.Key_Escape:
            self.test_running = False
        super().keyPressEvent(event)

    def _move_window(self, global_pos):
        super()._move_window(global_pos)
        self.notification_manager.update_position()

    def run_demo(self):
        """Switch to a disposable demo DB, reinitialize, and run the demo."""
        import shutil
        from utils import sql
        from utils.reset import reset_application

        current_db = sql.get_db_path()
        already_in_demo = current_db.endswith('demo_data.db')
        if not already_in_demo:
            self._real_db_path = current_db
            demo_db_path = os.path.join(
                os.path.dirname(current_db), 'demo_data.db'
            )
            self._demo_db_path = demo_db_path

            shutil.copyfile(current_db, demo_db_path)
            sql.set_db_filepath(demo_db_path)

        reset_application(force=True, preserve_audio_msgs=True, reset_models_=False)
        sql.execute(
            'UPDATE settings SET value = "1" '
            'WHERE field = "accepted_tos"'
        )

        system.manager.daemons.stop_all_daemons()
        self.init_app()
        # self.show()

        from gui.demo import DemoRunnable
        self._demo_runnable = DemoRunnable(
            self, on_finished=self._restore_after_demo
        )
        self.threadpool.start(self._demo_runnable)

    def _restore_after_demo(self):
        """Restore the user's real DB and reinitialize."""
        from utils import sql

        sql.set_db_filepath(self._real_db_path)
        self.test_running = False
        self.init_app()
        safe_single_shot(
            2000, system.manager.daemons.start_all_daemons
        )

        try:
            os.remove(self._demo_db_path)
        except OSError:
            pass

    def stop_demo(self):
        """Signal the running demo to cancel."""
        if hasattr(self, '_demo_runnable'):
            self._demo_runnable._cancelled = True


    def resizeEvent(self, event):
        self.notification_manager.update_position()
        self.position_title_bar()
        super().resizeEvent(event)
        # self.update_resize_grip_position()

    # def changeEvent(self, event):
    #     if event.type() == QEvent.WindowStateChange:
    #         if not self.isMinimized() and self.notification_manager.notifications:
    #             self.notification_manager.setVisible(True)
    #             for notification in self.notification_manager.notifications:
    #                 notification.timer.start()
    #             # self.notification_manager.update_position()
    #     super().changeEvent(event)

    def dragEnterEvent(self, event):
        # Check if the event contains file paths to accept it
        if event.mimeData().hasUrls():
            event.acceptProposedAction()

    def dragMoveEvent(self, event):
        # Check if the event contains file paths to accept it
        if event.mimeData().hasUrls():
            event.acceptProposedAction()

    def dropEvent(self, event):
        # Get the list of URLs from the event
        urls = event.mimeData().urls()

        # Extract local paths from the URLs
        paths = [url.toLocalFile() for url in urls]
        self.page_chat.attachment_bar.add_attachments(paths=paths)
        event.acceptProposedAction()


def launch():
    try:
        app = QApplication(sys.argv)
        app.setAttribute(Qt.AA_EnableHighDpiScaling)
        app.setStyle("Fusion")

        global loop
        loop = qasync.QEventLoop(app)
        asyncio.set_event_loop(loop)

        window = Main()
        window.show()
        
        with loop:
            loop.run_forever()

    except Exception as e:
        if 'AP_DEV_MODE' in os.environ:
            # When debugging in IDE, re-raise
            raise e
        display_message_box(
            icon=QMessageBox.Critical,
            title='Error',
            text=str(e)
        )
