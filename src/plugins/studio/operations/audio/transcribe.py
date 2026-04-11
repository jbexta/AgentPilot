"""Transcribe audio to SRT subtitles."""

import asyncio
import json
import os
import subprocess

from PySide6.QtCore import Qt, QThread, Signal
from PySide6.QtWidgets import (
    QDialog, QHBoxLayout, QLabel, QPushButton, QVBoxLayout, QWidget,
)

from gui import system
from gui.widgets.config_fields import ConfigFields
from plugins.studio.operations.base import BaseOperation


class Transcribe(BaseOperation):
    """Transcribe audio/video clips to SRT subtitles."""

    display_name = 'Transcribe'
    description = 'Transcribe audio to SRT subtitles'
    icon_path = ':/resources/icon-chat.png'

    def run(self):
        """Show transcribe dialog for each clip."""
        for clip in self.clips_to_modify:
            if not clip.filepath or not os.path.exists(clip.filepath):
                continue
            dialog = self.TranscribeDialog(
                self.studio, clip.filepath
            )
            dialog.exec_()

    class TranscribeDialog(QDialog):
        """Dialog for transcribing audio/video clips to SRT subtitles."""

        def __init__(self, parent, filepath):
            super().__init__(parent)
            self.setWindowFlags(
                Qt.Window
                | Qt.WindowTitleHint
                | Qt.WindowSystemMenuHint
                | Qt.WindowCloseButtonHint
                | Qt.WindowStaysOnTopHint
            )
            self.filepath = filepath
            self.setWindowTitle("Transcribe")
            self.resize(450, 200)
            self.layout = QVBoxLayout(self)

            self.config_fields = ConfigFields(
                self,
                schema=[{
                    'text': 'Model',
                    'key': 'model',
                    'type': 'model',
                    'model_kind': 'TEXT',
                    'width': 350,
                    'stretch_y': True,
                }]
            )
            self.config_fields.build_schema()
            self.config_fields.load()
            self.layout.addWidget(self.config_fields)

            self.status_label = QLabel("")
            self.layout.addWidget(self.status_label)

            button_box = QWidget()
            button_layout = QHBoxLayout(button_box)
            button_layout.setContentsMargins(0, 0, 0, 0)
            self.btn_transcribe = QPushButton("Transcribe")
            self.btn_transcribe.clicked.connect(self.start_transcription)
            self.btn_cancel = QPushButton("Cancel")
            self.btn_cancel.clicked.connect(self.reject)
            button_layout.addStretch()
            button_layout.addWidget(self.btn_cancel)
            button_layout.addWidget(self.btn_transcribe)
            self.layout.addWidget(button_box)

            self._thread = None

        def start_transcription(self):
            """Start the transcription thread."""
            self.config_fields.update_config()
            model_obj = self.config_fields.config.get('model')
            if not model_obj:
                return

            base = os.path.splitext(self.filepath)[0]
            srt_path = f"{base}.srt"

            self.btn_transcribe.setEnabled(False)
            self.status_label.setText("Transcribing...")

            self._thread = Transcribe.TranscribeThread(
                self.filepath, model_obj, srt_path
            )
            self._thread.progress.connect(self.on_progress)
            self._thread.finished_transcription.connect(self.on_finished)
            self._thread.error.connect(self.on_error)
            self._thread.start()

        def on_progress(self, msg):
            self.status_label.setText(msg)

        def on_finished(self, srt_path):
            self.status_label.setText(f"Done: {srt_path}")
            self.btn_transcribe.setEnabled(True)

        def on_error(self, msg):
            self.status_label.setText(f"Error: {msg}")
            self.btn_transcribe.setEnabled(True)

    class TranscribeThread(QThread):
        """Background thread for chunked audio transcription to SRT."""

        progress = Signal(str)
        finished_transcription = Signal(str)
        error = Signal(str)

        CHUNK_DURATION = 300  # 5 minutes per chunk

        def __init__(self, filepath, model_obj, srt_path):
            super().__init__()
            self.filepath = filepath
            self.model_obj = model_obj
            self.srt_path = srt_path

        def run(self):
            import srt
            from datetime import timedelta
            from gui.studios.video_studio import get_media_duration

            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            try:
                duration = get_media_duration(self.filepath)

                open(self.srt_path, 'w').close()

                all_subtitles = []
                subtitle_index = 1

                num_chunks = max(
                    1, int(duration // self.CHUNK_DURATION) + 1
                )
                for i in range(num_chunks):
                    offset = i * self.CHUNK_DURATION
                    chunk_dur = min(
                        self.CHUNK_DURATION, duration - offset
                    )
                    if chunk_dur <= 0:
                        break

                    self.progress.emit(
                        f"Chunk {i + 1}/{num_chunks}: "
                        f"extracting audio..."
                    )
                    chunk_path = self._extract_chunk(offset, chunk_dur)

                    self.progress.emit(
                        f"Chunk {i + 1}/{num_chunks}: "
                        f"transcribing..."
                    )
                    result = loop.run_until_complete(
                        self._transcribe_file(chunk_path)
                    )
                    segments = self._parse_segments(result)

                    for seg in segments:
                        sub = srt.Subtitle(
                            index=subtitle_index,
                            start=timedelta(
                                seconds=seg['start'] + offset
                            ),
                            end=timedelta(
                                seconds=seg['end'] + offset
                            ),
                            content=seg['text'].strip(),
                        )
                        all_subtitles.append(sub)
                        subtitle_index += 1

                    # Flush SRT after each chunk
                    with open(self.srt_path, 'w') as f:
                        f.write(srt.compose(all_subtitles))

                    os.remove(chunk_path)

                # Final write
                with open(self.srt_path, 'w') as f:
                    f.write(srt.compose(all_subtitles))

                self.finished_transcription.emit(self.srt_path)
            except Exception as e:
                self.error.emit(str(e))
            finally:
                loop.close()

        def _extract_chunk(self, offset, duration):
            """Extract audio chunk using ffmpeg subprocess."""
            chunk_path = self.filepath + f'.chunk_{offset}.wav'
            subprocess.run([
                'ffmpeg', '-y', '-i', self.filepath,
                '-ss', str(offset), '-t', str(duration),
                '-vn', '-acodec', 'pcm_s16le',
                '-ar', '16000', '-ac', '1',
                chunk_path
            ], capture_output=True)
            return chunk_path

        async def _transcribe_file(self, filepath):
            """Upload file and run STT model, return result dict."""
            from utils.helpers import convert_model_json_to_obj

            model_obj = convert_model_json_to_obj(self.model_obj)
            provider_name = model_obj['provider']
            provider = system.manager.providers.get(provider_name)

            model_s_params = system.manager.models.get_model(model_obj)
            model_obj['model_params'] = {
                **model_obj.get('model_params', {}),
                **model_s_params,
            }

            api_key = model_obj['model_params'].get('api_key')

            if provider_name == 'fal':
                import fal_client
                os.environ['FAL_API_KEY'] = api_key
                audio_url = fal_client.upload_file(filepath)
                model_obj['model_params']['audio_url'] = audio_url
            elif provider_name == 'replicate':
                os.environ['REPLICATE_API_TOKEN'] = api_key
                model_obj['model_params']['audio'] = open(
                    filepath, 'rb'
                )

            stream = await provider.run_model(model_obj)
            for item in stream:
                request_data = json.loads(item)
                break

            request_id = request_data['request_id']
            model_name = request_data['model_name']

            return await provider.get_transcription_result(
                model_name, request_id
            )

        def _parse_segments(self, result):
            """Normalize segments from different provider formats."""
            segments = []

            if isinstance(result, dict):
                if 'chunks' in result:
                    for chunk in result['chunks']:
                        ts = chunk.get('timestamp', [0, 0])
                        segments.append({
                            'start': (
                                ts[0] if ts[0] is not None else 0
                            ),
                            'end': (
                                ts[1] if ts[1] is not None else 0
                            ),
                            'text': chunk.get('text', ''),
                        })
                elif 'segments' in result:
                    for seg in result['segments']:
                        segments.append({
                            'start': seg.get('start', 0),
                            'end': seg.get('end', 0),
                            'text': seg.get('text', ''),
                        })
                elif 'text' in result:
                    segments.append({
                        'start': 0,
                        'end': 0,
                        'text': result['text'],
                    })

            elif isinstance(result, str):
                segments.append({
                    'start': 0,
                    'end': 0,
                    'text': result,
                })

            return segments
