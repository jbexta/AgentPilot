"""
FFmpeg-based media rendering utilities for studio timeline exports.

Provides functions to mix timeline audio from overlapping clips and
to extract segments of individual clip media files, as well as full
frame-by-frame video rendering with compositing.
"""

import os
import shutil
import subprocess
import tempfile
import wave

import numpy as np
from PIL import Image
from moviepy import VideoFileClip

from utils.media import get_ffmpeg_exe


def compute_audio_offset(ref_path, gen_path, sample_rate=16000):
    """Compute the temporal offset between two audio files.

    Uses FFT-based cross-correlation to find the lag at which the
    generated audio best aligns with the reference audio.

    Parameters
    ----------
    ref_path : str
        Path to the reference audio file.
    gen_path : str
        Path to the generated audio file.
    sample_rate : int
        Sample rate for comparison (default 16kHz).

    Returns
    -------
    float
        Offset in seconds.  Positive means the generated audio is
        delayed relative to the reference.  Returns 0 on failure or
        unreliable correlation.
    """
    tmp_files = []
    try:
        signals = []
        for path in (ref_path, gen_path):
            fd, tmp = tempfile.mkstemp(suffix='.wav')
            os.close(fd)
            tmp_files.append(tmp)
            cmd = [
                get_ffmpeg_exe(), '-y', '-i', path,
                '-vn', '-ac', '1', '-ar', str(sample_rate),
                '-f', 'wav', tmp,
            ]
            result = subprocess.run(
                cmd, capture_output=True, timeout=30,
            )
            if result.returncode != 0:
                return 0.0
            with wave.open(tmp, 'rb') as wf:
                n_frames = wf.getnframes()
                if n_frames == 0:
                    return 0.0
                raw = wf.readframes(n_frames)
            pcm = np.frombuffer(raw, dtype=np.int16).astype(np.float32)
            mx = np.max(np.abs(pcm))
            if mx > 0:
                pcm /= mx
            signals.append(pcm)

        ref, gen = signals
        if len(ref) < 0.1 * sample_rate or len(gen) < 0.1 * sample_rate:
            return 0.0

        n_fft = 1
        needed = len(ref) + len(gen) - 1
        while n_fft < needed:
            n_fft <<= 1

        corr = np.real(
            np.fft.ifft(
                np.fft.fft(ref, n_fft)
                * np.conj(np.fft.fft(gen, n_fft))
            )
        )
        peak = np.max(corr)
        std = np.std(corr)
        if std == 0 or peak / std < 5:
            return 0.0

        lag = int(np.argmax(corr))
        if lag > n_fft // 2:
            lag -= n_fft
        offset = lag / sample_rate

        # Cap to half the shorter clip duration
        max_offset = min(len(ref), len(gen)) / sample_rate / 2
        if abs(offset) > max_offset:
            return 0.0

        return offset
    except Exception:
        return 0.0
    finally:
        for tmp in tmp_files:
            try:
                os.unlink(tmp)
            except OSError:
                pass


def _has_audio_stream(filepath):
    """True if *filepath* contains an audio stream.

    Media type isn't enough: generated .mp4s are often video-only, and an
    input with no audio makes its ``[N:a]`` label match no stream, which
    fails the whole render.
    """
    proc = subprocess.run(
        [get_ffmpeg_exe(), '-hide_banner', '-i', filepath],
        capture_output=True, text=True, errors='replace',
    )
    return ': Audio:' in proc.stderr


def build_audio_clip_infos(clip_data_list, track_configs, fps):
    """Serialize timeline clips into ``render_timeline_audio()`` inputs.

    Skips clips that contribute no audio (disabled, image-only, or with
    no file on disk) and folds the clip's own volume together with its
    track volume.

    Parameters
    ----------
    clip_data_list : list of dict
        Serialized clips with keys: filepath, media_type, start_frame,
        in_frame, frame_count, track_index, is_disabled, volume. Clips
        are passed as plain dicts rather than live objects so callers
        can serialize on the main thread and render off it.
    track_configs : list of dict
        Per-track config; each may carry a ``volume`` (0-200).
    fps : float
        Project frames per second, used to convert frames to seconds.

    Returns
    -------
    list of dict
        Inputs for ``render_timeline_audio()``.
    """
    audio_clips = []
    for cd in clip_data_list:
        if cd.get('is_disabled'):
            continue
        if cd.get('media_type') not in ('audio', 'video'):
            continue  # images never carry audio: skip the probe below
        filepath = cd.get('filepath')
        if not filepath or not os.path.isfile(filepath):
            continue
        if not _has_audio_stream(filepath):
            continue

        clip_volume = cd.get('volume', 100)
        track_index = cd.get('track_index', 0)
        track_volume = 100
        if track_index < len(track_configs):
            track_volume = track_configs[track_index].get('volume', 100)

        audio_clips.append({
            'filepath': filepath,
            'start_time': cd['start_frame'] / fps,
            'in_point': cd['in_frame'] / fps,
            'duration': cd['frame_count'] / fps,
            'volume': (clip_volume * track_volume) / 100.0,
        })
    return audio_clips


def render_timeline_audio(clips, start_time, duration, fps, output_path):
    """Render mixed audio from all overlapping clips to a single file.

    Parameters
    ----------
    clips : list of dict
        Each dict has keys: filepath, start_time, in_point, duration,
        volume (0-200, where 100 is unity).
    start_time : float
        Start of the region to render, in seconds.
    duration : float
        Length of the region to render, in seconds.
    fps : float
        Project frames per second.
    output_path : str
        Destination WAV file path.
    """
    end_time = start_time + duration
    inputs = []

    for clip in clips:
        clip_start = clip['start_time']
        clip_end = clip_start + clip['duration']

        # Skip clips that don't overlap our render region
        if clip_end <= start_time or clip_start >= end_time:
            continue

        filepath = clip['filepath']
        if not filepath or not os.path.isfile(filepath):
            continue

        # Offset into the source media file
        media_offset = clip['in_point'] + max(0, start_time - clip_start)
        # How much of the clip to use
        clip_dur = min(clip_end, end_time) - max(clip_start, start_time)
        if clip_dur < 0.001:
            continue
        # Delay if clip starts after our render start
        delay_ms = max(0, int((clip_start - start_time) * 1000))
        # Volume: 0-200 scale → 0.0-2.0
        volume = clip.get('volume', 100) / 100.0

        inputs.append({
            'filepath': filepath,
            'offset': media_offset,
            'duration': clip_dur,
            'delay_ms': delay_ms,
            'volume': volume,
        })

    if not inputs:
        # Generate silence
        cmd = [
            get_ffmpeg_exe(), '-y',
            '-f', 'lavfi', '-i',
            f'anullsrc=r=44100:cl=stereo:d={duration}',
            '-acodec', 'pcm_s16le',
            output_path,
        ]
        subprocess.run(cmd, capture_output=True, check=True)
        return

    cmd = [get_ffmpeg_exe(), '-y']
    filter_parts = []

    for i, inp in enumerate(inputs):
        cmd.extend([
            '-ss', str(inp['offset']),
            '-t', str(inp['duration']),
            '-i', inp['filepath'],
        ])
        label = f'[{i}:a]'
        vol_label = f'[v{i}]'
        delay_label = f'[d{i}]'

        filter_parts.append(
            f'{label}volume={inp["volume"]}{vol_label}'
        )
        if inp['delay_ms'] > 0:
            filter_parts.append(
                f'{vol_label}adelay={inp["delay_ms"]}|'
                f'{inp["delay_ms"]}{delay_label}'
            )
        else:
            # Rename for consistency
            filter_parts.append(
                f'{vol_label}acopy{delay_label}'
            )

    n = len(inputs)
    mix_inputs = ''.join(f'[d{i}]' for i in range(n))
    filter_parts.append(
        f'{mix_inputs}amix=inputs={n}:duration=longest:normalize=0[out]'
    )

    filter_graph = ';'.join(filter_parts)
    cmd.extend([
        '-filter_complex', filter_graph,
        '-map', '[out]',
        '-acodec', 'pcm_s16le',
        '-ar', '44100',
        '-ac', '2',
        output_path,
    ])

    subprocess.run(cmd, capture_output=True, check=True)


def extract_clip_media(
    clip_filepath, start_time, duration, media_type, output_path
):
    """Extract a portion of a clip's media file.

    Parameters
    ----------
    clip_filepath : str
        Path to the source media file.
    start_time : float
        Seek position in seconds.
    duration : float
        Duration to extract in seconds.
    media_type : str
        One of 'audio', 'video', 'image'.
    output_path : str
        Destination file path.
    """
    if media_type == 'image':
        shutil.copy2(clip_filepath, output_path)
        return

    if media_type == 'audio':
        cmd = [
            get_ffmpeg_exe(), '-y',
            '-ss', str(start_time),
            '-t', str(duration),
            '-i', clip_filepath,
            '-vn',
            '-acodec', 'pcm_s16le',
            '-ar', '44100',
            '-ac', '2',
            output_path,
        ]
    else:
        # video
        cmd = [
            get_ffmpeg_exe(), '-y',
            '-ss', str(start_time),
            '-t', str(duration),
            '-i', clip_filepath,
            '-c', 'copy',
            output_path,
        ]

    subprocess.run(cmd, capture_output=True, check=True)


def render_timeline_frame(
    clip_data_list, frame, fps, width, height, output_path
):
    """Render a single composited timeline frame to an image file.

    Parameters
    ----------
    clip_data_list : list of dict
        Serialized clip data with keys: filepath, media_type,
        start_frame, in_frame, frame_count, track_index,
        is_disabled, scale, pos_x, pos_y, rotation.
    frame : int
        Timeline frame number to render.
    fps : float
        Project frames per second.
    width : int
        Output width in pixels.
    height : int
        Output height in pixels.
    output_path : str
        Destination image file path.
    """
    canvas = np.zeros((height, width, 3), dtype=np.uint8)
    active = _get_active_clips_at_frame(clip_data_list, frame)
    active.sort(key=lambda c: c['track_index'])

    clip_readers = {}
    try:
        for clip_data in active:
            frame_img = _decode_clip_frame(
                clip_data, frame, fps, clip_readers
            )
            if frame_img is not None:
                canvas = _composite_frame(canvas, frame_img, clip_data)
    finally:
        for reader in clip_readers.values():
            try:
                reader.close()
            except Exception:
                pass

    Image.fromarray(canvas).save(output_path)


def render_timeline_video(
    clip_data_list,
    start_frame,
    end_frame,
    fps,
    width,
    height,
    output_path,
    vcodec='libx264',
    crf=18,
    pix_fmt='yuv420p',
    audio_path=None,
    audio_codec='aac',
    audio_bitrate='192k',
    sample_rate=48000,
    channels=2,
    progress_callback=None,
):
    """Render composited video frame-by-frame via ffmpeg pipe.

    Parameters
    ----------
    clip_data_list : list of dict
        Serialized clip data with keys: filepath, media_type,
        start_frame, in_frame, out_frame, frame_count, track_index,
        is_disabled, scale, pos_x, pos_y, rotation.
    start_frame : int
        First frame to render.
    end_frame : int
        Frame after the last frame to render.
    fps : float
        Output frames per second.
    width : int
        Output width in pixels.
    height : int
        Output height in pixels.
    output_path : str
        Destination video file path.
    vcodec : str
        Video codec for ffmpeg.
    crf : int
        Constant rate factor (quality).
    pix_fmt : str
        Pixel format.
    audio_path : str or None
        Path to pre-rendered audio WAV to mux in.
    audio_codec : str or None
        Audio codec name, or None to skip audio.
    audio_bitrate : str
        Audio bitrate string (e.g. '192k').
    sample_rate : int
        Audio sample rate.
    channels : int
        Number of audio channels.
    progress_callback : callable or None
        Called as ``progress_callback(current_frame_index, total_frames)``.
        Should return True to continue or False to cancel.
    """
    total_frames = end_frame - start_frame

    # Build ffmpeg command
    cmd = [
        get_ffmpeg_exe(), '-y',
        '-f', 'rawvideo',
        '-vcodec', 'rawvideo',
        '-s', f'{width}x{height}',
        '-pix_fmt', 'rgb24',
        '-r', str(fps),
        '-i', '-',  # stdin pipe
    ]

    if audio_path and audio_codec and os.path.isfile(audio_path):
        cmd.extend(['-i', audio_path])

    cmd.extend([
        '-c:v', vcodec,
        '-crf', str(crf),
        '-pix_fmt', pix_fmt,
        '-preset', 'medium',
    ])

    if audio_path and audio_codec and os.path.isfile(audio_path):
        cmd.extend([
            '-c:a', audio_codec,
            '-b:a', audio_bitrate,
            '-ar', str(sample_rate),
            '-ac', str(channels),
        ])
    else:
        cmd.extend(['-an'])

    cmd.append(output_path)

    proc = subprocess.Popen(
        cmd, stdin=subprocess.PIPE,
        stdout=subprocess.DEVNULL, stderr=subprocess.PIPE,
    )

    clip_readers = {}
    try:
        for i, frame_num in enumerate(range(start_frame, end_frame)):
            # Create black canvas
            canvas = np.zeros((height, width, 3), dtype=np.uint8)

            # Get active visual clips at this frame
            active = _get_active_clips_at_frame(clip_data_list, frame_num)

            # Sort by track_index descending (lower track = bottom layer)
            active.sort(key=lambda c: c['track_index'])

            for clip_data in active:
                frame_img = _decode_clip_frame(
                    clip_data, frame_num, fps, clip_readers
                )
                if frame_img is not None:
                    canvas = _composite_frame(
                        canvas, frame_img, clip_data
                    )

            proc.stdin.write(canvas.tobytes())

            if progress_callback:
                if not progress_callback(i + 1, total_frames):
                    break
    finally:
        # Close readers
        for reader in clip_readers.values():
            try:
                reader.close()
            except Exception:
                pass
        proc.stdin.close()
        proc.wait()

    if proc.returncode != 0 and proc.returncode is not None:
        stderr = proc.stderr.read().decode(errors='replace')
        raise RuntimeError(
            f"ffmpeg exited with code {proc.returncode}: {stderr[-500:]}"
        )


def _get_active_clips_at_frame(clip_data_list, frame):
    """Return visual clips that are active at the given frame.

    Skips audio-only and disabled clips.
    """
    active = []
    for cd in clip_data_list:
        if cd.get('is_disabled'):
            continue
        if cd['media_type'] == 'audio':
            continue
        clip_start = cd['start_frame']
        clip_end = clip_start + cd['frame_count']
        if clip_start <= frame < clip_end:
            active.append(cd)
    return active


def _decode_clip_frame(clip_data, current_frame, fps, clip_readers):
    """Decode a single frame from a clip source.

    Uses cached VideoFileClip readers for video files.
    Returns a PIL Image in RGB mode, or None on failure.

    Parameters
    ----------
    clip_data : dict
        Serialized clip data.
    current_frame : int
        Current timeline frame number.
    fps : float
        Project FPS.
    clip_readers : dict
        Cache of filepath -> VideoFileClip instances.
    """
    filepath = clip_data.get('filepath')
    if not filepath or not os.path.isfile(filepath):
        return None

    media_type = clip_data['media_type']
    # Source frame offset
    local_frame = (
        current_frame - clip_data['start_frame'] + clip_data['in_frame']
    )
    local_time = local_frame / fps

    try:
        if media_type == 'image':
            img = Image.open(filepath).convert('RGB')
            return img
        elif media_type == 'video':
            if filepath not in clip_readers:
                clip_readers[filepath] = VideoFileClip(filepath)
            reader = clip_readers[filepath]
            # Clamp to valid range
            t = min(local_time, reader.duration - 0.001)
            t = max(0, t)
            frame_arr = reader.get_frame(t)
            return Image.fromarray(frame_arr).convert('RGB')
    except Exception:
        return None

    return None


def _composite_frame(canvas, frame_img, clip_data):
    """Composite a decoded frame onto the canvas.

    Applies scale, rotation, and position from clip_data.
    Returns the updated canvas as a numpy array.

    Parameters
    ----------
    canvas : numpy.ndarray
        Current canvas (H, W, 3) uint8.
    frame_img : PIL.Image.Image
        Decoded frame image in RGB.
    clip_data : dict
        Clip data with scale, pos_x, pos_y, rotation keys.
    """
    scale = clip_data.get('scale', 1.0)
    pos_x = clip_data.get('pos_x', 0.0)
    pos_y = clip_data.get('pos_y', 0.0)
    rotation = clip_data.get('rotation', 0.0)

    # Scale
    if scale != 1.0 and scale > 0:
        new_w = max(1, int(frame_img.width * scale))
        new_h = max(1, int(frame_img.height * scale))
        frame_img = frame_img.resize(
            (new_w, new_h), Image.Resampling.LANCZOS
        )

    # Rotate
    if rotation != 0.0:
        frame_img = frame_img.rotate(
            -rotation, resample=Image.Resampling.BICUBIC, expand=True
        )

    # Paste position (top-left anchored at pos_x, pos_y, matching preview)
    paste_x = int(pos_x)
    paste_y = int(pos_y)

    canvas_img = Image.fromarray(canvas)
    canvas_img.paste(frame_img, (paste_x, paste_y))
    return np.array(canvas_img)
