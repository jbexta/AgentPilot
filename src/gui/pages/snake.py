import random

from PySide6.QtCore import Qt, QRect, QTimer
from PySide6.QtGui import QColor, QPainter
from PySide6.QtWidgets import QSizePolicy, QWidget

from gui.gui_utils.layouts import CVBoxLayout
from gui.widgets.config_widget import ConfigWidget

_CELL = 20
_COLS = 20
_ROWS = 20
_BASE_INTERVAL = 150

_POWERUPS = {
    'slow':   (2.5,  35, 'SLOW MO',   '#00bcd4'),
    'speed':  (0.4,  25, 'SPEED UP',  '#ff9800'),
    'ghost':  (1.0,  30, 'GHOST',     '#9c27b0'),
    'double': (1.0,  40, 'x2 SCORE',  '#ffd600'),
}


class SnakeGame(QWidget):

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setSizePolicy(
            QSizePolicy.Expanding, QSizePolicy.Expanding,
        )
        self.setFocusPolicy(Qt.StrongFocus)
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._tick)
        self._init_state()
        self._timer.start(_BASE_INTERVAL)

    def _init_state(self):
        mid = (_COLS // 2, _ROWS // 2)
        self.snake = [mid, (mid[0] - 1, mid[1]), (mid[0] - 2, mid[1])]
        self.direction = (1, 0)
        self.next_direction = (1, 0)
        self.score = 0
        self.game_over = False
        self.powerup_cell = None
        self.powerup_ttl = 0
        self.active_powerup = None
        self.active_ticks = 0
        self.spawn_countdown = random.randint(15, 25)
        self._place_food()

    def _reset(self):
        self._init_state()
        self._timer.setInterval(_BASE_INTERVAL)

    def _place_food(self):
        occupied = set(self.snake)
        if self.powerup_cell:
            occupied.add(self.powerup_cell[:2])
        free = [
            (c, r) for c in range(_COLS) for r in range(_ROWS)
            if (c, r) not in occupied
        ]
        self.food = random.choice(free) if free else None

    def _spawn_powerup(self):
        occupied = set(self.snake)
        if self.food:
            occupied.add(self.food)
        free = [
            (c, r) for c in range(_COLS) for r in range(_ROWS)
            if (c, r) not in occupied
        ]
        if not free:
            return
        col, row = random.choice(free)
        key = random.choice(list(_POWERUPS))
        self.powerup_cell = (col, row, key)
        self.powerup_ttl = random.randint(18, 28)

    def _activate_powerup(self, key):
        mult, duration, _, _ = _POWERUPS[key]
        self.active_powerup = key
        self.active_ticks = duration
        self._timer.setInterval(int(_BASE_INTERVAL * mult))

    def _deactivate_powerup(self):
        self.active_powerup = None
        self.active_ticks = 0
        self._timer.setInterval(_BASE_INTERVAL)

    def _tick(self):
        if self.game_over:
            return

        if self.active_powerup:
            self.active_ticks -= 1
            if self.active_ticks <= 0:
                self._deactivate_powerup()

        if self.powerup_cell:
            self.powerup_ttl -= 1
            if self.powerup_ttl <= 0:
                self.powerup_cell = None

        if self.powerup_cell is None:
            self.spawn_countdown -= 1
            if self.spawn_countdown <= 0:
                self._spawn_powerup()
                self.spawn_countdown = random.randint(15, 25)

        self.direction = self.next_direction
        head = (
            (self.snake[0][0] + self.direction[0]) % _COLS,
            (self.snake[0][1] + self.direction[1]) % _ROWS,
        )

        ghost_active = self.active_powerup == 'ghost'
        if head in self.snake and not ghost_active:
            self.game_over = True
            self.update()
            return

        self.snake.insert(0, head)

        if head == self.food:
            points = 2 if self.active_powerup == 'double' else 1
            self.score += points
            self._place_food()
        elif (
            self.powerup_cell
            and head == self.powerup_cell[:2]
        ):
            self._activate_powerup(self.powerup_cell[2])
            self.powerup_cell = None
        else:
            self.snake.pop()

        self.update()

    def keyPressEvent(self, event):
        key = event.key()
        dx, dy = self.direction
        if key in (Qt.Key_Up, Qt.Key_W) and dy == 0:
            self.next_direction = (0, -1)
        elif key in (Qt.Key_Down, Qt.Key_S) and dy == 0:
            self.next_direction = (0, 1)
        elif key in (Qt.Key_Left, Qt.Key_A) and dx == 0:
            self.next_direction = (-1, 0)
        elif key in (Qt.Key_Right, Qt.Key_D) and dx == 0:
            self.next_direction = (1, 0)
        elif key == Qt.Key_Return and self.game_over:
            self._reset()
        else:
            super().keyPressEvent(event)

    def paintEvent(self, event):
        cell = min(self.width() // _COLS, self.height() // _ROWS)
        grid_w = cell * _COLS
        grid_h = cell * _ROWS
        ox = (self.width() - grid_w) // 2
        oy = (self.height() - grid_h) // 2
        pad = max(1, cell // 10)

        painter = QPainter(self)
        painter.fillRect(ox, oy, grid_w, grid_h, QColor('#1a1a2e'))

        if self.food:
            fx, fy = self.food
            painter.fillRect(
                ox + fx * cell + pad, oy + fy * cell + pad,
                cell - pad * 2, cell - pad * 2,
                QColor('#e94560'),
            )

        if self.powerup_cell:
            px, py, pkey = self.powerup_cell
            _, _, _, color = _POWERUPS[pkey]
            painter.fillRect(
                ox + px * cell + pad, oy + py * cell + pad,
                cell - pad * 2, cell - pad * 2,
                QColor(color),
            )

        ghost_active = self.active_powerup == 'ghost'
        for i, (sx, sy) in enumerate(self.snake):
            if ghost_active:
                color = (
                    QColor('#ce93d8') if i == 0 else QColor('#9c27b0')
                )
            else:
                color = (
                    QColor('#1565c0') if i == 0 else QColor('#42a5f5')
                )
            painter.fillRect(
                ox + sx * cell + 1, oy + sy * cell + 1,
                cell - 2, cell - 2, color,
            )

        painter.setPen(QColor('#ffffff'))
        painter.drawText(ox + 4, oy + 14, f'Score: {self.score}')

        if self.active_powerup:
            _, _, label, color = _POWERUPS[self.active_powerup]
            painter.setPen(QColor(color))
            painter.drawText(
                ox + grid_w - 90, oy + 14,
                f'{label} ({self.active_ticks})',
            )

        if self.game_over:
            grid_rect = QRect(ox, oy, grid_w, grid_h)
            painter.fillRect(grid_rect, QColor(0, 0, 0, 140))
            painter.setPen(QColor('#ffffff'))
            painter.drawText(
                grid_rect, Qt.AlignCenter,
                f'Game Over\nScore: {self.score}'
                f'\n\nPress Enter to restart',
            )


class Page_Snake_Settings(ConfigWidget):
    display_name = 'Snake'
    page_type = 'main'
    icon_path = ':/resources/icon-tasks.png'

    def __init__(self, parent):
        super().__init__(parent=parent)
        self.layout = CVBoxLayout(self)
        self.game = SnakeGame()
        self.layout.addWidget(self.game)
