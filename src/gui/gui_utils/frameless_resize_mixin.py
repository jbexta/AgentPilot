from PySide6.QtGui import Qt


class FramelessResizeMixin:
    """Mixin providing frameless window resize and move behaviour.

    Call :meth:`init_frameless_resize` from the subclass ``__init__``
    after setting the ``Qt.FramelessWindowHint`` window flag.
    """

    def init_frameless_resize(self, margin=10):
        """Initialise resize state variables.

        Parameters
        ----------
        margin : int
            Pixel width of the resize grab area along each edge.
        """
        self._mouse_pressed = False
        self._mouse_pos = None
        self._mouse_global_pos = None
        self._resizing = False
        self._resize_margins = margin

    # -- mouse events -----------------------------------------------

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self._mouse_pressed = True
            self._mouse_pos = event.pos()
            self._mouse_global_pos = event.globalPos()
            self._resizing = self._is_mouse_on_edge(event.pos())
            self._update_cursor_shape(event.pos())

    def mouseMoveEvent(self, event):
        if self._mouse_pressed:
            if self._resizing:
                self._resize_window(event.globalPos())
            else:
                self._move_window(event.globalPos())

    def mouseReleaseEvent(self, event):
        self._mouse_pressed = False
        self._resizing = False
        self._mouse_pos = None
        self._mouse_global_pos = None
        self.setCursor(Qt.ArrowCursor)

    # -- helpers ----------------------------------------------------

    def _is_mouse_on_edge(self, pos):
        rect = self.rect()
        m = self._resize_margins
        return (pos.x() < m
                or pos.x() > rect.width() - m
                or pos.y() < m
                or pos.y() > rect.height() - m)

    def _move_window(self, global_pos):
        if self._mouse_global_pos is None:
            return
        diff = global_pos - self._mouse_global_pos
        self.move(self.pos() + diff)
        self._mouse_global_pos = global_pos

    def _resize_window(self, global_pos):
        diff = global_pos - self._mouse_global_pos
        new_rect = self.geometry()
        m = self._resize_margins

        if self._mouse_pos.x() < m:
            new_rect.setLeft(new_rect.left() + diff.x())
        elif self._mouse_pos.x() > self.width() - m:
            new_rect.setRight(new_rect.right() + diff.x())

        if self._mouse_pos.y() < m:
            new_rect.setTop(new_rect.top() + diff.y())
        elif self._mouse_pos.y() > self.height() - m:
            new_rect.setBottom(new_rect.bottom() + diff.y())

        self.setGeometry(new_rect)
        self._mouse_pos = self.mapFromGlobal(global_pos)
        self._mouse_global_pos = global_pos

    def _update_cursor_shape(self, pos):
        rect = self.rect()
        m = self._resize_margins
        left = pos.x() < m
        right = pos.x() > rect.width() - m
        top = pos.y() < m
        bottom = pos.y() > rect.height() - m

        if (left and top) or (right and bottom):
            self.setCursor(Qt.SizeFDiagCursor)
        elif (left and bottom) or (right and top):
            self.setCursor(Qt.SizeBDiagCursor)
        elif left or right:
            self.setCursor(Qt.SizeHorCursor)
        elif top or bottom:
            self.setCursor(Qt.SizeVerCursor)
        else:
            self.setCursor(Qt.ArrowCursor)
