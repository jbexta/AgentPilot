"""Desktop controller for computer use via pyautogui."""

import asyncio
import base64
import subprocess
from io import BytesIO

import pyautogui
from PIL import Image


KEY_MAP = {
    'Return': 'enter',
    'return': 'enter',
    'BackSpace': 'backspace',
    'space': 'space',
    'Left': 'left',
    'Right': 'right',
    'Up': 'up',
    'Down': 'down',
    'Page_Up': 'pageup',
    'Page_Down': 'pagedown',
    'super': 'win',
    'Tab': 'tab',
    'Escape': 'escape',
    'Delete': 'delete',
    'Home': 'home',
    'End': 'end',
    'Control_L': 'ctrl',
    'Control_R': 'ctrl',
    'Alt_L': 'alt',
    'Alt_R': 'alt',
    'Shift_L': 'shift',
    'Shift_R': 'shift',
    'Meta': 'win',
}


class ComputerUseDesktop:
    """Manages desktop control for computer use via pyautogui."""

    def __init__(self, grace_period=3.0):
        self.grace_period = grace_period
        self.cancelled = False
        self.overlay = None
        self._esc_listener = None
        logical_w, logical_h = pyautogui.size()
        max_dim = 1280
        scale = min(max_dim / logical_w, max_dim / logical_h, 1.0)
        self.target_w = int(logical_w * scale)
        self.target_h = int(logical_h * scale)
        self.scale_x = logical_w / self.target_w
        self.scale_y = logical_h / self.target_h

    def start_esc_listener(self):
        """Start global Esc key listener via pynput."""
        from pynput.keyboard import Key, Listener

        self.cancelled = False

        def on_press(key):
            if key == Key.esc:
                self.cancelled = True
                return False

        self._esc_listener = Listener(on_press=on_press, daemon=True)
        self._esc_listener.start()

    def stop_esc_listener(self):
        """Stop the global Esc key listener."""
        if self._esc_listener:
            self._esc_listener.stop()
            self._esc_listener = None

    async def launch(self):
        """No-op -- desktop is always available."""
        pyautogui.FAILSAFE = False

    async def screenshot(self):
        """Take desktop screenshot resized to target resolution."""
        if self.overlay:
            self.overlay.hide_overlay()
            await asyncio.sleep(0.05)
        img = await asyncio.to_thread(pyautogui.screenshot)
        if self.overlay:
            self.overlay.show_overlay()
        target = (self.target_w, self.target_h)
        if img.size != target:
            img = img.resize(target, Image.LANCZOS)
        buf = BytesIO()
        img.save(buf, format='PNG')
        return base64.b64encode(buf.getvalue()).decode('utf-8')

    async def click(self, x, y, button='left'):
        """Wait grace period, then click."""
        await asyncio.sleep(self.grace_period)
        if self.cancelled:
            return
        await asyncio.to_thread(pyautogui.click, x, y, button=button)

    async def double_click(self, x, y):
        """Double click at position."""
        await asyncio.sleep(self.grace_period)
        if self.cancelled:
            return
        await asyncio.to_thread(pyautogui.doubleClick, x, y)

    async def triple_click(self, x, y):
        """Triple click at position."""
        await asyncio.sleep(self.grace_period)
        if self.cancelled:
            return
        await asyncio.to_thread(pyautogui.click, x, y, clicks=3)

    async def type_text(self, text):
        """Type text. Uses xdotool for unicode support."""
        try:
            text.encode('ascii')
            await asyncio.to_thread(
                pyautogui.typewrite, text, interval=0.02
            )
        except UnicodeEncodeError:
            await asyncio.to_thread(
                subprocess.run,
                ['xdotool', 'type', '--clearmodifiers', text],
                check=True,
            )

    async def key_press(self, key):
        """Press a key or combo, translating Anthropic key names."""
        parts = key.split('+')
        mapped = [KEY_MAP.get(k.strip(), k.strip().lower())
                  for k in parts]
        if len(mapped) == 1:
            await asyncio.to_thread(pyautogui.press, mapped[0])
        else:
            await asyncio.to_thread(pyautogui.hotkey, *mapped)

    async def scroll(self, x, y, direction, amount):
        """Scroll at position."""
        await asyncio.to_thread(pyautogui.moveTo, x, y)
        clicks = amount * 3
        if direction == 'up':
            await asyncio.to_thread(pyautogui.scroll, clicks)
        elif direction == 'down':
            await asyncio.to_thread(pyautogui.scroll, -clicks)
        elif direction == 'left':
            await asyncio.to_thread(pyautogui.hscroll, -clicks)
        elif direction == 'right':
            await asyncio.to_thread(pyautogui.hscroll, clicks)

    async def drag(self, start_coord, end_coord):
        """Drag from start to end coordinates."""
        await asyncio.sleep(self.grace_period)
        if self.cancelled:
            return
        await asyncio.to_thread(
            pyautogui.moveTo, start_coord[0], start_coord[1]
        )
        await asyncio.to_thread(pyautogui.mouseDown)
        await asyncio.to_thread(
            pyautogui.moveTo, end_coord[0], end_coord[1],
            duration=0.5
        )
        await asyncio.to_thread(pyautogui.mouseUp)

    async def mouse_move(self, x, y):
        """Move mouse to position."""
        await asyncio.to_thread(pyautogui.moveTo, x, y)

    async def close(self):
        """No-op -- nothing to close."""
        pass

    async def execute_action(self, action_dict):
        """Execute an action dict from Anthropic's tool_use.

        Parameters
        ----------
        action_dict : dict
            Action from Anthropic, e.g.
            {"action": "left_click", "coordinate": [x, y]}

        Returns
        -------
        str
            Base64 PNG screenshot after action.
        """
        action = action_dict.get('action', '')
        coord = action_dict.get('coordinate', [0, 0])
        coord = [int(coord[0] * self.scale_x),
                 int(coord[1] * self.scale_y)]

        if action == 'left_click':
            await self.click(coord[0], coord[1], button='left')
        elif action == 'right_click':
            await self.click(coord[0], coord[1], button='right')
        elif action == 'middle_click':
            await self.click(coord[0], coord[1], button='middle')
        elif action == 'double_click':
            await self.double_click(coord[0], coord[1])
        elif action == 'triple_click':
            await self.triple_click(coord[0], coord[1])
        elif action == 'type':
            text = action_dict.get('text', '')
            await self.type_text(text)
        elif action == 'key':
            key = action_dict.get('text', '')
            await self.key_press(key)
        elif action == 'scroll':
            direction = action_dict.get('direction', 'down')
            amount = action_dict.get('amount', 3)
            await self.scroll(coord[0], coord[1], direction, amount)
        elif action == 'mouse_move':
            await self.mouse_move(coord[0], coord[1])
        elif action == 'drag':
            raw_start = action_dict.get('start_coordinate')
            if raw_start:
                start = [int(raw_start[0] * self.scale_x),
                         int(raw_start[1] * self.scale_y)]
            else:
                start = coord  # already scaled
            raw_end = action_dict.get('end_coordinate', [0, 0])
            end = [int(raw_end[0] * self.scale_x),
                   int(raw_end[1] * self.scale_y)]
            await self.drag(start, end)
        elif action == 'screenshot':
            pass
        elif action == 'cursor_position':
            pass

        return await self.screenshot()
