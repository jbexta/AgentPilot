"""Playwright browser manager for computer use."""

import asyncio
import base64

from playwright.async_api import async_playwright


RIPPLE_JS = """
(([x, y, duration]) => {
    const ripple = document.createElement('div');
    const size = 30;
    Object.assign(ripple.style, {
        position: 'fixed',
        left: (x - size / 2) + 'px',
        top: (y - size / 2) + 'px',
        width: size + 'px',
        height: size + 'px',
        borderRadius: '50%',
        border: '3px solid rgba(255, 0, 0, 0.8)',
        backgroundColor: 'rgba(255, 0, 0, 0.2)',
        pointerEvents: 'none',
        zIndex: '2147483647',
        animation: `computer-use-ripple ${duration}s ease-out forwards`,
    });
    const style = document.createElement('style');
    style.textContent = `
        @keyframes computer-use-ripple {
            0% { transform: scale(1); opacity: 1; }
            100% { transform: scale(4); opacity: 0; }
        }
    `;
    document.head.appendChild(style);
    document.body.appendChild(ripple);
    setTimeout(() => {
        ripple.remove();
        style.remove();
    }, duration * 1000);
})
"""

KEY_MAP = {
    'Return': 'Enter',
    'return': 'Enter',
    'BackSpace': 'Backspace',
    'space': ' ',
    'Left': 'ArrowLeft',
    'Right': 'ArrowRight',
    'Up': 'ArrowUp',
    'Down': 'ArrowDown',
    'Page_Up': 'PageUp',
    'Page_Down': 'PageDown',
    'super': 'Meta',
}


class ComputerUseBrowser:
    """Manages a Playwright browser for computer use."""

    def __init__(self, width=1280, height=800, grace_period=3.0):
        self.width = width
        self.height = height
        self.grace_period = grace_period
        self._playwright = None
        self.browser = None
        self.page = None
        self.cancelled = False

    async def launch(self):
        """Launch headful Chromium browser."""
        self._playwright = await async_playwright().start()
        self.browser = await self._playwright.chromium.launch(
            headless=False
        )
        context = await self.browser.new_context(
            viewport={'width': self.width, 'height': self.height}
        )
        self.page = await context.new_page()

    async def screenshot(self):
        """Take viewport screenshot, return base64 PNG."""
        png_bytes = await self.page.screenshot(type='png')
        return base64.b64encode(png_bytes).decode('utf-8')

    async def _show_ripple(self, x, y):
        """Inject ripple overlay and wait grace period."""
        await self.page.evaluate(
            RIPPLE_JS, [x, y, self.grace_period]
        )
        await asyncio.sleep(self.grace_period)

    async def click(self, x, y, button='left'):
        """Move mouse, show ripple, wait grace period, click."""
        await self.page.mouse.move(x, y)
        await self._show_ripple(x, y)
        if self.cancelled:
            return
        await self.page.mouse.click(x, y, button=button)

    async def double_click(self, x, y):
        """Double click with ripple effect."""
        await self.page.mouse.move(x, y)
        await self._show_ripple(x, y)
        if self.cancelled:
            return
        await self.page.mouse.dblclick(x, y)

    async def triple_click(self, x, y):
        """Triple click with ripple effect."""
        await self.page.mouse.move(x, y)
        await self._show_ripple(x, y)
        if self.cancelled:
            return
        await self.page.mouse.click(x, y, click_count=3)

    async def type_text(self, text):
        """Type text character by character."""
        await self.page.keyboard.type(text)

    async def key_press(self, key):
        """Press a key, translating Anthropic key names."""
        key = KEY_MAP.get(key, key)
        await self.page.keyboard.press(key)

    async def scroll(self, x, y, direction, amount):
        """Scroll at position."""
        await self.page.mouse.move(x, y)
        scroll_amount = amount * 100
        if direction == 'up':
            await self.page.mouse.wheel(0, -scroll_amount)
        elif direction == 'down':
            await self.page.mouse.wheel(0, scroll_amount)
        elif direction == 'left':
            await self.page.mouse.wheel(-scroll_amount, 0)
        elif direction == 'right':
            await self.page.mouse.wheel(scroll_amount, 0)

    async def drag(self, start_coord, end_coord):
        """Drag from start to end coordinates."""
        await self.page.mouse.move(start_coord[0], start_coord[1])
        await self._show_ripple(start_coord[0], start_coord[1])
        if self.cancelled:
            return
        await self.page.mouse.down()
        await self.page.mouse.move(end_coord[0], end_coord[1])
        await self.page.mouse.up()

    async def mouse_move(self, x, y):
        """Move mouse to position."""
        await self.page.mouse.move(x, y)

    async def close(self):
        """Close browser and playwright."""
        if self.browser:
            await self.browser.close()
            self.browser = None
        if self._playwright:
            await self._playwright.stop()
            self._playwright = None

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
            start = action_dict.get('start_coordinate', coord)
            end = action_dict.get('end_coordinate', [0, 0])
            await self.drag(start, end)
        elif action == 'screenshot':
            pass  # just take screenshot below
        elif action == 'cursor_position':
            pass  # just take screenshot

        return await self.screenshot()
