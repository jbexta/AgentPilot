import json
import os
from dataclasses import dataclass
from enum import Enum
from typing import List, Optional, Tuple

from PIL import Image, ImageDraw

from PySide6.QtWidgets import (
    QWidget, QSplitter, QLabel, QPushButton, QListWidget, 
    QListWidgetItem, QGraphicsView, QGraphicsScene, QGraphicsPixmapItem, 
    QFileDialog, QMessageBox, QGroupBox, QSlider, QComboBox, QColorDialog,
    QToolButton, QButtonGroup, QScrollArea
)
from PySide6.QtCore import (
    Qt, QPointF
)
from PySide6.QtGui import (
    QPixmap, QImage, QPainter, QColor
)

from gui.util import CustomMenu, find_main, CVBoxLayout, CHBoxLayout
from utils.helpers import set_module_type


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

        # Convert PIL Image to QPixmap
        data = img.tobytes('raw', 'RGBA')
        qimage = QImage(data, img.width, img.height, QImage.Format_RGBA8888)
        return QPixmap.fromImage(qimage)

    def composite(self, base: Image.Image) -> Image.Image:
        """Composite this layer onto base image."""
        if not self.visible:
            return base

        # Apply opacity
        layer_img = self.image.copy()
        if self.opacity < 1.0:
            alpha = layer_img.split()[3]
            alpha = alpha.point(lambda p: int(p * self.opacity))
            layer_img.putalpha(alpha)

        # Simple alpha composite for now
        # In a full implementation, would handle all blend modes
        return Image.alpha_composite(base, layer_img)

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
    - Drawing tools (brush, eraser, shapes, text)
    - Selection tools
    - Filters and adjustments
    - Transform operations
    - Undo/redo history
    - Export to various formats
    """

    associated_extensions = ['png', 'jpg', 'jpeg', 'bmp', 'gif', 'tiff', 'webp']

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

        # History for undo/redo
        self.history = []
        self.history_index = -1

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
                    'text': 'New',
                    'target': parent.new_document,
                },
                {
                    'text': 'Open',
                    'target': parent.open_file,
                },
                {
                    'text': 'Save',
                    'target': parent.save_project,
                },
                {
                    'text': 'Export',
                    'target': parent.export_image,
                },
                {
                    'text': 'Undo',
                    'target': parent.undo,
                },
                {
                    'text': 'Redo',
                    'target': parent.redo,
                },
            ]
            self.create_toolbar(parent)

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
        self.history.clear()
        self.history_index = -1

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
                "Image Files (*.png *.jpg *.jpeg *.bmp *.gif *.tiff *.webp);;All Files (*)"
            )

        if not filepath or not os.path.exists(filepath):
            return

        try:
            # Load image
            img = Image.open(filepath).convert('RGBA')

            # Create new document with image size
            self.clear_project(img.width, img.height)

            # Replace background layer with image
            self.layers[0].image = img
            self.layers[0].name = os.path.basename(filepath)

            # Update display
            self.canvas.update_display()
            self.layers_panel.refresh_layers()

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
            # Composite all layers
            result = Image.new('RGBA', (self.canvas_width, self.canvas_height), (255, 255, 255, 255))

            for layer in self.layers:
                result = layer.composite(result)

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

    def add_layer(self):
        """Add a new layer."""
        layer = RasterLayer(f"Layer {len(self.layers) + 1}", self.canvas_width, self.canvas_height)
        self.layers.append(layer)
        self.current_layer = layer
        self.layers_panel.refresh_layers()
        self.canvas.update_display()

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

    def duplicate_layer(self):
        """Duplicate the current layer."""
        if self.current_layer:
            new_layer = RasterLayer(f"{self.current_layer.name} copy", self.canvas_width, self.canvas_height)
            new_layer.image = self.current_layer.image.copy()
            new_layer.opacity = self.current_layer.opacity
            new_layer.blend_mode = self.current_layer.blend_mode
            self.layers.append(new_layer)
            self.current_layer = new_layer
            self.layers_panel.refresh_layers()
            self.canvas.update_display()

    def merge_down(self):
        """Merge current layer with layer below."""
        if not self.current_layer or len(self.layers) <= 1:
            return

        current_index = self.layers.index(self.current_layer)
        if current_index == 0:
            QMessageBox.warning(self, "Warning", "Cannot merge down the bottom layer!")
            return

        # Composite current layer onto layer below
        lower_layer = self.layers[current_index - 1]
        lower_layer.image = self.current_layer.composite(lower_layer.image)

        # Remove current layer
        self.layers.remove(self.current_layer)
        self.current_layer = lower_layer

        self.layers_panel.refresh_layers()
        self.canvas.update_display()

    def flatten_image(self):
        """Flatten all layers into one."""
        if len(self.layers) <= 1:
            return

        # Composite all layers
        result = Image.new('RGBA', (self.canvas_width, self.canvas_height), (255, 255, 255, 255))
        for layer in self.layers:
            result = layer.composite(result)

        # Keep only one layer
        self.layers.clear()
        background = RasterLayer("Background", self.canvas_width, self.canvas_height)
        background.image = result
        self.layers.append(background)
        self.current_layer = background

        self.layers_panel.refresh_layers()
        self.canvas.update_display()

    def undo(self):
        """Undo last action."""
        # TODO: Implement proper undo system
        QMessageBox.information(self, "Undo", "Undo not yet implemented")

    def redo(self):
        """Redo last undone action."""
        # TODO: Implement proper redo system
        QMessageBox.information(self, "Redo", "Redo not yet implemented")


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

        # Drawing state
        self.is_drawing = False
        self.last_point: Optional[QPointF] = None
        self.current_tool = ToolType.BRUSH
        self.brush_size = 10
        self.brush_opacity = 1.0
        self.brush_hardness = 1.0
        self.foreground_color = QColor(0, 0, 0, 255)

        # PIL draw object for current stroke
        self.temp_layer: Optional[Image.Image] = None
        self.temp_draw: Optional[ImageDraw.ImageDraw] = None

        # Floating "Open in studio" button
        self.studio_button = QPushButton("Open in studio", self)
        self.studio_button.setStyleSheet("""
            QPushButton {
                background-color: rgba(50, 50, 50, 200);
                color: white;
                border: 1px solid #666;
                border-radius: 4px;
                padding: 5px 10px;
            }
            QPushButton:hover {
                background-color: rgba(70, 70, 70, 220);
            }
        """)
        self.studio_button.setCursor(Qt.PointingHandCursor)
        self.studio_button.clicked.connect(lambda: self.studio.set_fullscreen(not self.studio.full_screen))
        self.studio_button.hide()  # Hidden by default

        # Enable mouse tracking to detect hover
        self.setMouseTracking(True)

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
        result = Image.new('RGBA', (self.studio.canvas_width, self.studio.canvas_height), (255, 255, 255, 0))

        for layer in self.studio.layers:
            if layer.visible:
                result = layer.composite(result)

        # Convert to QPixmap
        data = result.tobytes('raw', 'RGBA')
        qimage = QImage(data, result.width, result.height, QImage.Format_RGBA8888)
        pixmap = QPixmap.fromImage(qimage)

        self.canvas_item.setPixmap(pixmap)

    def set_tool(self, tool: ToolType):
        """Set the current tool."""
        self.current_tool = tool

        # Update cursor
        if tool == ToolType.BRUSH or tool == ToolType.ERASER:
            self.viewport().setCursor(Qt.CrossCursor)
        elif tool == ToolType.EYEDROPPER:
            self.viewport().setCursor(Qt.PointingHandCursor)
        else:
            self.viewport().setCursor(Qt.ArrowCursor)

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
        self.zoom_level *= 1.2
        self.scale(1.2, 1.2)
        self.studio.zoom_label.setText(f"{int(self.zoom_level * 100)}%")

    def zoom_out(self):
        """Zoom out."""
        self.zoom_level /= 1.2
        self.scale(1.0 / 1.2, 1.0 / 1.2)
        self.studio.zoom_label.setText(f"{int(self.zoom_level * 100)}%")

    def zoom_fit(self):
        """Zoom to fit canvas in view."""
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
        if event.button() == Qt.LeftButton and self.studio.current_layer:
            self.is_drawing = True
            pos = self.mapToScene(event.pos())
            self.last_point = pos

            if self.current_tool == ToolType.BRUSH:
                self._start_brush_stroke(pos)
            elif self.current_tool == ToolType.ERASER:
                self._start_eraser_stroke(pos)
            elif self.current_tool == ToolType.FILL:
                self._fill_at_point(pos)
            elif self.current_tool == ToolType.EYEDROPPER:
                self._pick_color_at_point(pos)

        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        """Handle mouse move."""
        if self.is_drawing and self.last_point and self.studio.current_layer:
            pos = self.mapToScene(event.pos())

            if self.current_tool == ToolType.BRUSH:
                self._continue_brush_stroke(pos)
            elif self.current_tool == ToolType.ERASER:
                self._continue_eraser_stroke(pos)

            self.last_point = pos

        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        """Handle mouse release."""
        if event.button() == Qt.LeftButton and self.is_drawing:
            self.is_drawing = False
            self.last_point = None

            if self.current_tool in (ToolType.BRUSH, ToolType.ERASER):
                self._finish_stroke()

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

    def _start_brush_stroke(self, pos: QPointF):
        """Start a new brush stroke."""
        if not self.studio.current_layer:
            return

        # Create temporary layer for this stroke
        self.temp_layer = Image.new('RGBA', (self.studio.canvas_width, self.studio.canvas_height), (0, 0, 0, 0))
        self.temp_draw = ImageDraw.Draw(self.temp_layer)

        # Draw initial point
        x, y = int(pos.x()), int(pos.y())
        color = (
            self.foreground_color.red(),
            self.foreground_color.green(),
            self.foreground_color.blue(),
            int(255 * self.brush_opacity)
        )

        radius = self.brush_size // 2
        self.temp_draw.ellipse([x - radius, y - radius, x + radius, y + radius], fill=color)

    def _continue_brush_stroke(self, pos: QPointF):
        """Continue brush stroke."""
        if not self.temp_draw or not self.last_point:
            return

        # Draw line from last point to current point
        x1, y1 = int(self.last_point.x()), int(self.last_point.y())
        x2, y2 = int(pos.x()), int(pos.y())

        color = (
            self.foreground_color.red(),
            self.foreground_color.green(),
            self.foreground_color.blue(),
            int(255 * self.brush_opacity)
        )

        # Draw line with brush size
        self.temp_draw.line([x1, y1, x2, y2], fill=color, width=self.brush_size)

        # Draw circle at endpoint for smooth line
        radius = self.brush_size // 2
        self.temp_draw.ellipse([x2 - radius, y2 - radius, x2 + radius, y2 + radius], fill=color)

        # Update display
        self._update_temp_display()

    def _start_eraser_stroke(self, pos: QPointF):
        """Start eraser stroke."""
        self._start_brush_stroke(pos)

    def _continue_eraser_stroke(self, pos: QPointF):
        """Continue eraser stroke."""
        if not self.temp_draw or not self.last_point or not self.studio.current_layer:
            return

        # Erase by drawing transparent
        x1, y1 = int(self.last_point.x()), int(self.last_point.y())
        x2, y2 = int(pos.x()), int(pos.y())

        # Create eraser mask
        mask = Image.new('L', (self.studio.canvas_width, self.studio.canvas_height), 0)
        mask_draw = ImageDraw.Draw(mask)

        radius = self.brush_size // 2
        mask_draw.line([x1, y1, x2, y2], fill=255, width=self.brush_size)
        mask_draw.ellipse([x2 - radius, y2 - radius, x2 + radius, y2 + radius], fill=255)

        # Apply eraser to current layer directly
        current_img = self.studio.current_layer.image
        alpha = current_img.split()[3]
        alpha = Image.composite(Image.new('L', alpha.size, 0), alpha, mask)
        current_img.putalpha(alpha)

        # Update display
        self.update_display()

    def _finish_stroke(self):
        """Finish brush/eraser stroke."""
        if not self.temp_layer or not self.studio.current_layer:
            self.temp_layer = None
            self.temp_draw = None
            return

        # Composite temp layer onto current layer
        self.studio.current_layer.image = Image.alpha_composite(
            self.studio.current_layer.image,
            self.temp_layer
        )

        # Clean up
        self.temp_layer = None
        self.temp_draw = None

        # Update display
        self.update_display()

    def _update_temp_display(self):
        """Update display with temporary stroke."""
        if not self.temp_layer or not self.studio.current_layer:
            return

        # Composite layers with temp layer
        result = Image.new('RGBA', (self.studio.canvas_width, self.studio.canvas_height), (255, 255, 255, 0))

        for layer in self.studio.layers:
            if layer.visible:
                if layer == self.studio.current_layer:
                    # Add temp layer on top of current layer
                    composite = Image.alpha_composite(layer.image, self.temp_layer)
                    temp_layer_obj = Layer("temp", self.studio.canvas_width, self.studio.canvas_height)
                    temp_layer_obj.image = composite
                    temp_layer_obj.opacity = layer.opacity
                    result = temp_layer_obj.composite(result)
                else:
                    result = layer.composite(result)

        # Update canvas
        data = result.tobytes('raw', 'RGBA')
        qimage = QImage(data, result.width, result.height, QImage.Format_RGBA8888)
        pixmap = QPixmap.fromImage(qimage)
        self.canvas_item.setPixmap(pixmap)

    def _fill_at_point(self, pos: QPointF):
        """Fill with foreground color at point."""
        # TODO: Implement flood fill algorithm
        QMessageBox.information(self, "Fill", "Fill tool not yet implemented")

    def _pick_color_at_point(self, pos: QPointF):
        """Pick color from canvas at point."""
        x, y = int(pos.x()), int(pos.y())

        if 0 <= x < self.studio.canvas_width and 0 <= y < self.studio.canvas_height:
            # Get pixel from composite image
            result = Image.new('RGBA', (self.studio.canvas_width, self.studio.canvas_height), (255, 255, 255, 255))
            for layer in self.studio.layers:
                result = layer.composite(result)

            pixel = result.getpixel((x, y))
            color = QColor(pixel[0], pixel[1], pixel[2], pixel[3])

            self.studio.foreground_color = color
            self.studio.update_color_button(self.studio.fg_color_btn, color)
            self.foreground_color = color


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

    def refresh_layers(self):
        """Refresh the layers list."""
        self.layers_list.clear()

        # Add layers in reverse order (top to bottom)
        for layer in reversed(self.studio.layers):
            item = QListWidgetItem(layer.name)
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

    def on_opacity_changed(self, value: int):
        """Handle opacity change."""
        if self.studio.current_layer:
            self.studio.current_layer.opacity = value / 100.0
            self.opacity_label.setText(f"{value}%")
            self.studio.canvas.update_display()

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