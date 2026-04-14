from functools import partial
import json
import os
import subprocess
import threading
import time
from typing import Any, Dict, List
from PIL import Image
from moviepy import VideoFileClip, AudioFileClip


from PySide6.QtWidgets import (
    QApplication, QComboBox, QHBoxLayout, QMenu, QSlider, QVBoxLayout, QWidget, QSplitter, QLabel,
    QPushButton, QGraphicsView, QGraphicsScene, QGraphicsRectItem,
    QFileDialog, QMessageBox, QGraphicsItem, QGraphicsLineItem,
    QGraphicsItemGroup, QGraphicsObject, QGraphicsPixmapItem, QDialog, QProgressBar
)
from PySide6.QtCore import (
    QRectF, Qt, Signal, QUrl, QPointF, Slot, QTimer, QObject
)
from PySide6.QtGui import (
    QColor, QCursor, QIcon, QImage, QKeySequence, QPen, QBrush, QPixmap, QPainter,
    QPainterPath, QLinearGradient
)
from PySide6.QtMultimedia import QMediaPlayer, QAudioOutput

from gui.util import CustomMenu, clear_layout, colorize_pixmap, find_main, CVBoxLayout, CHBoxLayout, get_member_settings_class
from gui import system
from gui.widgets.config_widget import ConfigWidget
from gui.widgets.config_side_tabs import ConfigSideTabs
from utils import sql
from plugins.workflows.widgets.workflow_settings import HeaderFields
from gui.widgets.config_fields import ConfigFields
from gui.widgets.collections_widget import CollectionsWidget
from utils.helpers import get_media_type_from_ext, set_module_type, AUDIO_EXTS, IMAGE_EXTS, VIDEO_EXTS

from PySide6.QtGui import QPixmap

from PySide6.QtCore import QThread, Signal, QObject
import asyncio
import hashlib
import tempfile
import numpy as np
from moviepy import VideoFileClip


# Module-level lazy-init semaphore for limiting concurrent ffmpeg thumbnail extractions
_thumbnail_semaphore = None


def _get_thumbnail_semaphore():
    """Lazy-init asyncio.Semaphore(2) for thumbnail concurrency."""
    global _thumbnail_semaphore
    if _thumbnail_semaphore is None:
        _thumbnail_semaphore = asyncio.Semaphore(2)
    return _thumbnail_semaphore


def _get_thumbnail_cache_dir():
    """Return (and create) the disk cache directory for thumbnails."""
    cache_dir = os.path.join(tempfile.gettempdir(), 'agentpilot_thumb_cache')
    os.makedirs(cache_dir, exist_ok=True)
    return cache_dir


def _thumb_cache_key(filepath, frame_num, thumb_height):
    """Return the disk cache filename for a specific thumbnail."""
    path_hash = hashlib.md5(filepath.encode()).hexdigest()[:12]
    return f'{path_hash}_{frame_num}_{thumb_height}.jpg'


def frame_to_time(frame: int, fps: float) -> float:
    """Convert frame number to time in seconds."""
    return frame / fps


def time_to_frame(time_seconds: float, fps: float) -> int:
    """Convert time in seconds to frame number."""
    return int(time_seconds * fps)


@set_module_type('Studios')
class VideoStudio(ConfigWidget):
    """
    Full-featured video editor studio similar to Kdenlive.
    """
    associated_extensions = list(VIDEO_EXTS) + list(AUDIO_EXTS)

    def __init__(self, parent=None, full_screen=True):
        super().__init__(parent)
        self.main = find_main()
        self.current_clip = None
        self.full_screen = full_screen
        self.current_file_path = None  # Track currently open .agpm file

        # # Workflow backing store — each clip becomes a member
        # self.workflow = None
        # self._init_workflow()

        # Project Settings
        self.project_width = 1920
        self.project_height = 1080
        self.project_fps = 30

        self.layout = CVBoxLayout(self)

        # self.media_bin = MediaBin()
        self.timeline = TimelineView(self)
        self.timeline_toolbar = self.TimelineContextMenu(self)
        self.track_control_panel = TrackControlPanel(self)

        self.menubar = self.MenuBar(self)
        self.preview_panel = VideoPreviewPanel(self)
        self.timeline_panel = QWidget()  # CHBoxLayout()
        timeline_layout = CVBoxLayout(self.timeline_panel)
        inner_timeline_layout = CHBoxLayout()
        timeline_layout.addWidget(self.timeline_toolbar)
        timeline_layout.addLayout(inner_timeline_layout)

        inner_timeline_layout.addWidget(self.timeline)
        inner_timeline_layout.addWidget(self.track_control_panel)

        # Left panel tabs for Collections and Properties
        self.left_panel_tabs = ConfigSideTabs(
            self,
            pages={
                "Collections": CollectionsWidget(self),
                "Properties": MemberConfigWidget(self),
            },
        )
        self.left_panel_tabs.build_schema()
        self.left_panel_tabs.sections['Properties'].hide()

        self.member_config_widget = self.left_panel_tabs.pages['Properties']
        self.collections_widget = self.left_panel_tabs.pages['Collections']

        self.upper_h_splitter = QSplitter(Qt.Horizontal)
        self.upper_h_splitter.addWidget(self.left_panel_tabs)
        self.upper_h_splitter.addWidget(self.preview_panel)

        self.v_splitter = QSplitter(Qt.Vertical)
        self.v_splitter.addWidget(self.upper_h_splitter)
        self.v_splitter.addWidget(self.timeline_panel)

        self.layout.addWidget(self.menubar)
        self.layout.addWidget(self.v_splitter)

        self.set_fullscreen(self.full_screen)
        self.timeline.scene.selectionChanged.connect(self.on_selection_changed)
        
        recent_files = self._get_recent_files()
        if recent_files:
            self._open_file_path(recent_files[0], only_load_config=True)
        else:
            self.load_config({})
    
    def load_config(self, json_config=None):
        if json_config is None:
            json_config = self.config

        default_tracks = [
            {
                'name': 'Track 1',
            },
            {
                'name': 'Track 2',
            },
        ]
        self.timeline.tracks = json_config.get('tracks', default_tracks)

        self.project_width = json_config.get('project_width', 1920)
        self.project_height = json_config.get('project_height', 1080)
        self.project_fps = json_config.get('project_fps', 30)

        # Load clips (deserialize from dict to MediaMember objects)
        clips_data = json_config.get('clips', {})
        self.timeline.clips = {}
        for clip_id, clip_dict in clips_data.items():
            # Handle both old format (MediaMember objects) and new format (dicts)
            if isinstance(clip_dict, dict):
                member_config = clip_dict.get('member_config', {})
                start_frame = clip_dict.get('start_frame', 0)
                track_index = clip_dict.get('track_index', 0)

                member = self.timeline.MediaMember(
                    timeline_view=self.timeline,
                    member_id=clip_id,
                    member_config=member_config,
                    start_frame=start_frame,
                    in_frame=clip_dict.get('in_frame', 0),
                    out_frame=clip_dict.get('out_frame', 150),
                    track_index=track_index,
                )

                member.is_locked = clip_dict.get('is_locked', False)
                member.is_disabled = clip_dict.get('is_disabled', False)
                self.timeline.scene.addItem(member)
                self.timeline.clips[clip_id] = member
                # self._register_clip_member(clip_id, member_config)

        if hasattr(self, 'preview_panel'):
            self.preview_panel.update_dimensions()
    
    def load(self):
        # self.load_clips()
        self.load_tracks()
    
    # def load_clips(self):
    #     for _, clip in self.timeline.clips.items():
    #         self.timeline.scene.removeItem(clip)
    #     # self.timeline.clips = {}

    #     clips_data = self.config.get('clips', [])
    #     # Iterate over the parsed 'members' data and add them to the scene
    #     for clip_info in clips_data:
    #         pass

    #     # self.view.fit_to_all()
    
    def load_tracks(self):
        self.track_control_panel.load()

        # Update scene rect and playhead height
        timeline_height = len(self.timeline.tracks) * 60
        self.timeline.update_scene_rect()
        if self.timeline.playhead_item:
            self.timeline.playhead_item.setLine(0, 0, 0, timeline_height)
        if self.timeline.loop_start_flag is not None:
            self.timeline.loop_start_flag.update_height(timeline_height)
        if self.timeline.loop_end_flag is not None:
            self.timeline.loop_end_flag.update_height(timeline_height)

    def get_config(self):
        # Serialize clips with frame-based values
        clips_data = {
            clip_id: clip.to_dict()
            for clip_id, clip in self.timeline.clips.items()
        }
        return {
            'tracks': self.track_control_panel.get_config(),
            'clips': clips_data,
            'project_width': self.project_width,
            'project_height': self.project_height,
            'project_fps': float(self.project_fps),
        }
    
    def save_config(self):
        pass

    # def _init_workflow(self):
    #     """Create a Workflow backing store for the studio.

    #     Each timeline clip is registered as a workflow member so that
    #     generation results can be persisted via ``save_message``.
    #     """
    #     from plugins.workflows.members.workflow import Workflow

    #     self.workflow = Workflow(
    #         main=self.main,
    #         kind='STUDIO',
    #         config={},
    #     )
    #     self.workflow.autorun = False

    # def _register_clip_member(self, clip_id, member_config):
    #     """Register a timeline clip as a workflow member.

    #     Parameters
    #     ----------
    #     clip_id : str
    #         Unique clip / member identifier.
    #     member_config : dict
    #         The clip's member configuration dict.
    #     """
    #     if self.workflow is None:
    #         return

    #     members = self.workflow.config.setdefault('members', [])
    #     # Avoid duplicates
    #     if any(m.get('id') == clip_id for m in members):
    #         return
    #     members.append({
    #         'id': clip_id,
    #         'config': member_config,
    #         'loc_x': 0,
    #         'loc_y': 0,
    #     })

    def on_selection_changed(self):
        selected_objects = self.timeline.scene.selectedItems()

        if len(selected_objects) == 1:
            clip = selected_objects[0]
            self.member_config_widget.display_member(member=clip)
            self.left_panel_tabs.sections['Properties'].show()
            if hasattr(self.member_config_widget.config_widget, 'reposition_view'):
                self.member_config_widget.config_widget.reposition_view()
        else:
            self.left_panel_tabs.sections['Properties'].hide()

        self.timeline_toolbar.reload_predicates()

    def set_fullscreen(self, fullscreen):
        """Toggle fullscreen mode."""
        self.full_screen = fullscreen
        self.timeline_panel.setVisible(not fullscreen)
        self.track_control_panel.setVisible(not fullscreen)
        self.left_panel_tabs.setVisible(not fullscreen)
        self.menubar.setVisible(not fullscreen)
        if not fullscreen:
            self.preview_panel.studio_button.hide()

    class MenuBar(CustomMenu):
        def __init__(self, parent):
            super().__init__(parent)
            self.schema = [
                {
                    'text': 'File',
                    'submenu': [
                        {
                            'text': 'New',
                            'shortcut': QKeySequence.New,
                            'target': parent.new_project,
                        },
                        {
                            'text': 'Open',
                            'shortcut': QKeySequence.Open,
                            'target': parent.open_file,
                        },
                        {
                            'text': 'Open Recent',
                            'submenu': lambda: parent._get_recent_menu_items(),
                        },
                        {
                            'text': 'Save',
                            'shortcut': QKeySequence.Save,
                            'target': lambda: parent.save() if parent.current_file_path else parent.save_as(),
                        },
                        {
                            'text': 'Save As',
                            'shortcut': QKeySequence.SaveAs,
                            'target': parent.save_as,
                        },
                        {'type': 'separator'},
                        {
                            'text': 'Render',
                            'shortcut': 'Ctrl+Shift+R',
                            'target': parent.render_project,
                        },
                    ],
                },
                {
                    'text': 'Edit',
                    'submenu': [
                        # {
                        #     'type': 'create_standard',
                        #     'widget': lambda: next(parent.timeline.scene.selectedItems(), None),
                        # }
                        {
                            'text': 'Project Settings',
                            'target': parent.project_settings,
                        }
                    ],
                },
                {
                    'text': 'View',
                    'submenu': [
                        {
                            'text': 'Zoom In',
                            'shortcut': QKeySequence.ZoomIn,
                            'target': parent.timeline.zoom_in,
                        },
                        {
                            'text': 'Zoom Out',
                            'shortcut': QKeySequence.ZoomOut,
                            'target': parent.timeline.zoom_out,
                        },
                    ],
                },
            ]
            self.create_menubar(parent)

    class TimelineContextMenu(CustomMenu):
        def __init__(self, parent):
            super().__init__(parent)
            self.schema = [
                {
                    'text': 'Add',
                    'icon_path': ':/resources/icon-new.png',
                    'target': lambda: self.show_add_context_menu(),
                },
                {
                    'type': 'separator',
                },
                {
                    'text': 'Copy',
                    'icon_path': ':/resources/icon-copy.png',
                    # 'target': self.copy_selected_items,
                    'enabled': lambda: self.has_selected_clips(),
                },
                {
                    'text': 'Paste',
                    'icon_path': ':/resources/icon-paste.png',
                    # 'target': self.paste_items,
                    'enabled': lambda: self.has_copied_items(),
                },
                {
                    'text': 'Delete',
                    'icon_path': ':/resources/icon-delete-2.png',
                    # 'target': self.delete_selected_items,
                    'target': parent.delete_clip,
                    'enabled': lambda: self.has_selected_clips(),
                },
                {
                    'text': 'Split',
                    'icon_path': ':/resources/icon-split.png',
                    'target': parent.split_clip,
                    'enabled': lambda: self.has_selected_clips(),
                },
                {
                    'text': 'Lock',
                    'icon_path': ':/resources/icon-pin-on.png',
                    'target': self.toggle_lock,
                    'enabled': lambda: self.has_selected_clips(),
                },
                {
                    'text': 'Disable',
                    'icon_path': ':/resources/icon-minus.png',
                    'target': self.toggle_disable,
                    'enabled': lambda: self.has_selected_clips(),
                },
                {
                    'type': 'separator',
                },
                {
                    'text': 'Group',
                    'icon_path': ':/resources/icon-screenshot.png',
                    # 'target': self.group_selected_items,
                    'enabled': lambda: self.selected_clip_count() > 1,
                },
                {
                    'text': 'Volume',
                    'icon_path': ':/resources/icon-volume.png',
                    'visibility_predicate': lambda: self.selected_clip_type() == 'video' or self.selected_clip_type() == 'audio',
                    'submenu': [
                        {
                            'text': 'Volume',
                            'widget': self._create_volume_slider_widget,
                        },
                    ],
                },
                {
                    'flatmenu': self.video_menu,
                    'prefix': 'video_',
                    'visibility_predicate': lambda: self.selected_clip_type() == 'video',
                },
                {
                    'flatmenu': self.audio_menu,
                    'prefix': 'audio_',
                    'visibility_predicate': lambda: self.selected_clip_type() == 'audio',
                },
                {
                    'flatmenu': self.image_menu,
                    'prefix': 'image_',
                    'visibility_predicate': lambda: self.selected_clip_type() == 'image',
                },
                {
                    'text': 'Loop',
                    'icon_path': ':/resources/icon-iterate.png',
                    'target': parent.timeline.toggle_loop_flags,
                },
                {
                    'type': 'stretch',
                },
                {
                    'text': 'Zoom Out',
                    'icon_path': ':/resources/icon-minus.png',
                    'target': parent.timeline.zoom_out,
                },
                {
                    'text': 'Zoom In',
                    'icon_path': ':/resources/icon-new.png',
                    'target': parent.timeline.zoom_in,
                },
            ]
            self.create_toolbar(parent)
        
        def _create_volume_slider_widget(self):
            """Create a volume slider widget for use in menus."""
            container = QWidget()
            layout = QHBoxLayout(container)
            layout.setContentsMargins(8, 4, 8, 4)

            slider = QSlider(Qt.Horizontal)
            slider.setMinimum(0)
            slider.setMaximum(200)
            slider.setFixedWidth(100)

            # Get current volume from selected clip
            selected_items = self.parent.timeline.scene.selectedItems()
            if selected_items:
                clip = selected_items[0]
                current_volume = clip.member_config.get('volume', 100)
                slider.setValue(current_volume)
            else:
                slider.setValue(100)

            value_label = QLabel(f'{slider.value()}%')
            value_label.setFixedWidth(50)

            def on_volume_changed(value):
                mouse_pressed = slider.isSliderDown()
                if mouse_pressed and (value == 99 or value == 101):
                    slider.setValue(100)
                    return
                value_label.setText(f'{value}%')
                selected_items = self.parent.timeline.scene.selectedItems()
                if selected_items:
                    clip = selected_items[0]
                    clip.member_config['volume'] = value
                    clip.update()  # Trigger repaint to show volume indicator

            slider.valueChanged.connect(on_volume_changed)
            slider.sliderReleased.connect(self.parent.update_config)  # Save when user finishes adjusting

            layout.addWidget(slider)
            layout.addWidget(value_label)

            return container

        @property
        def video_menu(self):
            return [
                {
                    'text': 'Operations',
                    'tooltip': 'AI-powered operations',
                    'icon_path': ':/resources/icon-wand.png',
                    'submenu': lambda: self.clip_operations_menu('video'),
                },
                {
                    'text': 'Effects',
                    'tooltip': 'Apply effects to video',
                    'icon_path': ':/resources/icon-effects.png',
                    'submenu': [
                        {
                            'text': 'Video',
                            'tooltip': 'Apply effects to video',
                            'submenu': lambda: self.clip_effects_menu('image'),
                        },
                        {
                            'text': 'Audio',
                            'tooltip': 'Apply effects to audio',
                            'submenu': lambda: self.clip_effects_menu('audio'),
                        },
                    ]
                },
                {
                    'text': 'Extract',
                    'submenu': [
                        {
                            'text': 'Audio Track',
                            'tooltip': 'Extract audio track from video',
                            'target': self.parent.separate_audio_track,
                        },
                        {
                            'text': 'Frame',
                            'tooltip': 'Extract frame from video',
                            'submenu': [
                                {
                                    'text': 'Current Frame',
                                    'tooltip': 'Extract current frame from video',
                                    'target': partial(self.parent.extract_frame, 'current'),
                                },
                                {
                                    'text': 'First Frame',
                                    'tooltip': 'Extract first frame from video',
                                    'target': partial(self.parent.extract_frame, 'first'),
                                },
                                {
                                    'text': 'Last Frame',
                                    'tooltip': 'Extract last frame from video',
                                    'target': partial(self.parent.extract_frame, 'last'),
                                },
                            ]
                        },
                        {
                            'text': 'Transitions',
                            'target': self.parent.split_at_transitions,
                            'tooltip': 'Split at shot transitions',
                        },
                    ]
                },
                {
                    'text': 'Add to Collection',
                    'icon_path': ':/resources/icon-folder.png',
                    'submenu': lambda: self.collection_folders_menu(),
                },
            ]

        @property
        def audio_menu(self):
            return [
                {
                    'text': 'Operations',
                    'tooltip': 'AI-powered operations',
                    'icon_path': ':/resources/icon-wand.png',
                    'submenu': lambda: self.clip_operations_menu('audio'),
                },
                {
                    'text': 'Effects',
                    'tooltip': 'Apply effects to audio',
                    'icon_path': ':/resources/icon-effects.png',
                    'submenu': [
                        {
                            'flatmenu': lambda: self.clip_effects_menu('audio'),
                            'prefix': 'audio_',
                        },
                    ],
                },
                {
                    'text': 'Extract',
                    'submenu': [
                        {
                            'text': 'Speech',
                            'tooltip': 'Extract speech from audio',
                        },
                        {
                            'text': 'Stems',
                            'tooltip': 'Extract frame from video',
                        },
                    ]
                },
                {
                    'text': 'Add to Collection',
                    'icon_path': ':/resources/icon-folder.png',
                    'submenu': lambda: self.collection_folders_menu(),
                },
            ]
        
        @property
        def image_menu(self):
            return [
                {
                    'text': 'Operations',
                    'tooltip': 'AI-powered operations',
                    'icon_path': ':/resources/icon-wand.png',
                    'submenu': lambda: self.clip_operations_menu('image'),
                },
                {
                    'text': 'Effects',
                    'tooltip': 'Apply effects to image',
                    'icon_path': ':/resources/icon-effects.png',
                    'submenu': [
                        {
                            'flatmenu': lambda: self.clip_effects_menu('image'),
                            'prefix': 'image_',
                        },
                    ],
                },
                {
                    'text': 'Add to Collection',
                    'icon_path': ':/resources/icon-folder.png',
                    'submenu': lambda: self.collection_folders_menu(),
                },
            ]
        
        def clip_effects_menu(self, clip_type):
            effects = system.manager.modules.get_modules_in_folder(
                module_type=f'{clip_type}_effects',
                fetch_keys=('name', 'class',)
            )
            menu_items = []
            for name, effect_class in effects:
                display_name = getattr(effect_class, 'display_name', name.replace('_', ' ').title())
                tooltip = getattr(effect_class, 'description', '')
                menu_items.append({
                    'text': display_name,
                    'tooltip': tooltip,
                    'target': partial(self.apply_effect, effect_class),
                })
            return menu_items

        def clip_operations_menu(self, clip_type):
            """Build menu of AI operations for the given clip type."""
            operations = system.manager.modules.get_modules_in_folder(
                module_type=f'{clip_type}_operations',
                fetch_keys=('name', 'class',)
            )
            menu_items = []
            for name, op_class in operations:
                display_name = getattr(
                    op_class, 'display_name',
                    name.replace('_', ' ').title()
                )
                tooltip = getattr(op_class, 'description', '')
                icon = getattr(op_class, 'icon_path', '')
                item = {
                    'text': display_name,
                    'tooltip': tooltip,
                    'target': partial(self.run_operation, op_class),
                }
                if icon:
                    item['icon_path'] = icon
                menu_items.append(item)
            return menu_items

        def run_operation(self, operation_class):
            """Instantiate and run an operation on selected clips."""
            selected = self.parent.timeline.scene.selectedItems()
            clips = [
                c for c in selected
                if isinstance(c, self.parent.timeline.MediaMember)
            ]
            if not clips:
                return
            operation = operation_class(
                studio=self.parent,
                clips_to_modify=clips,
            )
            operation.run()

        def apply_effect(self, effect_class):
            """Apply an effect to selected clips."""
            selected_items = self.parent.timeline.scene.selectedItems()
            if not selected_items:
                return
            for item in selected_items:
                if hasattr(item, 'apply_effect'):
                    item.apply_effect(effect_class)

        def collection_folders_menu(self):
            """Return submenu of collection folders."""
            folders = self.parent.collections_widget.get_folders()
            if not folders:
                return [{'text': '(No folders)', 'enabled': False}]
            return [
                {'text': f, 'target': partial(self.add_to_collection, f)}
                for f in folders
            ]

        def add_to_collection(self, folder_name):
            """Add selected clip to collection folder."""
            selected = self.parent.timeline.scene.selectedItems()
            if not selected:
                return
            clip = selected[0]
            if hasattr(clip, 'filepath') and clip.filepath:
                self.parent.collections_widget.add_item(folder_name, clip.filepath)

        def selected_clip_count(self):
            return len(self.parent.timeline.scene.selectedItems())
        
        def has_selected_clips(self):
            return self.selected_clip_count() > 0
        
        def only_one_selected_clip(self):
            return self.selected_clip_count() == 1
        
        def selected_clip_type(self):
            if not self.only_one_selected_clip():
                return None
            return self.parent.timeline.scene.selectedItems()[0].member_type
            
        def has_copied_items(self):
            try:
                clipboard = QApplication.clipboard()
                copied_data = clipboard.text()
                start_text = 'WORKFLOW_MEMBERS:'
                return copied_data.startswith(start_text)

            except Exception as e:
                return False

        def selected_clip_is_locked(self):
            selected = self.parent.timeline.scene.selectedItems()
            if len(selected) == 1:
                return selected[0].is_locked
            return False

        def toggle_lock(self):
            selected = self.parent.timeline.scene.selectedItems()
            for clip in selected:
                clip.is_locked = not clip.is_locked
                clip.update()
            self.parent.update_config()

        def toggle_disable(self):
            selected = self.parent.timeline.scene.selectedItems()
            for clip in selected:
                clip.is_disabled = not clip.is_disabled
                clip.update()
            self.parent.update_config()

        def create_new_member_menu(self, parent=None):
            menu = QMenu('Add', parent)

            member_modules = system.manager.modules.get_modules_in_folder(
                module_type='Members',
                fetch_keys=('name', 'kind_folder', 'class',)
            )
            for module_name, module_kind, module_class in member_modules:
                if module_kind != 'media':
                    continue
                default_name = getattr(module_class, 'default_name', module_name.capitalize())
                workflow_insert_mode = getattr(module_class, 'workflow_insert_mode', None)
                icon_path = getattr(module_class, 'default_avatar', None)
                if icon_path:
                    icon = QIcon(colorize_pixmap(QPixmap(icon_path)))
                if workflow_insert_mode == 'single':
                    menu.addAction(icon, module_name.replace('_', ' ').title(), partial(
                        self.parent.timeline.add_insertable_entity,
                        {"_TYPE": module_name, "name": default_name}
                    ))
                # elif workflow_insert_mode == 'list':
                #     menu.addAction(module_name.replace('_', ' ').title(), partial(self.choose_member, module_name))
                else:
                    continue
            return menu

        def show_add_context_menu(self):
            menu = self.create_new_member_menu()
            menu.exec_(QCursor.pos())

    def new_project(self):
        """Create new project."""
        reply = QMessageBox.question(
            self,
            "New Project",
            "Create a new project?",
            QMessageBox.Yes | QMessageBox.No
        )

        if reply == QMessageBox.Yes:
            self.clear_project()
    
    def clear_project(self):
        """Clear project."""
        self.current_file_path = None

        # Stop playback and audio before removing clips
        self.preview_panel.stop_playback()

        # Remove stale PreviewClipItems from the preview scene
        for item in list(self.preview_panel.scene.items()):
            if isinstance(item, PreviewClipItem):
                self.preview_panel.scene.removeItem(item)

        # Remove timeline clips
        for clip in self.timeline.clips.values():
            self.timeline.scene.removeItem(clip)
        self.timeline.clips.clear()

    def save_as(self):
        """Save project as (prompts for file location)."""
        default_path = self.current_file_path or ''
        filepath, _ = QFileDialog.getSaveFileName(
            self,
            "Save Project As",
            default_path,
            "AgentPilot Media Project (*.agpm)"
        )
        if not filepath:
            return

        # Ensure .agpm extension
        if not filepath.endswith('.agpm'):
            filepath += '.agpm'

        self.current_file_path = filepath
        self.save()
        self._add_to_recent_files(self.current_file_path)
    
    def update_config(self):
        self.save()

    def save(self):
        """Save project to current file, or prompt for location if none."""
        if not self.current_file_path:
            # self.save_as()
            return

        config = self.get_config()
        with open(self.current_file_path, 'w', encoding='utf-8') as f:
            json.dump(config, f, indent=2)

    def open_file(self, filepath: str = None):
        """Open a project file or media file."""
        if not filepath:
            filters = [
                "AgentPilot Media Project (*.agpm)",
                "Video Files (*.mp4 *.avi *.mov *.mkv *.webm *.wmv *.flv)",
                "Image Files (*.png *.jpg *.jpeg *.gif *.bmp *.webp *.tiff)",
                "Audio Files (*.mp3 *.wav *.flac *.ogg *.m4a *.aac *.wma)",
                "All Files (*)"
            ]
            filepath, _ = QFileDialog.getOpenFileName(
                self,
                "Open File",
                "",
                ";;".join(filters)
            )
            if not filepath:
                return

        self._open_file_path(filepath)
    
    def _open_file_path(self, filepath: str, only_load_config: bool = False):
        """Open a file by path (used by open_file and open recent)."""
        if not os.path.exists(filepath):
            QMessageBox.warning(self, "File Not Found", f"File not found: {filepath}")
            return

        ext = os.path.splitext(filepath)[1].lower()
        media_type = get_media_type_from_ext(ext)

        if ext == '.agpm':
            # Load project file
            with open(filepath, 'r', encoding='utf-8') as f:
                config = json.load(f)
            self.clear_project()
            self.load_config(config)
            if not only_load_config:
                self.load()

            self.current_file_path = filepath
            self._add_to_recent_files(filepath)

        elif media_type is not None:
            # Create new project with single clip
            self.clear_project()

            member_config = {
                '_TYPE': media_type,
                'name': os.path.basename(filepath),
                'browse.path': filepath,
            }

            # Create and add clip directly
            clip_id = self.timeline.next_available_member_id()
            member = self.timeline.MediaMember(
                timeline_view=self.timeline,
                member_id=clip_id,
                start_frame=0,
                track_index=0,
                member_config=member_config,
            )
            self.timeline.scene.addItem(member)
            self.timeline.clips[clip_id] = member

            playhead_frame = self.timeline.get_playhead_frame()
            self.preview_panel.request_frame(max(0, playhead_frame))

            # resize canvas
            media_width, media_height = self.get_media_dimensions(filepath)
            self.resize_canvas(media_width, media_height)

    def get_media_dimensions(self, filepath: str):
        ext = os.path.splitext(filepath)[1].lower()
        if ext in VIDEO_EXTS:
            # get video dimensions
            video = VideoFileClip(filepath)
            return video.size
        elif ext in IMAGE_EXTS:
            # get image dimensions
            image = Image.open(filepath)
            return image.width, image.height
        return 0, 0
    
    def _get_recent_files(self) -> List[str]:
        """Get recent files list from settings table."""
        value = sql.get_scalar(
            "SELECT value FROM settings WHERE field = 'video_studio_recent_files'",
            load_json=True
        )
        if value is None:
            return []
        return value if isinstance(value, list) else []

    def _add_to_recent_files(self, filepath: str):
        """Add filepath to recent files list (max 10 items)."""
        recent = self._get_recent_files()

        # Remove duplicates and insert at front
        if filepath in recent:
            recent.remove(filepath)
        recent.insert(0, filepath)

        # Limit to 10 items
        recent = recent[:10]

        # Save to database
        existing = sql.get_scalar(
            "SELECT value FROM settings WHERE field = 'video_studio_recent_files'"
        )
        if existing is None:
            sql.execute(
                "INSERT INTO settings (field, value) VALUES ('video_studio_recent_files', ?)",
                (json.dumps(recent),)
            )
        else:
            sql.execute(
                "UPDATE settings SET value = ? WHERE field = 'video_studio_recent_files'",
                (json.dumps(recent),)
            )

    def _get_recent_menu_items(self) -> List[dict]:
        """Get recent files as menu items for dynamic submenu."""
        recent = self._get_recent_files()
        if not recent:
            return [{'text': '(No recent files)', 'enabled': False}]

        items = []
        for filepath in recent:
            filename = os.path.basename(filepath)
            items.append({
                'text': filename,
                'tooltip': filepath,
                'target': partial(self._open_file_path, filepath),
            })
        return items

    def cut_clip(self):
        return

    def split_clip(self):
        """Split all selected clips at the playhead position."""
        selected_items = self.timeline.scene.selectedItems()
        if not selected_items:
            return

        playhead_frame = self.timeline.get_playhead_frame()
        ppf = self.timeline.units_per_frame

        for clip in selected_items:
            if not isinstance(clip, self.timeline.MediaMember):
                continue

            # Check if playhead is within the clip's timeline span
            clip_start = clip.start_frame
            clip_end = clip.start_frame + clip.frame_count

            if playhead_frame <= clip_start or playhead_frame >= clip_end:
                # Playhead not within this clip, skip
                continue

            # Calculate the split point in media frames
            frames_into_clip = playhead_frame - clip_start
            split_media_frame = clip.in_frame + frames_into_clip

            # Store original values before modifying
            original_out_frame = clip.out_frame

            # Modify the first clip: trim end to playhead
            clip.out_frame = split_media_frame
            clip.prepareGeometryChange()
            clip.setRect(0, 0, clip.frame_count * ppf, 50)

            # Create the second clip: starts at playhead
            new_clip_id = self.timeline.next_available_member_id()
            new_member_config = clip.member_config.copy()

            new_clip = self.timeline.MediaMember(
                timeline_view=self.timeline,
                member_id=new_clip_id,
                start_frame=playhead_frame,
                track_index=clip.track_index,
                member_config=new_member_config,
            )

            # Set the in/out points for the new clip
            new_clip.in_frame = split_media_frame
            new_clip.out_frame = original_out_frame

            # Update the rect to match the new frame count
            new_clip.prepareGeometryChange()
            new_clip.setRect(0, 0, new_clip.frame_count * ppf, 50)
            new_clip.setPos(playhead_frame * ppf, clip.track_index * 60)

            # Add to scene and clips dict
            self.timeline.scene.addItem(new_clip)
            self.timeline.clips[new_clip_id] = new_clip

        self.timeline.studio.save()

    def separate_audio_track(self):
        """Separate audio track from video."""
        selected_items = self.timeline.scene.selectedItems()
        if not selected_items:
            return
        clip_to_separate = selected_items[0]
        if not isinstance(clip_to_separate, self.timeline.MediaMember):
            return
        if clip_to_separate.member_type != 'video':
            return
        
        # copy the browse.path to a new Audio member
        audio_member_id = self.timeline.next_available_member_id()
        audio_member_config = {k: v for k, v in clip_to_separate.member_config.items()}
        audio_member_config['_TYPE'] = 'audio'
        audio_member = self.timeline.MediaMember(
            timeline_view=self.timeline,
            member_id=audio_member_id,
            start_frame=clip_to_separate.start_frame,
            track_index=clip_to_separate.track_index + 1,
            member_config=audio_member_config,
        )

        self.timeline.scene.addItem(audio_member)
        self.timeline.clips[audio_member_id] = audio_member

        # set volume of clip_to_separate to 0
        clip_to_separate.member_config['volume'] = 0
        clip_to_separate.update()

    def extract_frame(self, mode='current'):
        """Extract a single frame from the selected video clip as a PNG image.

        Parameters
        ----------
        mode : str
            Which frame to extract: 'current', 'first', or 'last'.
        """
        selected_items = self.timeline.scene.selectedItems()
        if not selected_items:
            return
        clip = selected_items[0]
        if not isinstance(clip, self.timeline.MediaMember):
            return
        if clip.member_type != 'video':
            return

        filepath = clip.member_config.get('browse.path', '')
        if not filepath or not os.path.isfile(filepath):
            return

        fps = self.project_fps

        if mode == 'first':
            source_frame = clip.in_frame
        elif mode == 'last':
            source_frame = clip.out_frame - 1
        else:
            playhead_frame = self.timeline.get_playhead_frame()
            source_frame = playhead_frame - clip.start_frame + clip.in_frame
            source_frame = max(clip.in_frame, min(source_frame, clip.out_frame - 1))

        time_seconds = frame_to_time(source_frame, fps)

        stem = os.path.splitext(filepath)[0]
        output_path = f"{stem}_frame_{source_frame}.png"

        subprocess.run(
            [
                'ffmpeg', '-y',
                '-ss', str(time_seconds),
                '-i', filepath,
                '-frames:v', '1',
                '-q:v', '1',
                '-loglevel', 'error',
                output_path,
            ],
            check=False,
        )

        if not os.path.isfile(output_path):
            return

        # Insert extracted frame as an image clip on the timeline
        image_member_id = self.timeline.next_available_member_id()
        image_member_config = {
            '_TYPE': 'image',
            'name': os.path.basename(output_path),
            'browse.path': output_path,
        }
        playhead_frame = self.timeline.get_playhead_frame()
        image_member = self.timeline.MediaMember(
            timeline_view=self.timeline,
            member_id=image_member_id,
            start_frame=playhead_frame,
            track_index=clip.track_index + 1,
            member_config=image_member_config,
        )
        self.timeline.scene.addItem(image_member)
        self.timeline.clips[image_member_id] = image_member

    def split_at_transitions(self):
        """Detect scene transitions in selected video clips and split at each transition."""
        from scenedetect import detect, ContentDetector

        selected_items = self.timeline.scene.selectedItems()
        if not selected_items:
            return

        ppf = self.timeline.units_per_frame

        for clip in selected_items:
            if not isinstance(clip, self.timeline.MediaMember):
                continue

            # Only process video clips
            if clip.member_type != 'video':
                continue

            filepath = clip.filepath
            if not filepath or not os.path.exists(filepath):
                continue

            # Detect scenes using scenedetect
            try:
                scene_list = detect(filepath, ContentDetector())
            except Exception:
                continue

            if not scene_list:
                continue

            # Get transition times (start of each scene after the first)
            # Filter to only transitions within the clip's in/out points
            split_frames = []
            for scene_start, scene_end in scene_list[1:]:  # Skip first scene
                transition_time = scene_start.get_seconds()

                # Check if transition is within clip's visible portion
                if transition_time <= clip.in_point or transition_time >= clip.out_point:
                    continue

                # Convert to timeline frame
                frames_into_clip = time_to_frame(transition_time - clip.in_point, self.project_fps)
                timeline_frame = clip.start_frame + frames_into_clip
                split_frames.append(timeline_frame)

            if not split_frames:
                continue

            split_frames.sort()

            # Split clip at each transition (process in reverse to avoid index issues)
            current_clip = clip
            for split_frame in reversed(split_frames):
                # Ensure split point is within current clip bounds
                clip_start = current_clip.start_frame
                clip_end = current_clip.start_frame + current_clip.frame_count

                if split_frame <= clip_start or split_frame >= clip_end:
                    continue

                # Calculate split point in media frames
                frames_into_clip = split_frame - current_clip.start_frame
                split_media_frame = current_clip.in_frame + frames_into_clip

                # Store original out_frame
                original_out_frame = current_clip.out_frame

                # Trim current clip to end at split point
                current_clip.out_frame = split_media_frame
                current_clip.prepareGeometryChange()
                current_clip.setRect(0, 0, current_clip.frame_count * ppf, 50)

                # Create new clip for the portion after split
                new_clip_id = self.timeline.next_available_member_id()
                new_member_config = current_clip.member_config.copy()

                new_clip = self.timeline.MediaMember(
                    timeline_view=self.timeline,
                    member_id=new_clip_id,
                    start_frame=split_frame,
                    in_frame=split_media_frame,
                    out_frame=original_out_frame,
                    track_index=current_clip.track_index,
                    member_config=new_member_config,
                )

                # new_clip.in_frame = split_media_frame
                # new_clip.out_frame = original_out_frame
                new_clip.prepareGeometryChange()
                new_clip.setRect(0, 0, new_clip.frame_count * ppf, 50)
                new_clip.setPos(split_frame * ppf, current_clip.track_index * 60)

                self.timeline.scene.addItem(new_clip)
                self.timeline.clips[new_clip_id] = new_clip

        self.timeline.studio.save()

    def delete_clip(self):
        """Delete all selected clips from the timeline."""
        selected_items = self.timeline.scene.selectedItems()
        clips_to_delete = [
            item for item in selected_items
            if isinstance(item, self.timeline.MediaMember)
        ]
        if not clips_to_delete:
            return

        # Confirmation dialog
        count = len(clips_to_delete)
        msg = f"Delete {count} clip{'s' if count > 1 else ''}?"
        reply = QMessageBox.question(
            self, "Delete Clips", msg,
            QMessageBox.Yes | QMessageBox.No,
            defaultButton=QMessageBox.Yes,
        )
        if reply != QMessageBox.Yes:
            return

        for clip in clips_to_delete:
            self.timeline.scene.removeItem(clip)
            if clip.member_id in self.timeline.clips:
                del self.timeline.clips[clip.member_id]

        self.timeline.update_scene_rect()
        self.timeline.studio.save()

    def export_project(self):
        return

    def render_project(self):
        """Open render dialog and start rendering."""
        dialog = RenderDialog(self)
        if not dialog.exec_():
            return

        render_config = dialog.get_config()

        # Create progress dialog
        progress_dialog = RenderProgressDialog(self)

        # Create worker and thread
        self._render_thread = QThread()
        self._render_worker = RenderWorker(self, render_config)
        self._render_worker.moveToThread(self._render_thread)

        # Connect signals
        self._render_worker.progress.connect(progress_dialog.set_progress)
        self._render_worker.status.connect(progress_dialog.set_status)
        self._render_worker.finished.connect(progress_dialog.on_finished)
        self._render_worker.error.connect(progress_dialog.on_error)
        self._render_worker.finished.connect(self._render_thread.quit)
        self._render_worker.error.connect(self._render_thread.quit)
        progress_dialog.cancelled.connect(self._render_worker.cancel)

        self._render_thread.started.connect(self._render_worker.run)
        self._render_thread.finished.connect(
            lambda: self._cleanup_render()
        )

        self._render_thread.start()
        progress_dialog.exec_()

    def _cleanup_render(self):
        """Clean up render thread and worker."""
        if hasattr(self, '_render_worker'):
            self._render_worker.deleteLater()
            del self._render_worker
        if hasattr(self, '_render_thread'):
            self._render_thread.deleteLater()
            del self._render_thread

    def project_settings(self):
        """Open project settings dialog."""
        dialog = ProjectSettingsDialog(self)
        if dialog.exec_():
            settings = dialog.get_config()
            self.project_fps = float(settings['fps'])

            self.resize_canvas(settings['width'], settings['height'])
    
    def resize_canvas(self, width, height):
        self.project_width = width
        self.project_height = height
        self.preview_panel.update_dimensions()
    
    def get_content_dimensions(self):
        scene = self.preview_panel.scene
        bounding_rect = QRectF()

        for item in scene.items():
            if isinstance(item, PreviewClipItem) and item.pixmap:
                item_rect = item.mapToScene(item.content_rect()).boundingRect()
                if bounding_rect.isNull():
                    bounding_rect = item_rect
                else:
                    bounding_rect = bounding_rect.united(item_rect)

        return int(bounding_rect.width()), int(bounding_rect.height())


class ProjectSettingsDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowFlags(
            Qt.Window
            | Qt.WindowTitleHint
            | Qt.WindowSystemMenuHint
            | Qt.WindowCloseButtonHint
            | Qt.WindowStaysOnTopHint
        )
        self.studio = parent
        self.setWindowTitle("Project Settings")
        self.resize(400, 300)
        self.layout = QVBoxLayout(self)
        
        # Config Fields
        self.config_fields = ConfigFields(
            self,
            schema=[
                {
                    'text': 'Width',
                    'key': 'width',
                    'type': int,
                    'default': parent.project_width,
                },
                {
                    'text': 'Height',
                    'key': 'height',
                    'type': int,
                    'default': parent.project_height,
                },
                {
                    'text': 'FPS',
                    'key': 'fps',
                    'type': (15, 23.976, 24, 25, 29.97, 30, 50, 59.94, 60),
                    'default': parent.project_fps,
                },
            ]
        )
        self.config_fields.load_config({}) # Load defaults from schema
        self.config_fields.build_schema()
        self.config_fields.load()
        self.layout.addWidget(self.config_fields)

        # Fit to contents button
        self.btn_fit_canvas = QPushButton("Fit canvas to contents")
        self.btn_fit_canvas.clicked.connect(self.fit_canvas_to_contents)
        self.layout.addWidget(self.btn_fit_canvas)

        # Buttons
        button_box = QWidget()
        button_layout = QHBoxLayout(button_box)
        button_layout.setContentsMargins(0, 0, 0, 0)

        self.btn_cancel = QPushButton("Cancel")
        self.btn_cancel.clicked.connect(self.reject)

        self.btn_ok = QPushButton("OK")
        self.btn_ok.clicked.connect(self.accept)

        button_layout.addStretch()
        button_layout.addWidget(self.btn_cancel)
        button_layout.addWidget(self.btn_ok)

        self.layout.addWidget(button_box)

    def get_config(self):
        self.config_fields.update_config()
        return self.config_fields.get_config()
    
    # def on_fit_canvas(self):
    #     self.studio.fit_canvas_to_contents()
        
    def fit_canvas_to_contents(self):
        """Calculate bounding box of all preview items and update dimensions."""
        # studio = self.parent()
        # if not hasattr(studio, 'preview_panel'):
        #     return

        new_width, new_height = self.studio.get_content_dimensions()

        # # Update config fields with new dimensions
        # new_width = int(width)
        # new_height = int(height)

        self.config_fields.width_wgt.set_value(new_width)
        self.config_fields.height_wgt.set_value(new_height)

        # # Offset items so content starts at origin (0,0)
        # offset_x = bounding_rect.x()
        # offset_y = bounding_rect.y()
        # if offset_x != 0 or offset_y != 0:
        #     for item in scene.items():
        #         if isinstance(item, PreviewClipItem):
        #             item.media_member.pos_x -= offset_x
        #             item.media_member.pos_y -= offset_y
        #             item.update_from_member()


FORMAT_CODEC_MAP = {
    'MP4 (H.264)': {'ext': '.mp4', 'vcodec': 'libx264', 'acodec': 'aac'},
    'MP4 (H.265)': {'ext': '.mp4', 'vcodec': 'libx265', 'acodec': 'aac'},
    'WebM (VP9)': {'ext': '.webm', 'vcodec': 'libvpx-vp9', 'acodec': 'libopus'},
    'MOV (ProRes)': {'ext': '.mov', 'vcodec': 'prores_ks', 'acodec': 'pcm_s16le'},
    'AVI': {'ext': '.avi', 'vcodec': 'libx264', 'acodec': 'mp3'},
    'MKV': {'ext': '.mkv', 'vcodec': 'libx264', 'acodec': 'aac'},
}

QUALITY_CRF_MAP = {
    'Low': 32,
    'Medium': 23,
    'High': 18,
    'Very High': 14,
    'Lossless': 0,
}

AUDIO_CODEC_MAP = {
    'AAC': 'aac',
    'MP3': 'libmp3lame',
    'PCM': 'pcm_s16le',
    'Opus': 'libopus',
    'None (no audio)': None,
}


class RenderDialog(QDialog):
    """Dialog for configuring render/export settings."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowFlags(
            Qt.Window
            | Qt.WindowTitleHint
            | Qt.WindowSystemMenuHint
            | Qt.WindowCloseButtonHint
            | Qt.WindowStaysOnTopHint
        )
        self.studio = parent
        self.setWindowTitle("Render Project")
        self.resize(450, 500)
        self.layout = QVBoxLayout(self)

        self.config_fields = ConfigFields(
            self,
            schema=[
                # -- Output --
                {
                    'text': 'Output Path',
                    'key': 'output_path',
                    'type': 'file_picker',
                    'default': os.path.join(
                        os.path.expanduser('~'),
                        'render_output.mp4'
                    ),
                    'mode': 'save',
                    'file_filter': 'Video Files (*.mp4 *.webm *.mov *.avi *.mkv)',
                },
                {
                    'text': 'Format',
                    'key': 'format',
                    'type': tuple(FORMAT_CODEC_MAP.keys()),
                    'default': 'MP4 (H.264)',
                },
                # -- Video --
                {
                    'text': 'Resolution',
                    'key': 'resolution',
                    'type': ('Use Project', 'Custom'),
                    'default': 'Use Project',
                },
                {
                    'text': 'Width',
                    'key': 'custom_width',
                    'type': int,
                    'default': parent.project_width,
                    'minimum': 2,
                    'maximum': 7680,
                    'visibility_predicate': lambda fields: (
                        fields.config.get('resolution') == 'Custom'
                    ),
                },
                {
                    'text': 'Height',
                    'key': 'custom_height',
                    'type': int,
                    'default': parent.project_height,
                    'minimum': 2,
                    'maximum': 4320,
                    'visibility_predicate': lambda fields: (
                        fields.config.get('resolution') == 'Custom'
                    ),
                },
                {
                    'text': 'FPS',
                    'key': 'fps_mode',
                    'type': ('Use Project', 'Custom'),
                    'default': 'Use Project',
                },
                {
                    'text': 'Custom FPS',
                    'key': 'custom_fps',
                    'type': (15, 23.976, 24, 25, 29.97, 30, 50, 59.94, 60),
                    'default': 30,
                    'visibility_predicate': lambda fields: (
                        fields.config.get('fps_mode') == 'Custom'
                    ),
                },
                {
                    'text': 'Quality',
                    'key': 'quality',
                    'type': (
                        'Low', 'Medium', 'High',
                        'Very High', 'Lossless', 'Custom CRF'
                    ),
                    'default': 'High',
                },
                {
                    'text': 'CRF',
                    'key': 'custom_crf',
                    'type': int,
                    'default': 18,
                    'minimum': 0,
                    'maximum': 51,
                    'visibility_predicate': lambda fields: (
                        fields.config.get('quality') == 'Custom CRF'
                    ),
                },
                {
                    'text': 'Pixel Format',
                    'key': 'pix_fmt',
                    'type': (
                        'yuv420p', 'yuv444p',
                        'yuv420p10le', 'yuv444p10le'
                    ),
                    'default': 'yuv420p',
                },
                # -- Audio --
                {
                    'text': 'Audio Codec',
                    'key': 'audio_codec',
                    'type': tuple(AUDIO_CODEC_MAP.keys()),
                    'default': 'AAC',
                },
                {
                    'text': 'Sample Rate',
                    'key': 'sample_rate',
                    'type': ('44100', '48000'),
                    'default': '48000',
                    'visibility_predicate': lambda fields: (
                        fields.config.get('audio_codec')
                        != 'None (no audio)'
                    ),
                },
                {
                    'text': 'Channels',
                    'key': 'channels',
                    'type': ('Stereo', 'Mono'),
                    'default': 'Stereo',
                    'visibility_predicate': lambda fields: (
                        fields.config.get('audio_codec')
                        != 'None (no audio)'
                    ),
                },
                {
                    'text': 'Audio Bitrate',
                    'key': 'audio_bitrate',
                    'type': ('128k', '192k', '256k', '320k'),
                    'default': '192k',
                    'visibility_predicate': lambda fields: (
                        fields.config.get('audio_codec') not in (
                            'None (no audio)', 'PCM'
                        )
                    ),
                },
                # -- Range --
                {
                    'text': 'Auto Duration',
                    'key': 'auto_duration',
                    'type': bool,
                    'default': True,
                },
                {
                    'text': 'Start Frame',
                    'key': 'start_frame',
                    'type': int,
                    'default': 0,
                    'minimum': 0,
                    'visibility_predicate': lambda fields: (
                        not fields.config.get('auto_duration', True)
                    ),
                },
                {
                    'text': 'End Frame',
                    'key': 'end_frame',
                    'type': int,
                    'default': 300,
                    'minimum': 1,
                    'visibility_predicate': lambda fields: (
                        not fields.config.get('auto_duration', True)
                    ),
                },
                {
                    'text': 'Use Loop Region',
                    'key': 'use_loop_region',
                    'type': bool,
                    'default': False,
                    'visibility_predicate': lambda fields: (
                        self._has_loop_region()
                    ),
                },
            ]
        )
        self.config_fields.load_config({})
        self.config_fields.build_schema()
        self.config_fields.load()
        self.layout.addWidget(self.config_fields)

        # Buttons
        button_box = QWidget()
        button_layout = QHBoxLayout(button_box)
        button_layout.setContentsMargins(0, 0, 0, 0)

        self.btn_cancel = QPushButton("Cancel")
        self.btn_cancel.clicked.connect(self.reject)

        self.btn_render = QPushButton("Render")
        self.btn_render.clicked.connect(self._on_render)

        button_layout.addStretch()
        button_layout.addWidget(self.btn_cancel)
        button_layout.addWidget(self.btn_render)
        self.layout.addWidget(button_box)

    def _has_loop_region(self):
        """Check if the timeline has loop flags set."""
        tl = self.studio.timeline
        return (
            tl.loop_start_flag is not None
            and tl.loop_end_flag is not None
        )

    def _calculate_timeline_end_frame(self):
        """Find the last frame across all clips."""
        end = 0
        for clip in self.studio.timeline.clips.values():
            clip_end = clip.start_frame + clip.frame_count
            if clip_end > end:
                end = clip_end
        return end

    def _on_render(self):
        """Validate settings and accept dialog."""
        self.config_fields.update_config()
        config = self.config_fields.get_config()

        output_path = config.get('output_path', '').strip()
        if not output_path:
            QMessageBox.warning(
                self, "Render", "Please specify an output path."
            )
            return

        # Auto-append extension if missing
        fmt = config.get('format', 'MP4 (H.264)')
        ext = FORMAT_CODEC_MAP[fmt]['ext']
        if not os.path.splitext(output_path)[1]:
            output_path += ext
            self.config_fields.output_path_wgt.set_value(output_path)

        if os.path.exists(output_path):
            reply = QMessageBox.question(
                self, "Render",
                f"File already exists:\n{output_path}\n\nOverwrite?",
                QMessageBox.Yes | QMessageBox.No,
                QMessageBox.No,
            )
            if reply != QMessageBox.Yes:
                return

        self.accept()

    def get_config(self):
        """Return resolved render configuration."""
        self.config_fields.update_config()
        config = self.config_fields.get_config()

        fmt = config.get('format', 'MP4 (H.264)')
        fmt_info = FORMAT_CODEC_MAP[fmt]

        # Resolution
        if config.get('resolution') == 'Custom':
            width = config.get('custom_width', self.studio.project_width)
            height = config.get('custom_height', self.studio.project_height)
        else:
            width = self.studio.project_width
            height = self.studio.project_height

        # FPS
        if config.get('fps_mode') == 'Custom':
            fps = float(config.get('custom_fps', 30))
        else:
            fps = float(self.studio.project_fps)

        # CRF
        quality = config.get('quality', 'High')
        if quality == 'Custom CRF':
            crf = config.get('custom_crf', 18)
        else:
            crf = QUALITY_CRF_MAP.get(quality, 18)

        # Frame range
        if config.get('use_loop_region') and self._has_loop_region():
            start_frame = self.studio.timeline.get_loop_start_frame()
            end_frame = self.studio.timeline.get_loop_end_frame()
        elif config.get('auto_duration', True):
            start_frame = 0
            end_frame = self._calculate_timeline_end_frame()
        else:
            start_frame = config.get('start_frame', 0)
            end_frame = config.get('end_frame', 300)

        # Audio codec
        audio_codec_key = config.get('audio_codec', 'AAC')
        audio_codec = AUDIO_CODEC_MAP.get(audio_codec_key)

        return {
            'output_path': config.get('output_path', ''),
            'vcodec': fmt_info['vcodec'],
            'ext': fmt_info['ext'],
            'width': width,
            'height': height,
            'fps': fps,
            'crf': crf,
            'pix_fmt': config.get('pix_fmt', 'yuv420p'),
            'audio_codec': audio_codec,
            'sample_rate': int(config.get('sample_rate', 48000)),
            'channels': 2 if config.get('channels') == 'Stereo' else 1,
            'audio_bitrate': config.get('audio_bitrate', '192k'),
            'start_frame': start_frame,
            'end_frame': end_frame,
        }


class RenderProgressDialog(QDialog):
    """Progress dialog shown during rendering."""

    cancelled = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowFlags(
            Qt.Window
            | Qt.WindowTitleHint
            | Qt.WindowSystemMenuHint
            | Qt.WindowCloseButtonHint
            | Qt.WindowStaysOnTopHint
        )
        self.setWindowTitle("Rendering")
        self.setMinimumWidth(400)
        self.setModal(True)
        layout = QVBoxLayout(self)

        self.status_label = QLabel("Preparing...")
        layout.addWidget(self.status_label)

        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 100)
        layout.addWidget(self.progress_bar)

        self.frame_label = QLabel("")
        layout.addWidget(self.frame_label)

        self.btn_cancel = QPushButton("Cancel")
        self.btn_cancel.clicked.connect(self._on_cancel)
        layout.addWidget(self.btn_cancel)

    def set_progress(self, current, total):
        if total > 0:
            self.progress_bar.setValue(int(current * 100 / total))
        self.frame_label.setText(f"Frame {current} / {total}")

    def set_status(self, text):
        self.status_label.setText(text)

    def on_finished(self):
        self.status_label.setText("Render complete!")
        self.btn_cancel.setText("Close")
        self.btn_cancel.clicked.disconnect()
        self.btn_cancel.clicked.connect(self.accept)

    def on_error(self, msg):
        self.status_label.setText(f"Error: {msg}")
        self.btn_cancel.setText("Close")
        self.btn_cancel.clicked.disconnect()
        self.btn_cancel.clicked.connect(self.reject)

    def _on_cancel(self):
        self.cancelled.emit()
        self.reject()


class RenderWorker(QObject):
    """Background worker that performs the actual rendering."""

    progress = Signal(int, int)
    status = Signal(str)
    finished = Signal()
    error = Signal(str)

    def __init__(self, studio, render_config):
        super().__init__()
        self.studio = studio
        self.config = render_config
        self._cancelled = False

    def cancel(self):
        self._cancelled = True

    @Slot()
    def run(self):
        try:
            self._do_render()
        except Exception as e:
            self.error.emit(str(e))

    def _do_render(self):
        from utils.media_export import render_timeline_audio, render_timeline_video

        cfg = self.config
        fps = cfg['fps']
        start_frame = cfg['start_frame']
        end_frame = cfg['end_frame']
        total_frames = end_frame - start_frame

        if total_frames <= 0:
            self.error.emit("No frames to render.")
            return

        # Serialize clip data from timeline (avoid cross-thread Qt access)
        clip_data_list = []
        for clip_id, clip in self.studio.timeline.clips.items():
            clip_data_list.append({
                'member_id': clip.member_id,
                'filepath': clip.filepath,
                'media_type': clip.member_type,
                'start_frame': clip.start_frame,
                'in_frame': clip.in_frame,
                'out_frame': clip.out_frame,
                'frame_count': clip.frame_count,
                'track_index': clip.track_index,
                'is_disabled': clip.is_disabled,
                'scale': getattr(clip, 'scale', 1.0),
                'pos_x': getattr(clip, 'pos_x', 0.0),
                'pos_y': getattr(clip, 'pos_y', 0.0),
                'rotation': getattr(clip, 'rotation', 0.0),
                'volume': clip.member_config.get('volume', 100),
            })

        track_configs = self.studio.track_control_panel.get_config()

        # Phase 1: Audio
        temp_audio = None
        if cfg['audio_codec'] is not None:
            self.status.emit("Rendering audio...")
            audio_clips = []
            for cd in clip_data_list:
                if cd['is_disabled']:
                    continue
                if cd['media_type'] not in ('audio', 'video'):
                    continue
                if not cd['filepath'] or not os.path.isfile(cd['filepath']):
                    continue

                clip_volume = cd.get('volume', 100)
                track_vol = 100
                if cd['track_index'] < len(track_configs):
                    track_vol = track_configs[cd['track_index']].get(
                        'volume', 100
                    )
                combined_volume = (clip_volume * track_vol) / 100.0

                audio_clips.append({
                    'filepath': cd['filepath'],
                    'start_time': cd['start_frame'] / fps,
                    'in_point': cd['in_frame'] / fps,
                    'duration': cd['frame_count'] / fps,
                    'volume': combined_volume,
                })

            import tempfile
            temp_audio = os.path.join(
                tempfile.gettempdir(), '_render_audio.wav'
            )
            start_time = start_frame / fps
            duration = total_frames / fps
            render_timeline_audio(
                audio_clips, start_time, duration, fps, temp_audio
            )

        if self._cancelled:
            self._cleanup(temp_audio, None)
            return

        # Phase 2: Video
        self.status.emit("Rendering video...")

        def progress_callback(current, total):
            self.progress.emit(current, total)
            return not self._cancelled

        output_path = cfg['output_path']
        render_timeline_video(
            clip_data_list=clip_data_list,
            start_frame=start_frame,
            end_frame=end_frame,
            fps=fps,
            width=cfg['width'],
            height=cfg['height'],
            output_path=output_path,
            vcodec=cfg['vcodec'],
            crf=cfg['crf'],
            pix_fmt=cfg['pix_fmt'],
            audio_path=temp_audio,
            audio_codec=cfg['audio_codec'],
            audio_bitrate=cfg['audio_bitrate'],
            sample_rate=cfg['sample_rate'],
            channels=cfg['channels'],
            progress_callback=progress_callback,
        )

        # Clean up temp audio
        self._cleanup(temp_audio, None)

        if self._cancelled:
            # Remove partial output
            if os.path.exists(output_path):
                os.remove(output_path)
            return

        self.finished.emit()

    def _cleanup(self, temp_audio, _):
        if temp_audio and os.path.exists(temp_audio):
            try:
                os.remove(temp_audio)
            except OSError:
                pass


class TimelineScene(QGraphicsScene):
    """Scene that paints track backgrounds dynamically."""

    def __init__(self, timeline_view, parent=None):
        super().__init__(parent)
        self.timeline_view = timeline_view

    def drawBackground(self, painter, rect):
        super().drawBackground(painter, rect)
        painter.setPen(QPen(QColor(80, 80, 80)))
        painter.setBrush(QBrush(QColor(40, 40, 40)))
        for i, _ in enumerate(self.timeline_view.tracks):
            y = i * 60
            if y + 60 < rect.y() or y > rect.y() + rect.height():
                continue
            painter.drawRect(QRectF(rect.x(), y, rect.width(), 60))


class TimelineView(QGraphicsView):
    """Timeline view for video editing with multiple tracks."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.studio = parent
        self.scene = TimelineScene(self)
        self.setScene(self.scene)
        self.setAlignment(Qt.AlignLeft | Qt.AlignTop)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOn)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOn)
        self.setDragMode(QGraphicsView.RubberBandDrag)
        self.setAcceptDrops(True)
        self.setTransformationAnchor(QGraphicsView.AnchorUnderMouse)
        self.setViewportUpdateMode(QGraphicsView.FullViewportUpdate)

        # self.members_in_view: Dict[str, self.timeline.MediaMember] = {}
        self.new_members = None
    
        self.clips = {}
        self.tracks = []
        self.playhead_frame = 0  # Current playhead position in frames
        self.playhead_item = None
        self.units_per_frame = 3  # Base scale factor (units per frame)
        self._updating_playhead = False  # Flag to prevent feedback loop

        # Throttle timer for frame requests during scrubbing
        self._scrub_timer = QTimer()
        self._scrub_timer.setSingleShot(True)
        self._scrub_timer.timeout.connect(self._perform_frame_request)
        self._pending_frame = None  # Pending frame number for scrubbing
        self._scrub_throttle_ms = 30  # 30ms = ~33fps max during scrubbing

        # Scrubbing state (dragging on empty area to move playhead)
        self._is_scrubbing = False

        # Loop flags
        self.loop_start_flag = None
        self.loop_end_flag = None

        # Initialize timeline with default tracks.
        self.scene.clear()
        self.tracks = []
        
        self.scene.setSceneRect(0, 0, 3000, 600)
        
        # Create draggable playhead
        self.playhead_item = self.PlayheadItem(len(self.tracks) * 60)
        self.playhead_item.timeline_view = self
        self.scene.addItem(self.playhead_item)
    
    def set_playhead_frame(self, frame_number: int):
        """Set playhead position in frames."""
        self.playhead_frame = frame_number
        if self.playhead_item:
            x = frame_number * self.units_per_frame
            self._updating_playhead = True  # Set flag before programmatic update
            self.playhead_item.setPos(x, 0)
            self._updating_playhead = False  # Clear flag after update

    def get_playhead_frame(self) -> int:
        """Get current playhead position in frames from playhead's actual position."""
        if self.playhead_item:
            x = self.playhead_item.pos().x()
            return int(x / self.units_per_frame)
        return 0

    def get_playhead_time(self) -> float:
        """Get current playhead position in seconds (convenience method)."""
        return frame_to_time(self.get_playhead_frame(), self.studio.project_fps)

    def toggle_loop_flags(self):
        """Toggle loop start/end flags on the timeline."""
        if self.loop_start_flag is not None:
            self.scene.removeItem(self.loop_start_flag)
            self.scene.removeItem(self.loop_end_flag)
            self.loop_start_flag = None
            self.loop_end_flag = None
            return

        height = len(self.tracks) * 60
        fps = self.studio.project_fps
        current_frame = self.get_playhead_frame()
        end_frame = current_frame + int(fps * 5)

        self.loop_start_flag = self.LoopFlagItem(
            height, is_start=True,
        )
        self.loop_start_flag.timeline_view = self
        self.loop_start_flag.frame = current_frame
        self.loop_start_flag.setPos(
            current_frame * self.units_per_frame, 0,
        )
        self.scene.addItem(self.loop_start_flag)

        self.loop_end_flag = self.LoopFlagItem(
            height, is_start=False,
        )
        self.loop_end_flag.timeline_view = self
        self.loop_end_flag.frame = end_frame
        self.loop_end_flag.setPos(
            end_frame * self.units_per_frame, 0,
        )
        self.scene.addItem(self.loop_end_flag)

    def get_loop_start_frame(self):
        """Get loop start position in frames."""
        if self.loop_start_flag is None:
            return 0
        return self.loop_start_flag.frame

    def get_loop_end_frame(self):
        """Get loop end position in frames."""
        if self.loop_end_flag is None:
            return 0
        return self.loop_end_flag.frame

    def _on_playhead_moved(self):
        """Only render frame manually if not playing (scrub)."""
        frame = self.get_playhead_frame()
        self.playhead_frame = frame

        # Auto-pan when playhead is within 100px of viewport edge
        playhead_scene_x = frame * self.units_per_frame
        playhead_view_x = self.mapFromScene(playhead_scene_x, 0).x()
        view_width = self.viewport().width()
        edge_margin = 100
        h_bar = self.horizontalScrollBar()
        if playhead_view_x < edge_margin:
            h_bar.setValue(h_bar.value() - (edge_margin - int(playhead_view_x)))
        elif playhead_view_x > view_width - edge_margin:
            h_bar.setValue(h_bar.value() + (int(playhead_view_x) - (view_width - edge_margin)))

        if not self.studio.preview_panel.is_playing:
            # Store pending frame and start/restart timer
            self._pending_frame = max(0, frame)
            self._scrub_timer.stop()
            self._scrub_timer.start(self._scrub_throttle_ms)

    def _perform_frame_request(self):
        """Actually perform the frame request after throttle delay."""
        if self._pending_frame is not None:
            self.studio.preview_panel.request_frame(self._pending_frame)
            self._pending_frame = None

    def zoom_in(self):
        """Zoom in on timeline."""
        self.scale((1.0 / 0.98), 1.0)
        self.update_scene_rect()

    def zoom_out(self):
        """Zoom out on timeline."""
        self.scale(0.98, 1.0)
        self.update_scene_rect()

    def update_scene_rect(self):
        """Recalculate scene rect to fit content plus padding."""
        max_x = 0
        for clip in self.clips.values():
            clip_end = clip.pos().x() + clip.rect().width()
            if clip_end > max_x:
                max_x = clip_end
        playhead_x = self.playhead_frame * self.units_per_frame
        if playhead_x > max_x:
            max_x = playhead_x
        if self.loop_end_flag is not None:
            flag_x = self.loop_end_flag.pos().x()
            if flag_x > max_x:
                max_x = flag_x
        t = self.transform()
        padding = (self.viewport().width() / t.m11()
                   if t.m11() > 0
                   else self.viewport().width())
        total_width = max(padding, max_x + padding)
        timeline_height = max(1, len(self.tracks)) * 60
        self.scene.setSceneRect(0, 0, total_width, timeline_height)

    def add_insertable_entity(self, item, del_pairs=None):
        if self.new_members:
            return

        all_items = [(QPointF(0, 0), item)]

        self.new_members = [
            (
                pos,
                self.MediaMember(
                    timeline_view=self,
                    member_id=None,
                    start_frame=0,
                    track_index=None,
                    member_config=config,
                ),
            ) for pos, config in all_items
        ]
        for _, entity in self.new_members:
            self.scene.addItem(entity)

        self.setFocus()

    def add_entity(self):
        start_member_id = int(self.next_available_member_id())

        member_index_id_map = {}
        for i, enitity_tup in enumerate(self.new_members):
            entity_id = str(start_member_id + i)
            _, entity = enitity_tup
            entity_config = entity.member_config

            # Use entity's current position after mouse movement
            current_pos = entity.pos()

            member = self.MediaMember(
                timeline_view=self,
                member_id=entity_id,
                start_frame=int(current_pos.x() / self.units_per_frame),
                track_index=int(current_pos.y() / 60),
                member_config=entity_config,
            )
            # set z
            # member.setZValue(1)
            self.scene.addItem(member)
            self.clips[entity_id] = member
            member_index_id_map[i] = entity_id

        self.cancel_new_entity()
        self.update_scene_rect()

    def cancel_new_entity(self):
        # Remove the new entity from the scene and delete it
        if self.new_members:
            for pos, entity in self.new_members:
                self.scene.removeItem(entity)

        self.new_members = None
        # self.del_pairs = None
        self.update()
        
    def next_available_member_id(self) -> str:
        member_ids = [int(k) for k in self.clips.keys()] + [0]
        return str(max(member_ids) + 1)

    def contextMenuEvent(self, event):
        studio_menu = self.studio.timeline_toolbar
        schema = [item.copy() for item in studio_menu.schema]
        schema[0].pop('target')
        schema[0]['submenu'] = studio_menu.create_new_member_menu()
        menu = CustomMenu(parent=self, schema=schema)
        menu.show_popup_menu()
    
    def wheelEvent(self, event):
        """Handle mouse wheel event for zooming with Ctrl."""
        if event.modifiers() == Qt.ControlModifier:
            # Perform zoom
            if event.angleDelta().y() > 0:
                self.zoom_in()
            else:
                self.zoom_out()

            event.accept()
        else:
            super().wheelEvent(event)

    def dragEnterEvent(self, event):
        """Handle drag enter event."""
        if event.mimeData().hasUrls():
            event.acceptProposedAction()
        else:
            event.ignore()

    def dragMoveEvent(self, event):
        """Handle drag move event."""
        if event.mimeData().hasUrls():
            event.acceptProposedAction()
        else:
            event.ignore()

    def dropEvent(self, event):
        """Handle drop event - add clips to timeline."""
        mime_data = event.mimeData()

        # Get drop position in scene coordinates
        pos = self.mapToScene(event.pos())
        start_frame = max(0, int(pos.x() / self.units_per_frame))
        track_index = max(0, int(pos.y() / 60))

        # Ensure track index is valid
        if track_index >= len(self.tracks):
            track_index = len(self.tracks) - 1

        filepaths = []

        # Handle files dropped from file manager, MediaBin, or Collections
        if mime_data.hasUrls():
            for url in mime_data.urls():
                filepath = url.toLocalFile()
                if os.path.exists(filepath):
                    filepaths.append(filepath)

        if not filepaths:
            event.ignore()
            return

        if len(filepaths) > 1:
            raise NotImplementedError()

        filepath = filepaths[0]
        ext = os.path.splitext(filepath)[1].lower()
        media_type = get_media_type_from_ext(ext)

        # Determine media type from extension
        if media_type is None:
            event.ignore()
            return

        config = {
            "_TYPE": media_type,
            "name": os.path.basename(filepath),
            "mode": "Browse",
            "browse.path": filepath,
        }

        # Create clip directly at drop position
        clip_id = self.next_available_member_id()
        member = self.MediaMember(
            timeline_view=self,
            member_id=clip_id,
            start_frame=start_frame,
            track_index=track_index,
            member_config=config,
        )
        self.scene.addItem(member)
        self.clips[clip_id] = member
        self.update_scene_rect()

        event.acceptProposedAction()

    def _get_snap_candidates(self):
        """Get all potential snap points from other clips."""
        snap_points = []
        for clip in self.clips.values():
            if clip.isSelected():
                continue
            clip_start = clip.pos().x()
            clip_end = clip.pos().x() + clip.rect().width()
            snap_points.extend([clip_start, clip_end])

        return snap_points

    def mouseReleaseEvent(self, event):
        self._is_scrubbing = False
        super().mouseReleaseEvent(event)

    def mousePressEvent(self, event):
        if self.new_members:
            self.add_entity()
            return

        pos = self.mapToScene(event.pos())
        item = self.scene.itemAt(pos, self.transform())

        # If click in empty area (not on a clip), seek playhead to clicked position
        # Ctrl+click draws selection instead
        is_loop_flag = (item is not None
                        and isinstance(item.group(), self.LoopFlagItem))
        if not isinstance(item, self.MediaMember) and not is_loop_flag:
            is_ctrl_held = event.modifiers() & Qt.ControlModifier
            is_left = event.button() == Qt.LeftButton
            is_right = event.button() == Qt.RightButton

            if (is_left and not is_ctrl_held) or is_right:
                self.scene.clearSelection()
                frame = max(0, int(pos.x() / self.units_per_frame))
                self.studio.preview_panel.stop_playback()
                self.set_playhead_frame(frame)
                self._on_playhead_moved()
                # Start scrubbing mode for left button drag
                if is_left:
                    self._is_scrubbing = True

        # Only allow rubber band selection when Ctrl is held
        if event.modifiers() & Qt.ControlModifier:
            self.setDragMode(QGraphicsView.RubberBandDrag)
        else:
            self.setDragMode(QGraphicsView.NoDrag)

        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        mouse_point = self.mapToScene(event.pos())

        # Handle scrubbing (dragging playhead)
        if self._is_scrubbing:
            frame = max(0, int(mouse_point.x() / self.units_per_frame))
            self.set_playhead_frame(frame)
            self._on_playhead_moved()
            event.accept()
            return

        if self.new_members:
            for pos, entity in self.new_members:
                new_y = mouse_point.y() // 60 * 60
                mouse_point.setY(new_y)
                entity.setCentredPos(mouse_point)

            if self.scene:
                self.scene.update()
            self.update()

        super().mouseMoveEvent(event)

    def keyPressEvent(self, event):
        if event.key() == Qt.Key_Delete or event.key() == Qt.Key_Escape:
            if self.new_members:
                self.cancel_new_entity()
                event.accept()
                return

        if event.key() == Qt.Key_Delete:
            self.studio.delete_clip()
            event.accept()
        elif event.key() == Qt.Key_Escape:
            selected_items = self.scene.selectedItems()
            if selected_items:
                # deselect all items
                self.scene.clearSelection()
                event.accept()
                return

        # elif event.modifiers() == Qt.ControlModifier:
        #     if event.key() == Qt.Key_C:
        #         self.parent.workflow_buttons.copy_selected_items()  # !404!
        #         event.accept()
        #     elif event.key() == Qt.Key_V:
        #         self.parent.workflow_buttons.paste_items()  # !404!
        #         event.accept()
        else:
            super().keyPressEvent(event)


    class PlayheadItem(QGraphicsLineItem):
        """Draggable playhead indicator for the timeline."""

        def __init__(self, height, parent=None):
            super().__init__(0, 0, 0, height, parent)
            pen = QPen(QColor(255, 0, 0), 2)
            pen.setCosmetic(True)
            self.setPen(pen)
            self.setFlag(QGraphicsItem.ItemIsMovable, True)
            self.setFlag(QGraphicsItem.ItemIsSelectable, False)
            self.setFlag(QGraphicsItem.ItemSendsGeometryChanges, True)
            # set to fixed 1px width ( pen)
            self.setZValue(100)  # Ensure playhead is on top
            self.timeline_view = None

        def itemChange(self, change, value):
            """Constrain playhead to vertical movement only."""
            if change == QGraphicsItem.ItemPositionChange and self.timeline_view:
                self.timeline_view.scene.clearSelection()
                new_pos = QPointF(value)
                # Keep y = 0
                new_pos.setY(0)
                # Constrain to non-negative x
                if new_pos.x() < 0:
                    new_pos.setX(0)
                return new_pos
            elif change == QGraphicsItem.ItemPositionHasChanged and self.timeline_view:  # different from ItemPositionChange
                # Only notify timeline if this is a user-initiated drag, not a programmatic update
                if not self.timeline_view._updating_playhead:
                    self.timeline_view.studio.preview_panel.stop_playback()
                    self.timeline_view._on_playhead_moved()
            return super().itemChange(change, value)

    class LoopFlagItem(QGraphicsItemGroup):
        """Draggable loop flag with a small handle rectangle."""

        def __init__(self, height, is_start=True, parent=None):
            super().__init__(parent)
            from gui.style import TEXT_COLOR
            self._is_start = is_start
            self._dragging = False
            self._drag_offset = 0
            self.timeline_view = None
            self.frame = 0

            color = QColor(TEXT_COLOR)
            pen = QPen(color, 1)
            pen.setCosmetic(True)

            # Vertical line spanning full timeline height
            self._line = QGraphicsLineItem(0, 0, 0, height)
            self._line.setPen(pen)
            self.addToGroup(self._line)

            # Handle rectangle (10x10)
            if is_start:
                self._handle = QGraphicsRectItem(-10, 0, 10, 10)
            else:
                self._handle = QGraphicsRectItem(0, 0, 10, 10)
            self._handle.setBrush(QBrush(color))
            self._handle.setPen(QPen(Qt.NoPen))
            self.addToGroup(self._handle)

            self.setZValue(99)
            self.setFlag(QGraphicsItem.ItemIsMovable, False)

        def update_height(self, h):
            """Resize the vertical line when tracks change."""
            self._line.setLine(0, 0, 0, h)

        def mousePressEvent(self, event):
            handle_rect = self._handle.mapToScene(
                self._handle.boundingRect()
            ).boundingRect()
            if handle_rect.contains(event.scenePos()):
                self._dragging = True
                self._drag_offset = (
                    event.scenePos().x() - self.pos().x()
                )
                event.accept()
            else:
                event.ignore()

        def mouseMoveEvent(self, event):
            if not self._dragging:
                event.ignore()
                return
            new_x = event.scenePos().x() - self._drag_offset
            if new_x < 0:
                new_x = 0
            self.setPos(new_x, 0)
            event.accept()

        def mouseReleaseEvent(self, event):
            if not self._dragging:
                event.ignore()
                return
            self._dragging = False
            # Snap to nearest frame boundary
            if self.timeline_view:
                upf = self.timeline_view.units_per_frame
                frame = round(self.pos().x() / upf)
                if frame < 0:
                    frame = 0
                # Enforce start < end constraint
                tv = self.timeline_view
                if self._is_start and tv.loop_end_flag is not None:
                    end_frame = round(
                        tv.loop_end_flag.pos().x() / upf
                    )
                    if frame >= end_frame:
                        frame = end_frame - 1
                elif (not self._is_start
                        and tv.loop_start_flag is not None):
                    start_frame = round(
                        tv.loop_start_flag.pos().x() / upf
                    )
                    if frame <= start_frame:
                        frame = start_frame + 1
                self.frame = frame
                self.setPos(frame * upf, 0)
            event.accept()

    class MediaMember(QGraphicsRectItem):  # akin to DraggableMember
        (NoHandle, Left, Right) = range(3)
        """Represents a media clip on the timeline."""

        def __init__(
            self,
            timeline_view,
            member_id: str,
            member_config: Dict[str, Any],
            start_frame: int = 0,
            in_frame: int = 0,
            out_frame: int = None,
            track_index: int = 0
    ):
            super().__init__()
            from gui.style import TEXT_COLOR
            color = QColor(TEXT_COLOR)
            color.setAlphaF(0.1)
            self.setBrush(QBrush(color))

            self.timeline_view = timeline_view
            self.member_id = member_id
            self.member_config = member_config
            self.member_type = member_config.get('_TYPE', 'video')

            self.filepath = None  # member_config.get('browse.path', '')
            self.filename = None  # os.path.basename(self.filepath)
            self.source_frame_count = 150

            self.track_index = track_index or 0

            # Frame-based positioning
            self.start_frame = start_frame
            self.in_frame = in_frame
            self.out_frame = out_frame

            # Lazy preview loader (handles both waveform and video previews)
            self.waveform_loader = self.WaveformLazyLoader(self)
            self.thumbnail_loader = self.ThumbnailLazyLoader(self)

            # Set source filepath
            filepath = member_config.get('browse.path', '')
            self.set_source_filepath(filepath)

            # Position clip using start_frame
            ppf = self.timeline_view.units_per_frame
            self.setPos(self.start_frame * ppf, self.track_index * 60)

            # Transformation attributes for video preview
            self.scale = member_config.get('scale', 1.0)
            self.pos_x = member_config.get('pos_x', 0.0)
            self.pos_y = member_config.get('pos_y', 0.0)
            self.rotation = member_config.get('rotation', 0.0)

            # --- State for lock and resizing logic ---
            self.is_locked = False
            self.is_disabled = False
            self.is_resizing = False
            self.current_resize_handle = self.NoHandle
            self.setFlag(QGraphicsItem.ItemIsMovable)
            self.setFlag(QGraphicsItem.ItemIsSelectable)
            self.setFlag(QGraphicsItem.ItemSendsGeometryChanges)
            self.setAcceptHoverEvents(True)

        @property
        def duration(self) -> float:
            """Duration in seconds of the clip after any trimming."""
            fps = self.timeline_view.studio.project_fps
            return (self.out_frame - self.in_frame) / fps

        @property
        def frame_count(self) -> int:
            """Number of frames in the trimmed portion of the clip."""
            return max(0, self.out_frame - self.in_frame)

        @property
        def start_time(self) -> float:
            """Start time in seconds (for compatibility with preview/decode)."""
            return frame_to_time(self.start_frame, self.timeline_view.studio.project_fps)

        @property
        def in_point(self) -> float:
            """In point in seconds (for compatibility with preview/decode)."""
            return frame_to_time(self.in_frame, self.timeline_view.studio.project_fps)

        @property
        def out_point(self) -> float:
            """Out point in seconds (for compatibility with preview/decode)."""
            return frame_to_time(self.out_frame, self.timeline_view.studio.project_fps)

        def to_dict(self) -> dict:
            """Serialize clip to dictionary with frame-based values."""
            return {
                'member_config': self.member_config,
                'start_frame': self.start_frame,
                'in_frame': self.in_frame,
                'out_frame': self.out_frame,
                'track_index': self.track_index,
                'is_locked': self.is_locked,
                'is_disabled': self.is_disabled,
            }

        def calculate_visible_frames(self):
            """Returns (start_frame, end_frame) in source media coords, or None."""
            timeline = self.timeline_view
            upf = timeline.units_per_frame

            # Viewport bounds in frames
            vp = timeline.mapToScene(timeline.viewport().rect()).boundingRect()
            view_start = int(vp.x() / upf)
            view_end = int((vp.x() + vp.width()) / upf)

            # Clip bounds on timeline
            clip_start = self.start_frame
            clip_end = clip_start + self.frame_count

            # Intersection
            vis_start = max(clip_start, view_start)
            vis_end = min(clip_end, view_end)
            if vis_start >= vis_end:
                return None

            # Convert to source media frames + padding
            PADDING_FRAMES = 50
            src_start = vis_start - clip_start + self.in_frame  # - PADDING_FRAMES
            src_end = vis_end - clip_start + self.in_frame  # + PADDING_FRAMES

            return (max(self.in_frame, src_start), min(self.out_frame, src_end))
        
        def set_source_filepath(self, filepath: str):
            self.filepath = filepath
            self.filename = os.path.basename(self.filepath)

            # Get FPS from project settings
            fps = self.timeline_view.studio.project_fps

            file_duration = get_media_duration(self.filepath)
            num_frames = int(file_duration * fps)
            self.source_frame_count = num_frames

            if self.out_frame is None or self.out_frame > num_frames:
                self.out_frame = num_frames

            ppf = self.timeline_view.units_per_frame
            self.setRect(0, 0, self.frame_count * ppf, 50)

            # Invalidate waveform cache when source changes
            self.waveform_loader.invalidate_cache()
            self.thumbnail_loader.invalidate_cache()

        def setCentredPos(self, pos):
            self.setPos(pos.x() - self.boundingRect().width() / 2, pos.y() - self.boundingRect().height() / 2)

        def itemChange(self, change, value):
            if change == QGraphicsItem.ItemPositionChange:
                new_pos = QPointF(value)

                # Snap Y to track rows, clamped to valid range
                max_track = len(self.timeline_view.tracks) - 1
                new_y = max(0, min(max_track * 60, round(new_pos.y() / 60) * 60))
                new_pos.setY(new_y)

                # Lock: prevent horizontal movement
                if self.is_locked:
                    new_pos.setX(self.pos().x())
                else:
                    # Snap X to other clips, then constrain to non-negative
                    snapped_x = self._apply_snapping(max(0, new_pos.x()))
                    new_pos.setX(snapped_x)

                # Update clip properties (frame-based)
                ppf = self.timeline_view.units_per_frame
                self.start_frame = int(new_pos.x() / ppf)
                self.track_index = int(new_pos.y() / 60)
                self.timeline_view.update_scene_rect()

                return new_pos
            elif change == QGraphicsItem.ItemSelectedHasChanged:
                self.setZValue(1 if value else 0)
            return super().itemChange(change, value)

        def _apply_snapping(self, x_pos, snap_threshold=15):
            """Apply horizontal snapping to nearby clip edges."""
            snap_points = self.timeline_view._get_snap_candidates()

            if not snap_points:
                return x_pos

            clip_start = x_pos
            clip_end = x_pos + self.rect().width()

            # Find closest snap point for either clip start or end
            for snap_point in snap_points:
                for clip_edge in [clip_start, clip_end]:
                    distance = abs(clip_edge - snap_point)
                    if distance < snap_threshold:
                        return x_pos + (snap_point - clip_edge)

            return x_pos

        def get_handle_at(self, pos: QPointF):
            # Get the bounding rect directly (no proxy)
            rect = self.boundingRect()
            # Fixed screen-pixel handle size, adjusted for zoom level
            screen_handle_size = 15
            zoom = self.timeline_view.transform().m11()
            handle_size = screen_handle_size / zoom if zoom > 0 else screen_handle_size

            # Only check for left and right handles (no vertical resizing)
            on_left = pos.x() - rect.left() < handle_size
            on_right = rect.right() - pos.x() < handle_size

            if on_left: return self.Left
            if on_right: return self.Right
            return self.NoHandle

        def set_cursor_for_handle(self, handle):
            if handle in (self.Left, self.Right):
                self.setCursor(Qt.SizeHorCursor)
            else:
                self.setCursor(Qt.ArrowCursor)

        def mousePressEvent(self, event):
            handle = self.get_handle_at(event.pos())
            if self.is_locked:
                handle = self.NoHandle
            if handle != self.NoHandle and self.isSelected():
                self.is_resizing = True
                self.current_resize_handle = handle
                # Store original rect and position separately
                self.original_rect = self.rect()
                self.original_pos = self.pos()
                self.original_mouse_pos = event.scenePos()
                self.setFlag(QGraphicsItem.ItemIsMovable, False)
                event.accept()
            else:
                super().mousePressEvent(event)

        def mouseMoveEvent(self, event):
            if self.is_resizing:
                delta = event.scenePos() - self.original_mouse_pos
                new_rect = QRectF(self.original_rect)
                handle = self.current_resize_handle
                new_pos = QPointF(self.original_pos)
                ppf = self.timeline_view.units_per_frame
                fps = self.timeline_view.studio.project_fps
                min_frames = 1  # Minimum 1 frame

                # # Calculate source frame count (can't extend beyond source duration)
                # source_frame_count = time_to_frame(self.duration, fps)

                # Store original values (before any position changes trigger itemChange)
                original_in_frame = getattr(self, '_resize_original_in_frame', self.in_frame)
                original_out_frame = getattr(self, '_resize_original_out_frame', self.out_frame)
                if not hasattr(self, '_resize_original_in_frame'):
                    self._resize_original_in_frame = self.in_frame
                    self._resize_original_out_frame = self.out_frame

                if handle == self.Left:
                    # Resizing from left edge - adjusts in_frame
                    delta_frames = int(delta.x() / ppf)
                    new_in_frame = original_in_frame + delta_frames

                    # Constrain: can't go below 0 (can't extend before source start)
                    new_in_frame = max(0, new_in_frame)
                    # Constrain: must leave at least min_frames visible
                    new_in_frame = min(new_in_frame, original_out_frame - min_frames)

                    # Calculate actual pixel delta after constraints
                    actual_delta_frames = new_in_frame - original_in_frame
                    actual_delta_x = actual_delta_frames * ppf

                    new_rect.setWidth(self.original_rect.width() - actual_delta_x)
                    new_pos.setX(self.original_pos.x() + actual_delta_x)

                    self.in_frame = new_in_frame

                elif handle == self.Right:
                    # Resizing from right edge - adjusts out_frame
                    delta_frames = int(delta.x() / ppf)
                    new_out_frame = original_out_frame + delta_frames

                    # Constrain: can't exceed source duration (only for clips with media)
                    if self.filepath and os.path.isfile(self.filepath):
                        new_out_frame = min(self.source_frame_count, new_out_frame)
                    # Constrain: must leave at least min_frames visible
                    new_out_frame = max(new_out_frame, original_in_frame + min_frames)

                    # Calculate actual pixel delta after constraints
                    actual_delta_frames = new_out_frame - original_out_frame
                    actual_delta_x = actual_delta_frames * ppf

                    new_rect.setWidth(self.original_rect.width() + actual_delta_x)

                    self.out_frame = new_out_frame

                # Update position and rect
                self.prepareGeometryChange()
                self.setPos(new_pos)
                self.setRect(new_rect)

                event.accept()
            else:
                super().mouseMoveEvent(event)

        def mouseReleaseEvent(self, event):
            if self.is_resizing:
                self.is_resizing = False
                self.current_resize_handle = self.NoHandle
                self.setFlag(QGraphicsItem.ItemIsMovable, True)
                # Clean up temporary resize tracking attributes
                if hasattr(self, '_resize_original_in_frame'):
                    del self._resize_original_in_frame
                if hasattr(self, '_resize_original_out_frame'):
                    del self._resize_original_out_frame
                # Invalidate waveform cache since trim points changed
                self.waveform_loader.invalidate_cache()
                self.thumbnail_loader.invalidate_cache()
                self.timeline_view.update_scene_rect()
                event.accept()
            else:
                super().mouseReleaseEvent(event)
            self.timeline_view.studio.save()

        # # def save_pos(self):
        # #     new_loc_x = max(0, int(self.x()))
        # #     new_loc_y = max(0, int(self.y()))

        # #     current_size = self.member_proxy.size() # * self.member_proxy.scale()

        # #     members = self.workflow_settings.config.get('members', [])
        # #     member = next((m for m in members if m['id'] == self.id), None)

        # #     if member:
        # #         pos_changed = new_loc_x != member.get('loc_x') or new_loc_y != member.get('loc_y')
        # #         size_changed = not math.isclose(current_size.width(), member.get('width', 0)) or \
        # #                     not math.isclose(current_size.height(), member.get('height', 0))
        # #         if not pos_changed and not size_changed:
        # #             return

        # #     self.workflow_settings.update_config()

        def hoverMoveEvent(self, event):
            if self.is_resizing or not self.isSelected():  # or self.workflow_settings.view.mini_view:
                self.setCursor(Qt.ArrowCursor)
                super().hoverMoveEvent(event)
                return

            handle = self.get_handle_at(event.pos())
            if handle > 0:
                pass
            self.set_cursor_for_handle(handle)
            super().hoverMoveEvent(event)

        def hoverLeaveEvent(self, event):
            self.setCursor(Qt.ArrowCursor)
            super().hoverLeaveEvent(event)

        def paint(self, painter, option, widget):
            if self.is_disabled:
                painter.setOpacity(0.2)
            # Draw base rectangle
            super().paint(painter, option, widget)
            rect = self.rect()

            if self.member_type == 'audio':
                # Audio: waveform fills full height
                self._draw_waveform(painter, rect, full_height=True)
            else:
                # Video: top half thumbnails, bottom half waveform
                top_rect = QRectF(rect.x(), rect.y(), rect.width(), rect.height() / 2)
                bottom_rect = QRectF(rect.x(), rect.y() + rect.height() / 2,
                                     rect.width(), rect.height() / 2)
                self._draw_thumbnails(painter, top_rect)
                self._draw_waveform(painter, bottom_rect, full_height=False)

            if self.is_locked:
                self._draw_lock_indicator(painter, rect)

        def _draw_lock_indicator(self, painter, rect):
            """Draw a white line at the bottom of the clip to indicate lock."""
            painter.save()
            painter.setPen(QPen(QColor(255, 255, 255, 160), 1))
            y = rect.bottom() - 1
            painter.drawLine(QPointF(rect.left(), y), QPointF(rect.right(), y))
            painter.restore()

        def _draw_waveform(self, painter, rect, full_height=True):
            """Draw waveform visualization in the given rect using lazy-loaded data."""
            # Get visible waveform data from the lazy loader
            waveform_result = self.waveform_loader.get_visible_waveform()
            if waveform_result is None:
                return

            waveform_data, start_frame, end_frame = waveform_result
            if not waveform_data:
                return

            num_samples = len(waveform_data)
            if num_samples == 0:
                return

            painter.save()
            painter.setRenderHint(QPainter.Antialiasing)
            painter.setClipRect(rect)

            units_per_frame = self.timeline_view.units_per_frame

            # Calculate the x position where this waveform data starts (in clip-local coordinates)
            # start_frame is in source media coordinates, convert to clip-local
            clip_local_start_frame = start_frame - self.in_frame
            clip_local_end_frame = end_frame - self.in_frame

            # Width of the waveform region
            waveform_width = (clip_local_end_frame - clip_local_start_frame) * units_per_frame
            sample_width = waveform_width / num_samples if num_samples > 0 else 1

            # X offset within the clip rect
            x_start = rect.x() + clip_local_start_frame * units_per_frame

            center_y = rect.y() + rect.height() / 2
            max_amplitude = rect.height() * 0.4

            # Build waveform path
            path = QPainterPath()
            path.moveTo(x_start, center_y)

            # Draw upper half of waveform
            for i, peak in enumerate(waveform_data):
                x = x_start + i * sample_width
                y = center_y - peak * max_amplitude
                path.lineTo(x, y)

            path.lineTo(x_start + waveform_width, center_y)

            # Draw lower half of waveform (mirrored)
            for i in range(num_samples - 1, -1, -1):
                peak = waveform_data[i]
                x = x_start + i * sample_width
                y = center_y + peak * max_amplitude
                path.lineTo(x, y)

            path.closeSubpath()

            from gui.style import TEXT_COLOR, PRIMARY_COLOR
            q_text_color = QColor(TEXT_COLOR)
            q_primary_color = QColor(PRIMARY_COLOR)
            TEXT_COLOR_RED = q_text_color.red()
            TEXT_COLOR_GREEN = q_text_color.green()
            TEXT_COLOR_BLUE = q_text_color.blue()
            PRIMARY_COLOR_RED = q_primary_color.red()
            PRIMARY_COLOR_GREEN = q_primary_color.green()
            PRIMARY_COLOR_BLUE = q_primary_color.blue()
            MIDWAY_TEXT_AND_PRIMARY_COLOR = QColor(
                (TEXT_COLOR_RED + PRIMARY_COLOR_RED) / 2,
                (TEXT_COLOR_GREEN + PRIMARY_COLOR_GREEN) / 2,
                (TEXT_COLOR_BLUE + PRIMARY_COLOR_BLUE) / 2
            )

            # Get volume and calculate alpha/green tint
            clip_volume = self.member_config.get('volume', 100)
            clip_track = self.timeline_view.studio.track_control_panel.get_config()[self.track_index]
            track_volume = clip_track.get('volume', 100)
            volume = (clip_volume * track_volume) / 100.0

            if volume < 100:
                # Reduce alpha: 0% volume = fully transparent, 100% = full opacity
                alpha = volume / 100.0
            else:
                alpha = 1.0

            if volume > 100:
                # Tint green: 100% = no tint, 200% = full green tint
                green_factor = (volume - 100) / 100.0  # 0 to 1
            else:
                green_factor = 0.0

            def apply_volume_color(color):
                """Apply alpha and green tint based on volume."""
                r, g, b = color.red(), color.green(), color.blue()
                # Add green tint
                if green_factor > 0:
                    g = min(255, int(g + (255 - g) * green_factor * 0.6))
                result = QColor(r, g, b)
                result.setAlphaF(alpha)
                return result

            # Draw center line
            center_line_color = apply_volume_color(QColor(MIDWAY_TEXT_AND_PRIMARY_COLOR))
            center_line_color.setAlphaF(max(alpha, 0.4))
            painter.setPen(QPen(center_line_color, 1))
            painter.drawLine(QPointF(rect.x(), center_y), QPointF(rect.x() + rect.width(), center_y))

            # Fill with gradient (with volume-based coloring)
            gradient = QLinearGradient(0, center_y - max_amplitude, 0, center_y + max_amplitude)
            gradient.setColorAt(0, apply_volume_color(QColor(TEXT_COLOR)))
            gradient.setColorAt(0.5, apply_volume_color(MIDWAY_TEXT_AND_PRIMARY_COLOR))
            gradient.setColorAt(1, apply_volume_color(QColor(TEXT_COLOR)))

            painter.setPen(Qt.NoPen)
            painter.setBrush(QBrush(gradient))
            painter.drawPath(path)

            painter.restore()

        def _draw_thumbnails(self, painter, rect):
            """Draw video thumbnails in the given rect using lazy-loaded previews."""
            thumbnail_result = self.thumbnail_loader.get_visible_previews()
            if thumbnail_result is None:
                return

            preview_cache, range_start, range_end, frame_stride = thumbnail_result
            if not preview_cache:
                return

            painter.save()
            painter.setClipRect(rect)

            upf = self.timeline_view.units_per_frame
            # Each thumbnail spans frame_stride frames = frame_stride * upf scene units
            thumb_scene_width = frame_stride * upf

            for frame_num, pixmap in preview_cache.items():
                # Convert source frame to clip-local position
                clip_local_frame = frame_num - self.in_frame
                x = rect.x() + clip_local_frame * upf

                # Scale thumbnail to fit the scene width it represents
                target_rect = QRectF(x, rect.y(), thumb_scene_width, pixmap.height())
                painter.drawPixmap(target_rect.toRect(), pixmap)

            painter.restore()

        class WaveformLazyLoader:
            """Lazy loads waveform data for visible portions."""
            SAMPLES_PER_FRAME = 4

            def __init__(self, media_member):
                self.member = media_member
                # Waveform cache
                self._waveform_range = None  # (start_frame, end_frame)
                self._waveform_data = None   # waveform list
                self._waveform_loading = False

            def get_visible_waveform(self):
                """Returns (waveform_data, start_frame, end_frame) or None if off-screen."""
                visible = self.member.calculate_visible_frames()
                if visible is None:
                    return None

                start, end = visible

                # Check if cache covers the visible region
                cache_valid = False
                if self._waveform_range and self._waveform_data:
                    cs, ce = self._waveform_range
                    if cs <= start and ce >= end:
                        cache_valid = True

                # Trigger async load if cache doesn't cover visible region
                if not cache_valid and not self._waveform_loading:
                    self._waveform_loading = True
                    asyncio.ensure_future(self._load_waveform(start, end))

                # Return cached data if available (even if stale, while loading)
                if self._waveform_range and self._waveform_data:
                    display_data = self._get_display_samples()
                    return (display_data, self._waveform_range[0], self._waveform_range[1])

                return None

            def _get_display_samples(self):
                """Return cached data, interpolated to max MAX_DISPLAY_SAMPLES."""
                num_samples = len(self._waveform_data)
                MAX_DISPLAY_SAMPLES = 2000
                if num_samples <= MAX_DISPLAY_SAMPLES:
                    return self._waveform_data

                # Interpolate to max samples
                indices = np.linspace(0, num_samples - 1, MAX_DISPLAY_SAMPLES)
                return list(np.interp(indices, np.arange(num_samples), self._waveform_data))

            async def _load_waveform(self, start_frame, end_frame):
                """Extract waveform for frame range using ffmpeg fast seeking."""
                member = self.member
                filepath = member.filepath
                fps = member.timeline_view.studio.project_fps

                def _extract():
                    try:
                        start_time = start_frame / fps
                        duration = (end_frame - start_frame) / fps

                        # Use ffmpeg with fast seeking (-ss before -i)
                        cmd = [
                            'ffmpeg', '-ss', str(start_time),
                            '-i', filepath,
                            '-t', str(duration),
                            '-vn',  # No video
                            '-ac', '1',  # Mono
                            '-ar', '8000',  # Low sample rate (enough for waveform)
                            '-f', 's16le',  # Raw PCM
                            '-loglevel', 'error',
                            'pipe:1'
                        ]
                        result = subprocess.run(cmd, capture_output=True)
                        if result.returncode != 0:
                            return []

                        # Convert raw PCM to numpy array
                        audio = np.frombuffer(result.stdout, dtype=np.int16).astype(np.float32)
                        audio /= 32768.0  # Normalize to -1..1

                        if len(audio) == 0:
                            return []

                        # Downsample to target resolution
                        num_samples = (end_frame - start_frame) * self.SAMPLES_PER_FRAME
                        chunk_size = max(1, len(audio) // num_samples)

                        waveform = []
                        for i in range(0, len(audio), chunk_size):
                            chunk = audio[i:i + chunk_size]
                            if len(chunk) > 0:
                                waveform.append(float(np.max(np.abs(chunk))))

                        # Normalize
                        if waveform:
                            max_peak = max(waveform)
                            if max_peak > 0:
                                waveform = [p / max_peak for p in waveform]

                        return waveform
                    except Exception as e:
                        print(f"Error extracting waveform: {e}")
                        return []

                waveform = await asyncio.to_thread(_extract)
                self._waveform_loading = False

                if waveform:
                    self._waveform_range = (start_frame, end_frame)
                    self._waveform_data = waveform
                    member.update()

            def invalidate_cache(self):
                """Clear all caches when clip changes."""
                self._waveform_range = None
                self._waveform_data = None
                self._waveform_loading = False

        class ThumbnailLazyLoader:
            """Lazy loads video preview data for visible portions."""

            def __init__(self, media_member):
                self.member = media_member
                self.aspect_ratio = None

                # Preview cache
                self._preview_cache = {}      # {frame_num: QPixmap}
                self._preview_range = None    # (start_frame, end_frame, frame_stride)
                self._preview_loading = False

                # Stale cache fallback (shown while fresh data loads)
                self._stale_cache = {}
                self._stale_range = None

                # Debounce state
                self._pending_load_args = None
                self._load_generation = 0

            def get_visible_previews(self):
                """Returns (preview_dict, start_frame, end_frame, frame_stride) or None.

                preview_dict maps frame numbers to thumbnails.
                frame_stride: number of source frames each thumbnail represents.
                """
                # Skip audio clips
                if self.member.member_type == 'audio':
                    return None

                # Fixed thumbnail height: half the clip height minus padding
                thumb_height = int(self.member.rect().height() / 2) - 2

                # Fixed thumbnail width: based on video aspect ratio (default 16:9)
                ar = self.aspect_ratio if self.aspect_ratio else 16 / 9
                thumb_width = int(thumb_height * ar)


                # Get visible frames
                visible_frames = self.member.calculate_visible_frames()
                if visible_frames is None:
                    return None

                # Calculate frame stride for thumbnail extraction
                start_frame, end_frame = visible_frames
                frame_span = end_frame - start_frame
                timeline = self.member.timeline_view
                upf = timeline.units_per_frame
                frame_span_in_units = frame_span * upf
                vp_rect = timeline.viewport().rect()
                scene_rect = timeline.mapToScene(vp_rect).boundingRect()
                pixels_per_unit = vp_rect.width() / scene_rect.width()
                visible_frame_span_in_screen = frame_span_in_units * pixels_per_unit
                # Number of thumbnails that fit in visible area
                num_thumbnails = max(1, int(visible_frame_span_in_screen / thumb_width))
                # Frame stride: how many frames each thumbnail represents
                frame_stride = max(1, int(frame_span / num_thumbnails))
                # num_thumbnails += 1

                # Check cache validity
                cache_valid = False
                zoom_changed = False
                if self._preview_range is not None:
                    cs, ce, _ = self._preview_range
                    cached_frame_span = ce - cs
                    if cached_frame_span != frame_span:
                        zoom_changed = True
                    elif cs <= start_frame and ce >= end_frame:
                        cache_valid = True

                # Move cache to stale if zoom level changed
                if zoom_changed:
                    if self._preview_cache and self._preview_range:
                        self._stale_cache = self._preview_cache
                        self._stale_range = self._preview_range
                    self._preview_cache = {}
                    self._preview_range = None

                # Overscan: load 300% extra on each side for pan
                overscan = frame_span * 3
                member = self.member
                load_start = max(
                    member.in_frame, start_frame - overscan)
                load_end = min(
                    member.out_frame, end_frame + overscan)

                # Trigger debounced async load if needed
                if not cache_valid and not self._preview_loading:
                    self._pending_load_args = (
                        load_start, load_end,
                        frame_stride, thumb_height,
                    )
                    self._load_generation += 1
                    gen = self._load_generation
                    debounce = 150 if zoom_changed else 50
                    QTimer.singleShot(
                        debounce,
                        lambda g=gen: self._on_debounce_fire(g),
                    )

                # Return fresh cache if available
                if self._preview_cache and self._preview_range:
                    return (self._preview_cache, self._preview_range[0],
                            self._preview_range[1], self._preview_range[2])

                # Fall back to stale cache while loading
                if self._stale_cache and self._stale_range:
                    return (self._stale_cache, self._stale_range[0],
                            self._stale_range[1], self._stale_range[2])

                return None

            def _on_debounce_fire(self, generation):
                """Fire load only if this is still the latest request."""
                if generation != self._load_generation:
                    return
                if self._preview_loading:
                    return
                args = self._pending_load_args
                if args is None:
                    return
                self._pending_load_args = None
                self._preview_loading = True
                asyncio.ensure_future(self._load_previews(*args))

            async def _load_previews(self, start_frame, end_frame, frame_stride, thumb_height):
                """Extract video previews for the visible frame range.

                frame_stride: number of source frames each thumbnail represents.
                Uses a global semaphore to limit concurrent ffmpeg processes,
                and a disk cache to avoid re-extracting known frames.
                """
                sem = _get_thumbnail_semaphore()
                async with sem:
                    # Early exit if a newer load was requested while waiting
                    if self._pending_load_args is not None:
                        self._preview_loading = False
                        return

                    member = self.member
                    filepath = member.filepath
                    fps = member.timeline_view.studio.project_fps

                    def _extract():
                        try:
                            previews = {}
                            ar = None
                            cache_dir = _get_thumbnail_cache_dir()

                            # Calculate expected frame numbers
                            expected_frames = list(range(
                                start_frame, end_frame, frame_stride))
                            if not expected_frames:
                                return {}, None

                            # Check disk cache for already-extracted frames
                            uncached_frames = []
                            for fn in expected_frames:
                                key = _thumb_cache_key(
                                    filepath, fn, thumb_height)
                                cache_path = os.path.join(cache_dir, key)
                                if os.path.exists(cache_path):
                                    pixmap = QPixmap(cache_path)
                                    if not pixmap.isNull():
                                        previews[fn] = pixmap
                                        if ar is None:
                                            ar = (pixmap.width()
                                                  / pixmap.height())
                                        continue
                                uncached_frames.append(fn)

                            # All frames found in disk cache
                            if not uncached_frames:
                                return previews, ar

                            start_time = start_frame / fps
                            end_time = end_frame / fps
                            duration = end_time - start_time

                            output_fps = fps / frame_stride
                            vf = f'fps={output_fps},scale=-1:{thumb_height}'

                            cmd = [
                                'ffmpeg',
                                '-ss', str(start_time),
                            ]
                            if frame_stride >= 30:
                                cmd.extend(['-skip_frame', 'nokey'])
                            cmd.extend([
                                '-i', filepath,
                                '-t', str(duration),
                                '-vf', vf,
                                '-f', 'image2pipe',
                                '-vcodec', 'mjpeg',
                                '-q:v', '5',
                                '-loglevel', 'error',
                                'pipe:1'
                            ])
                            result = subprocess.run(
                                cmd, capture_output=True)
                            if result.returncode != 0 or not result.stdout:
                                return previews, ar

                            # Parse concatenated JPEG images
                            data = result.stdout
                            jpeg_start_marker = b'\xff\xd8\xff'
                            jpeg_end_marker = b'\xff\xd9'

                            positions = []
                            pos = 0
                            while True:
                                idx = data.find(jpeg_start_marker, pos)
                                if idx == -1:
                                    break
                                positions.append(idx)
                                pos = idx + 1

                            for i, sp in enumerate(positions):
                                if i >= len(expected_frames):
                                    break
                                fn = expected_frames[i]
                                # Skip frames already loaded from disk
                                if fn in previews:
                                    continue
                                em = data.find(jpeg_end_marker, sp)
                                if em == -1:
                                    ep = len(data)
                                else:
                                    ep = em + 2
                                jpeg_data = data[sp:ep]

                                pixmap = QPixmap()
                                pixmap.loadFromData(jpeg_data)
                                if not pixmap.isNull():
                                    previews[fn] = pixmap
                                    if ar is None:
                                        ar = (pixmap.width()
                                              / pixmap.height())
                                    # Write to disk cache
                                    key = _thumb_cache_key(
                                        filepath, fn, thumb_height)
                                    cache_path = os.path.join(
                                        cache_dir, key)
                                    try:
                                        pixmap.save(cache_path, 'JPEG', 85)
                                    except Exception:
                                        pass

                            return previews, ar
                        except Exception as e:
                            print(f"Error extracting thumbnails: {e}")
                            return {}, None

                    previews, ar = await asyncio.to_thread(_extract)
                    self._preview_loading = False

                    if previews:
                        # Merge if stride matches existing cache
                        if (self._preview_range
                                and self._preview_range[2]
                                == frame_stride):
                            self._preview_cache.update(previews)
                        else:
                            self._preview_cache = previews
                        self._preview_range = (
                            start_frame, end_frame, frame_stride)
                        self._stale_cache = {}
                        self._stale_range = None
                        if ar:
                            self.aspect_ratio = ar
                        member.update()

            def invalidate_cache(self):
                """Clear all caches when clip changes."""
                self._preview_cache = {}
                self._preview_range = None
                self._preview_loading = False
                self._stale_cache = {}
                self._stale_range = None
                self._pending_load_args = None
                self._load_generation += 1


class MemberConfigWidget(ConfigWidget):  # todo dedupe
    def __init__(self, parent):
        super().__init__(parent=parent)
        self.layout = CVBoxLayout(self)
        # self.object = None
        self.config_widget = None
        self.member_header_widget = HeaderFields(self)
        self.layout.addWidget(self.member_header_widget)
        self.hide()
    
    def load_config(self, json_config=None):
        super().load_config(json_config)
        self.member_header_widget.load_config(json_config)

    def get_config(self):
        if not self.config_widget:
            return {}
        header_config = self.member_header_widget.get_config()
        config = self.config_widget.get_config()
        return config | header_config

    def update_config(self):
        self.save_config()

    def save_config(self):
        if not self.config_widget:
            return
        config = self.get_config()

        studio = self.parent
        member_id = self.config_widget.member_id
        clip = studio.timeline.clips[member_id]
        old_filepath = clip.filepath

        config['_TYPE'] = clip.member_type
        clip.member_config = config

        # Update clip properties from config
        new_filepath = config.get('browse.path', '')
        if new_filepath != old_filepath:
            clip.set_source_filepath(new_filepath)

            # Refresh preview
            current_frame = studio.timeline.get_playhead_frame()
            studio.preview_panel.request_frame(current_frame)

        studio.update_config()

    def display_member(self, **kwargs):
        clear_layout(self.layout, skip_count=1)
        member_type = kwargs.get('member_type', None)  # member.member_type)
        member_config = kwargs.get('member_config', None)  # , member.member_config)
        member_id = kwargs.get('member_id', None)  # , member.id)
        member = kwargs.get('member', None)  # member.member_type
        if member:
            member_type = member.member_type
            member_config = member.member_config
            member_id = member.member_id

        member_settings_class = get_member_settings_class(member_type)
        
        self.member_header_widget.setVisible(member_settings_class is not None)
        if not member_settings_class:
            return
        
        kwargs = {}
        self.config_widget = member_settings_class(self, **kwargs)
        self.config_widget.member_id = member_id
        self.rebuild_member(config=member_config)

        self.show()

    def rebuild_member(self, config):
        clear_layout(self.layout, skip_count=1)  # 
        member_type = config.get('_TYPE', 'video')

        member_class = system.manager.modules.get_module_class('Members', module_name=member_type)
        if member_class:
            default_avatar = getattr(member_class, 'default_avatar', '')
            self.member_header_widget.widgets[0].schema[0]['default'] = default_avatar
            self.member_header_widget.build_schema()

        self.member_header_widget.load_config(config)
        self.member_header_widget.load()
        
        self.config_widget.load_config(config)
        self.config_widget.build_schema()
        self.config_widget.load()
        self.layout.addWidget(self.config_widget)

        if hasattr(self.config_widget, 'reposition_view'):
            self.config_widget.reposition_view()


class TrackControlPanel(ConfigWidget):
    """Panel containing controls for timeline tracks"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.studio = parent
        self.track_controls = []
        
        self.layout = CVBoxLayout(self)

        # Container for track controls
        self.tracks_container = QWidget()
        self.tracks_layout = CVBoxLayout(self.tracks_container)

        # Add track button at bottom
        self.add_track_btn = QPushButton("+ Add Track")
        self.add_track_btn.clicked.connect(self.on_add_track)

        # Layout assembly
        self.layout.addWidget(self.tracks_container)
        self.layout.addStretch(1)
        self.layout.addWidget(self.add_track_btn)
    
    def load(self):
        for track_control in self.track_controls:
            self.tracks_layout.removeWidget(track_control)
            track_control.deleteLater()
        self.track_controls = []

        tracks = self.studio.timeline.tracks
        for track_index, track_config in enumerate(tracks):
            track_control = self.TrackControl(self, track_index, track_config)
            self.track_controls.append(track_control)
            self.tracks_layout.addWidget(track_control)
    
    def get_config(self):
        return [track_control.get_config() for track_control in self.track_controls]

    def on_add_track(self):
        """Add a new track"""
        track_index = len(self.studio.timeline.tracks)
        track_config = {}
        self.studio.timeline.tracks.append(track_config)
        self.studio.load()
    
    def remove_track(self, track_index):
        self.studio.timeline.tracks.pop(track_index)
        self.studio.load()
    
    class TrackControl(ConfigFields):
        def __init__(self, parent, track_index, track_config):
            super().__init__(parent)
            self.track_index = track_index
            self.setFixedHeight(60)
            #
            self.setProperty('class', 'track-control')  # Set CSS class for styling
            self.schema = [
                {
                    'type': str,
                    'text': 'Track Name',
                    'transparent': True,
                    'default': 'Track 1',
                    'stretch_x': True,
                    'label_position': None,
                    'row_key': 0,
                },
                # {
                #     'text': 'M',
                #     'type': 'button_toggle',
                #     'label_position': None,
                #     'default': False,
                #     'tooltip': 'Mute track',
                #     'row_key': 0,
                # },
                # {
                #     'text': 'S',
                #     'type': 'button_toggle',
                #     'label_position': None,
                #     'default': False,
                #     'tooltip': 'Solo track',
                #     'row_key': 0,
                # },
                {
                    'text': '⋮',
                    'type': 'button',
                    'target': self.show_options_context_menu, # partial(parent.remove_track, self.track_index),
                    'label_position': None,
                    'default': False,
                    'tooltip': 'Remove track',
                    'row_key': 0,
                },
                {
                    'text': 'Volume',
                    'type': int,
                    'style': 'slider',
                    'minimum': 0,
                    'maximum': 100,
                    'default': 100,
                    'width': 50,
                    'label_position': None,
                    'row_key': 1,
                },
                {
                    'text': 'Pan',
                    'type': int,
                    'style': 'slider',
                    'minimum': -100,
                    'maximum': 100,
                    'default': 0,
                    'width': 50,
                    'left_label': 'L',
                    'right_label': 'R',
                    'show_slider_fill': False,
                    'slider_snap_to': 20,
                    'label_position': None,
                    'row_key': 1,
                },
            ]
            self.load_config(track_config)
            self.build_schema()
            self.load()
            volume_slider_widget = getattr(self, 'volume_wgt', None)
            if volume_slider_widget:
                volume_slider_widget.inner_widget.valueChanged.connect(lambda: QTimer.singleShot(50, self.redraw_clips_in_track))
        
        def redraw_clips_in_track(self):
            for clip in self.parent.studio.timeline.clips.values():
                if clip.track_index == self.track_index:
                    clip.update()

        def show_options_context_menu(self):
            """Show options context menu"""
            menu = self.TrackContextMenu(self)
            menu.show_popup_menu()
    
        class TrackContextMenu(CustomMenu):
            def __init__(self, parent):
                super().__init__(parent)
                self.schema = [
                    {
                        'text': 'Delete Track',
                        'target': partial(parent.parent.remove_track, parent.track_index)
                    },
                    # {
                    #     'text': ' Track',
                    # }
                ]

class PreviewClipItem(QGraphicsPixmapItem):
    """
    A transformable graphics item for the video preview.
    Wraps the video frame and provides handles for moving, resizing, and rotating.
    """
    # Handle constants
    NoHandle = 0
    TopLeft = 1
    TopRight = 2
    BottomLeft = 3
    BottomRight = 4

    def __init__(self, media_member, parent=None):
        super().__init__(parent)
        self.preview_panel = self._get_preview_panel()
        self.media_member = media_member
        self.setFlags(QGraphicsItem.ItemIsMovable | QGraphicsItem.ItemIsSelectable | QGraphicsItem.ItemSendsGeometryChanges)
        self.setAcceptHoverEvents(True)
        self.setShapeMode(QGraphicsPixmapItem.BoundingRectShape)

        # Visual settings
        from gui.style import TEXT_COLOR, PRIMARY_COLOR
        self.handle_size = 10
        self.handle_brush = QBrush(QColor(TEXT_COLOR))
        self.handle_pen = QPen(QColor(PRIMARY_COLOR), 1)

        # State
        self.is_resizing = False
        self.is_rotating = False
        self.current_handle = self.NoHandle
        self.start_mouse_pos = QPointF()
        self.start_geometry = QRectF()
        self.start_rotation = 0.0
        self.start_scale = 1.0
        self.start_pos = QPointF()

        # Initialize transform from member
        self.update_from_member()

    def update_from_member(self):
        """Sync visual state from MediaMember data."""
        self.setPos(self.media_member.pos_x, self.media_member.pos_y)
        self.setRotation(self.media_member.rotation)
        self.setScale(self.media_member.scale)
        self.update_transform_origin()
        self.update()

    def update_transform_origin(self):
        """Set transform origin to center of content."""
        rect = self.content_rect()
        self.setTransformOriginPoint(rect.center())

    def set_pixmap(self, pixmap):
        self.setPixmap(pixmap)
        self.update_transform_origin()

    def boundingRect(self):
        base = super().boundingRect()
        if base.isEmpty():
            return base
        margin = self.handle_size
        return base.adjusted(-margin, -margin, margin, margin)

    def content_rect(self):
        pm = self.pixmap()
        if pm and not pm.isNull():
            return QRectF(0, 0, pm.width(), pm.height())
        return QRectF()

    def _get_preview_panel(self):
        """Get the VideoPreviewPanel from the scene."""
        scene = self.scene()
        if not scene:
            return None
        for view in scene.views():
            if view.parent() and isinstance(view.parent(), VideoPreviewPanel):
                return view.parent()
        return None

    def _get_canvas_rect_local(self):
        """Get canvas rect in local coordinates."""
        scene = self.scene()
        if not scene:
            return None
        for item in scene.items():
            if isinstance(item, QGraphicsRectItem) and item.zValue() == -100:
                return self.mapRectFromScene(item.rect())
        return None

    def paint(self, painter, option, widget):
        pm = self.pixmap()
        if not pm or pm.isNull():
            return

        canvas_local = self._get_canvas_rect_local()
        content = self.content_rect()

        if canvas_local:
            painter.save()
            # Draw outside canvas at 10% opacity
            outside_path = QPainterPath()
            outside_path.addRect(content)
            inside_path = QPainterPath()
            inside_path.addRect(canvas_local.intersected(content))
            outside_path = outside_path.subtracted(inside_path)

            painter.setClipPath(outside_path)
            painter.setOpacity(0.1)
            super().paint(painter, option, widget)

            # Draw inside canvas at full opacity
            painter.setClipRect(canvas_local.intersected(content))
            painter.setOpacity(1.0)
            super().paint(painter, option, widget)
            painter.restore()
        else:
            super().paint(painter, option, widget)

        # Draw selection UI if selected
        if self.isSelected():
            rect = content

            # Draw border
            # painter.setPen(self.border_pen)
            painter.setBrush(Qt.NoBrush)
            painter.drawRect(rect)

            # Draw handles
            painter.setPen(self.handle_pen)
            painter.setBrush(self.handle_brush)

            # Corners
            handles = [
                (rect.topLeft(), self.TopLeft),
                (rect.topRight(), self.TopRight),
                (rect.bottomLeft(), self.BottomLeft),
                (rect.bottomRight(), self.BottomRight)
            ]

            hs = self.handle_size
            hs2 = hs / 2

            for pt, _ in handles:
                painter.drawRect(QRectF(pt.x() - hs2, pt.y() - hs2, hs, hs))

            # Rotation handle removed

    def get_handle_at(self, pos):
        if not self.isSelected():
            return self.NoHandle
            
        rect = self.content_rect()
        hs = self.handle_size
        hs2 = hs / 2
        
        # Check corners
        corners = [
            (rect.topLeft(), self.TopLeft),
            (rect.topRight(), self.TopRight),
            (rect.bottomLeft(), self.BottomLeft),
            (rect.bottomRight(), self.BottomRight)
        ]
        
        for pt, handle in corners:
            handle_rect = QRectF(pt.x() - hs2, pt.y() - hs2, hs, hs)
            if handle_rect.contains(pos):
                return handle

        return self.NoHandle

    def mousePressEvent(self, event):
        handle = self.get_handle_at(event.pos())
        
        # Check for Ctrl+Drag rotation
        if event.modifiers() & Qt.ControlModifier:
            self.is_rotating = True
            self.start_mouse_pos = event.scenePos()
            self.start_rotation = self.rotation()
            self.setFlag(QGraphicsItem.ItemIsMovable, False) # Disable move while rotating
            event.accept()
            return

        if handle != self.NoHandle:
            self.is_resizing = True
            self.current_handle = handle
            self.start_mouse_pos = event.scenePos()
            self.start_geometry = self.content_rect()
            self.start_scale = self.scale()
            self.start_pos = self.pos()
            
            # Determine opposite corner for anchoring
            rect = self.content_rect()
            if handle == self.TopLeft:
                self.opposite_corner_local = rect.bottomRight()
            elif handle == self.TopRight:
                self.opposite_corner_local = rect.bottomLeft()
            elif handle == self.BottomLeft:
                self.opposite_corner_local = rect.topRight()
            elif handle == self.BottomRight:
                self.opposite_corner_local = rect.topLeft()
                
            # Store opposite corner in scene coordinates (fixed point)
            self.opposite_corner_scene = self.mapToScene(self.opposite_corner_local)
            
            event.accept()
        else:
            super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if self.is_resizing:
            current_pos = event.scenePos()

            # Calculate new scale based on distance change relative to opposite corner
            # We project the mouse movement onto the diagonal to maintain aspect ratio logic if needed,
            # but for uniform scaling we can just use distance ratio.

            start_dist = (self.start_mouse_pos - self.opposite_corner_scene).manhattanLength()
            current_dist = (current_pos - self.opposite_corner_scene).manhattanLength()

            if start_dist > 0:
                scale_factor = current_dist / start_dist
                new_scale = self.start_scale * scale_factor

                # Apply new scale
                self.setScale(new_scale)

                # Correct position to keep opposite corner fixed
                # After scaling, the opposite corner (in local coords) will map to a new scene position.
                # We need to shift the item so that it maps back to self.opposite_corner_scene.

                new_opposite_scene = self.mapToScene(self.opposite_corner_local)
                correction = self.opposite_corner_scene - new_opposite_scene
                self.setPos(self.pos() + correction)

                # Update model
                self.media_member.scale = new_scale
                self.media_member.member_config['scale'] = new_scale
                self.media_member.pos_x = self.pos().x()
                self.media_member.pos_y = self.pos().y()
                self.media_member.member_config['pos_x'] = self.pos().x()
                self.media_member.member_config['pos_y'] = self.pos().y()

        elif self.is_rotating:
            center = self.mapToScene(self.transformOriginPoint())
            current_pos = event.scenePos()
            
            angle = np.degrees(np.arctan2(current_pos.y() - center.y(), current_pos.x() - center.x()))
            start_angle = np.degrees(np.arctan2(self.start_mouse_pos.y() - center.y(), self.start_mouse_pos.x() - center.x()))
            
            delta_angle = angle - start_angle
            new_rotation = self.start_rotation + delta_angle
            
            self.setRotation(new_rotation)
            self.media_member.rotation = new_rotation
            self.media_member.member_config['rotation'] = new_rotation
            
        else:
            super().mouseMoveEvent(event)
            
    def mouseReleaseEvent(self, event):
        self.is_resizing = False
        self.is_rotating = False
        self.current_handle = self.NoHandle
        self.setFlag(QGraphicsItem.ItemIsMovable, True)  # Re-enable move

        # Hide snap lines when drag ends
        preview_panel = self._get_preview_panel()
        if preview_panel:
            preview_panel.hide_snap_lines()

        super().mouseReleaseEvent(event)

    def itemChange(self, change, value):
        if change == QGraphicsItem.ItemPositionChange and self.scene():
            new_pos = QPointF(value)

            # Apply snapping if we have a preview panel
            preview_panel = self._get_preview_panel()
            if preview_panel and not self.is_resizing and not self.is_rotating:
                snapped_pos, active_lines = preview_panel.calculate_snap(self, new_pos)
                preview_panel.show_snap_lines(active_lines)
                new_pos = snapped_pos

            # Update member position
            self.media_member.pos_x = new_pos.x()
            self.media_member.pos_y = new_pos.y()
            self.media_member.member_config['pos_x'] = new_pos.x()
            self.media_member.member_config['pos_y'] = new_pos.y()

            return new_pos

        return super().itemChange(change, value)

    def hoverMoveEvent(self, event):
        # Check for Ctrl key for rotation cursor
        if event.modifiers() & Qt.ControlModifier:
             self.setCursor(Qt.PointingHandCursor) # Rotation cursor
             super().hoverMoveEvent(event)
             return

        handle = self.get_handle_at(event.pos())
        if handle in (self.TopLeft, self.BottomRight):
            self.setCursor(Qt.SizeFDiagCursor)
        elif handle in (self.TopRight, self.BottomLeft):
            self.setCursor(Qt.SizeBDiagCursor)
        else:
            self.setCursor(Qt.SizeAllCursor if self.isSelected() else Qt.ArrowCursor)
        super().hoverMoveEvent(event)


class VideoPreviewPanel(QWidget):
    """Enhanced video preview panel with playback controls."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.studio = parent
        self.playback_workers = {}  # clip_id -> (thread, worker)
        self._retiring = set()  # prevent GC of fire-and-forget workers

        # Snap lines for preview items
        self.snap_lines = []  # List of QGraphicsLineItem for visual feedback
        self.snap_threshold_percent = 0.05  # 5% of canvas dimension
        
        self.seek_decode_thread = QThread()
        self.seek_decode_worker = VideoDecodeWorker()
        self.seek_decode_worker.moveToThread(self.seek_decode_thread)
        self.seek_decode_worker.decode_request.connect(
            self.seek_decode_worker._on_decode_request, Qt.QueuedConnection)
        self.seek_decode_worker.frame_decoded.connect(self._on_seek_frame_decoded)
        self.seek_decode_thread.start()

        # Master timeline clock
        self.timeline_worker = None
        self.timeline_thread = None

        # state
        self.is_playing = False
        self.playback_speed = 1.0
        self._playback_offsets = {}  # clip_id -> timeline offset
        self.audio_player = _AudioPlayer(studio=self.studio)

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
        self.studio_button.clicked.connect(lambda: self.studio.set_fullscreen(False))
        self.studio_button.hide()

        # Graphics View for Preview
        self.scene = QGraphicsScene(self)
        self.preview_view = QGraphicsView(self.scene)
        self.preview_view.setRenderHint(QPainter.Antialiasing)
        self.preview_view.setRenderHint(QPainter.SmoothPixmapTransform)
        self.preview_view.setViewportUpdateMode(QGraphicsView.FullViewportUpdate)
        self.preview_view.setBackgroundBrush(QBrush(QColor(20, 20, 20)))
        self.preview_view.setAlignment(Qt.AlignCenter)

        self.setup_ui()
        self.update_dimensions()

        # Enable mouse tracking to detect hover
        self.setMouseTracking(True)

    def setup_ui(self):
        """Build the preview panel UI."""
        layout = CVBoxLayout(self)

        # Frame preview widget
        layout.addWidget(self.preview_view)

        # Control panel
        controls = CHBoxLayout()
        
        # Play/Pause button
        self.play_button = QPushButton("▶")
        self.play_button.setFixedSize(25, 25)
        self.play_button.clicked.connect(self.toggle_playback)
        controls.addWidget(self.play_button)
        
        self.time_label = QLabel("00:00:00.00")
        self.time_label.setStyleSheet("QLabel { color: #fff; background: #222; padding: 5px; }")
        controls.addWidget(self.time_label)

        controls.addStretch()

        # Speed control
        controls.addWidget(QLabel("Speed:"))
        self.speed_combo = QComboBox()
        self.speed_combo.addItems(["0.25x", "0.5x", "1x", "1.5x", "2x"])
        self.speed_combo.setCurrentText("1x")
        controls.addWidget(self.speed_combo)
        
        # Mute button for audio
        self.mute_button = QPushButton("🔊")
        self.mute_button.setFixedSize(25, 25)
        self.mute_button.setCheckable(True)
        self.mute_button.setToolTip("Mute audio")
        self.mute_button.clicked.connect(self.toggle_mute)
        controls.addWidget(self.mute_button)

        layout.addLayout(controls)

    def update_dimensions(self):
        """Update scene dimensions and canvas indicator based on project settings."""
        width = getattr(self.studio, 'project_width', 1920)
        height = getattr(self.studio, 'project_height', 1080)

        # Scene rect is larger than canvas to allow off-canvas positioning
        margin = max(width, height)
        self.scene.setSceneRect(-margin, -margin, width + 2 * margin, height + 2 * margin)

        # Create or update canvas indicator
        if not hasattr(self, 'canvas_rect'):
            # Canvas background (what will be rendered)
            self.canvas_rect = self.scene.addRect(
                0, 0, width, height,
                QPen(Qt.NoPen),
                QBrush(QColor(30, 30, 30))  # Dark background for canvas area
            )
            self.canvas_rect.setZValue(-100)  # Behind everything

        else:
            # Update existing canvas rect and border
            self.canvas_rect.setRect(0, 0, width, height)

        # Fit view to show the canvas
        self.fit_canvas_in_view()
    
    # ---------- Playback control ----------
    def start_playback(self):
        """Start playback using master timeline worker."""
        if self.is_playing:
            return

        start_frame = self.studio.timeline.get_playhead_frame()
        fps = self.studio.project_fps

        # Start master clock (frame-based)
        self.timeline_thread = QThread()
        self.timeline_worker = TimelinePlaybackWorker(start_frame=start_frame, fps=fps)
        self.timeline_worker.moveToThread(self.timeline_thread)
        self.timeline_thread.started.connect(self.timeline_worker.run)
        self.timeline_worker.frame_updated.connect(self.on_frame_updated)
        self.timeline_worker.finished.connect(self.timeline_thread.quit)
        self.timeline_thread.start()

        # Start audio playback (still uses time)
        timeline_time = frame_to_time(start_frame, fps)
        self.audio_player.play(timeline_time)

        self.is_playing = True
        self.play_button.setText("⏸")

    def stop_playback(self):
        """Stop playback and terminate all workers."""
        self.is_playing = False
        self.play_button.setText("▶")

        # Stop audio playback
        self.audio_player.stop()

        # Stop master clock
        if self.timeline_worker:
            self.timeline_worker.stop()
        if self.timeline_thread and self.timeline_thread.isRunning():
            self.timeline_thread.quit()
            self.timeline_thread.wait()
        self.timeline_worker = None
        self.timeline_thread = None

        # Stop all clip workers
        for clip_id, (thread, worker) in self.playback_workers.items():
            worker.stop()
            worker._ready.set()  # unblock if pre-warming
            if thread.isRunning():
                thread.quit()
                thread.wait()
        self.playback_workers.clear()
        self._prev_video_active_ids = None
        self._prev_video_upcoming_ids = None

        # Drain any retiring workers from previous sync cycles
        for thread, worker in list(self._retiring):
            if thread.isRunning():
                thread.quit()
                thread.wait()
        self._retiring.clear()

    def _retire_all_video_workers(self):
        """Retire all video decode workers so they are recreated on
        the next ``sync_playback_workers`` call.  Uses the same
        non-blocking retire pattern as ``sync_playback_workers``."""
        for clip_id in list(self.playback_workers.keys()):
            thread, worker = self.playback_workers.pop(clip_id)
            self._playback_offsets.pop(clip_id, None)
            try:
                worker.frame_decoded.disconnect()
            except RuntimeError:
                pass
            worker.stop()
            worker._ready.set()
            pair = (thread, worker)
            self._retiring.add(pair)
            thread.finished.connect(
                lambda p=pair: (
                    self._retiring.discard(p),
                    p[1].deleteLater(),
                    p[0].deleteLater(),
                )
            )
            thread.quit()
        self._prev_video_active_ids = None
        self._prev_video_upcoming_ids = None

    def on_frame_updated(self, current_frame: int):
        """Called by master clock every frame."""
        if not self.is_playing:
            return
        fps = self.studio.project_fps
        current_time = frame_to_time(current_frame, fps)

        # Update UI
        self.studio.timeline.set_playhead_frame(current_frame)

        # Check loop region
        tl = self.studio.timeline
        if (tl.loop_start_flag is not None
                and tl.loop_end_flag is not None):
            end_frame = tl.get_loop_end_frame()
            if current_frame >= end_frame:
                start_frame = tl.get_loop_start_frame()
                tl.set_playhead_frame(start_frame)
                start_time = frame_to_time(start_frame, fps)
                self.timeline_worker.seek(start_frame)
                self.audio_player.seek(start_time)
                self._retire_all_video_workers()
                return

        # Auto-pan timeline to keep playhead centered
        timeline = self.studio.timeline
        playhead_scene_x = current_frame * timeline.units_per_frame
        playhead_view_x = timeline.mapFromScene(
            playhead_scene_x, 0
        ).x()
        view_width = timeline.viewport().width()
        if playhead_view_x > view_width / 2:
            center_y = timeline.mapToScene(
                0, timeline.viewport().height() // 2
            ).y()
            timeline.centerOn(playhead_scene_x, center_y)

        # Format time label: "HH:MM:SS.CC (F###)"
        hours = int(current_time // 3600)
        minutes = int((current_time % 3600) // 60)
        seconds = int(current_time % 60)
        centiseconds = int((current_time % 1) * 100)
        self.time_label.setText(f"{hours:02d}:{minutes:02d}:{seconds:02d}.{centiseconds:02d} (F{current_frame})")

        # Sync clip workers (still uses time for decode workers)
        self.sync_playback_workers(current_time)

        # Sync audio players
        self.audio_player.sync(current_time)

    def sync_playback_workers(self, current_time: float):
        """Start/stop decode workers based on active clips at current_time."""
        active_clips = self.get_active_clips_at_time(current_time)
        active_ids = {c.member_id for c in active_clips}

        lookahead_time = current_time + 1.0
        upcoming_clips = self.get_active_clips_at_time(lookahead_time)
        upcoming_ids = {c.member_id for c in upcoming_clips}
        retain_ids = active_ids | upcoming_ids

        # Skip redundant work if the clip set hasn't changed
        active_changed = active_ids != getattr(
            self, '_prev_video_active_ids', None)
        upcoming_changed = upcoming_ids != getattr(
            self, '_prev_video_upcoming_ids', None)
        if not active_changed and not upcoming_changed:
            return
        self._prev_video_active_ids = active_ids.copy()
        self._prev_video_upcoming_ids = upcoming_ids.copy()

        # 1. Stop workers for clips that are no longer active
        # Use list(keys) to avoid runtime error during modification
        for clip_id in list(self.playback_workers.keys()):
            if clip_id not in retain_ids:
                thread, worker = self.playback_workers[clip_id]
                try:
                    worker.frame_decoded.disconnect()
                except RuntimeError:
                    pass
                worker.stop()
                worker._ready.set()  # unblock if pre-warming
                pair = (thread, worker)
                self._retiring.add(pair)
                thread.finished.connect(
                    lambda p=pair: (
                        self._retiring.discard(p),
                        p[1].deleteLater(),
                        p[0].deleteLater(),
                    )
                )
                thread.quit()
                del self.playback_workers[clip_id]
                self._playback_offsets.pop(clip_id, None)

                # Also hide/remove the preview item
                target_clip = self.studio.timeline.clips.get(clip_id)
                if target_clip:
                    for item in self.scene.items():
                        if isinstance(item, PreviewClipItem) and item.media_member == target_clip:
                            self.scene.removeItem(item)
                            break

        # 2. Start workers for new active clips
        for clip in active_clips:
            clip_id = clip.member_id
            if clip_id in self.playback_workers:
                thread, worker = self.playback_workers[clip_id]
                if worker._prewarm:
                    # Activate: connect signal, release gate
                    worker._prewarm = False
                    clip_start_on_timeline = float(getattr(clip, "start_time", 0.0))
                    in_point = float(getattr(clip, "in_point", 0.0))
                    timeline_offset = clip_start_on_timeline - in_point
                    self._playback_offsets[clip_id] = timeline_offset
                    worker.frame_decoded.connect(self._on_playback_frame_decoded)
                    # Directly inject pre-decoded frame from main thread (zero latency)
                    if worker._first_frame is not None:
                        clip_time, frame = worker._first_frame
                        self.on_frame_decoded(frame, clip_time + timeline_offset, clip_id, set_playhead=False)
                        worker._first_frame_consumed = True
                    worker._ready.set()
                continue

            filepath = clip.filepath
            if not os.path.exists(filepath):
                continue

            # Skip audio clips - they don't need video decode workers
            ext = os.path.splitext(filepath)[1].lower()
            if ext in AUDIO_EXTS:
                continue

            # Calculate start time for this clip
            clip_start_on_timeline = float(getattr(clip, "start_time", 0.0))
            in_point = float(getattr(clip, "in_point", 0.0))

            # Where are we in the clip?
            clip_local_time = current_time - clip_start_on_timeline + in_point
            clip_local_time = max(0.0, clip_local_time)

            # Create worker
            thread = QThread()
            worker = VideoDecodeWorker(filepath=filepath, start_time=clip_local_time, fps=self.studio.project_fps, clip_id=clip_id)
            worker.moveToThread(thread)
            thread.started.connect(worker.run)

            # Store timeline offset
            timeline_offset = clip_start_on_timeline - in_point

            self._playback_offsets[clip_id] = timeline_offset
            worker.frame_decoded.connect(self._on_playback_frame_decoded)
            worker.finished.connect(thread.quit)

            thread.start()
            self.playback_workers[clip_id] = (thread, worker)

        # 3. Pre-warm workers for upcoming clips
        for clip in upcoming_clips:
            clip_id = clip.member_id
            if clip_id in self.playback_workers or clip_id in active_ids:
                continue
            filepath = clip.filepath
            if not os.path.exists(filepath):
                continue
            ext = os.path.splitext(filepath)[1].lower()
            if ext in AUDIO_EXTS:
                continue

            clip_start_on_timeline = float(getattr(clip, "start_time", 0.0))
            in_point = float(getattr(clip, "in_point", 0.0))

            thread = QThread()
            worker = VideoDecodeWorker(
                filepath=filepath, start_time=in_point,
                fps=self.studio.project_fps, clip_id=clip_id,
                prewarm=True,
            )
            worker.moveToThread(thread)
            thread.started.connect(worker.run)
            worker.finished.connect(thread.quit)
            thread.start()
            self.playback_workers[clip_id] = (thread, worker)
    
    @Slot(np.ndarray, float, str)
    def _on_seek_frame_decoded(self, frame, time_seconds, clip_id):
        self.on_frame_decoded(frame, time_seconds, clip_id, set_playhead=False)

    @Slot(np.ndarray, float, str)
    def _on_playback_frame_decoded(self, frame, clip_time, clip_id):
        """Playback frame handler — offset is stored in _playback_offsets."""
        if clip_id not in self.playback_workers:
            return  # worker was retired; ignore stale queued signal
        offset = self._playback_offsets.get(clip_id, 0.0)
        self.on_frame_decoded(frame, clip_time + offset, clip_id, set_playhead=False)

    def on_frame_decoded(self, frame, time_seconds, clip_id, set_playhead=True):
        """Called when a new frame is decoded by worker."""
        if frame is None:
            return

        # Convert numpy array → QPixmap
        frame = np.ascontiguousarray(frame)
        h, w, ch = frame.shape
        bytes_per_line = ch * w
        qimg = QImage(frame.tobytes(), w, h, bytes_per_line, QImage.Format_RGB888)
        pixmap = QPixmap.fromImage(qimg)

        # Find or create PreviewClipItem for this clip_id
        preview_item = None
        target_clip = self.studio.timeline.clips.get(clip_id)

        if target_clip:
            for item in self.scene.items():
                if isinstance(item, PreviewClipItem) and item.media_member == target_clip:
                    preview_item = item
                    break

            if not preview_item:
                preview_item = PreviewClipItem(target_clip)
                preview_item.setZValue(target_clip.track_index)
                self.scene.addItem(preview_item)

            preview_item.set_pixmap(pixmap)
            preview_item.setVisible(True)


        # Note: We no longer set playhead here during playback,
        # as TimelinePlaybackWorker handles it.
        # We might still use set_playhead=True for seek operations (request_frame).
        if set_playhead:
            fps = self.studio.project_fps
            current_frame = time_to_frame(time_seconds, fps)
            self.studio.timeline.set_playhead_frame(current_frame)

            # Update label with frame number
            hours = int(time_seconds // 3600)
            minutes = int((time_seconds % 3600) // 60)
            seconds = int(time_seconds % 60)
            centiseconds = int((time_seconds % 1) * 100)
            self.time_label.setText(f"{hours:02d}:{minutes:02d}:{seconds:02d}.{centiseconds:02d} (F{current_frame})")

    # ---------- Clip helpers ----------
    def get_active_clips_at_frame(self, frame: int):
        """
        Return list of timeline clip objects active at `frame`.
        A clip is active when the timeline frame is within [start_frame, start_frame + frame_count).
        """
        if not hasattr(self.studio.timeline, "clips"):
            return []
        active = []
        for clip in self.studio.timeline.clips.values():
            if clip.is_disabled:
                continue
            clip_start = clip.start_frame
            frame_count = clip.frame_count
            if frame_count <= 0:
                continue
            if frame >= clip_start and frame < (clip_start + frame_count):
                active.append(clip)
        return active

    def get_active_clips_at_time(self, time_seconds: float):
        """
        Return list of timeline clip objects active at `time_seconds`.
        Converts time to frame and delegates to get_active_clips_at_frame.
        """
        frame = time_to_frame(time_seconds, self.studio.project_fps)
        return self.get_active_clips_at_frame(frame)

    def request_frame(self, frame: int):
        """Request a single frame decode in background for all active clips."""
        fps = self.studio.project_fps
        time_seconds = frame_to_time(frame, fps)
        active = self.get_active_clips_at_frame(frame)

        # Identify clips that are no longer active and hide/remove their preview items
        active_ids = {c.member_id for c in active}
        stale = [item for item in self.scene.items()
                 if isinstance(item, PreviewClipItem)
                 and item.media_member.member_id not in active_ids]
        for item in stale:
            self.scene.removeItem(item)

        if not active:
            return

        for clip in active:
            filepath = clip.filepath
            clip_id = clip.member_id
            if not os.path.exists(filepath):
                continue

            # Skip audio clips - they don't need visual preview
            if clip.member_type == 'audio':
                continue

            # Timeline frame → clip-local time mapping
            # The clip stores start_frame and in_frame/out_frame
            # We need to calculate the local time within the media file
            clip_start_frame = clip.start_frame
            in_frame = clip.in_frame

            # Calculate local frame within the clip
            local_frame = frame - clip_start_frame + in_frame
            local_frame = max(0, local_frame)

            # Convert to time for the decode worker
            local_t = frame_to_time(local_frame, fps)

            # Clamp to valid range [0, duration]
            duration = clip.duration
            if duration > 0.0:
                local_t = max(0.0, min(local_t, duration))

            # Set current task from main thread so stale queued requests
            # see an advanced _current_task and bail out early.
            self.seek_decode_worker._current_task = (filepath, local_t, clip_id)
            self.seek_decode_worker.decode_request.emit(filepath, local_t, clip_id)

    def toggle_playback(self):
        """Toggle play/pause state."""
        if self.is_playing:
            self.stop_playback()
        else:
            self.start_playback()

    def toggle_mute(self):
        """Toggle audio mute."""
        is_muted = self.mute_button.isChecked()

        if is_muted:
            self.mute_button.setText("🔇")
            self.audio_player.set_muted(True)
        else:
            self.mute_button.setText("🔊")
            self.audio_player.set_muted(False)

            # Resume audio if playing
            if self.is_playing:
                current_frame = self.studio.timeline.get_playhead_frame()
                current_time = frame_to_time(
                    current_frame, self.studio.project_fps
                )
                self.audio_player.play(current_time)

    def position_studio_button(self):
        """Position the studio button in the top right corner."""
        if not hasattr(self, 'studio_button'):
            return
        button_width = self.studio_button.sizeHint().width()
        button_height = self.studio_button.sizeHint().height()
        margin = 10
        x = self.width() - button_width - margin
        y = margin
        self.studio_button.setGeometry(x, y, button_width, button_height)
        self.studio_button.raise_()

    def resizeEvent(self, event):
        """Handle widget resize to reposition studio button and fit canvas in view."""
        super().resizeEvent(event)
        self.position_studio_button()
        self.fit_canvas_in_view()

    def fit_canvas_in_view(self):
        """Fit the canvas (project dimensions) into the view with some padding."""
        if not hasattr(self, 'preview_view') or not hasattr(self, 'canvas_rect'):
            return
        # Fit to the canvas rect (project dimensions), not the entire scene
        canvas_rect = self.canvas_rect.rect()
        # Add small padding around the canvas
        padding = 20
        padded_rect = QRectF(
            canvas_rect.x() - padding,
            canvas_rect.y() - padding,
            canvas_rect.width() + 2 * padding,
            canvas_rect.height() + 2 * padding
        )
        self.preview_view.fitInView(padded_rect, Qt.KeepAspectRatio)

    def get_canvas_snap_lines(self):
        """
        Return snap line positions for the canvas.
        Returns dict with keys: left, right, top, bottom, vcenter, hcenter
        Values are in scene coordinates.
        """
        if not hasattr(self, 'canvas_rect'):
            return {}
        rect = self.canvas_rect.rect()
        return {
            'left': rect.left(),
            'right': rect.right(),
            'top': rect.top(),
            'bottom': rect.bottom(),
            'vcenter': rect.center().x(),
            'hcenter': rect.center().y(),
        }

    def get_snap_threshold(self):
        """Get snap threshold in scene units (5% of canvas width/height)."""
        if not hasattr(self, 'canvas_rect'):
            return 50  # fallback
        rect = self.canvas_rect.rect()
        # Use average of width and height
        return max(rect.width(), rect.height()) * self.snap_threshold_percent

    def show_snap_lines(self, active_lines):
        """
        Show snap lines for the given set of line positions.
        active_lines: dict with keys like 'left', 'vcenter', etc. and bool values
        """
        self.hide_snap_lines()
        if not hasattr(self, 'canvas_rect'):
            return

        canvas = self.canvas_rect.rect()
        snap_positions = self.get_canvas_snap_lines()
        pen = QPen(QColor(255, 100, 100), 1, Qt.DashLine)
        pen.setCosmetic(True)

        for key, should_show in active_lines.items():
            if not should_show:
                continue
            pos = snap_positions.get(key)
            if pos is None:
                continue

            # Vertical lines (left, right, vcenter)
            if key in ('left', 'right', 'vcenter'):
                line = QGraphicsLineItem(pos, canvas.top() - 100, pos, canvas.bottom() + 100)
            # Horizontal lines (top, bottom, hcenter)
            else:
                line = QGraphicsLineItem(canvas.left() - 100, pos, canvas.right() + 100, pos)

            line.setPen(pen)
            line.setZValue(1000)
            self.scene.addItem(line)
            self.snap_lines.append(line)

    def hide_snap_lines(self):
        """Remove all visible snap lines from the scene."""
        for line in self.snap_lines:
            self.scene.removeItem(line)
        self.snap_lines.clear()

    def calculate_snap(self, clip_item, new_pos):
        """
        Calculate snapped position for a PreviewClipItem.
        Returns (snapped_pos, active_snap_lines_dict).
        """
        if not hasattr(self, 'canvas_rect') or not clip_item.pixmap:
            return new_pos, {}

        canvas_snaps = self.get_canvas_snap_lines()
        threshold = self.get_snap_threshold()
        active_lines = {}

        # Get clip bounds in scene coordinates at new_pos
        # The clip's content rect is at (0,0) in local coords
        content = clip_item.content_rect()
        scale = clip_item.scale()

        # Calculate clip edges at the proposed position
        clip_left = new_pos.x()
        clip_right = new_pos.x() + content.width() * scale
        clip_top = new_pos.y()
        clip_bottom = new_pos.y() + content.height() * scale
        clip_vcenter = new_pos.x() + (content.width() * scale) / 2
        clip_hcenter = new_pos.y() + (content.height() * scale) / 2

        snapped_x = new_pos.x()
        snapped_y = new_pos.y()

        # Check horizontal snaps (affects X position)
        best_x_snap = None
        best_x_dist = threshold

        # Check vertical snaps (affects Y position)
        best_y_snap = None
        best_y_dist = threshold

        clip_h_snaps = [clip_left, clip_right, clip_vcenter]
        clip_v_snaps = [clip_top, clip_bottom, clip_hcenter]

        for clip_snap in clip_h_snaps:
            for snap_key in ('left', 'vcenter', 'right'):
                snap_pos = canvas_snaps.get(snap_key)
                if snap_pos is None:
                    continue
                dist = abs(clip_snap - snap_pos)
                if dist < best_x_dist:
                    best_x_dist = dist
                    best_x_snap = (snap_key, snap_pos - clip_snap + new_pos.x(), snap_key)

        for clip_snap in clip_v_snaps:
            for snap_key in ('top', 'hcenter', 'bottom'):
                snap_pos = canvas_snaps.get(snap_key)
                if snap_pos is None:
                    continue
                dist = abs(clip_snap - snap_pos)
                if dist < best_y_dist:
                    best_y_dist = dist
                    best_y_snap = (snap_key, snap_pos - clip_snap + new_pos.y(), snap_key)

        if best_x_snap:
            snapped_x = best_x_snap[1]
            active_lines[best_x_snap[2]] = True

        if best_y_snap:
            snapped_y = best_y_snap[1]
            active_lines[best_y_snap[2]] = True

        return QPointF(snapped_x, snapped_y), active_lines

    def enterEvent(self, event):
        """Show studio button when mouse enters, but only if in fullscreen mode."""
        super().enterEvent(event)
        if self.studio.full_screen:
            self.studio_button.show()

    def leaveEvent(self, event):
        """Hide studio button when mouse leaves."""
        super().leaveEvent(event)
        self.studio_button.hide()
    
    def closeEvent(self, event):
        self.stop_playback()
        # Drain retiring workers
        for thread, worker in list(self._retiring):
            if thread.isRunning():
                thread.quit()
                thread.wait()
        self._retiring.clear()
        # Clean up seek decode thread
        if self.seek_decode_thread and self.seek_decode_thread.isRunning():
            self.seek_decode_thread.quit()
            self.seek_decode_thread.wait()
        super().closeEvent(event)


class TimelinePlaybackWorker(QObject):
    """Worker that acts as a master clock for timeline playback (frame-based)."""
    frame_updated = Signal(int)  # Emits current frame number
    finished = Signal()

    def __init__(self, start_frame: int = 0, fps: float = 30.0, parent=None):
        super().__init__(parent)
        self.current_frame = start_frame
        self.fps = fps
        self._running = True

    def stop(self):
        self._running = False

    def seek(self, frame):
        """Reset playback origin to a new frame."""
        self._seek_frame = frame

    def run(self):
        frame_duration = 1.0 / self.fps
        start_wall_time = time.time()
        start_frame = self.current_frame
        tick = 0
        self._seek_frame = None

        while self._running:
            # Check for pending seek
            if self._seek_frame is not None:
                start_frame = self._seek_frame
                start_wall_time = time.time()
                tick = 0
                self._seek_frame = None

            now = time.time()
            elapsed = now - start_wall_time
            self.current_frame = start_frame + int(elapsed * self.fps)

            self.frame_updated.emit(self.current_frame)

            # Sleep until the next frame boundary to avoid accumulated drift
            tick += 1
            target_time = start_wall_time + tick * frame_duration
            sleep_time = target_time - time.time()
            if sleep_time > 0:
                time.sleep(sleep_time)

        self.finished.emit()


class VideoDecodeWorker(QObject):
    """Worker for sequential frame decoding using MoviePy.iter_frames()."""
    frame_decoded = Signal(np.ndarray, float, str)  # (frame, time_seconds, clip_id)
    finished = Signal()
    # new signal for requesting single frame decode (to connect externally)
    decode_request = Signal(str, float, str) # (filepath, time, clip_id)


    def __init__(self, filepath=None, start_time=0.0, fps=30.0, clip_id=None, prewarm=False, parent=None):
        super().__init__(parent)
        self.filepath = filepath
        self.start_time = start_time
        self.fps = fps
        self.clip_id = clip_id
        self._running = True
        self._prewarm = prewarm
        self._ready = threading.Event()
        self._first_frame = None  # (clip_time, numpy_frame) stored for direct consumption
        self._first_frame_consumed = False
        if not prewarm:
            self._ready.set()

        self._current_task = None

    @Slot(str, float, str)
    def _on_decode_request(self, filepath: str, timestamp: float, clip_id: str):
        """Internal slot for decoding a single frame."""
        task_id = (filepath, timestamp, clip_id)

        # _current_task is set from the main thread in request_frame().
        # If it has advanced past this task, skip the expensive decode.
        if self._current_task != task_id:
            return

        try:
            if not filepath or not os.path.exists(filepath):
                print(f"Filepath not found: {filepath}")
                return

            # Check if this is still the current task before expensive operations
            if self._current_task != task_id:
                return

            ext = os.path.splitext(filepath)[1].lower()

            # Handle images
            if ext in IMAGE_EXTS:
                img = QImage(filepath)
                if img.isNull():
                    print(f"Failed to load image: {filepath}")
                    return
                img = img.convertToFormat(QImage.Format_RGB888)
                frame = np.frombuffer(img.bits(), dtype=np.uint8).reshape(
                    img.height(), img.width(), 3).copy()
                if self._current_task == task_id:
                    self.frame_decoded.emit(frame, timestamp, clip_id)
                return

            # Handle video
            with VideoFileClip(filepath) as clip:
                # Check again before get_frame (most expensive operation)
                if self._current_task != task_id:
                    return

                timestamp = max(0.0, min(timestamp, clip.duration or 0.0))
                frame = clip.get_frame(timestamp).copy()

                # Final check before emitting
                if self._current_task == task_id:
                    self.frame_decoded.emit(frame, timestamp, clip_id)
        except Exception as e:
            print(f"[SeekDecodeWorker Error] {e}")

    def stop(self):
        self._running = False

    def run(self):
        try:
            if not self.filepath or not os.path.exists(self.filepath):
                return

            ext = os.path.splitext(self.filepath)[1].lower()
            frame_duration = 1.0 / self.fps

            # Handle images - emit same frame repeatedly
            if ext in IMAGE_EXTS:
                img = QImage(self.filepath)
                if img.isNull():
                    return
                img = img.convertToFormat(QImage.Format_RGB888)
                frame = np.frombuffer(img.bits(), dtype=np.uint8).reshape(
                    img.height(), img.width(), 3).copy()

                self._first_frame = (self.start_time, frame)

                self._ready.wait()
                if not self._running:
                    return

                t = self.start_time
                # Skip first emission if already consumed by activator
                if self._first_frame_consumed:
                    time.sleep(frame_duration)
                    t += frame_duration
                while self._running:
                    self.frame_decoded.emit(frame, t, self.clip_id)
                    time.sleep(frame_duration)
                    t += frame_duration
                return

            # Handle video
            with VideoFileClip(self.filepath) as clip:
                # Start iteration from the specified start time
                start_t = max(0, min(self.start_time, clip.duration - 0.001))  # Small offset to avoid edge case

                if start_t >= clip.duration:
                    print(f"[DecodeWorker] Start time {start_t} is beyond clip duration {clip.duration}")
                    return

                subclip = clip.subclipped(start_t)
                frame_gen = subclip.iter_frames(fps=self.fps, dtype="uint8", with_times=True)

                # Pre-decode first frame so it's ready instantly
                first = next(frame_gen, None)
                if first is not None:
                    t_first, frame_first = first
                    self._first_frame = (t_first + start_t, frame_first)

                self._ready.wait()
                if not self._running:
                    return

                start_wall = time.time()
                frame_index = 0

                # Emit pre-decoded first frame (skip if already consumed by activator)
                if first is not None:
                    if not self._first_frame_consumed:
                        t, frame = first
                        actual_time = t + start_t
                        self.frame_decoded.emit(frame, actual_time, self.clip_id)
                    frame_index += 1

                for t, frame in frame_gen:
                    if not self._running:
                        break

                    # Adjust time to be relative to the original clip
                    actual_time = t + start_t
                    self.frame_decoded.emit(frame, actual_time, self.clip_id)

                    # Sleep until absolute target time to prevent drift
                    frame_index += 1
                    target_time = start_wall + frame_index * frame_duration
                    sleep_time = target_time - time.time()
                    if sleep_time > 0:
                        time.sleep(sleep_time)

        except Exception as e:
            print(f"[DecodeWorker Error] {e}")
        finally:
            self.finished.emit()


def get_media_duration(filepath: str) -> float:
    """
    Get duration of media file in seconds using MoviePy.

    Falls back to a default duration if the file cannot be opened or is not
    a supported audio/video type.
    """
    if not filepath or not os.path.exists(filepath):
        return 5.0

    ext = os.path.splitext(filepath)[1].lower()

    # Images don't have a duration – keep a small default like before.
    if ext in IMAGE_EXTS:
        return 5.0

    try:
        # Audio files
        if ext in AUDIO_EXTS:
            with AudioFileClip(filepath) as clip:
                return float(clip.duration)

        # Everything else we treat as video
        with VideoFileClip(filepath) as clip:
            return float(clip.duration)

    except Exception:
        # Fallback to default duration if MoviePy fails
        return 5.0


class _AudioPlayer(QObject):
    """Multi-clip audio player using Qt's multimedia system.

    Key design choices
    ------------------
    * Players are only created / destroyed when the set of active clips
      changes (tracked via ``_prev_active_ids``), avoiding per-frame churn.
    * Media is seeked *before* playback starts by waiting for the
      ``LoadedMedia`` status, eliminating the brief burst from position 0
      that caused the looping-sound artefact.
    * Clip and track volumes are applied to each ``QAudioOutput``.
    """

    def __init__(self, studio):
        super().__init__()
        self.studio = studio
        self.timeline = studio.timeline
        self._muted = False
        self.is_playing = False
        self.clip_players = {}  # clip_id -> (player, audio_output, clip)
        self._prev_active_ids = set()

    def set_muted(self, muted: bool):
        self._muted = bool(muted)
        for player, audio_output, clip in self.clip_players.values():
            audio_output.setMuted(self._muted)

    def is_muted(self) -> bool:
        return self._muted

    def _get_active_clips_at_time(self, timeline_time: float):
        """Return clips that are active at the given timeline time."""
        active = []
        for clip in self.timeline.clips.values():
            if clip.is_disabled:
                continue
            clip_start = float(clip.start_time)
            in_point = float(clip.in_point)
            out_point = float(clip.out_point)
            clip_length = max(0.0, out_point - in_point)
            if clip_length <= 0:
                continue
            if clip_start <= timeline_time < (clip_start + clip_length):
                active.append(clip)
        return active

    def play(self, timeline_time: float):
        """Start playback."""
        self.is_playing = True
        self._prev_active_ids = set()  # Force full sync
        self.sync(timeline_time)

    def seek(self, timeline_time: float):
        """Seek all active players to a new timeline position."""
        for clip_id, (player, audio_output, clip) in list(
            self.clip_players.items()
        ):
            clip_start = float(clip.start_time)
            in_point = float(clip.in_point)
            media_pos_s = (timeline_time - clip_start) + in_point
            position_ms = max(0, int(media_pos_s * 1000))
            player.pause()
            player.setPosition(position_ms)
            player.play()
        # Force re-sync on next frame for clip set changes
        self._prev_active_ids = set()
        self.sync(timeline_time)

    def sync(self, timeline_time: float):
        """Sync audio players with active clips at current timeline time.

        Only creates / destroys players when the active-clip set changes.
        """
        if not self.is_playing:
            return

        active_clips = self._get_active_clips_at_time(timeline_time)
        active_ids = {c.member_id for c in active_clips}

        if active_ids == self._prev_active_ids:
            return
        self._prev_active_ids = active_ids.copy()

        # Stop players for clips that are no longer active
        for clip_id in list(self.clip_players.keys()):
            if clip_id not in active_ids:
                self._destroy_player(clip_id)

        # Start players for newly active clips
        for clip in active_clips:
            clip_id = clip.member_id
            if clip_id in self.clip_players:
                continue

            filepath = clip.filepath
            if not filepath or not os.path.exists(filepath):
                continue

            self._create_and_start_player(clip, timeline_time)

    # ------------------------------------------------------------------
    def _create_and_start_player(self, clip, timeline_time: float):
        """Create a player, seek to the correct position, then play."""
        clip_id = clip.member_id

        player = QMediaPlayer(self)
        audio_output = QAudioOutput(self)

        # Apply clip and track volumes
        clip_volume = clip.member_config.get('volume', 100) / 100.0
        track_configs = self.studio.track_control_panel.get_config()
        track_vol = 1.0
        if clip.track_index < len(track_configs):
            track_vol = track_configs[clip.track_index].get(
                'volume', 100
            ) / 100.0
        audio_output.setVolume(clip_volume * track_vol)
        audio_output.setMuted(self._muted)

        player.setAudioOutput(audio_output)
        player.errorOccurred.connect(
            lambda err, cid=clip_id: self._on_error(cid, err)
        )

        # Where in the media file should playback begin?
        clip_start = float(clip.start_time)
        in_point = float(clip.in_point)
        media_pos_s = (timeline_time - clip_start) + in_point
        position_ms = max(0, int(media_pos_s * 1000))

        player.setSource(QUrl.fromLocalFile(clip.filepath))
        player.play()
        if position_ms > 0:
            QTimer.singleShot(50, lambda p=player, ms=position_ms:
                              p.setPosition(ms))

        self.clip_players[clip_id] = (player, audio_output, clip)

    def _destroy_player(self, clip_id: str):
        """Stop and clean up a single clip player."""
        if clip_id not in self.clip_players:
            return
        player, audio_output, _ = self.clip_players.pop(clip_id)
        player.stop()
        player.setSource(QUrl())
        player.deleteLater()
        audio_output.deleteLater()

    def stop(self):
        """Stop all audio playback."""
        self.is_playing = False
        self._prev_active_ids = set()
        for clip_id in list(self.clip_players.keys()):
            self._destroy_player(clip_id)

    def _on_error(self, clip_id: str, error):
        """Handle media player errors."""
        if error != QMediaPlayer.NoError:
            entry = self.clip_players.get(clip_id)
            if entry:
                print(
                    f"Audio error on clip {clip_id}: "
                    f"{entry[0].errorString()}"
                )