import json
import os
import tempfile
from dataclasses import dataclass
from enum import Enum
from functools import partial
from typing import List, Optional, Tuple

from PIL import Image, ImageChops, ImageDraw

from PySide6.QtWidgets import (
    QWidget, QSplitter, QLabel, QPushButton, QListWidget,
    QListWidgetItem, QGraphicsView, QGraphicsScene, QGraphicsPixmapItem,
    QFileDialog, QMessageBox, QGroupBox, QSlider, QComboBox, QColorDialog,
    QToolButton, QButtonGroup, QScrollArea
)
from PySide6.QtCore import (
    Qt, QPointF, QTimer, Signal
)
from PySide6.QtGui import (
    QPixmap, QImage, QPainter, QColor
)

from gui import system
from gui.gui_utils.helpers import find_main
from gui.gui_utils.custom_menu import CustomMenu
from gui.gui_utils.library_dialog import LibraryDialog
from gui.gui_utils.layouts import CVBoxLayout, CHBoxLayout
from plugins.studio.actions.base import UndoHistory, snapshot_layer
from plugins.studio.actions.layer_edit import record_layer_edit
from plugins.studio.actions.layer_structure import records_doc
from plugins.studio.tools.image.base import CanvasTool
from utils import sql
from utils.helpers import display_message, get_text, set_module_type


class BlendMode(Enum):
    """Layer blending modes."""
    NORMAL = "Normal"
    MULTIPLY = "Multiply"
    SCREEN = "Screen"
    OVERLAY = "Overlay"
    DARKEN = "Darken"
    LIGHTEN = "Lighten"
    ADD = "Add"
    SUBTRACT = "Subtract"


BLEND_FUNCS = {
    BlendMode.MULTIPLY: ImageChops.multiply,
    BlendMode.SCREEN: ImageChops.screen,
    BlendMode.OVERLAY: ImageChops.overlay,
    BlendMode.DARKEN: ImageChops.darker,
    BlendMode.LIGHTEN: ImageChops.lighter,
    BlendMode.ADD: ImageChops.add,
    BlendMode.SUBTRACT: ImageChops.subtract,
}


def shift_image(img: Image.Image, dx: int, dy: int, size: Tuple[int, int] = None) -> Image.Image:
    """Return img translated by (dx, dy) on a transparent image of the given size."""
    size = size or img.size
    if size == img.size and not dx and not dy:
        return img
    out = Image.new(img.mode, size, 0)
    out.paste(img, (int(dx), int(dy)))
    return out


def union_bounds(layers: List['Layer']) -> Tuple[int, int, int, int]:
    """Bounding box (left, top, right, bottom) covering all given layers in canvas space."""
    left = min(layer.x for layer in layers)
    top = min(layer.y for layer in layers)
    right = max(layer.x + layer.image.width for layer in layers)
    bottom = max(layer.y + layer.image.height for layer in layers)
    return left, top, right, bottom


def pil_to_pixmap(img: Image.Image) -> QPixmap:
    """Convert a PIL image to a QPixmap."""
    data = img.tobytes('raw', 'RGBA')
    qimage = QImage(data, img.width, img.height, QImage.Format_RGBA8888)
    return QPixmap.fromImage(qimage)


class ToolType(Enum):
    """Drawing tool types."""
    SELECT = "Select"
    MOVE = "Move"
    BRUSH = "Brush"
    ERASER = "Eraser"
    FILL = "Fill"
    EYEDROPPER = "Eyedropper"
    TEXT = "Text"
    SHAPE_RECT = "Rectangle"
    SHAPE_ELLIPSE = "Ellipse"
    SHAPE_LINE = "Line"
    TRANSFORM = "Transform"


@dataclass
class BrushSettings:
    """Brush tool settings."""
    size: int = 10
    hardness: float = 1.0
    opacity: float = 1.0
    color: Tuple[int, int, int, int] = (0, 0, 0, 255)


class Layer:
    """
    Base layer class for image editing.

    A layer contains an image with transparency and various properties
    like opacity, visibility, and blending mode.
    """

    def __init__(self, name: str, width: int, height: int):
        self.name = name
        self.width = width
        self.height = height
        self.visible = True
        self.opacity = 1.0
        self.blend_mode = BlendMode.NORMAL
        self.locked = False

        # Create transparent RGBA image
        self.image = Image.new('RGBA', (width, height), (0, 0, 0, 0))

        # Position and transform
        self.x = 0
        self.y = 0
        self.rotation = 0.0
        self.scale_x = 1.0
        self.scale_y = 1.0

    def get_pixmap(self) -> QPixmap:
        """Convert layer image to QPixmap."""
        # Apply opacity
        if self.opacity < 1.0:
            img = self.image.copy()
            alpha = img.split()[3]
            alpha = alpha.point(lambda p: int(p * self.opacity))
            img.putalpha(alpha)
        else:
            img = self.image

        return pil_to_pixmap(img)

    def composite(self, base: Image.Image, origin: Tuple[int, int] = (0, 0)) -> Image.Image:
        """Composite this layer onto base image, whose top-left is at `origin` in canvas space."""
        if not self.visible:
            return base

        # Apply opacity
        layer_img = self.image.copy()
        if self.opacity < 1.0:
            alpha = layer_img.split()[3]
            alpha = alpha.point(lambda p: int(p * self.opacity))
            layer_img.putalpha(alpha)

        # Apply the layer's position offset and fit to the base's size
        layer_img = shift_image(layer_img, self.x - origin[0], self.y - origin[1], size=base.size)

        if self.blend_mode == BlendMode.NORMAL:
            return Image.alpha_composite(base, layer_img)

        # Blend RGB channels against the base, then composite the result
        # using the layer's alpha so transparent areas leave the base intact
        blended = BLEND_FUNCS[self.blend_mode](
            base.convert('RGB'),
            layer_img.convert('RGB'),
        ).convert('RGBA')
        blended.putalpha(layer_img.split()[3])
        return Image.alpha_composite(base, blended)

    def stamp(self, stroke: Image.Image):
        """
        Composite a canvas-space RGBA stroke onto this layer, converting into
        layer space. The layer image grows to fit strokes outside its bounds.
        """
        bbox = stroke.getbbox()
        if not bbox:
            return

        left = min(0, bbox[0] - self.x)
        top = min(0, bbox[1] - self.y)
        right = max(self.image.width, bbox[2] - self.x)
        bottom = max(self.image.height, bbox[3] - self.y)
        if (left, top) != (0, 0) or (right, bottom) != self.image.size:
            grown = Image.new('RGBA', (right - left, bottom - top), 0)
            grown.paste(self.image, (-left, -top))
            self.image = grown
            self.x += left
            self.y += top
            self.width, self.height = self.image.size

        self.image = Image.alpha_composite(
            self.image, shift_image(stroke, -self.x, -self.y, size=self.image.size))

    def erase(self, mask: Image.Image):
        """Clear alpha where a canvas-space 'L' mask is set, converting into layer space."""
        mask = shift_image(mask, -self.x, -self.y, size=self.image.size)
        alpha = self.image.split()[3]
        alpha = Image.composite(Image.new('L', alpha.size, 0), alpha, mask)
        self.image.putalpha(alpha)

    def clear(self):
        """Clear layer content."""
        self.image = Image.new('RGBA', (self.width, self.height), (0, 0, 0, 0))

    def fill(self, color: Tuple[int, int, int, int]):
        """Fill layer with color."""
        self.image = Image.new('RGBA', (self.width, self.height), color)


class RasterLayer(Layer):
    """Standard raster/bitmap layer."""

    def __init__(self, name: str, width: int, height: int):
        super().__init__(name, width, height)


class ImageLayer(Layer):
    """Layer created from an image file."""

    def __init__(self, name: str, filepath: str):
        img = Image.open(filepath).convert('RGBA')
        super().__init__(name, img.width, img.height)
        self.image = img
        self.filepath = filepath


@set_module_type('Studios')
class ImageStudio(QWidget):
    """
    Full-featured image editor studio similar to Photoshop.

    Features:
    - Layer-based editing with blending modes
    - Undo/redo history
    - Drawing tools (brush, eraser, shapes, text)
    - Selection tools
    - Filters and adjustments
    - Transform operations
    - Export to various formats
    """

    associated_extensions = ['png', 'jpg', 'jpeg', 'bmp', 'gif', 'tiff', 'webp', 'svg']
    modified = Signal()

    def __init__(self, parent=None, full_screen=True):
        super().__init__(parent)
        self.main = find_main()
        self.full_screen = full_screen

        # Document properties
        self.canvas_width = 1920
        self.canvas_height = 1080
        self.layers: List[Layer] = []
        self.current_layer: Optional[Layer] = None

        # Tool state
        self.current_tool = ToolType.BRUSH
        self.brush_settings = BrushSettings()
        self.foreground_color = QColor(0, 0, 0, 255)
        self.background_color = QColor(255, 255, 255, 255)

        # Undo/redo history (per-studio, in-memory)
        self.undo_history = UndoHistory(on_record=self.modified.emit)

        # Build UI
        self.layout = CVBoxLayout(self)

        # Menu/toolbar
        # menu = 
        self.toolbar = self.ImageContextMenu(self)
        self.layout.addWidget(self.toolbar)

        # Main splitter
        main_splitter = QSplitter(Qt.Horizontal)

        # Left panel: Tools
        self.tools_panel = self._create_tools_panel()
        main_splitter.addWidget(self.tools_panel)

        # Center panel: Canvas
        self.canvas_panel = self._create_canvas_panel()
        main_splitter.addWidget(self.canvas_panel)

        # Right panel: Layers and properties
        self.right_panel = self._create_right_panel()
        main_splitter.addWidget(self.right_panel)

        main_splitter.setSizes([150, 1200, 300])

        self.layout.addWidget(main_splitter)

        self.set_fullscreen(self.full_screen)

        # Initialize with a default layer
        self.clear_project(self.canvas_width, self.canvas_height)
    
    def set_fullscreen(self, fullscreen):
        """Toggle fullscreen mode."""
        self.full_screen = fullscreen
        self.toolbar.setVisible(not fullscreen)
        self.tools_panel.setVisible(not fullscreen)
        self.right_panel.setVisible(not fullscreen)
        if not fullscreen:
            studio_button = self.canvas.studio_button.hide()

    class ImageContextMenu(CustomMenu):
        """Context menu for image studio."""

        def __init__(self, parent):
            super().__init__(parent)
            self.schema = [
                {
                    'text': 'File',
                    'submenu': [
                        {'text': 'New', 'target': parent.new_document},
                        {'text': 'Open', 'target': parent.open_file},
                        {'text': 'Save', 'target': parent.save_project},
                        {'text': 'Export', 'target': parent.export_image},
                    ],
                },
                {
                    'text': 'Edit',
                    'submenu': parent.edit_menu_schema,
                },
                {
                    'text': 'Layer',
                    'submenu': parent.layer_menu_schema(),
                },
            ]
            self.create_menubar(parent)

    def edit_menu_schema(self):
        """Schema for the Edit menu, labelled with the next undo/redo action."""
        undo_label = self.undo_history.next_undo_label()
        redo_label = self.undo_history.next_redo_label()
        return [
            {
                'text': f'Undo ({undo_label})' if undo_label else 'Undo',
                'target': self.undo_history.undo,
                'enabled': undo_label is not None,
            },
            {
                'text': f'Redo ({redo_label})' if redo_label else 'Redo',
                'target': self.undo_history.redo,
                'enabled': redo_label is not None,
            },
        ]

    def layer_menu_schema(self):
        """Schema for the Layer menu, shared by the toolbar dropdown and the layers panel context menu."""
        return [
            {'text': 'New Layer', 'target': self.add_layer},
            {'text': 'Layer from File...', 'target': self.layer_from_file},
            {'text': 'Duplicate Layer', 'target': self.duplicate_layer},
            {'text': 'Delete Layer', 'target': self.delete_layer},
            {'text': 'Rename Layer...', 'target': self.rename_layer},
            {'type': 'separator'},
            {'text': 'Raise Layer', 'target': self.raise_layer},
            {'text': 'Lower Layer', 'target': self.lower_layer},
            {'type': 'separator'},
            {'text': 'Toggle Visibility', 'target': self.toggle_layer_visibility},
            {'text': 'Toggle Lock', 'target': self.toggle_layer_lock},
            {'type': 'separator'},
            {'text': 'Merge Down', 'target': self.merge_down},
            {'text': 'Merge Visible', 'target': self.merge_visible},
            {'text': 'Flatten Image', 'target': self.flatten_image},
            {'type': 'separator'},
            {'text': 'Run Workflow', 'submenu': self.workflow_menu_schema},
        ]

    def _create_tools_panel(self):
        """Create left panel with drawing tools."""
        panel = QWidget()
        layout = CVBoxLayout(panel)

        tools_group = QGroupBox("Tools")
        tools_layout = CVBoxLayout(tools_group)

        # Tool buttons
        self.tool_buttons = {}
        self.tool_button_group = QButtonGroup(self)

        tools_config = [
            (ToolType.SELECT, "☐", "Selection Tool"),
            (ToolType.MOVE, "✥", "Move Tool"),
            (ToolType.BRUSH, "🖌", "Brush Tool"),
            (ToolType.ERASER, "⌫", "Eraser Tool"),
            (ToolType.FILL, "🪣", "Fill Tool"),
            (ToolType.EYEDROPPER, "💧", "Eyedropper Tool"),
            (ToolType.TEXT, "T", "Text Tool"),
            (ToolType.SHAPE_RECT, "▭", "Rectangle Tool"),
            (ToolType.SHAPE_ELLIPSE, "○", "Ellipse Tool"),
            (ToolType.SHAPE_LINE, "╱", "Line Tool"),
        ]

        for tool_type, icon, tooltip in tools_config:
            btn = QToolButton()
            btn.setText(icon)
            btn.setToolTip(tooltip)
            btn.setCheckable(True)
            btn.setFixedSize(40, 40)
            btn.clicked.connect(lambda checked=False, t=tool_type: self.select_tool(t))
            self.tool_buttons[tool_type] = btn
            self.tool_button_group.addButton(btn)
            tools_layout.addWidget(btn)

        # Set default tool
        self.tool_buttons[ToolType.BRUSH].setChecked(True)

        tools_layout.addStretch()
        layout.addWidget(tools_group)

        # Color swatches
        color_group = QGroupBox("Colors")
        color_layout = CVBoxLayout(color_group)

        colors_h = CHBoxLayout()

        self.fg_color_btn = QPushButton()
        self.fg_color_btn.setFixedSize(40, 40)
        self.fg_color_btn.clicked.connect(self.choose_foreground_color)
        self.update_color_button(self.fg_color_btn, self.foreground_color)
        colors_h.addWidget(self.fg_color_btn)

        self.bg_color_btn = QPushButton()
        self.bg_color_btn.setFixedSize(40, 40)
        self.bg_color_btn.clicked.connect(self.choose_background_color)
        self.update_color_button(self.bg_color_btn, self.background_color)
        colors_h.addWidget(self.bg_color_btn)

        color_layout.addLayout(colors_h)
        layout.addWidget(color_group)

        # Brush settings
        brush_group = QGroupBox("Brush")
        brush_layout = CVBoxLayout(brush_group)

        # Size
        brush_layout.addWidget(QLabel("Size:"))
        self.brush_size_slider = QSlider(Qt.Horizontal)
        self.brush_size_slider.setRange(1, 200)
        self.brush_size_slider.setValue(self.brush_settings.size)
        self.brush_size_slider.valueChanged.connect(self.on_brush_size_changed)
        brush_layout.addWidget(self.brush_size_slider)

        self.brush_size_label = QLabel(f"{self.brush_settings.size}px")
        brush_layout.addWidget(self.brush_size_label)

        # Opacity
        brush_layout.addWidget(QLabel("Opacity:"))
        self.brush_opacity_slider = QSlider(Qt.Horizontal)
        self.brush_opacity_slider.setRange(1, 100)
        self.brush_opacity_slider.setValue(int(self.brush_settings.opacity * 100))
        self.brush_opacity_slider.valueChanged.connect(self.on_brush_opacity_changed)
        brush_layout.addWidget(self.brush_opacity_slider)

        self.brush_opacity_label = QLabel(f"{int(self.brush_settings.opacity * 100)}%")
        brush_layout.addWidget(self.brush_opacity_label)

        # Hardness
        brush_layout.addWidget(QLabel("Hardness:"))
        self.brush_hardness_slider = QSlider(Qt.Horizontal)
        self.brush_hardness_slider.setRange(0, 100)
        self.brush_hardness_slider.setValue(int(self.brush_settings.hardness * 100))
        self.brush_hardness_slider.valueChanged.connect(self.on_brush_hardness_changed)
        brush_layout.addWidget(self.brush_hardness_slider)

        self.brush_hardness_label = QLabel(f"{int(self.brush_settings.hardness * 100)}%")
        brush_layout.addWidget(self.brush_hardness_label)

        layout.addWidget(brush_group)

        layout.addStretch()

        return panel

    def _create_canvas_panel(self):
        """Create center panel with canvas."""
        panel = QWidget()
        layout = CVBoxLayout(panel)

        # Canvas view
        self.canvas = ImageCanvas(self)
        layout.addWidget(self.canvas)

        # Canvas controls
        controls = CHBoxLayout()

        # Zoom controls
        controls.addWidget(QLabel("Zoom:"))

        zoom_out_btn = QPushButton("-")
        zoom_out_btn.clicked.connect(self.canvas.zoom_out)
        controls.addWidget(zoom_out_btn)

        self.zoom_label = QLabel("100%")
        controls.addWidget(self.zoom_label)

        zoom_in_btn = QPushButton("+")
        zoom_in_btn.clicked.connect(self.canvas.zoom_in)
        controls.addWidget(zoom_in_btn)

        zoom_fit_btn = QPushButton("Fit")
        zoom_fit_btn.clicked.connect(self.canvas.zoom_fit)
        controls.addWidget(zoom_fit_btn)

        controls.addStretch()

        layout.addLayout(controls)

        return panel

    def _create_right_panel(self):
        """Create right panel with layers and properties."""
        panel = QWidget()
        layout = CVBoxLayout(panel)

        # Layers panel
        self.layers_panel = LayersPanel(self)
        layout.addWidget(self.layers_panel)

        # Properties panel
        self.properties_panel = PropertiesPanel(self)
        layout.addWidget(self.properties_panel)

        return panel

    def composite_layers(self, background=(0, 0, 0, 0), layers=None) -> Image.Image:
        """Composite layers (all by default) onto a new canvas-sized image."""
        result = Image.new('RGBA', (self.canvas_width, self.canvas_height), background)
        for layer in (self.layers if layers is None else layers):
            result = layer.composite(result)
        return result

    def clear_project(self, width: int, height: int):
        """Create a new document with given dimensions."""
        self.canvas_width = width
        self.canvas_height = height
        self.layers.clear()

        # Create background layer
        background = RasterLayer("Background", width, height)
        background.fill((255, 255, 255, 255))
        self.layers.append(background)
        self.current_layer = background

        # Update canvas
        self.canvas.setup_canvas(width, height)
        self.canvas.update_display()

        # Update layers panel
        self.layers_panel.refresh_layers()

        # Clear history
        self.undo_history.clear()

    def new_document(self):
        """Create a new document."""
        reply = QMessageBox.question(
            self,
            "New Document",
            "Create a new document? Unsaved changes will be lost.",
            QMessageBox.Yes | QMessageBox.No
        )

        if reply == QMessageBox.Yes:
            self.clear_project(self.canvas_width, self.canvas_height)

    def open_file(self, filepath: str = None):
        """Open an image file."""
        if not filepath:
            filepath, _ = QFileDialog.getOpenFileName(
                self,
                "Open Image",
                "",
                "Image Files (*.png *.jpg *.jpeg *.bmp *.gif *.tiff *.webp *.svg);;All Files (*)"
            )

        if not filepath or not os.path.exists(filepath):
            return

        try:
            # Load image
            if filepath.lower().endswith('.svg'):
                qimage = QImage(filepath).convertToFormat(
                    QImage.Format_RGBA8888)
                if qimage.isNull():
                    raise ValueError('Unreadable SVG')
                img = Image.frombytes(
                    'RGBA', (qimage.width(), qimage.height()),
                    qimage.constBits().tobytes(),
                    'raw', 'RGBA', qimage.bytesPerLine())
            else:
                img = Image.open(filepath).convert('RGBA')

            # Create new document with image size
            self.clear_project(img.width, img.height)

            # Replace background layer with image
            self.layers[0].image = img
            self.layers[0].name = os.path.basename(filepath)

            # Update display
            self.canvas.update_display()
            self.layers_panel.refresh_layers()

            # Fit image to screen
            self.canvas.zoom_fit()

        except Exception as e:
            QMessageBox.critical(self, "Error", f"Failed to open image: {str(e)}")

    def save_project(self):
        """Save project file."""
        filepath, _ = QFileDialog.getSaveFileName(
            self,
            "Save Project",
            "",
            "Image Studio Project (*.isp);;All Files (*)"
        )

        if filepath:
            self._save_project(filepath)

    def _save_project(self, filepath: str):
        """Save project to file."""
        try:
            project_data = {
                'width': self.canvas_width,
                'height': self.canvas_height,
                'layers': []
            }

            # Save each layer
            base_path = os.path.splitext(filepath)[0]
            os.makedirs(f"{base_path}_layers", exist_ok=True)

            for i, layer in enumerate(self.layers):
                layer_path = f"{base_path}_layers/layer_{i}.png"
                layer.image.save(layer_path, 'PNG')

                project_data['layers'].append({
                    'name': layer.name,
                    'image_path': layer_path,
                    'visible': layer.visible,
                    'opacity': layer.opacity,
                    'locked': layer.locked,
                    'blend_mode': layer.blend_mode.value,
                    'x': layer.x,
                    'y': layer.y,
                })

            with open(filepath, 'w') as f:
                json.dump(project_data, f, indent=2)

            QMessageBox.information(self, "Success", "Project saved successfully!")

        except Exception as e:
            QMessageBox.critical(self, "Error", f"Failed to save project: {str(e)}")

    def export_image(self):
        """Export flattened image."""
        filepath, _ = QFileDialog.getSaveFileName(
            self,
            "Export Image",
            "",
            "PNG (*.png);;JPEG (*.jpg);;All Files (*)"
        )

        if filepath:
            self._export_image(filepath)

    def _export_image(self, filepath: str):
        """Export the composite image to file."""
        try:
            result = self.composite_layers(background=(255, 255, 255, 255))

            # Convert to RGB if saving as JPEG
            if filepath.lower().endswith(('.jpg', '.jpeg')):
                result = result.convert('RGB')

            result.save(filepath)
            QMessageBox.information(self, "Success", "Image exported successfully!")

        except Exception as e:
            QMessageBox.critical(self, "Error", f"Failed to export image: {str(e)}")

    def select_tool(self, tool: ToolType):
        """Select a drawing tool."""
        self.current_tool = tool
        self.canvas.set_tool(tool)

        # Update tool button states
        for tool_type, btn in self.tool_buttons.items():
            btn.setChecked(tool_type == tool)

    def choose_foreground_color(self):
        """Choose foreground color."""
        color = QColorDialog.getColor(self.foreground_color, self, "Choose Foreground Color")
        if color.isValid():
            self.foreground_color = color
            self.update_color_button(self.fg_color_btn, color)
            self.canvas.set_foreground_color(color)

    def choose_background_color(self):
        """Choose background color."""
        color = QColorDialog.getColor(self.background_color, self, "Choose Background Color")
        if color.isValid():
            self.background_color = color
            self.update_color_button(self.bg_color_btn, color)

    def update_color_button(self, button: QPushButton, color: QColor):
        """Update color button appearance."""
        button.setStyleSheet(f"background-color: {color.name()}; border: 1px solid #000;")

    def on_brush_size_changed(self, value: int):
        """Handle brush size change."""
        self.brush_settings.size = value
        self.brush_size_label.setText(f"{value}px")
        self.canvas.set_brush_size(value)

    def on_brush_opacity_changed(self, value: int):
        """Handle brush opacity change."""
        self.brush_settings.opacity = value / 100.0
        self.brush_opacity_label.setText(f"{value}%")
        self.canvas.set_brush_opacity(value / 100.0)

    def on_brush_hardness_changed(self, value: int):
        """Handle brush hardness change."""
        self.brush_settings.hardness = value / 100.0
        self.brush_hardness_label.setText(f"{value}%")
        self.canvas.set_brush_hardness(value / 100.0)

    @records_doc()
    def add_layer(self):
        """Add a new layer."""
        layer = RasterLayer(f"Layer {len(self.layers) + 1}", self.canvas_width, self.canvas_height)
        self.layers.append(layer)
        self.current_layer = layer
        self.layers_panel.refresh_layers()
        self.canvas.update_display()

    @records_doc()
    def layer_from_file(self):
        """Add a new layer from an image file."""
        filepath, _ = QFileDialog.getOpenFileName(
            self,
            "Layer from File",
            "",
            "Image Files (*.png *.jpg *.jpeg *.bmp *.gif *.tiff *.webp);;All Files (*)"
        )

        if not filepath or not os.path.exists(filepath):
            return

        try:
            img = Image.open(filepath).convert('RGBA')
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Failed to open image: {str(e)}")
            return

        layer = RasterLayer(os.path.basename(filepath), self.canvas_width, self.canvas_height)
        layer.image.paste(img, (0, 0))
        self.layers.append(layer)
        self.current_layer = layer
        self.layers_panel.refresh_layers()
        self.canvas.update_display()

    @records_doc()
    def rename_layer(self):
        """Rename the current layer."""
        if not self.current_layer:
            return

        name, ok = get_text(self, "Rename Layer", "Layer name:", text=self.current_layer.name)
        if ok and name:
            self.current_layer.name = name
            self.layers_panel.refresh_layers()

    def raise_layer(self):
        """Move the current layer up in the stack."""
        self._move_layer(1)

    def lower_layer(self):
        """Move the current layer down in the stack."""
        self._move_layer(-1)

    @records_doc()
    def _move_layer(self, offset: int):
        if not self.current_layer:
            return

        index = self.layers.index(self.current_layer)
        new_index = index + offset
        if new_index < 0 or new_index >= len(self.layers):
            return

        self.layers[index], self.layers[new_index] = self.layers[new_index], self.layers[index]
        self.layers_panel.refresh_layers()
        self.canvas.update_display()

    @records_doc()
    def toggle_layer_visibility(self):
        """Toggle visibility of the current layer."""
        if self.current_layer:
            self.current_layer.visible = not self.current_layer.visible
            self.layers_panel.refresh_layers()
            self.canvas.update_display()

    @records_doc()
    def toggle_layer_lock(self):
        """Toggle lock of the current layer."""
        if self.current_layer:
            self.current_layer.locked = not self.current_layer.locked
            self.layers_panel.refresh_layers()

    @records_doc()
    def delete_layer(self):
        """Delete the current layer."""
        if len(self.layers) <= 1:
            QMessageBox.warning(self, "Warning", "Cannot delete the last layer!")
            return

        if self.current_layer in self.layers:
            self.layers.remove(self.current_layer)
            self.current_layer = self.layers[-1] if self.layers else None
            self.layers_panel.refresh_layers()
            self.canvas.update_display()

    @records_doc()
    def duplicate_layer(self):
        """Duplicate the current layer."""
        if self.current_layer:
            new_layer = RasterLayer(f"{self.current_layer.name} copy", self.canvas_width, self.canvas_height)
            new_layer.image = self.current_layer.image.copy()
            new_layer.opacity = self.current_layer.opacity
            new_layer.blend_mode = self.current_layer.blend_mode
            new_layer.x, new_layer.y = self.current_layer.x, self.current_layer.y
            self.layers.append(new_layer)
            self.current_layer = new_layer
            self.layers_panel.refresh_layers()
            self.canvas.update_display()

    @records_doc(pixels=True)
    def merge_down(self):
        """Merge current layer with layer below."""
        if not self.current_layer or len(self.layers) <= 1:
            return

        current_index = self.layers.index(self.current_layer)
        if current_index == 0:
            QMessageBox.warning(self, "Warning", "Cannot merge down the bottom layer!")
            return

        # Merge in the union of both layers' bounds so off-canvas content survives
        lower_layer = self.layers[current_index - 1]
        left, top, right, bottom = union_bounds([lower_layer, self.current_layer])
        merged = Image.new('RGBA', (right - left, bottom - top), 0)
        merged.paste(lower_layer.image, (lower_layer.x - left, lower_layer.y - top))
        lower_layer.image = self.current_layer.composite(merged, origin=(left, top))
        lower_layer.x, lower_layer.y = left, top
        lower_layer.width, lower_layer.height = lower_layer.image.size

        # Remove current layer
        self.layers.remove(self.current_layer)
        self.current_layer = lower_layer

        self.layers_panel.refresh_layers()
        self.canvas.update_display()

    @records_doc(pixels=True)
    def merge_visible(self):
        """Merge all visible layers into one, keeping hidden layers in place."""
        visible = [layer for layer in self.layers if layer.visible]
        if len(visible) <= 1:
            return

        # Merge in the union of the visible layers' bounds so off-canvas content survives
        left, top, right, bottom = union_bounds(visible)
        merged = RasterLayer("Merged", right - left, bottom - top)
        for layer in visible:
            merged.image = layer.composite(merged.image, origin=(left, top))
        merged.x, merged.y = left, top

        insert_at = self.layers.index(visible[0])
        self.layers = [layer for layer in self.layers if not layer.visible]
        self.layers.insert(insert_at, merged)
        self.current_layer = merged

        self.layers_panel.refresh_layers()
        self.canvas.update_display()

    @records_doc(pixels=True)
    def flatten_image(self):
        """Flatten all layers into one."""
        if len(self.layers) <= 1:
            return

        # Keep only one layer
        background = RasterLayer("Background", self.canvas_width, self.canvas_height)
        background.image = self.composite_layers(background=(255, 255, 255, 255))
        self.layers.clear()
        self.layers.append(background)
        self.current_layer = background

        self.layers_panel.refresh_layers()
        self.canvas.update_display()

    def workflow_menu_schema(self):
        """Schema for the 'Run Workflow' submenu: library picker + recently used."""
        schema = [
            {'text': 'Choose from library...', 'target': self.choose_workflow_from_library},
        ]

        # Recently used = the entities linked to the latest STUDIO context runs
        recents = sql.get_results("""
            SELECT json_extract(config, '$.linked_id') AS linked
            FROM contexts
            WHERE kind = 'STUDIO'
                AND json_extract(config, '$.linked_id') IS NOT NULL
            GROUP BY linked
            ORDER BY MAX(id) DESC
            LIMIT 8""", return_type='list')
        recent_items = []
        for linked in recents:
            entity_table, _, entity_uuid = linked.partition('.')
            name = sql.get_scalar(
                f"SELECT name FROM `{entity_table}` WHERE uuid = ?", (entity_uuid,)
            )
            if name:
                recent_items.append({
                    'text': name,
                    'target': partial(self.run_workflow_on_layer, entity_uuid, entity_table),
                })
        if recent_items:
            schema.append({'type': 'separator'})
            schema.extend(recent_items)
        return schema

    def choose_workflow_from_library(self):
        """Pick an entity from the library and run it on the current layer."""
        dialog = LibraryDialog(
            parent=self,
            callback=self._on_library_workflow_chosen,
            kind='conversation',
        )
        dialog.open()

    def _on_library_workflow_chosen(self, item, link=False):
        entity_uuid = item.text(1)
        entity_table = item.text(3)
        self.run_workflow_on_layer(entity_uuid, entity_table)

    def run_workflow_on_layer(self, entity_uuid: str, entity_table: str = 'entities'):
        """Run an entity workflow on the current layer's image."""
        from plugins.workflows.widgets.workflow_popup import run_entity_workflow_on_file

        layer = self.current_layer
        if not layer:
            return
        if layer.locked:
            display_message("Layer is locked", "Run Workflow")
            return

        fd, input_path = tempfile.mkstemp(prefix='layer_', suffix='.png')
        os.close(fd)
        layer.image.save(input_path, 'PNG')

        run_entity_workflow_on_file(
            parent=self,
            entity_uuid=entity_uuid,
            entity_table=entity_table,
            filepath=input_path,
            on_result=partial(self._replace_layer_image, layer),
        )

    def _replace_layer_image(self, layer: Layer, filepath: str):
        """Replace a layer's pixels in place with the image at filepath."""
        if layer not in self.layers:
            display_message("The layer no longer exists", "Run Workflow")
            return
        try:
            img = Image.open(filepath).convert('RGBA')
        except Exception as e:
            display_message(f"Failed to load image: {e}", "Run Workflow")
            return
        before = snapshot_layer(layer, pixels=True)
        layer.image = img
        layer.width, layer.height = img.size
        record_layer_edit(self, layer, before)
        self.layers_panel.refresh_layers()
        self.canvas.update_display()


class ImageCanvas(QGraphicsView):
    """Canvas for image editing with drawing tools."""

    def __init__(self, studio: ImageStudio):
        super().__init__()
        self.studio = studio
        self.scene = QGraphicsScene(self)
        self.setScene(self.scene)

        # View settings
        self.setRenderHint(QPainter.Antialiasing)
        self.setRenderHint(QPainter.SmoothPixmapTransform)
        self.setDragMode(QGraphicsView.NoDrag)
        self.setTransformationAnchor(QGraphicsView.AnchorUnderMouse)
        self.setResizeAnchor(QGraphicsView.AnchorUnderMouse)

        # Canvas items
        self.canvas_item: Optional[QGraphicsPixmapItem] = None
        self.zoom_level = 1.0
        self.auto_fit = True  # refit on resize until the user zooms manually

        # Drawing state
        self.is_drawing = False
        self.stroke_layer: Optional[Layer] = None
        self.stroke_before = None  # snapshot of stroke_layer taken on press, for undo
        self.last_point: Optional[QPointF] = None
        self.current_tool = ToolType.BRUSH
        self.active_tool = CanvasTool(self)
        self.brush_size = 10
        self.brush_opacity = 1.0
        self.brush_hardness = 1.0
        self.foreground_color = QColor(0, 0, 0, 255)

        # PIL draw object for current stroke
        self.temp_layer: Optional[Image.Image] = None
        self.temp_draw: Optional[ImageDraw.ImageDraw] = None

        # Floating "Open in studio" button
        self.studio_button = QPushButton("Open in studio", self)
        self.studio_button.setObjectName('imageStudioOpenButton')
        self.studio_button.setCursor(Qt.PointingHandCursor)
        self.studio_button.clicked.connect(lambda: self.studio.set_fullscreen(not self.studio.full_screen))
        self.studio_button.hide()  # Hidden by default

        # Enable mouse tracking to detect hover
        self.setMouseTracking(True)

        self.set_tool(self.current_tool)

    def setup_canvas(self, width: int, height: int):
        """Setup canvas with given dimensions."""
        self.scene.clear()
        self.canvas_item = QGraphicsPixmapItem()
        self.scene.addItem(self.canvas_item)
        self.scene.setSceneRect(0, 0, width, height)

    def update_display(self):
        """Update canvas display with composite of all layers."""
        if not self.studio.layers or not self.canvas_item:
            return

        # Composite all visible layers
        result = self.studio.composite_layers(background=(255, 255, 255, 0))
        self.canvas_item.setPixmap(pil_to_pixmap(result))

    def set_tool(self, tool: ToolType):
        """Set the current tool, resolving its handler from the image_tools modules."""
        self.current_tool = tool
        tool_class = system.manager.modules.get_module_class('Image_tools', tool.name.lower())
        self.active_tool = tool_class(self) if tool_class else CanvasTool(self)
        self.viewport().setCursor(self.active_tool.cursor)

    def set_foreground_color(self, color: QColor):
        """Set foreground color."""
        self.foreground_color = color

    def set_brush_size(self, size: int):
        """Set brush size."""
        self.brush_size = size

    def set_brush_opacity(self, opacity: float):
        """Set brush opacity."""
        self.brush_opacity = opacity

    def set_brush_hardness(self, hardness: float):
        """Set brush hardness."""
        self.brush_hardness = hardness

    def zoom_in(self):
        """Zoom in."""
        self.auto_fit = False
        self.zoom_level *= 1.2
        self.scale(1.2, 1.2)
        self.studio.zoom_label.setText(f"{int(self.zoom_level * 100)}%")

    def zoom_out(self):
        """Zoom out."""
        self.auto_fit = False
        self.zoom_level /= 1.2
        self.scale(1.0 / 1.2, 1.0 / 1.2)
        self.studio.zoom_label.setText(f"{int(self.zoom_level * 100)}%")

    def zoom_fit(self):
        """Zoom to fit canvas in view."""
        self.auto_fit = True
        self.fitInView(self.scene.sceneRect(), Qt.KeepAspectRatio)
        self.zoom_level = self.transform().m11()
        self.studio.zoom_label.setText(f"{int(self.zoom_level * 100)}%")

    def position_studio_button(self):
        """Position the studio button in the top right corner."""
        button_width = self.studio_button.sizeHint().width()
        button_height = self.studio_button.sizeHint().height()
        margin = 10
        x = self.width() - button_width - margin
        y = margin
        self.studio_button.setGeometry(x, y, button_width, button_height)
        self.studio_button.raise_()

    def resizeEvent(self, event):
        """Handle widget resize to reposition studio button."""
        super().resizeEvent(event)
        self.position_studio_button()
        if self.auto_fit:
            self.zoom_fit()

    def enterEvent(self, event):
        """Show studio button when mouse enters, but only if in fullscreen mode."""
        super().enterEvent(event)
        if self.studio.full_screen:
            self.studio_button.show()

    def leaveEvent(self, event):
        """Hide studio button when mouse leaves."""
        super().leaveEvent(event)
        self.studio_button.hide()

    def mousePressEvent(self, event):
        """Handle mouse press."""
        if (event.button() == Qt.LeftButton and self.studio.current_layer
                and not self.studio.current_layer.locked and not self.studio.full_screen):
            self.is_drawing = True
            self.stroke_layer = self.studio.current_layer
            self.stroke_before = snapshot_layer(self.stroke_layer, pixels=True)
            pos = self.mapToScene(event.pos())
            self.last_point = pos
            self.active_tool.on_press(pos)

        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        """Handle mouse move."""
        if self.is_drawing and self.last_point and self.studio.current_layer:
            pos = self.mapToScene(event.pos())
            self.active_tool.on_move(pos)
            self.last_point = pos

        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        """Handle mouse release."""
        if event.button() == Qt.LeftButton and self.is_drawing:
            self.is_drawing = False
            self.last_point = None
            self.active_tool.on_release()

            # Record the edit (stroke, erase, move, ...) the tool made to the layer
            layer, before = self.stroke_layer, self.stroke_before
            self.stroke_layer = None
            self.stroke_before = None
            if layer and before:
                record_layer_edit(self.studio, layer, before)

        super().mouseReleaseEvent(event)

    def wheelEvent(self, event):
        """Handle wheel event for zooming."""
        if event.modifiers() == Qt.ControlModifier:
            if event.angleDelta().y() > 0:
                self.zoom_in()
            else:
                self.zoom_out()
            event.accept()
        else:
            super().wheelEvent(event)

    def _update_temp_display(self):
        """Update display with temporary stroke."""
        if not self.temp_layer or not self.studio.current_layer:
            return

        # Composite layers with temp layer
        result = Image.new('RGBA', (self.studio.canvas_width, self.studio.canvas_height), (255, 255, 255, 0))

        for layer in self.studio.layers:
            if layer.visible:
                if layer == self.studio.current_layer:
                    # Preview the temp stroke stamped onto a copy of the current layer
                    preview = Layer("temp", self.studio.canvas_width, self.studio.canvas_height)
                    preview.image = layer.image.copy()
                    preview.opacity = layer.opacity
                    preview.blend_mode = layer.blend_mode
                    preview.x, preview.y = layer.x, layer.y
                    preview.stamp(self.temp_layer)
                    result = preview.composite(result)
                else:
                    result = layer.composite(result)

        # Update canvas
        self.canvas_item.setPixmap(pil_to_pixmap(result))


class LayersPanel(QWidget):
    """Panel for managing layers."""

    def __init__(self, studio: ImageStudio):
        super().__init__()
        self.studio = studio

        layout = CVBoxLayout(self)

        # Header
        header = QLabel("Layers")
        layout.addWidget(header)

        # Layers list
        self.layers_list = QListWidget()
        self.layers_list.currentRowChanged.connect(self.on_layer_selected)
        self.layers_list.setContextMenuPolicy(Qt.CustomContextMenu)
        self.layers_list.customContextMenuRequested.connect(self.show_layer_menu)
        layout.addWidget(self.layers_list)

        # Layer controls
        controls = CHBoxLayout()

        add_btn = QPushButton("+")
        add_btn.setToolTip("Add Layer")
        add_btn.clicked.connect(self.studio.add_layer)
        controls.addWidget(add_btn)

        delete_btn = QPushButton("-")
        delete_btn.setToolTip("Delete Layer")
        delete_btn.clicked.connect(self.studio.delete_layer)
        controls.addWidget(delete_btn)

        duplicate_btn = QPushButton("⎘")
        duplicate_btn.setToolTip("Duplicate Layer")
        duplicate_btn.clicked.connect(self.studio.duplicate_layer)
        controls.addWidget(duplicate_btn)

        merge_btn = QPushButton("↓")
        merge_btn.setToolTip("Merge Down")
        merge_btn.clicked.connect(self.studio.merge_down)
        controls.addWidget(merge_btn)

        layout.addLayout(controls)

        # Layer properties
        props_group = QGroupBox("Layer Properties")
        props_layout = CVBoxLayout(props_group)

        # Opacity
        props_layout.addWidget(QLabel("Opacity:"))
        self.opacity_slider = QSlider(Qt.Horizontal)
        self.opacity_slider.setRange(0, 100)
        self.opacity_slider.setValue(100)
        self.opacity_slider.valueChanged.connect(self.on_opacity_changed)
        props_layout.addWidget(self.opacity_slider)

        self.opacity_label = QLabel("100%")
        props_layout.addWidget(self.opacity_label)

        # Blend mode
        props_layout.addWidget(QLabel("Blend Mode:"))
        self.blend_combo = QComboBox()
        for mode in BlendMode:
            self.blend_combo.addItem(mode.value)
        self.blend_combo.currentTextChanged.connect(self.on_blend_mode_changed)
        props_layout.addWidget(self.blend_combo)

        layout.addWidget(props_group)

    def show_layer_menu(self, pos):
        """Show the shared Layer menu as a context menu, acting on the clicked layer."""
        item = self.layers_list.itemAt(pos)
        if item:
            self.layers_list.setCurrentItem(item)
        self.studio.toolbar.show_popup_menu(
            parent=self,
            schema=self.studio.layer_menu_schema(),
            position=self.layers_list.viewport().mapToGlobal(pos),
        )

    def refresh_layers(self):
        """Refresh the layers list."""
        self.layers_list.clear()

        # Add layers in reverse order (top to bottom)
        for layer in reversed(self.studio.layers):
            label = layer.name if not layer.locked else f"{layer.name} 🔒"
            item = QListWidgetItem(label)
            item.setData(Qt.UserRole, id(layer))

            # Add visibility checkbox
            if not layer.visible:
                item.setForeground(QColor(128, 128, 128))

            self.layers_list.addItem(item)

        # Select current layer
        if self.studio.current_layer:
            layer_id = id(self.studio.current_layer)
            for i in range(self.layers_list.count()):
                item = self.layers_list.item(i)
                if item.data(Qt.UserRole) == layer_id:
                    self.layers_list.setCurrentRow(i)
                    break

    def on_layer_selected(self, row: int):
        """Handle layer selection."""
        if row < 0 or row >= len(self.studio.layers):
            return

        # Layers are in reverse order in the list
        layer_index = len(self.studio.layers) - 1 - row
        self.studio.current_layer = self.studio.layers[layer_index]

        # Update properties
        if self.studio.current_layer:
            self.opacity_slider.setValue(int(self.studio.current_layer.opacity * 100))
            self.opacity_label.setText(f"{int(self.studio.current_layer.opacity * 100)}%")
            self.blend_combo.setCurrentText(self.studio.current_layer.blend_mode.value)

    @records_doc(merge_key='opacity')
    def on_opacity_changed(self, value: int):
        """Handle opacity change."""
        if self.studio.current_layer:
            self.studio.current_layer.opacity = value / 100.0
            self.opacity_label.setText(f"{value}%")
            self.studio.canvas.update_display()

    @records_doc()
    def on_blend_mode_changed(self, mode_name: str):
        """Handle blend mode change."""
        if self.studio.current_layer:
            for mode in BlendMode:
                if mode.value == mode_name:
                    self.studio.current_layer.blend_mode = mode
                    break
            self.studio.canvas.update_display()


class PropertiesPanel(QWidget):
    """Panel for displaying context-sensitive properties."""

    def __init__(self, studio: ImageStudio):
        super().__init__()
        self.studio = studio

        layout = CVBoxLayout(self)

        # Header
        header = QLabel("Properties")
        layout.addWidget(header)

        # Properties area (scrollable)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QScrollArea.NoFrame)

        props_widget = QWidget()
        props_layout = CVBoxLayout(props_widget)

        # Document info
        doc_group = QGroupBox("Document")
        doc_layout = CVBoxLayout(doc_group)

        self.size_label = QLabel("0 x 0 px")
        doc_layout.addWidget(self.size_label)

        props_layout.addWidget(doc_group)

        props_layout.addStretch()
        scroll.setWidget(props_widget)

        layout.addWidget(scroll)

        # Update info
        self.update_info()

    def update_info(self):
        """Update displayed information."""
        self.size_label.setText(f"{self.studio.canvas_width} x {self.studio.canvas_height} px")