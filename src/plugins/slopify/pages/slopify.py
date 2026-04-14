import asyncio
from functools import partial
import json
import math
import os
import random

import lyricsgenius
import qasync

from PySide6.QtWidgets import (
    QComboBox, QInputDialog, QMessageBox, QSplitter,
    QSizePolicy, QStyle, QWidget, QPushButton, QSlider, QLabel,
)
from PySide6.QtMultimedia import QMediaPlayer, QAudioOutput
from PySide6.QtCore import QTimer, QUrl, Qt
from PySide6.QtGui import QColor, QIcon

from gui.widgets.config_widget import ConfigWidget
from gui.widgets.config_table import ConfigTable
from gui.widgets.config_tabs import ConfigTabs
from gui.widgets.config_fields import ConfigFields
from gui.widgets.config_joined import ConfigJoined
from gui.widgets.config_side_tabs import ConfigSideTabs
from gui.util import CVBoxLayout, CHBoxLayout, IconButton, CustomMenu, find_main
from utils import sql
from utils.filesystem import get_application_path
from utils.helpers import (
    block_signals, compute_workflow_async, display_message,
    display_message_box, download_url_to_file,
    merge_config_into_workflow_config,
    set_module_type, path_to_pixmap, try_parse_json,
)
from plugins.workflows.widgets.chat_widget import ChattableWorkflowWidget


def _fmt(ms):
    """Format milliseconds as M:SS."""
    s = max(0, ms // 1000)
    return f'{s // 60}:{s % 60:02d}'


def sync_artist_songs(artist_id, artist_name):
    """Fetch songs from Genius and upsert into slopify_artist_songs.

    Returns the number of songs synced, or 0 on failure.
    """
    token = os.environ.get('GENIUS_API_TOKEN', '')
    if not token:
        return 0
    genius = lyricsgenius.Genius(token, timeout=10, retries=3)
    genius.verbose = False
    try:
        artist = genius.search_artist(
            artist_name, max_songs=150, sort='popularity',
            get_full_info=False, include_features=False,
            per_page=20,
        )
    except Exception:
        return 0
    if not artist or not artist.songs:
        return 0
    for s in artist.songs:
        existing = sql.get_scalar(
            "SELECT id FROM slopify_artist_songs"
            " WHERE artist_id = ? AND name = ?",
            (artist_id, s.title),
        )
        config = json.dumps({'lyrics': s.lyrics or ''})
        if existing:
            sql.execute(
                "UPDATE slopify_artist_songs"
                " SET config = ? WHERE id = ?",
                (config, existing),
            )
        else:
            sql.execute(
                "INSERT INTO slopify_artist_songs"
                " (artist_id, name, config) VALUES (?, ?, ?)",
                (artist_id, s.title, config),
            )
    return len(artist.songs)


def _safe_filename(name):
    """Sanitize a string for use as a filename."""
    import re
    return re.sub(r'[<>:"/\\|?*\r\n]+', '', name).strip()[:200] \
        or 'Untitled'


class CustomSlider(QSlider):
    """Custom slider with transparent background."""

    def __init__(self, parent, seek_on_release=False):
        super().__init__(parent)
        self.setOrientation(Qt.Horizontal)
        self._dragging = False
        self.seek_on_release = seek_on_release
        # call leave event to hide the slider
        self.leaveEvent(None)

    def mousePressEvent(self, event):
        """Jump to the clicked position and start dragging."""
        if event.button() == Qt.LeftButton:
            val = QStyle.sliderValueFromPosition(
                self.minimum(), self.maximum(),
                event.position().toPoint().x(), self.width(),
            )
            self.setValue(val)
            self._dragging = True
            if not self.seek_on_release:
                self.sliderMoved.emit(val)
            event.accept()
        else:
            super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        """Continue dragging after a click-jump."""
        if self._dragging:
            val = QStyle.sliderValueFromPosition(
                self.minimum(), self.maximum(),
                int(event.position().x()), self.width(),
            )
            self.setValue(val)
            if not self.seek_on_release:
                self.sliderMoved.emit(val)
            event.accept()
        else:
            super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        """Seek to final position on release."""
        if event.button() == Qt.LeftButton and self._dragging:
            self._dragging = False
            if self.seek_on_release:
                self.sliderMoved.emit(self.value())
        super().mouseReleaseEvent(event)

    def enterEvent(self, event):
        super().enterEvent(event)

        from gui.style import TEXT_COLOR
        from utils.helpers import apply_alpha_to_hex
        self.setStyleSheet(f"""
            QSlider::groove:horizontal {{
                background: transparent;
                height: 4px;
                border: none;
                border-radius: 2px;
            }}
            QSlider::handle:horizontal {{
                background: {TEXT_COLOR};
                width: 12px;
                height: 12px;
                margin: -4px 0;
                border-radius: 6px;
            }}
            QSlider::sub-page:horizontal {{
                background: #1db954;
                border-radius: 2px;
            }}
            QSlider::add-page:horizontal {{
                background: {apply_alpha_to_hex(TEXT_COLOR, 0.3)};
                border-radius: 2px;
            }}
        """)
    
    def leaveEvent(self, event):
        super().leaveEvent(event)
        
        from gui.style import TEXT_COLOR
        from utils.helpers import apply_alpha_to_hex
        self.setStyleSheet(f"""
            QSlider::groove:horizontal {{
                background: transparent;
                height: 4px;
                border: none;
                border-radius: 2px;
            }}
            QSlider::handle:horizontal {{
                background: transparent;
                border: none;
            }}
            QSlider::sub-page:horizontal {{
                background: {TEXT_COLOR};
                border-radius: 2px;
            }}
            QSlider::add-page:horizontal {{
                background: {apply_alpha_to_hex(TEXT_COLOR, 0.3)};
                border-radius: 2px;
            }}
        """)


@set_module_type('Pages')
class Page_Slopify(ConfigWidget):
    """AI music generator with persistent track queue and playback."""

    display_name = 'Slopify'
    icon_path = ':/resources/icon-audio.png'
    page_type = 'any'

    def __init__(self, parent):
        super().__init__(parent=parent)
        self.main = find_main()

        self.media_player = QMediaPlayer()
        self.audio_output = QAudioOutput()
        self.media_player.setAudioOutput(self.audio_output)
        # self.audio_output.setVolume(0.5)

        self.current_track_index = -1
        self.current_track_id = None
        self._pending = 0
        self._gen_running = False
        self.is_generating = False
        self._polling = False

        self._gen_timer = QTimer()
        self._gen_timer.timeout.connect(self._generation_tick)

        self._poll_timer = QTimer()
        self._poll_timer.timeout.connect(self._poll_tick)

        self.artist_config = self.ArtistConfigWidget(parent=self)
        self.artist_collection = self.ArtistCollection(parent=self)
        self.playlist_track_list = self.PlaylistTrackList(parent=self)
        self.playlist_collection = self.PlaylistCollection(parent=self)
        self.side_tabs = ConfigSideTabs(
            parent=self,
            pages={
                'Artists': self.artist_collection,
                'Playlists': self.playlist_collection,
            },
        )
        self.track_queue = self.TrackQueue(parent=self)
        self.player_controls = self.PlayerControls(parent=self)

        self.layout = CVBoxLayout(self)
        self.page_splitter = QSplitter(Qt.Vertical)
        self.page_splitter.setSizePolicy(
            QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.page_splitter.setChildrenCollapsible(False)
        self.page_splitter.addWidget(self.side_tabs)
        self.page_splitter.addWidget(self.track_queue)
        self.page_splitter.setSizes([300, 400])
        self.layout.addWidget(self.page_splitter, 1)
        self.layout.addWidget(self.player_controls)

        self.media_player.positionChanged.connect(
            self.player_controls.on_position_changed)
        self.media_player.durationChanged.connect(
            self.player_controls.on_duration_changed)
        self.media_player.durationChanged.connect(self._update_track_duration)
        self.media_player.mediaStatusChanged.connect(
            self._on_media_status_changed)

    def build_schema(self):
        super().build_schema()
        self.side_tabs.build_schema()
        self.track_queue.build_schema()
        self.artists_section = self.side_tabs.sections.get('Artists')
        self.playlists_section = self.side_tabs.sections.get(
            'Playlists')

        def _any_section_expanded():
            """Check if at least one side-tab section is expanded."""
            for sec in (self.artists_section, self.playlists_section):
                if sec and sec.is_expanded:
                    return True
            return False

        if self.artists_section:
            original_artists_toggle = self.artists_section.toggle

            def patched_artists_toggle():
                original_artists_toggle()
                if not _any_section_expanded():
                    QTimer.singleShot(
                        10, lambda: self.page_splitter.setSizes(
                            [0, 1000]))
                else:
                    self.page_splitter.setSizes([500, 500])

            self.artists_section.toggle = patched_artists_toggle

        if self.playlists_section:
            original_playlists_toggle = self.playlists_section.toggle

            def patched_playlists_toggle():
                original_playlists_toggle()
                if not _any_section_expanded():
                    QTimer.singleShot(
                        10, lambda: self.page_splitter.setSizes(
                            [0, 1000]))
                else:
                    self.page_splitter.setSizes([500, 500])

            self.playlists_section.toggle = patched_playlists_toggle

    def load(self):
        """Ensure DB tables exist, create/load workflow, load sub-widgets."""
        sql.execute("""
            CREATE TABLE IF NOT EXISTS slopify_tracks (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                context_id  INTEGER,
                filepath    TEXT DEFAULT '',
                title       TEXT DEFAULT '',
                duration_ms INTEGER DEFAULT 0,
                created_at  TEXT DEFAULT (datetime('now'))
            )
        """)
        sql.execute("""
            CREATE TABLE IF NOT EXISTS slopify_artists (
                id     INTEGER PRIMARY KEY AUTOINCREMENT,
                name   TEXT DEFAULT '',
                config TEXT DEFAULT '{}'
            )
        """)
        sql.execute("""
            CREATE TABLE IF NOT EXISTS slopify_pending (
                id           INTEGER PRIMARY KEY AUTOINCREMENT,
                artist_id    INTEGER,
                request_data TEXT DEFAULT '',
                title        TEXT DEFAULT '',
                created_at   TEXT DEFAULT (datetime('now'))
            )
        """)
        sql.execute("""
            CREATE TABLE IF NOT EXISTS slopify_artist_songs (
                id        INTEGER PRIMARY KEY AUTOINCREMENT,
                artist_id INTEGER,
                name      TEXT DEFAULT '',
                config    TEXT DEFAULT '{}'
            )
        """)
        sql.execute("""
            CREATE TABLE IF NOT EXISTS slopify_playlists (
                id     INTEGER PRIMARY KEY AUTOINCREMENT,
                name   TEXT DEFAULT '',
                config TEXT DEFAULT '{}'
            )
        """)
        sql.execute("""
            CREATE TABLE IF NOT EXISTS slopify_playlist_tracks (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                playlist_id INTEGER NOT NULL,
                track_id    INTEGER NOT NULL,
                position    INTEGER DEFAULT 0
            )
        """)

        self.artist_collection.load()
        self.playlist_collection.load()
        self.track_queue.load()
        self._start_polling()

    def update_config(self):
        self.save_config()

    def save_config(self):
        """Persist workflow config to the selected artist."""
        artist_id = self.artist_collection.get_selected_item_id()
        if artist_id is None:
            return
        config = self.artist_config.get_config()
        name = config.get('Info', {}).get('name', 'Unnamed')
        sql.execute(
            "UPDATE slopify_artists SET name = ?, config = ?"
            " WHERE id = ?",
            (name, json.dumps(config), artist_id),
        )
        # Block selection signals to prevent artist_collection.load()
        # from triggering on_item_selected → full WorkflowSettings
        # reload (which resets splitter sizes and view position).
        with block_signals(
            self.artist_collection.table.selectionModel()
        ):
            self.artist_collection.load()
        self.track_queue.load()
        self._refresh_now_playing_metadata()

    def _refresh_now_playing_metadata(self):
        """Refresh now-playing title/artist/avatar from DB for current track."""
        if self.current_track_id is None:
            return
        row = sql.get_results(
            """
                SELECT t.title, COALESCE(a.name, ''), COALESCE(a.config, '{}')
                FROM slopify_tracks t
                LEFT JOIN slopify_artists a ON a.id = t.artist_id
                WHERE t.id = ?
            """,
            (self.current_track_id,),
        )
        if not row:
            return
        title, artist, config_json = row[0]
        avatar_path = self.TrackQueue._extract_avatar_path(config_json)
        self.player_controls.set_now_playing(
            title or '',
            artist or '',
            avatar_path or '',
        )

    # ------------------------------------------------------------------
    # Generation
    # ------------------------------------------------------------------

    def on_start_stop_clicked(self):
        """Toggle continuous generation on/off."""
        if self.is_generating:
            self.is_generating = False
            self._gen_timer.stop()
            self.track_queue.set_start_button(generating=False)
        else:
            self.is_generating = True
            self.track_queue.set_start_button(generating=True)
            self._generation_tick()
            self._gen_timer.start(2000)

    def _pick_artist_id(self):
        """Return the artist id to use for the next generation.

        Uses the track-queue filter combo: a specific artist if one is
        selected, otherwise a random artist from the database.
        """
        artist_id = self.track_queue.artist_filter.currentData()
        if artist_id is not None:
            return artist_id
        priority_ratio = (
            self.track_queue.priority_ratio_field.get_value() / 100
        )
        priority_count = sql.get_scalar(
            "SELECT COUNT(*) FROM slopify_artists WHERE b_prior > 0"
        )
        limit_results = math.ceil(priority_count * (1 / priority_ratio))
        # limit_results = int(priority_count * mult)

        rows = sql.get_results(f"""
            SELECT
                a.id,
                (SELECT COUNT(t.id)
                 FROM slopify_tracks t
                 WHERE t.artist_id = a.id) AS track_count,
                a.b_prior
            FROM slopify_artists a
            GROUP BY a.id
            ORDER BY b_prior DESC, track_count ASC
            LIMIT {limit_results}
        """)
        if not rows:
            return None
        return random.choice(rows)[0]

    def _load_artist_config(self, artist_id):
        """Load the full config dict for *artist_id* from the DB."""
        config_json = sql.get_scalar(
            "SELECT config FROM slopify_artists WHERE id = ?",
            (artist_id,), load_json=True,
        )
        config = config_json or {'_TYPE': 'audio'}
        if 'Generation' not in config:
            config = {'Info': {}, 'Generation': config}
        return config

    def _load_artist_metadata(self, artist_id):
        """Return artist (name, avatar_path) for *artist_id*."""
        row = sql.get_results(
            "SELECT name, config FROM slopify_artists WHERE id = ?",
            (artist_id,),
        )
        if not row:
            return '', ''
        name = row[0][0] or ''
        config_json = row[0][1] or '{}'
        avatar_path = ''
        try:
            config = json.loads(config_json) if isinstance(config_json, str) else config_json
            if isinstance(config, dict):
                info = config.get('Info', {}) or {}
                avatar_path = info.get('avatar_path', '') or config.get('avatar_path', '') or ''
        except Exception:
            avatar_path = ''
        return name, avatar_path

    def _generation_tick(self):
        """Spawn a generation task if a slot is free (QTimer callback)."""
        if not self.is_generating:
            self._gen_timer.stop()
            self.track_queue.set_start_button(generating=False)
            return
        if self._gen_running:
            return

        tq = self.track_queue
        concurrent = tq.concurrent_field.get_value()
        unplayed = len(tq.new_unplayed_track_ids)
        include_unplayed = tq.include_unplayed_field.get_value()
        if not include_unplayed:
            unplayed = 0

        in_flight = len(tq.pending_tracks)
        if in_flight + unplayed >= concurrent:
            return

        asyncio.ensure_future(self._generate_one())

    async def _generate_one(self):
        """Run a single track generation cycle."""
        self._gen_running = True
        try:
            await self._generate_one_inner()
        finally:
            self._gen_running = False
    
    def _get_random_song(self, artist_id, artist_name):
        """Get a random song from the database."""
        song_description = ""
        song_rows = sql.get_results("""
            SELECT artist_id, name, config
            FROM slopify_artist_songs
            WHERE artist_id != ?
                AND LOWER(name) NOT LIKE "%(live%"
                AND LOWER(name) NOT LIKE "%mix)%"
                AND LOWER(name) NOT LIKE "%(mix%"
                AND LOWER(name) NOT LIKE "%(demo%"
                AND LOWER(name) NOT LIKE "%demo)%"
                AND LOWER(name) NOT LIKE "%(acoustic%"
                AND LOWER(name) NOT LIKE "%acoustic)%"
                AND LOWER(name) NOT LIKE "%(instrumental%"
                AND LOWER(name) NOT LIKE "%instrumental)%"
                AND LOWER(name) NOT LIKE "%[live%"
                AND LOWER(name) NOT LIKE "%mix]%"
                AND LOWER(name) NOT LIKE "%[mix%"
                AND LOWER(name) NOT LIKE "%[demo%"
                AND LOWER(name) NOT LIKE "%demo]%"
                AND LOWER(name) NOT LIKE "%[acoustic%"
                AND LOWER(name) NOT LIKE "%acoustic]%"
                AND LOWER(name) NOT LIKE "%[instrumental%"
                AND LOWER(name) NOT LIKE "%instrumental]%"
        """, (artist_id,))
        cands = [(a_id, n, c) for a_id, n, c in (song_rows or []) if n]
        if not cands:
            raise Exception("No songs available")
        
        song_aid, song_name, song_config = random.choice(cands)
        song_artist_name = sql.get_scalar(
            "SELECT name FROM slopify_artists"
            " WHERE id = ?", (song_aid,))
        song_lyrics = json.loads(song_config).get('lyrics', '')
        if not song_lyrics:
            raise Exception("No lyrics available")
        
        song_description = f"A song by `{artist_name}`"
        song_name = f"{artist_name} - {song_name} - {song_artist_name}"
        return song_name, song_description, song_lyrics
        # print(f">> Generating for: `{artist_name}` cover of `{song_name}` by `{song_artist_name}`")

    async def _generate_one_inner(self):
        """Inner generation logic."""
        artist_id = self._pick_artist_id()
        if artist_id is None:
            display_message(message='No artists available')
            return

        full_config = self._load_artist_config(artist_id)
        config = full_config['Generation']
        params = full_config.get('Info', {})
        if 'name' in params:
            params['artist'] = params['name']

        pending_id = self._add_pending_track(artist_id)

        try:
            title = f'{params.get("artist", "")} - Untitled'
            cover_ratio = self.track_queue.cover_ratio_field.get_value() / 100
            if random.random() < cover_ratio:
                song_name, song_description, song_lyrics = self._get_random_song(artist_id, params.get('artist', ''))
                params['song_name'] = song_name
                params['song_desc'] = song_description
                params['lyrics'] = song_lyrics
                title = song_name

            from plugins.workflows.members.workflow import Workflow
            wf_config = merge_config_into_workflow_config(config)
            workflow = Workflow(
                main=self.main, config=wf_config,
                kind='SLOPIFY', params=params,
                tool_uuid=None, chat_title='')
            result = await compute_workflow_async(
                workflow=workflow)

            # name_member = next(
            #     (m for m in workflow.members.values()
            #      if m.config.get('name', '') == 'Name generator'),
            #     None)
            # if name_member:
            #     name_msg = next(
            #         (m for m in workflow.message_history.messages
            #          if m.member_id == name_member.member_id),
            #         None)
            #     if name_msg:
            #         title = name_msg.content

        except Exception as e:
            display_message(message=f"Workflow error: {e}")
            self._remove_pending_track(pending_id)
            return

        _, result_dict = try_parse_json(result)
        filepath = result_dict.get('filepath', None)

        if filepath:
            await self._complete_pending_track(
                pending_id, filepath, title)
            return

        request_id = result_dict.get('request_id', None)
        if not request_id:
            display_message(
                message="Workflow didn't return valid audio")
            self._remove_pending_track(pending_id)
            return

        result_dict['title'] = title
        print(f"Setting request data for track {pending_id}: {result_dict}")
        self._set_track_request_data(pending_id, result_dict)

    def _add_pending_track(self, artist_id):
        """Insert a placeholder into slopify_pending."""
        artist_name, avatar_path = self._load_artist_metadata(artist_id)
        sql.execute("""
            INSERT INTO slopify_pending
                (artist_id, request_data, title)
            VALUES (?, '', 'Generating...')
        """, (artist_id,))
        pending_id = sql.get_scalar(
            "SELECT MAX(id) FROM slopify_pending")
        self.track_queue.pending_tracks[pending_id] = {
            'id': pending_id,
            'artist_id': artist_id,
            'request_data': '',
            'title': 'Generating...',
            'artist': artist_name,
            'avatar_path': avatar_path,
        }
        self.track_queue._refresh()
        self.track_queue.table.scrollToBottom()
        return pending_id

    def _set_track_request_data(self, pending_id, result_dict):
        """Persist request_data once a request_id is available."""
        request_data = json.dumps(result_dict)
        sql.execute("""
            UPDATE slopify_pending SET request_data = ?
            WHERE id = ?
        """, (request_data, pending_id))
        t = self.track_queue.pending_tracks.get(pending_id)
        if t:
            t['request_data'] = request_data

    def _start_polling(self):
        """Clean up stuck pending tracks and start the poll timer."""
        if self._polling:
            return
        # Remove stale pending rows with no request_data
        sql.execute(
            "DELETE FROM slopify_pending"
            " WHERE request_data IS NULL OR request_data = ''")
        stale = [pid for pid, t
                 in self.track_queue.pending_tracks.items()
                 if not t.get('request_data')]
        for pid in stale:
            self.track_queue.pending_tracks.pop(pid, None)
        if stale:
            self.track_queue._refresh()
        self._polling = True
        self._poll_timer.start(3000)

    def _poll_tick(self):
        """Poll each pending track for completion (QTimer callback)."""
        for p_id, t in list(self.track_queue.pending_tracks.items()):
            _, request_dict = try_parse_json(
                t.get('request_data', ''))
            if not request_dict:
                continue

            request_id = request_dict.get('request_id', None)
            if not request_id:
                continue

            artist = t.get('artist', 'Unknown Artist')
            title = request_dict.get('title', 'Untitled')
            filename_without_ext = _safe_filename(
                f"{artist} - {title}")
            asyncio.ensure_future(
                self._poll_one(p_id, request_dict,
                               filename_without_ext, title))

    async def _poll_one(self, p_id, request_dict,
                        filename_without_ext, title):
        """Poll and download a single pending track."""
        try:
            filepath = await self._poll_and_download(
                p_id, request_dict, filename_without_ext)
        except Exception as e:
            print(f"Poll error: {e}")
            return
        if not filepath:
            return
        await self._complete_pending_track(p_id, filepath, title)

    async def _poll_and_download(self, p_id, request_dict, filename_without_ext):
        """Poll provider until request completes, then download and return filepath."""
        from gui import system

        request_id = request_dict['request_id']
        model_name = request_dict['model_name']
        provider_name = request_dict['provider']

        provider = system.manager.providers.get(provider_name)
        if not provider:
            display_message(
                message=f"Provider '{provider_name}' not found")
            return None

        # while True:
        try:
            status = await provider.get_request_status(
                model_name, request_id)
        except Exception as e:
            display_message(message=f"Poll error: {e}")
            return None

        s = status.get('status')
        if s == 'failed':
            display_message(message=f"Poll failed: {s}")
            self._remove_pending_track(p_id)
            # return None

        if s != 'completed':
            return None

        media_urls = await provider.get_request_result(
            model_name, request_id)
        if not media_urls:
            return None

        app_path = get_application_path()
        music_dir = os.path.join(app_path, 'music')
        os.makedirs(music_dir, exist_ok=True)

        return await download_url_to_file(
            media_urls[0], base_dir=music_dir, filename_without_ext=filename_without_ext
        )

    def _remove_pending_track(self, pending_id):
        """Remove a pending track that failed to complete."""
        sql.execute(
            "DELETE FROM slopify_pending WHERE id = ?",
            (pending_id,))
        self.track_queue.pending_tracks.pop(pending_id, None)
        self.track_queue._refresh()

    async def _complete_pending_track(self, pending_id, filepath, title=None):
        """Move a pending track to slopify_tracks on success."""
        duration_ms = 0
        if filepath.lower().endswith('.wav'):
            from utils.media import get_audio_file_duration
            duration_ms = await asyncio.to_thread(
                get_audio_file_duration, filepath)

        pending_track = self.track_queue.pending_tracks.get(
            pending_id)
        if not pending_track:
            return
        artist_id = pending_track['artist_id']
        artist_name = pending_track['artist']
        avatar_path = pending_track.get('avatar_path', '') or ''
        if not avatar_path:
            _, avatar_path = self._load_artist_metadata(artist_id)

        # Remove from pending
        sql.execute(
            "DELETE FROM slopify_pending WHERE id = ?",
            (pending_id,))
        self.track_queue.pending_tracks.pop(pending_id, None)

        # Insert into completed tracks
        sql.execute("""
            INSERT INTO slopify_tracks
                (filepath, title, duration_ms, artist_id)
            VALUES (?, ?, ?, ?)
        """, (filepath, title, duration_ms, artist_id))
        track_id = sql.get_scalar(
            "SELECT MAX(id) FROM slopify_tracks")
        self.track_queue.tracks.append({
            'id': track_id,
            'filepath': filepath,
            'title': title,
            'duration_ms': duration_ms,
            'artist_id': artist_id,
            'artist': artist_name,
            'avatar_path': avatar_path,
        })
        self.track_queue.new_unplayed_track_ids.append(track_id)
        self.track_queue._refresh()
        self.track_queue.table.scrollToBottom()

        # Auto-play if player is idle
        new_idx = len(self.track_queue.tracks) - 1
        if (self.current_track_index == -1
                or self.media_player.playbackState()
                == QMediaPlayer.StoppedState):
            self.play_track(new_idx)

    # ------------------------------------------------------------------
    # Track management
    # ------------------------------------------------------------------

    def _add_track(self, filepath, artist_id):
        """Insert a track into the DB + queue, auto-play if idle."""
        title = os.path.splitext(os.path.basename(filepath))[0]
        artist_name, avatar_path = self._load_artist_metadata(artist_id)

        duration_ms = 0
        if filepath.lower().endswith('.wav'):
            from utils.media import get_audio_file_duration
            duration_ms = get_audio_file_duration(filepath)

        sql.execute("""
            INSERT INTO slopify_tracks
                (filepath, title, duration_ms, artist_id)
            VALUES (?, ?, ?, ?)
        """, (filepath, title, duration_ms, artist_id))
        track_id = sql.get_scalar("SELECT MAX(id) FROM slopify_tracks")

        self.track_queue.tracks.append({
            'id': track_id,
            'filepath': filepath,
            'title': title,
            'duration_ms': duration_ms,
            'artist_id': artist_id,
            'artist': artist_name,
            'avatar_path': avatar_path,
        })
        self.track_queue._refresh()
        self.track_queue.table.scrollToBottom()

        # if self.current_track_index == -1:
        #     self.play_track(position)

    # ------------------------------------------------------------------
    # Playback
    # ------------------------------------------------------------------

    def play_track(self, index):
        """Start playing the track at *index*."""
        if not (0 <= index < len(self.track_queue.tracks)):
            return
        track = self.track_queue.tracks[index]
        filepath = track['filepath']
        if not os.path.isfile(filepath):
            return

        self.current_track_index = index
        tid = track['id']
        self.current_track_id = tid
        self.track_queue.new_unplayed_track_ids = [
            i for i in self.track_queue.new_unplayed_track_ids
            if i > tid]
        self.media_player.setSource(QUrl.fromLocalFile(filepath))
        self.media_player.play()
        self.player_controls.set_playing(True)
        self.player_controls.set_now_playing(
            track.get('title', ''),
            track.get('artist', ''),
            track.get('avatar_path', ''))
        self.track_queue._refresh()
        self.track_queue.highlight_track(index)

    def play_next(self):
        next_idx = self.current_track_index + 1
        if next_idx < len(self.track_queue.tracks):
            self.play_track(next_idx)

    def play_prev(self):
        if self.current_track_index > 0:
            self.play_track(self.current_track_index - 1)

    def toggle_play_pause(self):
        state = self.media_player.playbackState()
        if state == QMediaPlayer.PlayingState:
            self.media_player.pause()
            self.player_controls.set_playing(False)
        elif self.current_track_index >= 0:
            self.media_player.play()
            self.player_controls.set_playing(True)
        elif self.track_queue.tracks:
            self.play_track(0)

    def stop_playback(self):
        """Stop the player and reset state."""
        self.media_player.stop()
        self.current_track_index = -1
        self.current_track_id = None
        self.player_controls.set_playing(False)
        self.player_controls.clear_now_playing()
        self.player_controls.on_position_changed(0)
        self.player_controls.on_duration_changed(0)
        self.track_queue._refresh()

    # ------------------------------------------------------------------
    # Media player callbacks
    # ------------------------------------------------------------------

    def _on_media_status_changed(self, status):
        if status == QMediaPlayer.EndOfMedia:
            self.player_controls.set_playing(False)
            next_idx = self.current_track_index + 1
            if next_idx < len(self.track_queue.tracks):
                self.play_track(next_idx)

    def _update_track_duration(self, ms):
        """Backfill duration for non-WAV tracks once the player knows it."""
        if ms <= 0 or self.current_track_index < 0:
            return
        track = self.track_queue.tracks[self.current_track_index]
        if track.get('duration_ms', 0) == 0:
            track['duration_ms'] = ms
            sql.execute(
                "UPDATE slopify_tracks SET duration_ms = ? WHERE id = ?",
                (ms, track['id']))
            self.track_queue._refresh()

    # ------------------------------------------------------------------
    # Nested widgets
    # ------------------------------------------------------------------

    class ArtistConfigWidget(ConfigTabs):
        """Tabbed config for an artist: Info metadata + Generation workflow."""

        def __init__(self, parent):
            self.info_tab = self.InfoTab(parent=parent)
            self.songs_tab = self.SongsTab(parent=parent)
            self.chattable_workflow = self.SlopifyChattableWorkflow(
                parent=parent)

            super().__init__(
                parent=parent,
                pages={
                    'Info': self.info_tab,
                    'Songs': self.songs_tab,
                    'Generation': self.chattable_workflow,
                },
            )

        def load_config(self, config=None):
            """Load config split by tab-name keys.

            Backward compat: if 'Generation' key is absent, treat
            the whole dict as legacy workflow config.
            """
            if config and 'Generation' not in config:
                config = {'Info': {}, 'Generation': config}
            config = config or {'Info': {}, 'Generation': {}}
            self.info_tab.load_config(config.get('Info', {}))
            self.chattable_workflow.workflow_settings.load_config(
                config.get('Generation', {}))
            # Set artist_id for songs tab
            p = self.parent
            while p and not isinstance(p, Page_Slopify):
                p = getattr(p, 'parent', None)
            if p:
                self.songs_tab.artist_id = (
                    p.artist_collection.get_selected_item_id())

        def get_config(self):
            """Return config nested under tab-name keys."""
            return {
                'Info': self.info_tab.get_config(),
                'Generation': self.chattable_workflow.get_config(),
            }

        def load(self):
            """Load all tabs, not just the current one."""
            self.info_tab.load()
            self.songs_tab.load()
            self.chattable_workflow.load()

        class SongsTab(ConfigTable):
            """Artist songs synced from Genius, with lyrics config."""

            def __init__(self, parent):
                super().__init__(
                    parent=parent,
                    schema=[
                        {'text': 'ID', 'key': 'id', 'visible': False},
                        {'text': 'Songs', 'key': 'name', 'stretch': True},
                    ],
                    table_name='slopify_artist_songs',
                    query=(
                        "SELECT id, name FROM slopify_artist_songs"
                        " WHERE artist_id = ? ORDER BY name"
                    ),
                    query_params=[lambda: self.artist_id],
                    layout_type='horizontal',
                    config_widget=self.SongConfig(parent=self),
                    show_table_buttons=False,
                )
                self.artist_id = None
                self.table.horizontalHeader().setVisible(False)

                btn_sync = QPushButton('Sync from Genius')
                btn_sync.setFixedHeight(25)
                btn_sync.clicked.connect(lambda: self.sync_songs())
                self.table_layout.insertWidget(0, btn_sync)

            class SongConfig(ConfigFields):
                """Lyrics editor for a single song."""

                def __init__(self, parent):
                    super().__init__(
                        parent=parent,
                        schema=[
                            {
                                'text': 'Lyrics',
                                'key': 'lyrics',
                                'type': str,
                                'num_lines': 15,
                                'stretch_x': True,
                                'stretch_y': True,
                                'wrap_text': True,
                                'default': '',
                                'label_position': None,
                            },
                        ],
                    )

            @qasync.asyncSlot()
            async def sync_songs(self):
                """Fetch all songs for the artist from Genius."""
                if self.artist_id is None:
                    display_message(message='No artist selected')
                    return
                p = self.parent
                while p and not isinstance(p, Page_Slopify):
                    p = getattr(p, 'parent', None)
                if not p:
                    return
                artist_name = p.artist_config.info_tab.get_config().get(
                    'name', '')
                if not artist_name or artist_name == 'Unnamed':
                    display_message(message='Artist has no name set')
                    return
                count = sync_artist_songs(
                    self.artist_id, artist_name)
                if not count:
                    display_message(message='No songs found')
                    return
                self.load()
                display_message(
                    message=f'Synced {len(songs)} songs')

        class SlopifyChattableWorkflow(ChattableWorkflowWidget):
            """Chattable workflow for Slopify artist generation.

            Hides message history and attachment bar, overrides
            config propagation to save to slopify_artists, lazily
            creates a context on send, and extracts audio results
            after each manual run to push into the track queue.
            """

            def __init__(self, parent, **kwargs):
                super().__init__(parent=parent, **kwargs)
                self.attachment_bar.hide()
                self.message_collection.hide()

            def update_config(self):
                """Propagate config up to Page_Slopify.save_config()."""
                page = find_main()
                if page is None:
                    return
                # Walk up to the Page_Slopify instance
                p = self.parent
                while p and not isinstance(p, Page_Slopify):
                    p = getattr(p, 'parent', None)
                if p:
                    p.save_config()
                # Sync workflow_settings config with current visual
                # state so a subsequent load() rebuilds correctly.
                config = self.workflow_settings.get_config()
                self.workflow_settings.load_config(config)
                self.input_widget.load()

            def load_config(self, json_config=None):
                """Load config directly into workflow_settings.

                Avoids creating a DB context row on every artist
                selection switch.
                """
                self.workflow_settings.load_config(json_config or {})

            def get_config(self):
                return self.workflow_settings.get_config()

            def load(self):
                """Load workflow_settings only (no DB context)."""
                self.workflow_settings.load()
                self.input_widget.load()

            @qasync.asyncSlot()
            async def on_send_message(self, restore_scroll_pos=None):
                """Lazily create a context, inject artist Info as
                workflow params, then run the workflow."""
                if self.workflow and self.workflow.responding:
                    self.workflow.behaviour.stop()
                    return

                # Get artist Info config for workflow params
                p = self.parent
                while p and not isinstance(p, Page_Slopify):
                    p = getattr(p, 'parent', None)
                if not p:
                    return

                artist_config = p.artist_config
                info_params = artist_config.info_tab.get_config()
                gen_config = self.workflow_settings.get_config()

                # Lazily create a context + workflow
                self.new_context(config=gen_config, kind='SLOPIFY')

                # Inject artist info as workflow params
                if self.workflow:
                    self.workflow.params = info_params

                # Run from next expected member
                next_member = self.workflow.next_expected_member()
                if not next_member:
                    return
                await self.run_workflow_async(
                    from_member_id=next_member.member_id)

            def end_turn(self):
                """Extract audio results from message history and
                push them to the track queue, then reset."""
                super().end_turn()

                if not self.workflow:
                    return

                p = self.parent
                while p and not isinstance(p, Page_Slopify):
                    p = getattr(p, 'parent', None)
                if not p:
                    return

                # Scan messages for audio results
                title = 'Untitled'
                filepath = None
                request_id = None
                result_dict = {}

                for msg in self.workflow.message_history.messages:
                    # Check for name generator output
                    member = self.workflow.members.get(
                        str(msg.member_id))
                    if member and member.config.get(
                            'name', '') == 'Name generator':
                        title = msg.content or title

                    # Check for audio result JSON
                    _, parsed = try_parse_json(msg.content)
                    if parsed:
                        if parsed.get('filepath'):
                            filepath = parsed['filepath']
                            result_dict = parsed
                        elif parsed.get('request_id'):
                            request_id = parsed['request_id']
                            result_dict = parsed

                if not filepath and not request_id:
                    return

                # Get artist id
                artist_id = p.artist_collection \
                    .get_selected_item_id()
                if artist_id is None:
                    return

                if filepath:
                    # Completed immediately - add to tracks
                    pending_id = p._add_pending_track(artist_id)
                    asyncio.ensure_future(
                        p._complete_pending_track(
                            pending_id, filepath, title))
                elif request_id:
                    # Needs polling - add as pending
                    pending_id = p._add_pending_track(artist_id)
                    result_dict['title'] = title
                    p._set_track_request_data(
                        pending_id, result_dict)

        class InfoTab(ConfigJoined):
            """Artist metadata fields grouped into top section + detail tabs."""

            def __init__(self, parent):
                super().__init__(
                    parent=parent,
                    widgets=[
                        self.TopFields(parent=self),
                        self.DetailTabs(parent=self),
                    ],
                )

            class TopFields(ConfigFields):
                def __init__(self, parent):
                    super().__init__(
                        parent=parent,
                        schema=[
                            {
                                'text': 'Avatar',
                                'key': 'avatar_path',
                                'type': 'image',
                                'diameter': 50,
                                'width': 50,
                                'circular': False,
                                'border': False,
                                'default': '',
                                'label_position': None,
                                'row_key': 0,
                            },
                            {
                                'text': 'Name',
                                'key': 'name',
                                'type': str,
                                'default': 'Unnamed',
                                'text_size': 14,
                                'label_position': None,
                                'transparent': True,
                                'row_key': 0,
                            },
                            {
                                'type': 'stretch',
                                'text': '',
                            },
                            {
                                'text': 'Genre',
                                'key': 'genre',
                                'type': str,
                                'default': '',
                                'has_toggle': True,
                                'label_width': 100,
                            },
                            {
                                'text': 'Language',
                                'key': 'language',
                                'type': str,
                                'default': '',
                                'has_toggle': True,
                                'label_width': 100,
                            },
                        ],
                    )

            class DetailTabs(ConfigTabs):
                stretch = 1

                def __init__(self, parent):
                    super().__init__(
                        parent=parent,
                        pages={
                            'Lyrical': self.LyricalTab(parent=self),
                            'Tone': self.ToneTab(parent=self),
                            'Imagery': self.ImageryTab(parent=self),
                            'Musical': self.MusicalTab(parent=self),
                        },
                    )

                class LyricalTab(ConfigFields):
                    def __init__(self, parent):
                        super().__init__(
                            parent=parent,
                            schema=[
                                {
                                    'text': 'Writing style',
                                    'key': 'writing_style',
                                    'type': str,
                                    'num_lines': 2,
                                    'stretch_x': True,
                                    'stretch_y': True,
                                    'wrap_text': True,
                                    'default': '',
                                    'label_position': 'top',
                                    'has_toggle': True,
                                    'row_key': 1,
                                },
                                {
                                    'text': 'Pacing',
                                    'key': 'pacing',
                                    'type': str,
                                    'num_lines': 2,
                                    'stretch_x': True,
                                    'stretch_y': True,
                                    'wrap_text': True,
                                    'default': '',
                                    'label_position': 'top',
                                    'has_toggle': True,
                                    'row_key': 1,
                                },
                                {
                                    'text': 'Topic',
                                    'key': 'topic',
                                    'type': str,
                                    'default': '',
                                    'label_width': 130,
                                    'has_toggle': True,
                                },
                                {
                                    'text': 'Rhyme scheme',
                                    'key': 'rhyme_scheme',
                                    'type': (
                                        'AABB',
                                        'ABAB',
                                        'ABCB',
                                        'Free Verse',
                                        'Mixed',
                                    ),
                                    'default': 'ABAB',
                                    'label_width': 130,
                                    'has_toggle': True,
                                    'row_key': 2,
                                },
                                {
                                    'text': 'Perspective',
                                    'key': 'perspective',
                                    'type': (
                                        'First Person',
                                        'Second Person',
                                        'Third Person',
                                        'Omniscient',
                                        'Mixed',
                                    ),
                                    'default': 'First Person',
                                    'label_width': 130,
                                    'has_toggle': True,
                                    'row_key': 2,
                                },
                                {
                                    'text': 'Tense',
                                    'key': 'tense',
                                    'type': (
                                        'Past',
                                        'Present',
                                        'Future',
                                        'Mixed',
                                    ),
                                    'default': 'Present',
                                    'label_width': 130,
                                    'has_toggle': True,
                                    'row_key': 3,
                                },
                                {
                                    'text': 'Vocabulary',
                                    'key': 'vocabulary',
                                    'type': (
                                        'Simple',
                                        'Conversational',
                                        'Poetic',
                                        'Academic',
                                        'Slang',
                                    ),
                                    'default': 'Conversational',
                                    'label_width': 130,
                                    'has_toggle': True,
                                    'row_key': 3,
                                },
                                {
                                    'text': 'Storytelling',
                                    'key': 'storytelling',
                                    'type': (
                                        'Abstract',
                                        'Narrative',
                                        'Conversational',
                                        'Stream of Consciousness',
                                        'Poetic',
                                    ),
                                    'default': 'Narrative',
                                    'has_toggle': True,
                                    'label_width': 130,
                                },
                            ],
                        )

                class ToneTab(ConfigFields):
                    def __init__(self, parent):
                        super().__init__(
                            parent=parent,
                            schema=[
                                {
                                    'text': 'Mood',
                                    'key': 'mood',
                                    'type': (
                                        'Euphoric',
                                        'Melancholic',
                                        'Aggressive',
                                        'Dreamy',
                                        'Nostalgic',
                                        'Anxious',
                                        'Serene',
                                        'Defiant',
                                        'Playful',
                                        'Haunting',
                                    ),
                                    'default': 'Dreamy',
                                    'label_width': 130,
                                },
                                {
                                    'text': 'Emotional arc',
                                    'key': 'emotional_arc',
                                    'type': str,
                                    'default': '',
                                    'label_width': 130,
                                },
                                {
                                    'text': 'Profanity',
                                    'key': 'profanity',
                                    'type': (
                                        'None',
                                        'Mild',
                                        'Moderate',
                                        'Heavy',
                                    ),
                                    'default': 'None',
                                    'label_width': 130,
                                },
                                {
                                    'text': 'Controversy',
                                    'key': 'controversy',
                                    'type': int,
                                    'style': 'slider',
                                    'minimum': 0,
                                    'maximum': 100,
                                    'default': 25,
                                    'left_label': 'Safe',
                                    'right_label': 'Edgy',
                                    'label_width': 130,
                                },
                            ],
                        )

                class ImageryTab(ConfigFields):
                    def __init__(self, parent):
                        super().__init__(
                            parent=parent,
                            schema=[
                                {
                                    'text': 'Imagery',
                                    'key': 'imagery',
                                    'type': (
                                        'Nature',
                                        'Urban',
                                        'Cosmic',
                                        'Domestic',
                                        'Surreal',
                                        'Industrial',
                                    ),
                                    'default': 'Nature',
                                    'label_width': 130,
                                },
                                {
                                    'text': 'Figurative lang.',
                                    'key': 'figurative_language',
                                    'type': int,
                                    'style': 'slider',
                                    'minimum': 0,
                                    'maximum': 100,
                                    'default': 50,
                                    'left_label': 'Literal',
                                    'right_label': 'Metaphorical',
                                    'label_width': 130,
                                },
                                {
                                    'text': 'Repetition',
                                    'key': 'repetition',
                                    'type': int,
                                    'style': 'slider',
                                    'minimum': 0,
                                    'maximum': 100,
                                    'default': 50,
                                    'left_label': 'Minimal',
                                    'right_label': 'Heavy hooks',
                                    'label_width': 130,
                                },
                                {
                                    'text': 'Complexity',
                                    'key': 'complexity',
                                    'type': int,
                                    'style': 'slider',
                                    'minimum': 0,
                                    'maximum': 100,
                                    'default': 50,
                                    'left_label': 'Simple',
                                    'right_label': 'Intricate',
                                    'label_width': 130,
                                },
                                {
                                    'text': 'Theme keywords',
                                    'key': 'theme_keywords',
                                    'type': str,
                                    'default': '',
                                    'label_width': 130,
                                },
                                {
                                    'text': 'Cultural refs',
                                    'key': 'cultural_references',
                                    'type': str,
                                    'default': '',
                                    'label_width': 130,
                                },
                            ],
                        )

                class MusicalTab(ConfigFields):
                    def __init__(self, parent):
                        super().__init__(
                            parent=parent,
                            schema=[
                                {
                                    'text': 'Tempo',
                                    'key': 'tempo',
                                    'type': (
                                        'Slow',
                                        'Mid-tempo',
                                        'Fast',
                                        'Variable',
                                    ),
                                    'default': 'Mid-tempo',
                                    'label_width': 130,
                                    'row_key': 4,
                                },
                                {
                                    'text': 'Production',
                                    'key': 'production_style',
                                    'type': (
                                        'Lo-fi',
                                        'Polished',
                                        'Raw',
                                        'Ambient',
                                        'Orchestral',
                                        'Minimalist',
                                    ),
                                    'default': 'Polished',
                                    'label_width': 130,
                                    'row_key': 4,
                                },
                                {
                                    'text': 'Energy',
                                    'key': 'energy',
                                    'type': int,
                                    'style': 'slider',
                                    'minimum': 0,
                                    'maximum': 100,
                                    'default': 50,
                                    'left_label': 'Chill',
                                    'right_label': 'Intense',
                                    'label_width': 130,
                                },
                                {
                                    'text': 'Vocal tone',
                                    'key': 'vocal_tone',
                                    'type': str,
                                    'default': '',
                                    'label_width': 130,
                                },
                                {
                                    'text': 'Key / scale',
                                    'key': 'key_scale',
                                    'type': (
                                        'Major',
                                        'Minor',
                                        'Modal',
                                        'Chromatic',
                                        'No Preference',
                                    ),
                                    'default': 'No Preference',
                                    'label_width': 130,
                                    'row_key': 5,
                                },
                                {
                                    'text': 'Structure',
                                    'key': 'song_structure',
                                    'type': (
                                        'Verse-Chorus',
                                        'AABA',
                                        'Through-Composed',
                                        'Freeform',
                                        'Epic',
                                    ),
                                    'default': 'Verse-Chorus',
                                    'label_width': 130,
                                    'row_key': 5,
                                },
                                {
                                    'text': 'Instrumentation',
                                    'key': 'instrumentation',
                                    'type': str,
                                    'num_lines': 2,
                                    'wrap_text': True,
                                    'default': '',
                                    'label_position': 'top',
                                    'row_key': 6,
                                },
                                {
                                    'text': 'Era influence',
                                    'key': 'era_influence',
                                    'type': str,
                                    'num_lines': 2,
                                    'wrap_text': True,
                                    'default': '',
                                    'label_position': 'top',
                                    'row_key': 6,
                                },
                            ],
                        )

    class ArtistCollection(ConfigTable):
        """Artist presets with workflow config per artist."""

        def __init__(self, parent):
            super().__init__(
                parent=parent,
                schema=[
                    {'text': 'ID', 'key': 'id', 'visible': False},
                    {'text': 'Artists', 'key': 'name', 'stretch': True},
                    {'text': 'Priority', 'key': 'b_prior', 'visible': False},
                ],
                layout_type='horizontal',
                config_widget=parent.artist_config,
                show_table_buttons=True,
                extra_tree_buttons=[
                    {
                        'text': 'Priority',
                        'icon_path': ':/resources/icon-pin-on.png',
                        'target': self.toggle_priority,
                    },
                    {
                        'text': 'Insert artists',
                        'icon_path': ':/resources/icon-pull.png',
                        'target': self.insert_artists,
                    },
                ],
            )
            self.table.horizontalHeader().setVisible(False)

        def load(self):
            rows = sql.get_results(
                "SELECT id, name, b_prior"
                " FROM slopify_artists ORDER BY name",
            )
            data = rows or []
            self.table.load(data, schema=self.schema)

            from gui.style import ACCENT_COLOR_1
            for row_idx, row in enumerate(data):
                if row[2]:
                    self.table.model._foreground_colors[row_idx] = \
                        QColor(ACCENT_COLOR_1)

        def on_item_selected(self):
            artist_id = self.get_selected_item_id()
            if artist_id is None:
                return
            row = sql.get_results(
                "SELECT name, config FROM slopify_artists"
                " WHERE id = ?",
                (artist_id,),
            )
            if not row:
                return
            name = row[0][0]
            config_json = row[0][1]
            config = json.loads(config_json) \
                if config_json else {'_TYPE': 'audio'}
            if 'Info' not in config:
                config = {'Info': {}, 'Generation': config}
            config['Info']['name'] = name
            self.parent.artist_config.load_config(config)
            self.parent.artist_config.load()

        def add_item(self):
            name, ok = QInputDialog.getText(
                self, 'New Artist', 'Artist name:')
            if not ok or not name.strip():
                return
            page = self.parent
            # get config of block called 'Song gen'
            from gui import system  # todo clean
            song_gen_block = system.manager.blocks.get('song_gen')
            if not song_gen_block:
                display_message(message='Song gen block not found')
                return
            song_gen_block['name'] = name.strip()
            config = {
                'Info': {},
                'Generation': song_gen_block,
            }
            sql.execute("""
                INSERT INTO slopify_artists (name, config)
                VALUES (?, ?)
            """, (name.strip(), json.dumps(config)))
            self.load()
            page.track_queue.load_artist_filter()

        def delete_item(self):
            artist_id = self.get_selected_item_id()
            if artist_id is None:
                return
            ret = display_message_box(
                icon=QMessageBox.Warning,
                text='Delete selected artist?',
                title='Delete Artist',
                buttons=QMessageBox.Yes | QMessageBox.No,
            )
            if ret != QMessageBox.Yes:
                return
            sql.execute(
                "DELETE FROM slopify_artists WHERE id = ?",
                (artist_id,),
            )
            self.load()
            self.parent.track_queue.load_artist_filter()

        def on_context_menu(self, menu):
            menu.addSeparator()
            btn_priority = menu.addAction('Priority')
            btn_priority.triggered.connect(self.toggle_priority)

        def toggle_priority(self):
            item_ids = self.get_selected_item_ids()
            if not item_ids:
                return
            placeholders = ','.join('?' * len(item_ids))
            sql.execute(
                "UPDATE slopify_artists"
                f" SET b_prior = NOT b_prior WHERE id IN ({placeholders})",
                tuple(item_ids),
            )
            self.load()

        def insert_artists(self):
            """Bulk-insert artists from a predefined list, skipping duplicates."""
            artist_names = [
                "2Pac", "50 Cent", "A Tribe Called Quest", "A$AP Rocky", "ABBA", "AC/DC", "Adele", "Aerosmith", "Akon", "Al Green", "Alanis Morissette", "Alice Cooper", "Alicia Keys", "Amber Lily", "Amy Winehouse", "Annie Lennox", "Arctic Monkeys", "Aretha Franklin", "Ariana Grande", "Avril Lavigne", "B.B. King", "BTS", "Backstreet Boys", "Bad Bunny", "Barbra Streisand", "Barry White", "Beck", "Ben E. King", "Ben Howard", "Benny Blanco", "Beyoncé", "Biffy Clyro", "Biggie Smalls", "Bill Withers", "Billie Eilish", "Billy Joel", "Björk", "Black Sabbath", "Blackpink", "Blink-182", "Blur", "Bob Dylan", "Bob Marley", "Bobby Alu", "Bon Jovi", "Boyz II Men", "Bring Me The Horizon", "Britney Spears", "Bruce Springsteen", "Bruno Mars", "Bryan Adams", "Busta Rhymes", "Calvin Harris", "Cardi B", "Carly Rae Jepsen", "Celine Dion", "Chance the Rapper", "Chase & Status", "Cher", "Chris Brown", "Christina Aguilera", "Cliff Richard", "Coldplay", "Colt Montgomery", "DMX", "Daddy Yankee", "Daft Punk", 
                "David Bowie", "David Guetta", "De La Soul", "Deep Purple", "Dermot Kennedy", "Destiny’s Child", "Diana Ross", "Dire Straits", "Doja Cat", "Dolly Parton", "Dr. Dre", "Drake", "Dua Lipa", "Duran Duran", "Eagles", "Eazy-E", "Ed Sheeran", "Ellie Goulding", "Elton John", "Elvis Presley", "Eminem", "Enrique Iglesias", "Estelle", "Eurythmics", "Evanescence", "Fall Out Boy", "Fatboy Slim", "Fleetwood Mac", "Florence + The Machine", "Foo Fighters", "Frank Ocean", "Frank Sinatra", "Fugees", "Future", "Gabrielle", "George Ezra", "George Michael", "Girls Aloud", "Gorillaz", "Green Day", "Guns N' Roses", "Gwen Stefani", "Halsey", "Harry Styles", "Ice Cube", "Iggy Azalea", "Imagine Dragons", "Iron Maiden", "J Balvin", "Jack Johnson", "James Bay", "Jamiroquai", "Janet Jackson", "Jason Derulo", "Jay-Z", "Jeff Buckley", "Jennifer Lopez", "Jess Glynne", "Jessie J", "Jimi Hendrix", "Joe Cocker", "John Legend", "John Mayer", "Johnny Cash", "Jorja Smith", "Joy Division", "Juice WRLD", 
                "Justin Bieber", "Justin Timberlake", "KISS", "Kaiser Chiefs", "Kano", "Kanye West", "Karol G", "Kasabian", "Katy Perry", "Kendrick Lamar", "Kid Cudi", "Kings of Leon", "Kylie Minogue", "LVDY", "Labrinth", "Lady Gaga", "Lana Del Rey", "Led Zeppelin", "Lenny Kravitz", "Lewis Capaldi", "Lil Wayne", "Limp Bizkit", "Linkin Park", "Lionel Richie", "Loyle Carner", "Ludacris", "Luther Vandross", "M.I.A.", "MEGA", "Machine Gun Kelly", "Macklemore", "Madonna", "Malka Russell", "Mariah Carey", "Maroon 5", "Marvin Gaye", "Massive Attack", "Meat Loaf", "Metallica", "Michael Jackson", "Mika", "Miley Cyrus", "Missy Elliott", "Morrissey", "Mumford & Sons", "Muse", "My Chemical Romance", "Naughty Boy", "Nelly", "New Order", "Nicki Minaj", "Nirvana", "Norah Jones", "Oasis", "Olivia Rodrigo", "One Direction", "OneRepublic", "Otis Sterling", "Outkast", "Ozzy Osbourne", "P!nk", "Paloma Faith", "Panic! At The Disco", "Paramore", "Passenger", "Pearl Jam", "Pet Shop Boys", "Pharrell Williams", 
                "Phil Collins", "Pink Floyd", "Pitbull", "Post Malone", "Prince", "Queen", "Radiohead", "Rag'n'Bone Man", "Ray Charles", "Red Hot Chili Peppers", "Rick Astley", "Rihanna", "Rita Ora", "Robbie Williams", "Rod Stewart", "Run-D.M.C.", "SF", "SZA", "Sabrina Carpenter", "Sam Garrett", "Sam Smith", "Satsang", "Sean Paul", "Selena Gomez", "Sex Pistols", "Shakira", "Shania Twain", "Shawn Mendes", "Sheryl Crow", "Simple Minds", "Skrillex", "Sleaford Mods", "Snoop Dogg", "Snow Patrol", "Spice Girls", "Stevie Nicks", "Stevie Wonder", "Stormzy", "Stray Kids", "Sugababes", "TLC", "Take That", "Talking Heads", "Tammi Terrell", "Taylor Swift", "The Beach Boys", "The Beatles", "The Black Eyed Peas", "The Charlatans", "The Chemical Brothers", "The Cranberries", "The Cure", "The Doors", "The Killers", "The Kinks", "The Libertines", "The Lumineers", "The Notorious B.I.G.", "The Offspring", "The Police", "The Prodigy", "The Rolling Stones", "The Script", "The Smiths", "The Stone Roses", 
                "The Stooges", "The Streets", "The Supremes", "The Weeknd", "The Who", "Tina Turner", "Tom Jones", "Toto", "Travis Scott", "Tupac Shakur", "Tyler, The Creator", "U2", "Usher", "Van Morrison", "Westlife", "Wham!", "Whitney Houston", "Will Smith", "Wu-Tang Clan"]
            
            existing = sql.get_results(
                "SELECT name FROM slopify_artists",
                return_type='list',
            )

            to_insert = [name for name in artist_names if name not in existing]
            if len(to_insert) == 0:
                display_message(message='All provided artists already exist')
                return
            
            ret = display_message_box(
                icon=QMessageBox.Question,
                    text=f'Download {len(to_insert)} artists?\n'
                        f'(existing names will be skipped)',
                title='Download Artists',
                buttons=QMessageBox.Yes | QMessageBox.No,
            )
            if ret != QMessageBox.Yes:
                return

            from gui import system
            song_gen_block = system.manager.blocks.get('song_gen')
            if not song_gen_block:
                display_message(message='Song gen block not found')
                return

            for name in to_insert:
                block = dict(song_gen_block)
                block['name'] = name
                config = {
                    'Info': {},
                    'Generation': block,
                }
                sql.execute(
                    "INSERT INTO slopify_artists (name, config)"
                    " VALUES (?, ?)",
                    (name, json.dumps(config)),
                )

            self.load()
            self.parent.track_queue.load_artist_filter()

    class PlaylistTrackList(ConfigTable):
        """Tracks belonging to the selected playlist."""

        def __init__(self, parent):
            super().__init__(
                parent=parent,
                schema=[
                    {'text': 'ID', 'key': 'id', 'visible': False},
                    {'text': 'Title', 'key': 'title', 'stretch': True},
                    {'text': 'Artist', 'key': 'artist', 'width': 150},
                    {'text': 'Duration', 'key': 'duration', 'width': 60},
                ],
                show_table_buttons=True,
            )
            self.playlist_id = None
            self.table.horizontalHeader().setVisible(False)

        def load(self):
            if self.playlist_id is None:
                self.table.load([], schema=self.schema)
                return
            rows = sql.get_results("""
                SELECT pt.id, COALESCE(t.title, ''),
                       COALESCE(a.name, ''), t.duration_ms
                FROM slopify_playlist_tracks pt
                LEFT JOIN slopify_tracks t ON t.id = pt.track_id
                LEFT JOIN slopify_artists a ON a.id = t.artist_id
                WHERE pt.playlist_id = ?
                ORDER BY pt.position
            """, (self.playlist_id,))
            data = [
                (r[0], r[1], r[2], _fmt(r[3] or 0))
                for r in (rows or [])
            ]
            self.table.load(data, schema=self.schema)

        def on_item_selected(self):
            pass

        def add_item(self):
            pass

        def delete_item(self):
            row_id = self.get_selected_item_id()
            if row_id is None:
                return
            sql.execute(
                "DELETE FROM slopify_playlist_tracks WHERE id = ?",
                (row_id,),
            )
            self.load()

    class PlaylistCollection(ConfigTable):
        """List of user playlists."""

        def __init__(self, parent):
            super().__init__(
                parent=parent,
                schema=[
                    {'text': 'ID', 'key': 'id', 'visible': False},
                    {
                        'text': 'Playlists', 'key': 'name',
                        'stretch': True,
                    },
                ],
                layout_type='horizontal',
                config_widget=parent.playlist_track_list,
                show_table_buttons=True,
            )
            self.table.horizontalHeader().setVisible(False)

        def load(self):
            rows = sql.get_results(
                "SELECT id, name FROM slopify_playlists ORDER BY id",
            )
            self.table.load(rows or [], schema=self.schema)

        def on_item_selected(self):
            playlist_id = self.get_selected_item_id()
            if playlist_id is None:
                return
            self.parent.playlist_track_list.playlist_id = playlist_id
            self.parent.playlist_track_list.load()

        def add_item(self):
            name, ok = QInputDialog.getText(
                self, 'New Playlist', 'Playlist name:')
            if not ok or not name.strip():
                return
            sql.execute(
                "INSERT INTO slopify_playlists (name) VALUES (?)",
                (name.strip(),),
            )
            self.load()

        def delete_item(self):
            playlist_id = self.get_selected_item_id()
            if playlist_id is None:
                return
            sql.execute(
                "DELETE FROM slopify_playlist_tracks"
                " WHERE playlist_id = ?",
                (playlist_id,),
            )
            sql.execute(
                "DELETE FROM slopify_playlists WHERE id = ?",
                (playlist_id,),
            )
            self.parent.playlist_track_list.playlist_id = None
            self.parent.playlist_track_list.load()
            self.load()

    class PlayerControls(QWidget):
        """Fixed-height transport bar: prev/play/next, progress, volume."""

        def __init__(self, parent):
            super().__init__(parent)
            self.parent = parent
            self.setFixedHeight(80)

            from gui.style import TEXT_COLOR
            from utils.helpers import apply_alpha_to_hex

            self.layout = CHBoxLayout(self)

            self.btn_prev = IconButton(
                parent=self,
                icon_path=':/resources/icon-prev-track.png',
                size=25,
                tooltip='Previous',
                target=lambda: parent.play_prev(),
            )
            self.btn_play = IconButton(
                parent=self,
                icon_path=':/resources/icon-play.png',
                size=45,
                tooltip='Play',
                target=lambda: parent.toggle_play_pause(),
            )
            self.btn_next = IconButton(
                parent=self,
                icon_path=':/resources/icon-next-track.png',
                size=25,
                tooltip='Next',
                target=lambda: parent.play_next(),
            )

            self.progress_slider = CustomSlider(self, seek_on_release=True)
            self.progress_slider.setMinimumWidth(150)
            self.progress_slider.setRange(0, 0)
            self.progress_slider.sliderMoved.connect(
                lambda ms: parent.media_player.setPosition(ms))
            # set stretch to 1

            light_text_color = apply_alpha_to_hex(TEXT_COLOR, 0.65)
            self.time_elapsed = QLabel('0:00')
            self.time_elapsed.setStyleSheet(f'color: {light_text_color}; font-size: 12px;')
            self.time_total = QLabel('0:00')
            self.time_total.setStyleSheet(f'color: {light_text_color}; font-size: 12px;')

            self.btn_volume = IconButton(
                parent=self,
                icon_path=':/resources/icon-volume.png',
                size=25,
                tooltip='Mute',
                target=self.toggle_mute,
            )
            self.volume_slider = CustomSlider(self)
            self.volume_slider.setRange(0, 100)
            self.volume_slider.setValue(50)
            self.volume_slider.setFixedWidth(80)
            self.volume_slider.valueChanged.connect(
                lambda v: parent.audio_output.setVolume(v / 100.0))
            
            self.now_playing_title = QLabel('')
            self.now_playing_artist = QLabel('')
            self.now_playing_avatar = QLabel('')
            self.now_playing_avatar.setFixedSize(45, 45)
            self.now_playing_avatar.setScaledContents(True)
            self.now_playing_artist.setStyleSheet(f'color: {light_text_color}; font-size: 12px;')
            self.now_playing_title.setFixedWidth(250)
            self.now_playing_artist.setFixedWidth(250)

            now_playing_text_layout = CVBoxLayout()
            now_playing_text_layout.addStretch(1)
            now_playing_text_layout.addWidget(self.now_playing_title)
            now_playing_text_layout.addWidget(self.now_playing_artist)
            now_playing_text_layout.addStretch(1)

            now_playing_layout = CHBoxLayout()
            now_playing_layout.addWidget(self.now_playing_avatar)
            now_playing_layout.addSpacing(10)
            now_playing_layout.addLayout(now_playing_text_layout)
            now_playing_layout.addStretch(1)

            controls_v_layout = CVBoxLayout()
            controls_h1_layout = CHBoxLayout()
            controls_h2_layout = CHBoxLayout()
            controls_h1_layout.addStretch(1)
            controls_h1_layout.addWidget(self.btn_prev)
            controls_h1_layout.addSpacing(15)
            controls_h1_layout.addWidget(self.btn_play)
            controls_h1_layout.addSpacing(15)
            controls_h1_layout.addWidget(self.btn_next)
            controls_h1_layout.addStretch(1)
            
            controls_h2_layout.addWidget(self.time_elapsed)
            controls_h2_layout.addWidget(self.progress_slider)
            controls_h2_layout.addSpacing(3)
            controls_h2_layout.addWidget(self.time_total)
            controls_v_layout.addSpacing(15)
            controls_v_layout.addLayout(controls_h1_layout)
            controls_v_layout.addSpacing(5)
            controls_v_layout.addLayout(controls_h2_layout)
            controls_v_layout.addSpacing(10)

            self.layout.addLayout(now_playing_layout)
            self.layout.addLayout(controls_v_layout, 1)
            self.layout.addSpacing(135)
            self.layout.addWidget(self.btn_volume)
            self.layout.addSpacing(10)
            self.layout.addWidget(self.volume_slider)

        def toggle_mute(self):
            ao = self.parent.audio_output
            ao.setMuted(not ao.isMuted())
            icon = ':/resources/icon-volume-off.png' if ao.isMuted() \
                else ':/resources/icon-volume.png'
            self.btn_volume.setIconPixmap(path_to_pixmap(icon, diameter=20))

        def set_playing(self, is_playing):
            """Swap the play/pause icon."""
            icon = ':/resources/icon-pause.png' if is_playing \
                else ':/resources/icon-play.png'
            self.btn_play.setIconPixmap(path_to_pixmap(icon, diameter=45))

        def set_now_playing(self, title, artist, avatar_path=None):
            """Update the now-playing labels."""
            self.now_playing_title.setText(title or '')
            self.now_playing_artist.setText(artist or '')
            self.now_playing_avatar.setPixmap(
                path_to_pixmap(avatar_path, diameter=38))

        def clear_now_playing(self):
            """Blank the now-playing labels."""
            self.now_playing_title.setText('')
            self.now_playing_artist.setText('')
            self.now_playing_avatar.clear()

        def on_position_changed(self, ms):
            """Slot for QMediaPlayer.positionChanged."""
            if self.progress_slider._dragging:
                return
            self.progress_slider.setValue(ms)
            self.time_elapsed.setText(_fmt(ms))
            self.time_total.setText(_fmt(self.progress_slider.maximum()))

        def on_duration_changed(self, ms):
            """Slot for QMediaPlayer.durationChanged."""
            self.progress_slider.setRange(0, ms)

    class TrackQueue(ConfigTable):
        """Persistent track list with Generate/Clear controls."""

        def __init__(self, parent):
            super().__init__(
                parent=parent,
                schema=[
                    {'text': '#', 'visible': False},
                    {'text': 'Title', 'stretch': True},
                    {'text': 'Artist', 'width': 150},
                    {'text': 'Duration', 'width': 60},
                ],
                show_table_buttons=False,
                full_row_select=True,
            )
            self.tracks = []
            self.pending_tracks = {}
            self.new_unplayed_track_ids = []
            self._avatar_pixmap_cache = {}

            self.table.setSortingEnabled(False)
            self.table.verticalHeader().setVisible(False)
            self.table.setShowGrid(False)
            self.table.horizontalHeader().setDefaultAlignment(Qt.AlignLeft)
            self.table.doubleClicked.connect(self._on_double_click)

            # set table background color to transparent
            from gui.style import PRIMARY_COLOR, TEXT_COLOR
            from utils.helpers import apply_alpha_to_hex
            transparent_color = apply_alpha_to_hex(TEXT_COLOR, 0.03)
            self.table.setStyleSheet(f'background-color: {transparent_color};')
            # set table header background color to transparent
            self.table.horizontalHeader().setStyleSheet(f'background-color: {transparent_color};')

            btn_bar = CHBoxLayout()
            self.btn_start = QPushButton('Start')
            self.btn_start.setFixedHeight(25)
            self.btn_start.clicked.connect(
                lambda: parent.on_start_stop_clicked())
            from gui.fields.combo import BaseCombo
            self.artist_filter = BaseCombo(parent=self, pinned_index=0)
            self.artist_filter.setFixedHeight(25)
            self.artist_filter.setFixedWidth(175)
            self.artist_filter.currentIndexChanged.connect(
                lambda: self.load())

            concurrent_label = QLabel('Concurrent')
            from gui.fields.integer import Integer
            self.concurrent_field = Integer(
                parent=self,
                minimum=1,
                maximum=10,
            )
            self.concurrent_field.setFixedWidth(50)
            self.concurrent_field.set_value(3)

            cover_ratio_label = QLabel('Cover ratio')
            self.cover_ratio_field = Integer(
                parent=self, minimum=0, maximum=100,
            )
            self.cover_ratio_field.setFixedWidth(50)
            self.cover_ratio_field.set_value(95)

            priority_ratio_label = QLabel('Priority ratio')
            self.priority_ratio_field = Integer(
                parent=self, minimum=0, maximum=100,
            )
            self.priority_ratio_field.setFixedWidth(50)
            self.priority_ratio_field.set_value(95)

            include_unplayed_label = QLabel('Include unplayed')
            from gui.fields.boolean import Boolean
            self.include_unplayed_field = Boolean(parent=self)
            self.include_unplayed_field.set_value(True)

            btn_bar.addWidget(self.btn_start)
            btn_bar.addStretch(1)
            btn_bar.addWidget(concurrent_label)
            btn_bar.addWidget(self.concurrent_field)
            btn_bar.addWidget(cover_ratio_label)
            btn_bar.addWidget(self.cover_ratio_field)
            btn_bar.addWidget(priority_ratio_label)
            btn_bar.addWidget(self.priority_ratio_field)
            btn_bar.addWidget(include_unplayed_label)
            btn_bar.addWidget(self.include_unplayed_field)
            btn_bar.addStretch(1)
            btn_bar.addWidget(self.artist_filter)
            self.table_layout.insertLayout(0, btn_bar)

        def on_item_selected(self):
            pass  # selection via double-click only

        def load(self):
            self.load_artist_filter()
            self.load_tracks()

        def load_artist_filter(self):
            """Repopulate the artist filter combo from DB."""
            current_data = self.artist_filter.currentData()
            self.artist_filter.blockSignals(True)
            self.artist_filter.clear()
            self.artist_filter.addItem('All artists', None)
            rows = sql.get_results(
                "SELECT id, name FROM slopify_artists ORDER BY name",
            )
            for row in (rows or []):
                self.artist_filter.addItem(row[1], row[0])
            # Restore previous selection
            if current_data is not None:
                for i in range(self.artist_filter.count()):
                    if self.artist_filter.itemData(i) == current_data:
                        self.artist_filter.setCurrentIndex(i)
                        break
            self.artist_filter.blockSignals(False)

        def load_tracks(self):
            artist_id = self.artist_filter.currentData()
            # Load completed tracks
            base = """
                SELECT t.id, t.filepath, t.title, t.duration_ms,
                    t.artist_id, COALESCE(a.name, ''), COALESCE(a.config, '{}')
                FROM slopify_tracks t
                LEFT JOIN slopify_artists a ON a.id = t.artist_id
            """
            if artist_id is not None:
                rows = sql.get_results(
                    f"{base} WHERE t.artist_id = ? ORDER BY t.id",
                    (artist_id,),
                )
            else:
                rows = sql.get_results(
                    f"{base} ORDER BY t.id")
            self.tracks = []
            for r in (rows or []):
                self.tracks.append({
                    'id': r[0],
                    'filepath': r[1],
                    'title': r[2],
                    'duration_ms': r[3],
                    'artist_id': r[4],
                    'artist': r[5],
                    'avatar_path': self._extract_avatar_path(r[6]),
                })
            # Load pending tracks
            pbase = """
                SELECT p.id, p.artist_id, p.request_data, p.title,
                    COALESCE(a.name, ''), COALESCE(a.config, '{}')
                FROM slopify_pending p
                LEFT JOIN slopify_artists a ON a.id = p.artist_id
            """
            if artist_id is not None:
                prows = sql.get_results(
                    f"{pbase} WHERE p.artist_id = ? ORDER BY p.id",
                    (artist_id,),
                )
            else:
                prows = sql.get_results(
                    f"{pbase} ORDER BY p.id")
            self.pending_tracks = {
                r[0]: {'id': r[0], 'artist_id': r[1],
                       'request_data': r[2] or '',
                       'title': r[3], 'artist': r[4],
                       'avatar_path': self._extract_avatar_path(r[5])}
                for r in (prows or [])
            }
            self._refresh()

        @staticmethod
        def _extract_avatar_path(config_json):
            """Read avatar path from artist config JSON."""
            if not config_json:
                return ''
            try:
                config = json.loads(config_json) if isinstance(config_json, str) else config_json
                if not isinstance(config, dict):
                    return ''
                info = config.get('Info', {}) or {}
                return info.get('avatar_path', '') or config.get('avatar_path', '') or ''
            except Exception:
                return ''

        def _get_avatar_pixmap(self, avatar_path, diameter=25):
            key = (avatar_path or '', diameter)
            pixmap = self._avatar_pixmap_cache.get(key)
            if pixmap is None:
                pixmap = path_to_pixmap(avatar_path, diameter=diameter)
                self._avatar_pixmap_cache[key] = pixmap
            return pixmap

        def _set_title_icon(self, row, avatar_path):
            source_index = self.table.model.index(row, 1)
            if not source_index.isValid():
                return
            self.table.model.setData(
                source_index,
                QIcon(self._get_avatar_pixmap(avatar_path, diameter=25)),
                Qt.DecorationRole,
            )

        def _refresh(self):
            current_idx = self.parent.current_track_index
            data = []
            title_icons = []
            for i, t in enumerate(self.tracks):
                title = t.get('title') or t.get('filepath', '')
                if i == current_idx:
                    title = f'{title}    \u25B6'
                dur = _fmt(t.get('duration_ms', 0))
                artist = t.get('artist') or 'Unknown'
                data.append((i + 1, title, artist, dur))
                title_icons.append((title, t.get('avatar_path', '')))
            for t in self.pending_tracks.values():
                title = t.get('title') or 'Generating...'
                artist = t.get('artist') or 'Unknown'
                data.append(('', title, artist, ''))
                title_icons.append((title, t.get('avatar_path', '')))
            self.table.clearSelection()
            self.table.load(data, schema=self.schema)
            for row, (_, avatar_path) in enumerate(title_icons):
                self._set_title_icon(row, avatar_path)
            if 0 <= current_idx < len(self.tracks):
                self.highlight_track(current_idx)
            self.table.scrollToBottom()

        def set_start_button(self, generating):
            """Toggle the Start/Stop button text."""
            self.btn_start.setText('Stop' if generating else 'Start')

        def highlight_track(self, index):
            self.table.selectRow(index)

        def remove_track(self, index):
            if not (0 <= index < len(self.tracks)):
                return
            track = self.tracks.pop(index)
            sql.execute(
                "DELETE FROM slopify_tracks WHERE id = ?",
                (track['id'],))
            self._refresh()

        def _on_double_click(self, model_index):
            source_index = self.table.proxy_model.mapToSource(model_index)
            row = source_index.row()
            if row < len(self.tracks):
                self.parent.play_track(row)

        def contextMenuEvent(self, event):
            index = self.table.indexAt(
                self.table.viewport().mapFrom(self, event.pos()))
            if not index.isValid():
                return
            source_index = self.table.proxy_model.mapToSource(index)
            row = source_index.row()
            if row < 0 or row >= len(self.tracks):
                return
            menu = self.TrackContextMenu(self, row)
            menu.show_popup_menu()

        class TrackContextMenu(CustomMenu):
            """Context menu for tracks in the queue."""

            def __init__(self, parent, track_index):
                super().__init__(parent)
                self.schema = [
                    {
                        'text': 'Open in studio',
                        'target': partial(
                            parent._open_track_in_studio,
                            track_index,
                        ),
                    },
                    {
                        'text': 'Open in Files',
                        'target': partial(
                            parent._open_track_in_files,
                            track_index,
                        ),
                    },
                    {
                        'text': 'Add to Playlist',
                        'submenu': lambda: parent._build_playlist_submenu(
                            track_index),
                    },
                    {
                        'text': 'Delete',
                        'target': partial(
                            parent._delete_track,
                            track_index,
                        ),
                    },
                ]

        def _open_track_in_files(self, index):
            """Navigate to the track's directory in the Files page."""
            if not (0 <= index < len(self.tracks)):
                return
            filepath = self.tracks[index].get('filepath', '')
            if not filepath or not os.path.isfile(filepath):
                return
            from pathlib import Path
            main = find_main()
            files_page = main.main_pages.pages.get('files')
            if files_page:
                main.main_pages.goto_page('files')
                files_page.navigate_to(Path(filepath))

        def _open_track_in_studio(self, index):
            """Open the track's audio file in the video studio."""
            if not (0 <= index < len(self.tracks)):
                return
            filepath = self.tracks[index].get('filepath', '')
            if not filepath or not os.path.isfile(filepath):
                return
            main = find_main()
            videos_page = main.main_pages.pages.get('videos')
            if videos_page:
                main.main_pages.goto_page('videos')
                videos_page.open_file(filepath)

        def _build_playlist_submenu(self, track_index):
            """Return submenu items for adding a track to a playlist."""
            rows = sql.get_results(
                "SELECT id, name FROM slopify_playlists ORDER BY id",
            )
            if not rows:
                return [{'text': '(No playlists)', 'enabled': False}]
            return [
                {
                    'text': name,
                    'target': partial(
                        self._add_track_to_playlist,
                        track_index, pid),
                }
                for pid, name in rows
            ]

        def _add_track_to_playlist(self, track_index, playlist_id):
            """Insert a track into a playlist's junction table."""
            if not (0 <= track_index < len(self.tracks)):
                return
            track_id = self.tracks[track_index]['id']
            pos = sql.get_scalar(
                "SELECT COALESCE(MAX(position), -1) + 1"
                " FROM slopify_playlist_tracks"
                " WHERE playlist_id = ?",
                (playlist_id,),
            ) or 0
            sql.execute(
                "INSERT INTO slopify_playlist_tracks"
                " (playlist_id, track_id, position)"
                " VALUES (?, ?, ?)",
                (playlist_id, track_id, pos),
            )
            # Refresh the playlist track list if this playlist is selected
            ptl = self.parent.playlist_track_list
            if ptl.playlist_id == playlist_id:
                ptl.load()

        def _delete_track(self, index):
            """Remove a track from the queue, stopping playback if needed."""
            if not (0 <= index < len(self.tracks)):
                return
            page = self.parent
            if page.current_track_index == index:
                page.stop_playback()
            elif page.current_track_index > index:
                page.current_track_index -= 1
            self.remove_track(index)