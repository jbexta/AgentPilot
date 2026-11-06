import ast
import sys

from PySide6.QtWidgets import *
from PySide6.QtCore import QEvent, QPoint, QTimer
from PySide6.QtGui import Qt
from typing_extensions import override

from gui.gui_utils.helpers import Attention
from gui.gui_utils.icon_button import IconButton
from gui.gui_utils.layouts import CVBoxLayout, CHBoxLayout
from gui.widgets.config_widget import ConfigWidget
from utils import sql
from utils.helpers import display_message, format_llm_tools, set_module_type


class FlipSplitterHandle(QSplitterHandle):
    def mousePressEvent(self, event):
        self.press_pos = event.position()
        super().mousePressEvent(event)

    def mouseReleaseEvent(self, event):
        super().mouseReleaseEvent(event)
        moved = (event.position() - self.press_pos).manhattanLength()
        if moved < QApplication.startDragDistance() and self.splitter().count() == 2:
            joined = self.splitter().parentWidget()
            joined.flip_btn.popup(self.mapTo(joined, event.position().toPoint()))


class FlipSplitter(QSplitter):
    def createHandle(self):
        return FlipSplitterHandle(self.orientation(), self)


class FlipButton(IconButton):
    def __init__(self, parent):
        super().__init__(parent=parent, icon_path=':/resources/icon-split.png', size=24,
                         target=parent.flip_orientation)
        self.setProperty('class', 'splitter-flip')
        self.timer = QTimer(self, interval=3000, timeout=lambda: self.underMouse() or self.hide())
        self.hide()

    def popup(self, pos):
        new = 'vertical' if self.parent.layout_type == 'horizontal' else 'horizontal'
        self.setToolTip(f'Switch to {new}')
        self.move(pos - QPoint(12, 12))
        self.show()
        self.raise_()
        self.timer.start()
        QApplication.instance().installEventFilter(self)

    def hideEvent(self, event):
        QApplication.instance().removeEventFilter(self)
        self.timer.stop()
        super().hideEvent(event)

    def eventFilter(self, obj, event):
        if event.type() == QEvent.MouseButtonPress and not self.underMouse():
            self.hide()
        return False


@set_module_type('Widgets')
class ConfigJoined(ConfigWidget):
    def __init__(self, parent, **kwargs):
        super().__init__(parent=parent)
        propagate_config = kwargs.get('propagate_config', None)
        if propagate_config is not None:
            self.propagate_config = propagate_config
        self.resize_inversion = kwargs.get('resize_inversion', False)
        self.layout_type = kwargs.get('layout_type', 'vertical')
        # self.propagate = kwargs.get('propagate', True)
        self.resizable = kwargs.get('resizable', False)
        self.layout = CVBoxLayout(self) if self.layout_type == 'vertical' else CHBoxLayout(self)

        if self.resizable:
            splitter_orientation = Qt.Horizontal if self.layout_type == 'horizontal' else Qt.Vertical
            self.splitter = FlipSplitter(splitter_orientation)
            self.splitter.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
            self.splitter.setChildrenCollapsible(False)
            self.layout.addWidget(self.splitter)
            self.flip_btn = FlipButton(self)
            self.call_sites = []
            frame = sys._getframe(1)
            while frame:
                self.call_sites.append((frame.f_globals['__name__'], frame.f_lineno))
                if frame.f_locals.get('self') is not self:
                    break
                frame = frame.f_back

        self.widgets = kwargs.get('widgets', [])
        self.add_stretch_to_end = kwargs.get('add_stretch_to_end', False)
        # self.user_editable = True

    @override
    def build_schema(self):
        for widget in self.widgets:
            if hasattr(widget, 'build_schema'):
                widget.build_schema()

            stretch = getattr(widget, 'stretch', 0)
            if self.resizable:
                self.splitter.addWidget(widget)
            else:
                self.layout.addWidget(widget, stretch)

        if self.add_stretch_to_end:
            self.layout.addStretch(1)
        
        if hasattr(self, 'after_init'):
            self.after_init()

    @override
    def load(self):
        for widget in self.widgets:
            if hasattr(widget, 'load'):
                widget.load()

    def flip_orientation(self):
        self.flip_btn.hide()
        new = 'vertical' if self.layout_type == 'horizontal' else 'horizontal'
        try:
            self.write_layout_type(new)
        except Exception as e:
            display_message(str(e), title='Cannot change orientation', icon=QMessageBox.Warning)
            return
        sizes = self.splitter.sizes()
        self.splitter.setOrientation(Qt.Vertical if new == 'vertical' else Qt.Horizontal)
        self.splitter.setSizes(sizes)
        self.layout_type = new

    def write_layout_type(self, new):
        class_names = {c.__name__ for c in type(self).__mro__} | {'__init__'}
        for module_name, lineno in self.call_sites:
            module = sys.modules[module_name]
            virtual = hasattr(module.__loader__, 'source_code')
            if virtual:
                old = module.__loader__.source_code
            else:
                with open(module.__file__, encoding='utf-8') as f:
                    old = f.read()

            call = next((
                n for n in ast.walk(ast.parse(old))
                if isinstance(n, ast.Call) and n.lineno == lineno
                and getattr(n.func, 'attr', getattr(n.func, 'id', None)) in class_names
            ), None)
            if not call:
                raise ValueError(f'{module_name}:{lineno} changed since load, restart to re-sync')

            kw = next((k for k in call.keywords if k.arg == 'layout_type'), None)
            if kw and isinstance(kw.value, ast.Constant):
                node, start, text = kw.value, kw.value.col_offset, repr(new)
            elif kw or any(k.arg is None for k in call.keywords):
                continue
            else:
                node = max(call.args + call.keywords, key=lambda n: (n.end_lineno, n.end_col_offset))
                start, text = node.end_col_offset, f', layout_type={new!r}'

            lines = old.splitlines(keepends=True)
            line = lines[node.end_lineno - 1].encode()
            lines[node.end_lineno - 1] = (line[:start] + text.encode() + line[node.end_col_offset:]).decode()
            source = ''.join(lines)

            if virtual:
                module.__loader__.source_code = source
            else:
                with open(module.__file__, 'w', encoding='utf-8') as f:
                    f.write(source)
            sql.execute(
                "UPDATE modules SET config = json_set(config, '$.data', ?) WHERE json_extract(config, '$.data') = ?",
                (source, old),
            )
            return

        module_name, lineno = self.call_sites[-1]
        raise ValueError(f'layout_type is set by an expression at {module_name}:{lineno}')

    @override
    def attention(self):
        return max(
            (w.attention() for w in self.widgets if hasattr(w, 'attention')),
            default=Attention.NONE,
        )

    @override
    def get_agent_visualisation(self, refs):
        parts = [format_llm_tools(self, refs), self.agent_visualisation()]
        for widget in self.widgets:
            if hasattr(widget, 'get_agent_visualisation'):
                parts.append(widget.get_agent_visualisation(refs))
        return '\n'.join(p for p in parts if p)

    @override
    def get_config(self):
        config = {}
        format_block_keys = []
        for widget in self.widgets:
            if not getattr(widget, 'propagate_config', True) or not hasattr(widget, 'get_config'):
                continue
            cc = widget.get_config()
            fbk = cc.pop('_format_block_keys', [])
            format_block_keys.extend(fbk)
            config.update(cc)
        if format_block_keys:
            config['_format_block_keys'] = format_block_keys
        return config