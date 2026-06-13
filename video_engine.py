"""
video_engine.py — Quran Reels Maker: Production Core Engine
=============================================================
Senior Full-Stack Python / AI Automation Architecture
Implements: Quran API fetching, Pexels background automation, RTL Arabic text
rendering, audio effects mixing, video composition, and webhook publishing.

All operations use strict error handling with try/except/finally blocks.
All MoviePy clips are explicitly closed to prevent memory leaks.
"""

import os
import sys
import time
import random
import logging
import hashlib
import traceback
import textwrap
import requests
import numpy as np

from pathlib import Path
from typing import Optional, Tuple, List, Dict, Any

# ─── Arabic Text Processing ───────────────────────────────────────────────────
try:
    import arabic_reshaper
    from bidi.algorithm import get_display as bidi_get_display
except ImportError as arabic_import_error:
    logging.critical(
        "[video_engine] FATAL: arabic_reshaper or python-bidi not installed. "
        "Run: pip install arabic-reshaper python-bidi  |  Error: %s",
        arabic_import_error,
    )
    sys.exit(1)

# ─── MoviePy Imports ─────────────────────────────────────────────────────────
try:
    from moviepy.editor import (
        VideoFileClip,
        AudioFileClip,
        TextClip,
        CompositeVideoClip,
        CompositeAudioClip,
        ColorClip,
        concatenate_audioclips,
    )
    from moviepy.audio.AudioClip import AudioArrayClip
except ImportError as moviepy_import_error:
    logging.critical(
        "[video_engine] FATAL: moviepy not installed. "
        "Run: pip install moviepy  |  Error: %s",
        moviepy_import_error,
    )
    sys.exit(1)

# ─── Pillow (for font validation) ────────────────────────────────────────────
try:
    from PIL import ImageFont
except ImportError:
    logging.warning(
        "[video_engine] Pillow not installed. Font validation will be skipped. "
        "Run: pip install Pillow"
    )
    ImageFont = None

# ─── Logging Configuration ───────────────────────────────────────────────────
logging.basicConfig(
    level=logging.DEBUG,
    format="%(asctime)s  [%(levelname)-8s]  %(name)s :: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler("quran_reels.log", encoding="utf-8"),
    ],
)
logger = logging.getLogger("video_engine")

# ─── Configuration Constants ─────────────────────────────────────────────────
PEXELS_API_KEY: str = "KrwFskWjoRUAyYd3maF7gipFddjfJAigmI21NMsfBb3QZ4iGbLPIimTv"
FONTS_DIR: str = "static/fonts/Amiri-Regular.ttf"

BASE_DIR: Path = Path(__file__).resolve().parent
OUTPUTS_DIR: Path = BASE_DIR / "outputs"
STATIC_DIR: Path = BASE_DIR / "static"
STATIC_AUDIO_DIR: Path = STATIC_DIR / "audio"
STATIC_VIDEO_DIR: Path = STATIC_DIR / "videos"
STATIC_FONTS_DIR: Path = STATIC_DIR / "fonts"
TEMP_DIR: Path = BASE_DIR / "outputs" / "temp"

QURAN_API_BASE: str = "https://api.alquran.cloud/v1/ayah"
EVERYAYAH_BASE: str = "https://everyayah.com/data"
PEXELS_VIDEO_API: str = "https://api.pexels.com/videos/search"

VIDEO_WIDTH: int = 1080
VIDEO_HEIGHT: int = 1920
VIDEO_FPS: int = 24
VIDEO_CODEC: str = "libx264"
AUDIO_CODEC: str = "aac"
AMBIENT_VOLUME_FACTOR: float = 0.15

HTTP_TIMEOUT_SECONDS: int = 30
HTTP_DOWNLOAD_TIMEOUT_SECONDS: int = 120
MAX_PEXELS_RESULTS: int = 15
REQUEST_RETRY_COUNT: int = 3
REQUEST_RETRY_DELAY_SECONDS: float = 2.0

# ─── Reciter Definitions ─────────────────────────────────────────────────────
RECITER_MAP: Dict[str, str] = {
    "Alafasy": "Alafasy_128kbps",
    "AbdulBaset": "AbdulSamad_128kbps_withbassm",
    "Husary": "Husary_128kbps",
    "Minshawi": "Minshawy_Murattal_128kbps",
    "Sudais": "Abdurrahmaan_As-Sudais_192kbps",
    "Ghamdi": "Ghamadi_40kbps",
}

# ─── Surah Theme Keyword Mapping ─────────────────────────────────────────────
SURAH_THEME_MAP: Dict[int, str] = {
    1:   "calm morning light sky spiritual",
    2:   "vast desert sand dunes arabic landscape",
    3:   "green forest path light beams nature",
    4:   "flowing river water reflections serene",
    5:   "lush green meadow peaceful sunset",
    6:   "starry night sky galaxy cosmos",
    7:   "ancient mountains majestic landscape sunrise",
    8:   "dramatic storm clouds lightning power",
    9:   "urban city lights night aerial",
    10:  "ocean waves calm sea horizon",
    11:  "volcanic mountain eruption dramatic sky",
    12:  "beautiful garden flowers bloom spring",
    13:  "thunderstorm rain lightning dramatic sky",
    14:  "sacred mosque architecture interior light",
    15:  "rocky desert canyon cliffs golden hour",
    16:  "honeybee flower garden macro nature",
    17:  "night sky stars moon glowing",
    18:  "cave waterfall mystical forest ancient",
    19:  "newborn baby gentle nature soft light",
    20:  "mountain peak snow sunrise clouds",
    21:  "cosmic nebula galaxy space universe",
    22:  "pilgrims crowd spiritual devotion holy",
    23:  "fertile farmland green crops abundance",
    24:  "bright light candle darkness spiritual glow",
    25:  "cosmic creation nebula vast universe",
    36:  "yasin glowing light spiritual arabic calligraphy",
    55:  "ocean tropical paradise nature scenery",
    56:  "clouds heaven paradise tropical nature",
    57:  "iron mountain strength vastness landscape",
    67:  "galaxy universe night sky stars",
    78:  "mountain sunrise majestic landscape horizon",
    89:  "ancient ruins civilization history landscape",
    112: "abstract geometric light spiritual unity",
    113: "dawn sunrise light breaking darkness",
    114: "protective light dark sky cosmic",
}
DEFAULT_THEME_KEYWORDS: str = "cinematic nature landscape serene aerial"


def ensure_directories_exist() -> None:
    """Create all required output and temp directories if they do not exist."""
    directories_to_create: List[Path] = [
        OUTPUTS_DIR,
        TEMP_DIR,
        STATIC_AUDIO_DIR,
        STATIC_VIDEO_DIR,
        STATIC_FONTS_DIR,
    ]
    for directory in directories_to_create:
        try:
            directory.mkdir(parents=True, exist_ok=True)
            logger.debug("[ensure_directories_exist] Verified directory: %s", directory)
        except OSError as directory_creation_error:
            logger.error(
                "[ensure_directories_exist] Failed to create directory %s: %s",
                directory,
                directory_creation_error,
            )
            raise


def get_theme_keywords_for_surah(surah_number: int) -> str:
    """
    Return the Pexels search keyword string mapped to a given Surah number.
    Falls back to the default cinematic nature keyword if no mapping exists.
    """
    keywords: str = SURAH_THEME_MAP.get(surah_number, DEFAULT_THEME_KEYWORDS)
    logger.info(
        "[get_theme_keywords_for_surah] Surah %d -> Keywords: '%s'",
        surah_number,
        keywords,
    )
    return keywords


def fetch_ayah_data(
    surah_number: int, ayah_number: int
) -> Optional[Dict[str, Any]]:
    """
    Fetch Arabic Uthmani text and English Sahih translation for a single Ayah
    from the AlQuran Cloud API.

    Returns a dict with keys 'arabic' and 'english', or None on failure.
    """
    endpoint_url: str = (
        f"{QURAN_API_BASE}/{surah_number}:{ayah_number}"
        f"/editions/quran-uthmani,en.sahih"
    )
    logger.info("[fetch_ayah_data] Requesting: %s", endpoint_url)

    for attempt_index in range(1, REQUEST_RETRY_COUNT + 1):
        response_object: Optional[requests.Response] = None
        try:
            response_object = requests.get(
                endpoint_url,
                timeout=HTTP_TIMEOUT_SECONDS,
                headers={"Accept": "application/json"},
            )
            response_object.raise_for_status()
            json_payload: Dict[str, Any] = response_object.json()

            api_status_code: int = json_payload.get("code", 0)
            if api_status_code != 200:
                logger.warning(
                    "[fetch_ayah_data] API returned non-200 code %d for %d:%d",
                    api_status_code,
                    surah_number,
                    ayah_number,
                )
                return None

            editions_data: List[Dict[str, Any]] = json_payload.get("data", [])
            if not isinstance(editions_data, list) or len(editions_data) < 2:
                logger.warning(
                    "[fetch_ayah_data] Unexpected data structure for %d:%d: %s",
                    surah_number,
                    ayah_number,
                    editions_data,
                )
                return None

            arabic_text: str = editions_data[0].get("text", "")
            english_text: str = editions_data[1].get("text", "")

            logger.info(
                "[fetch_ayah_data] Successfully fetched %d:%d",
                surah_number,
                ayah_number,
            )
            return {"arabic": arabic_text, "english": english_text}

        except requests.exceptions.Timeout:
            logger.warning(
                "[fetch_ayah_data] Timeout on attempt %d/%d for %d:%d",
                attempt_index,
                REQUEST_RETRY_COUNT,
                surah_number,
                ayah_number,
            )
        except requests.exceptions.ConnectionError as conn_err:
            logger.warning(
                "[fetch_ayah_data] Connection error on attempt %d/%d: %s",
                attempt_index,
                REQUEST_RETRY_COUNT,
                conn_err,
            )
        except requests.exceptions.HTTPError as http_err:
            logger.warning(
                "[fetch_ayah_data] HTTP error on attempt %d/%d: %s",
                attempt_index,
                REQUEST_RETRY_COUNT,
                http_err,
            )
        except (ValueError, KeyError) as parse_error:
            logger.error(
                "[fetch_ayah_data] JSON parse error for %d:%d: %s",
                surah_number,
                ayah_number,
                parse_error,
            )
            return None
        finally:
            if response_object is not None:
                response_object.close()

        if attempt_index < REQUEST_RETRY_COUNT:
            logger.info(
                "[fetch_ayah_data] Retrying in %.1f seconds...",
                REQUEST_RETRY_DELAY_SECONDS,
            )
            time.sleep(REQUEST_RETRY_DELAY_SECONDS)

    logger.error(
        "[fetch_ayah_data] All %d attempts failed for %d:%d",
        REQUEST_RETRY_COUNT,
        surah_number,
        ayah_number,
    )
    return None


def apply_arabic_reshaping_and_bidi(raw_arabic_text: str) -> str:
    """
    Apply arabic_reshaper and python-bidi transformations so that Arabic text
    renders correctly in left-to-right rendering environments (such as MoviePy
    PIL-based text rendering). This ensures characters are properly joined and
    displayed right-to-left without reversal artifacts.
    """
    try:
        reshaped_text: str = arabic_reshaper.reshape(raw_arabic_text)
        bidi_text: str = bidi_get_display(reshaped_text)
        logger.debug(
            "[apply_arabic_reshaping_and_bidi] Reshaped %d chars to %d chars",
            len(raw_arabic_text),
            len(bidi_text),
        )
        return bidi_text
    except Exception as reshaping_error:
        logger.error(
            "[apply_arabic_reshaping_and_bidi] Reshaping failed, "
            "returning raw text. Error: %s",
            reshaping_error,
        )
        return raw_arabic_text


def download_ayah_audio_file(
    surah_number: int,
    ayah_number: int,
    reciter_folder: str,
    save_path: Path,
) -> bool:
    """
    Download a single Ayah audio file from everyayah.com using the reciter's
    folder path convention: {surah_padded}{ayah_padded}.mp3

    Returns True on success, False on failure.
    """
    surah_padded: str = str(surah_number).zfill(3)
    ayah_padded: str = str(ayah_number).zfill(3)
    audio_filename: str = f"{surah_padded}{ayah_padded}.mp3"
    audio_url: str = f"{EVERYAYAH_BASE}/{reciter_folder}/{audio_filename}"

    logger.info(
        "[download_ayah_audio_file] Downloading: %s -> %s",
        audio_url,
        save_path,
    )

    for attempt_index in range(1, REQUEST_RETRY_COUNT + 1):
        response_object: Optional[requests.Response] = None
        try:
            response_object = requests.get(
                audio_url,
                timeout=HTTP_DOWNLOAD_TIMEOUT_SECONDS,
                stream=True,
            )
            response_object.raise_for_status()

            audio_bytes: bytes = response_object.content
            if len(audio_bytes) < 1000:
                logger.warning(
                    "[download_ayah_audio_file] Suspiciously small file (%d bytes) "
                    "for %s. Retrying attempt %d/%d.",
                    len(audio_bytes),
                    audio_url,
                    attempt_index,
                    REQUEST_RETRY_COUNT,
                )
                if attempt_index < REQUEST_RETRY_COUNT:
                    time.sleep(REQUEST_RETRY_DELAY_SECONDS)
                    continue
                return False

            save_path.write_bytes(audio_bytes)
            logger.info(
                "[download_ayah_audio_file] Saved %d bytes to %s",
                len(audio_bytes),
                save_path,
            )
            return True

        except requests.exceptions.Timeout:
            logger.warning(
                "[download_ayah_audio_file] Timeout attempt %d/%d for %s",
                attempt_index,
                REQUEST_RETRY_COUNT,
                audio_url,
            )
        except requests.exceptions.ConnectionError as conn_error:
            logger.warning(
                "[download_ayah_audio_file] Connection error attempt %d/%d: %s",
                attempt_index,
                REQUEST_RETRY_COUNT,
                conn_error,
            )
        except requests.exceptions.HTTPError as http_error:
            logger.error(
                "[download_ayah_audio_file] HTTP error for %s: %s",
                audio_url,
                http_error,
            )
            return False
        except OSError as file_write_error:
            logger.error(
                "[download_ayah_audio_file] File write error to %s: %s",
                save_path,
                file_write_error,
            )
            return False
        finally:
            if response_object is not None:
                response_object.close()

        if attempt_index < REQUEST_RETRY_COUNT:
            logger.info(
                "[download_ayah_audio_file] Retrying in %.1f seconds...",
                REQUEST_RETRY_DELAY_SECONDS,
            )
            time.sleep(REQUEST_RETRY_DELAY_SECONDS)

    logger.error(
        "[download_ayah_audio_file] All %d attempts failed for %s",
        REQUEST_RETRY_COUNT,
        audio_url,
    )
    return False


def build_master_audio_track(
    surah_number: int,
    start_ayah: int,
    end_ayah: int,
    reciter_name: str,
) -> Optional[Path]:
    """
    Download audio files for a range of Ayahs and concatenate them into a
    single master audio MP3 file. Returns the Path to the master track on
    success, or None if all downloads fail.

    MoviePy AudioFileClip objects are explicitly closed in the finally block.
    """
    reciter_folder: str = RECITER_MAP.get(reciter_name, RECITER_MAP["Alafasy"])
    logger.info(
        "[build_master_audio_track] Building track for Surah %d, Ayahs %d-%d "
        "using reciter folder: %s",
        surah_number,
        start_ayah,
        end_ayah,
        reciter_folder,
    )

    downloaded_audio_paths: List[Path] = []
    audio_clips_to_close: List[AudioFileClip] = []

    try:
        for ayah_index in range(start_ayah, end_ayah + 1):
            audio_save_path: Path = TEMP_DIR / f"ayah_{surah_number}_{ayah_index}.mp3"
            download_success: bool = download_ayah_audio_file(
                surah_number=surah_number,
                ayah_number=ayah_index,
                reciter_folder=reciter_folder,
                save_path=audio_save_path,
            )
            if download_success and audio_save_path.exists():
                downloaded_audio_paths.append(audio_save_path)
                logger.info(
                    "[build_master_audio_track] Queued audio: %s",
                    audio_save_path,
                )
            else:
                logger.warning(
                    "[build_master_audio_track] Skipping Ayah %d:%d — download failed.",
                    surah_number,
                    ayah_index,
                )

        if not downloaded_audio_paths:
            logger.error(
                "[build_master_audio_track] No audio files downloaded. Cannot build track."
            )
            return None

        individual_clips: List[AudioFileClip] = []
        for audio_path in downloaded_audio_paths:
            try:
                single_clip: AudioFileClip = AudioFileClip(str(audio_path))
                individual_clips.append(single_clip)
                audio_clips_to_close.append(single_clip)
                logger.debug(
                    "[build_master_audio_track] Loaded clip: %s (%.2fs)",
                    audio_path.name,
                    single_clip.duration,
                )
            except Exception as clip_load_error:
                logger.error(
                    "[build_master_audio_track] Failed to load clip %s: %s",
                    audio_path,
                    clip_load_error,
                )

        if not individual_clips:
            logger.error(
                "[build_master_audio_track] Could not load any audio clips into MoviePy."
            )
            return None

        master_clip = concatenate_audioclips(individual_clips)
        audio_clips_to_close.append(master_clip)

        master_audio_path: Path = TEMP_DIR / f"master_audio_{surah_number}_{start_ayah}_{end_ayah}.mp3"
        master_clip.write_audiofile(
            str(master_audio_path),
            codec="mp3",
            logger=None,
        )
        logger.info(
            "[build_master_audio_track] Master audio written: %s (%.2fs)",
            master_audio_path,
            master_clip.duration,
        )
        return master_audio_path

    except Exception as track_build_error:
        logger.error(
            "[build_master_audio_track] Unexpected error during track building: %s\n%s",
            track_build_error,
            traceback.format_exc(),
        )
        return None

    finally:
        for clip_to_close in audio_clips_to_close:
            try:
                clip_to_close.close()
                logger.debug(
                    "[build_master_audio_track] Closed audio clip: %s",
                    getattr(clip_to_close, "filename", "unknown"),
                )
            except Exception as close_error:
                logger.warning(
                    "[build_master_audio_track] Error closing clip: %s",
                    close_error,
                )


def fetch_pexels_background_video(surah_number: int) -> Optional[Path]:
    """
    Fetch a vertical (portrait) background video from the Pexels API based on
    Surah theme keywords. Prefer 1080x1920 resolution; accept 720x1280 as
    fallback. Stream-download the chosen video to temp_bg.mp4.

    Returns the Path to the downloaded video, or None if the API call fails.
    """
    theme_keywords: str = get_theme_keywords_for_surah(surah_number)
    search_query: str = theme_keywords.split(",")[0].strip()

    logger.info(
        "[fetch_pexels_background_video] Querying Pexels for: '%s'",
        search_query,
    )

    pexels_headers: Dict[str, str] = {
        "Authorization": PEXELS_API_KEY,
        "Accept": "application/json",
    }
    pexels_params: Dict[str, Any] = {
        "query": search_query,
        "orientation": "portrait",
        "size": "large",
        "per_page": MAX_PEXELS_RESULTS,
    }

    response_object: Optional[requests.Response] = None
    try:
        response_object = requests.get(
            PEXELS_VIDEO_API,
            headers=pexels_headers,
            params=pexels_params,
            timeout=HTTP_TIMEOUT_SECONDS,
        )
        response_object.raise_for_status()
        pexels_data: Dict[str, Any] = response_object.json()

        pexels_videos: List[Dict[str, Any]] = pexels_data.get("videos", [])
        if not pexels_videos:
            logger.warning(
                "[fetch_pexels_background_video] No videos returned from Pexels "
                "for query: '%s'",
                search_query,
            )
            return None

        logger.info(
            "[fetch_pexels_background_video] Pexels returned %d videos.",
            len(pexels_videos),
        )

        preferred_resolutions: List[Tuple[int, int]] = [
            (1080, 1920),
            (720, 1280),
            (540, 960),
        ]
        candidate_video_urls: List[str] = []

        for video_item in pexels_videos:
            video_files_list: List[Dict[str, Any]] = video_item.get("video_files", [])
            for video_file_entry in video_files_list:
                file_width: int = video_file_entry.get("width", 0)
                file_height: int = video_file_entry.get("height", 0)
                file_link: str = video_file_entry.get("link", "")
                file_type: str = video_file_entry.get("file_type", "")

                if "mp4" not in file_type and not file_link.endswith(".mp4"):
                    continue

                for pref_width, pref_height in preferred_resolutions:
                    if file_width == pref_width and file_height == pref_height:
                        candidate_video_urls.append(file_link)
                        logger.debug(
                            "[fetch_pexels_background_video] Candidate found: "
                            "%dx%d -> %s",
                            file_width,
                            file_height,
                            file_link[:80],
                        )
                        break

        if not candidate_video_urls:
            logger.warning(
                "[fetch_pexels_background_video] No matching resolution videos found. "
                "Attempting to use any portrait video from results."
            )
            for video_item in pexels_videos:
                video_files_list = video_item.get("video_files", [])
                for video_file_entry in video_files_list:
                    file_height = video_file_entry.get("height", 0)
                    file_width = video_file_entry.get("width", 0)
                    file_link = video_file_entry.get("link", "")
                    if file_height > file_width and file_link:
                        candidate_video_urls.append(file_link)
                        break
                if candidate_video_urls:
                    break

        if not candidate_video_urls:
            logger.error(
                "[fetch_pexels_background_video] No suitable video candidates found."
            )
            return None

        selected_url: str = random.choice(candidate_video_urls)
        logger.info(
            "[fetch_pexels_background_video] Selected video URL: %s",
            selected_url[:100],
        )

        return stream_download_video(
            video_url=selected_url,
            save_path=TEMP_DIR / "temp_bg.mp4",
        )

    except requests.exceptions.Timeout:
        logger.error(
            "[fetch_pexels_background_video] Pexels API request timed out."
        )
        return None
    except requests.exceptions.ConnectionError as connection_error:
        logger.error(
            "[fetch_pexels_background_video] Pexels API connection error: %s",
            connection_error,
        )
        return None
    except requests.exceptions.HTTPError as http_error:
        logger.error(
            "[fetch_pexels_background_video] Pexels HTTP error: %s", http_error
        )
        return None
    except (ValueError, KeyError) as parse_error:
        logger.error(
            "[fetch_pexels_background_video] JSON parse error: %s", parse_error
        )
        return None
    finally:
        if response_object is not None:
            response_object.close()


def stream_download_video(video_url: str, save_path: Path) -> Optional[Path]:
    """
    Stream-download a video file from a URL in chunks and save to disk.
    Returns the save_path on success, or None on failure.
    """
    logger.info(
        "[stream_download_video] Downloading video to: %s", save_path
    )
    response_object: Optional[requests.Response] = None
    try:
        response_object = requests.get(
            video_url,
            stream=True,
            timeout=HTTP_DOWNLOAD_TIMEOUT_SECONDS,
        )
        response_object.raise_for_status()

        total_bytes_written: int = 0
        chunk_size: int = 1024 * 256

        with open(save_path, "wb") as video_file_handle:
            for chunk in response_object.iter_content(chunk_size=chunk_size):
                if chunk:
                    video_file_handle.write(chunk)
                    total_bytes_written += len(chunk)

        logger.info(
            "[stream_download_video] Downloaded %.2f MB to %s",
            total_bytes_written / (1024 * 1024),
            save_path,
        )
        return save_path

    except requests.exceptions.Timeout:
        logger.error("[stream_download_video] Download timed out for: %s", video_url[:100])
        return None
    except requests.exceptions.ConnectionError as conn_error:
        logger.error("[stream_download_video] Connection error: %s", conn_error)
        return None
    except requests.exceptions.HTTPError as http_error:
        logger.error("[stream_download_video] HTTP error: %s", http_error)
        return None
    except OSError as file_error:
        logger.error("[stream_download_video] File write error: %s", file_error)
        return None
    finally:
        if response_object is not None:
            response_object.close()


def get_background_video_path(surah_number: int) -> Path:
    """
    Attempt to fetch a Pexels background video. If the fetch fails, fall back
    to the default background video at static/videos/default_bg.mp4. If even
    the default is missing, create a black fallback video clip and save it.

    Always returns a valid Path to a usable video file.
    """
    pexels_video_path: Optional[Path] = fetch_pexels_background_video(surah_number)

    if pexels_video_path is not None and pexels_video_path.exists():
        logger.info(
            "[get_background_video_path] Using Pexels video: %s", pexels_video_path
        )
        return pexels_video_path

    logger.warning(
        "[get_background_video_path] Pexels fetch failed. "
        "Falling back to static/videos/default_bg.mp4"
    )

    default_video_path: Path = STATIC_VIDEO_DIR / "default_bg.mp4"
    if default_video_path.exists():
        logger.info(
            "[get_background_video_path] Using default background: %s",
            default_video_path,
        )
        return default_video_path

    logger.warning(
        "[get_background_video_path] Default background video not found at %s. "
        "Generating a black placeholder background video.",
        default_video_path,
    )

    black_video_path: Path = TEMP_DIR / "black_placeholder_bg.mp4"
    black_clip: Optional[ColorClip] = None
    try:
        black_clip = ColorClip(
            size=(VIDEO_WIDTH, VIDEO_HEIGHT),
            color=(0, 0, 0),
            duration=60,
        )
        black_clip.write_videofile(
            str(black_video_path),
            fps=VIDEO_FPS,
            codec=VIDEO_CODEC,
            logger=None,
        )
        logger.info(
            "[get_background_video_path] Black placeholder video created: %s",
            black_video_path,
        )
        return black_video_path
    except Exception as placeholder_error:
        logger.error(
            "[get_background_video_path] Failed to create placeholder video: %s",
            placeholder_error,
        )
        raise RuntimeError(
            "Cannot produce any background video. "
            "Check MoviePy and FFmpeg installation."
        ) from placeholder_error
    finally:
        if black_clip is not None:
            try:
                black_clip.close()
            except Exception:
                pass


def build_ambient_audio_overlay(
    ambient_effect: str,
    quran_audio_duration: float,
) -> Optional[Any]:
    """
    Load an ambient audio asset (Rain or Echo) based on the selected effect,
    loop or trim it to match the Quran audio duration, and reduce its volume
    to AMBIENT_VOLUME_FACTOR (0.15).

    Returns a volumeX-adjusted AudioFileClip or None if loading fails.
    All clips loaded internally are closed in the finally block.
    """
    effect_audio_map: Dict[str, str] = {
        "Rain": str(STATIC_AUDIO_DIR / "rain_ambient.mp3"),
        "Echo": str(STATIC_AUDIO_DIR / "echo_ambient.mp3"),
    }

    if ambient_effect not in effect_audio_map:
        logger.info(
            "[build_ambient_audio_overlay] No ambient effect selected (effect='%s'). "
            "Skipping overlay.",
            ambient_effect,
        )
        return None

    effect_audio_path: str = effect_audio_map[ambient_effect]
    if not Path(effect_audio_path).exists():
        logger.warning(
            "[build_ambient_audio_overlay] Ambient audio file not found: %s. "
            "Skipping overlay.",
            effect_audio_path,
        )
        return None

    ambient_clip: Optional[AudioFileClip] = None
    try:
        ambient_clip = AudioFileClip(effect_audio_path)
        ambient_duration: float = ambient_clip.duration
        logger.info(
            "[build_ambient_audio_overlay] Loaded '%s' ambient audio: %.2fs",
            ambient_effect,
            ambient_duration,
        )

        if ambient_duration < quran_audio_duration:
            number_of_loops: int = int(quran_audio_duration / ambient_duration) + 2
            looped_clips: List[AudioFileClip] = [
                AudioFileClip(effect_audio_path) for _ in range(number_of_loops)
            ]
            concatenated_ambient: Any = concatenate_audioclips(looped_clips)
            trimmed_ambient: Any = concatenated_ambient.subclip(0, quran_audio_duration)

            for looped_clip in looped_clips:
                try:
                    looped_clip.close()
                except Exception:
                    pass

            ambient_adjusted: Any = trimmed_ambient.volumex(AMBIENT_VOLUME_FACTOR)
            logger.info(
                "[build_ambient_audio_overlay] Looped ambient to %.2fs at volume %.2f",
                quran_audio_duration,
                AMBIENT_VOLUME_FACTOR,
            )
            return ambient_adjusted
        else:
            trimmed_ambient = ambient_clip.subclip(0, quran_audio_duration)
            ambient_adjusted = trimmed_ambient.volumex(AMBIENT_VOLUME_FACTOR)
            ambient_clip = None
            logger.info(
                "[build_ambient_audio_overlay] Trimmed ambient to %.2fs at volume %.2f",
                quran_audio_duration,
                AMBIENT_VOLUME_FACTOR,
            )
            return ambient_adjusted

    except Exception as ambient_error:
        logger.error(
            "[build_ambient_audio_overlay] Error processing ambient audio '%s': %s\n%s",
            ambient_effect,
            ambient_error,
            traceback.format_exc(),
        )
        return None
    finally:
        if ambient_clip is not None:
            try:
                ambient_clip.close()
            except Exception:
                pass


def wrap_text_for_video(text: str, max_chars_per_line: int) -> str:
    """
    Wrap a text string so that no line exceeds max_chars_per_line characters.
    Returns the wrapped string with newlines.
    """
    lines: List[str] = textwrap.wrap(text, width=max_chars_per_line)
    return "\n".join(lines)


def generate_quran_reel_video(
    surah_number: int,
    start_ayah: int,
    end_ayah: int,
    reciter_name: str,
    ambient_effect: str,
    webhook_url: str,
) -> Dict[str, Any]:
    """
    Main orchestration function. Executes the full video production pipeline:

    1. Ensure directory structure exists.
    2. Fetch Ayah text data (Arabic + English).
    3. Build the master audio track from downloaded recitation files.
    4. Retrieve or fallback to a background video.
    5. Compose the ambient audio overlay if requested.
    6. Build the composite video with text overlays, dimming, and audio.
    7. Render the final MP4 to the outputs/ directory.
    8. Optionally publish to a webhook.

    Returns a result dict with keys: 'success' (bool), 'output_path' (str),
    'message' (str).
    """
    logger.info(
        "=" * 70 +
        "\n[generate_quran_reel_video] Starting pipeline: "
        "Surah %d, Ayahs %d-%d, Reciter='%s', Effect='%s'"
        "\n" + "=" * 70,
        surah_number,
        start_ayah,
        end_ayah,
        reciter_name,
        ambient_effect,
    )

    clips_to_close: List[Any] = []

    try:
        ensure_directories_exist()

        # ── Step 1: Fetch All Ayah Text Data ─────────────────────────────────
        logger.info("[generate_quran_reel_video] Step 1: Fetching Ayah text data...")
        all_arabic_texts: List[str] = []
        all_english_texts: List[str] = []

        for ayah_index in range(start_ayah, end_ayah + 1):
            ayah_data: Optional[Dict[str, Any]] = fetch_ayah_data(
                surah_number=surah_number,
                ayah_number=ayah_index,
            )
            if ayah_data:
                all_arabic_texts.append(ayah_data["arabic"])
                all_english_texts.append(ayah_data["english"])
            else:
                logger.warning(
                    "[generate_quran_reel_video] Missing text for %d:%d, using placeholder.",
                    surah_number,
                    ayah_index,
                )
                all_arabic_texts.append("﷽")
                all_english_texts.append("[Translation unavailable]")

        combined_arabic_raw: str = "  ۝  ".join(all_arabic_texts)
        combined_english_raw: str = "  |  ".join(all_english_texts)

        logger.info(
            "[generate_quran_reel_video] Combined Arabic length: %d chars",
            len(combined_arabic_raw),
        )

        # ── Step 2: Apply RTL Arabic Reshaping ───────────────────────────────
        logger.info("[generate_quran_reel_video] Step 2: Applying Arabic RTL reshaping...")
        combined_arabic_bidi: str = apply_arabic_reshaping_and_bidi(combined_arabic_raw)
        combined_english_wrapped: str = wrap_text_for_video(combined_english_raw, 42)

        # ── Step 3: Build Master Audio Track ─────────────────────────────────
        logger.info("[generate_quran_reel_video] Step 3: Building master audio track...")
        master_audio_path: Optional[Path] = build_master_audio_track(
            surah_number=surah_number,
            start_ayah=start_ayah,
            end_ayah=end_ayah,
            reciter_name=reciter_name,
        )

        if master_audio_path is None or not master_audio_path.exists():
            logger.error(
                "[generate_quran_reel_video] Master audio track unavailable. Aborting."
            )
            return {
                "success": False,
                "output_path": "",
                "message": "Failed to build audio track. Check reciter download URLs.",
            }

        # ── Step 4: Load Audio and Get Duration ──────────────────────────────
        logger.info("[generate_quran_reel_video] Step 4: Loading master audio clip...")
        quran_audio_clip: AudioFileClip = AudioFileClip(str(master_audio_path))
        clips_to_close.append(quran_audio_clip)
        quran_duration: float = quran_audio_clip.duration
        logger.info(
            "[generate_quran_reel_video] Master audio duration: %.2f seconds",
            quran_duration,
        )

        # ── Step 5: Get Background Video ─────────────────────────────────────
        logger.info("[generate_quran_reel_video] Step 5: Retrieving background video...")
        background_video_path: Path = get_background_video_path(surah_number)

        raw_background_clip: VideoFileClip = VideoFileClip(
            str(background_video_path),
            audio=False,
        )
        clips_to_close.append(raw_background_clip)

        # Loop background if shorter than audio, then trim to exact duration
        if raw_background_clip.duration < quran_duration:
            loops_needed: int = int(quran_duration / raw_background_clip.duration) + 2
            from moviepy.editor import concatenate_videoclips
            looped_clips_list: List[VideoFileClip] = [
                VideoFileClip(str(background_video_path), audio=False)
                for _ in range(loops_needed)
            ]
            for lc in looped_clips_list:
                clips_to_close.append(lc)
            background_clip_full = concatenate_videoclips(looped_clips_list)
            clips_to_close.append(background_clip_full)
        else:
            background_clip_full = raw_background_clip

        background_clip_trimmed = background_clip_full.subclip(0, quran_duration)
        clips_to_close.append(background_clip_trimmed)

        # Resize to target portrait dimensions
        background_clip_resized = background_clip_trimmed.resize(
            (VIDEO_WIDTH, VIDEO_HEIGHT)
        )
        clips_to_close.append(background_clip_resized)
        logger.info(
            "[generate_quran_reel_video] Background clip prepared: "
            "%dx%d, %.2fs",
            VIDEO_WIDTH,
            VIDEO_HEIGHT,
            quran_duration,
        )

        # ── Step 6: Create Dimming Overlay ────────────────────────────────────
        logger.info("[generate_quran_reel_video] Step 6: Adding dimming overlay...")
        dim_overlay: ColorClip = ColorClip(
            size=(VIDEO_WIDTH, VIDEO_HEIGHT),
            color=(0, 0, 0),
            duration=quran_duration,
        ).set_opacity(0.50)
        clips_to_close.append(dim_overlay)

        # ── Step 7: Create Text Clips ─────────────────────────────────────────
        logger.info("[generate_quran_reel_video] Step 7: Creating text clips...")
        font_path: str = str(BASE_DIR / FONTS_DIR)

        if not Path(font_path).exists():
            logger.warning(
                "[generate_quran_reel_video] Font not found at %s. "
                "Using 'DejaVu-Sans' system fallback.",
                font_path,
            )
            font_path = "DejaVu-Sans"

        arabic_text_clip: TextClip = TextClip(
            combined_arabic_bidi,
            fontsize=72,
            font=font_path,
            color="white",
            stroke_color="black",
            stroke_width=2,
            method="caption",
            size=(VIDEO_WIDTH - 100, None),
            align="center",
        ).set_duration(quran_duration).set_pos(("center", "center"))
        clips_to_close.append(arabic_text_clip)
        logger.info(
            "[generate_quran_reel_video] Arabic text clip created: %s",
            arabic_text_clip.size,
        )

        english_text_clip: TextClip = TextClip(
            combined_english_wrapped,
            fontsize=36,
            font=font_path if Path(font_path).exists() else "DejaVu-Sans",
            color="#FFD700",
            stroke_color="black",
            stroke_width=1,
            method="caption",
            size=(VIDEO_WIDTH - 100, None),
            align="center",
        ).set_duration(quran_duration).set_pos(("center", 1400))
        clips_to_close.append(english_text_clip)
        logger.info(
            "[generate_quran_reel_video] English translation clip created: %s",
            english_text_clip.size,
        )

        # ── Step 8: Compose Video Layers ─────────────────────────────────────
        logger.info("[generate_quran_reel_video] Step 8: Compositing video layers...")
        composite_video_layers: List[Any] = [
            background_clip_resized,
            dim_overlay,
            arabic_text_clip,
            english_text_clip,
        ]
        composite_video: CompositeVideoClip = CompositeVideoClip(
            composite_video_layers,
            size=(VIDEO_WIDTH, VIDEO_HEIGHT),
        )
        clips_to_close.append(composite_video)

        # ── Step 9: Compose Audio Track ───────────────────────────────────────
        logger.info("[generate_quran_reel_video] Step 9: Composing audio tracks...")
        ambient_overlay_clip: Optional[Any] = build_ambient_audio_overlay(
            ambient_effect=ambient_effect,
            quran_audio_duration=quran_duration,
        )

        if ambient_overlay_clip is not None:
            clips_to_close.append(ambient_overlay_clip)
            final_audio_clip: Any = CompositeAudioClip(
                [quran_audio_clip, ambient_overlay_clip]
            )
            clips_to_close.append(final_audio_clip)
            logger.info(
                "[generate_quran_reel_video] Composited Quran + '%s' ambient audio.",
                ambient_effect,
            )
        else:
            final_audio_clip = quran_audio_clip
            logger.info(
                "[generate_quran_reel_video] Using Quran audio only (no ambient overlay)."
            )

        composite_video_with_audio: Any = composite_video.set_audio(final_audio_clip)
        clips_to_close.append(composite_video_with_audio)

        # ── Step 10: Render Output File ───────────────────────────────────────
        unique_hash: str = hashlib.md5(
            f"{surah_number}_{start_ayah}_{end_ayah}_{reciter_name}_{time.time()}".encode()
        ).hexdigest()[:10]
        output_filename: str = f"quran_reel_{surah_number}_{start_ayah}_{end_ayah}_{unique_hash}.mp4"
        output_file_path: Path = OUTPUTS_DIR / output_filename

        logger.info(
            "[generate_quran_reel_video] Step 10: Rendering to: %s",
            output_file_path,
        )

        composite_video_with_audio.write_videofile(
            str(output_file_path),
            fps=VIDEO_FPS,
            codec=VIDEO_CODEC,
            audio_codec=AUDIO_CODEC,
            temp_audiofile=str(TEMP_DIR / f"temp_audio_{unique_hash}.m4a"),
            remove_temp=True,
            threads=2,
            logger=None,
        )

        if not output_file_path.exists():
            logger.error(
                "[generate_quran_reel_video] Output file not found after render: %s",
                output_file_path,
            )
            return {
                "success": False,
                "output_path": "",
                "message": f"Render completed but output file missing: {output_filename}",
            }

        output_size_mb: float = output_file_path.stat().st_size / (1024 * 1024)
        logger.info(
            "[generate_quran_reel_video] Render complete! File: %s (%.2f MB)",
            output_file_path,
            output_size_mb,
        )

        # ── Step 11: Optional Webhook Publishing ──────────────────────────────
        if webhook_url and webhook_url.strip():
            logger.info(
                "[generate_quran_reel_video] Step 11: Publishing to webhook: %s",
                webhook_url,
            )
            publish_to_webhook(
                output_video_path=output_file_path,
                webhook_url=webhook_url.strip(),
                surah_number=surah_number,
                start_ayah=start_ayah,
                end_ayah=end_ayah,
            )
        else:
            logger.info(
                "[generate_quran_reel_video] Step 11: No webhook URL provided. Skipping."
            )

        return {
            "success": True,
            "output_path": f"outputs/{output_filename}",
            "message": (
                f"Reel generated successfully for Surah {surah_number} "
                f"Ayahs {start_ayah}-{end_ayah}."
            ),
        }

    except Exception as pipeline_error:
        logger.error(
            "[generate_quran_reel_video] Pipeline failed with exception: %s\n%s",
            pipeline_error,
            traceback.format_exc(),
        )
        return {
            "success": False,
            "output_path": "",
            "message": f"Video generation failed: {str(pipeline_error)}",
        }

    finally:
        logger.info(
            "[generate_quran_reel_video] Cleaning up %d open clips...",
            len(clips_to_close),
        )
        for clip_instance in reversed(clips_to_close):
            try:
                clip_instance.close()
                logger.debug(
                    "[generate_quran_reel_video] Closed clip: %s",
                    type(clip_instance).__name__,
                )
            except Exception as close_error:
                logger.warning(
                    "[generate_quran_reel_video] Error closing clip %s: %s",
                    type(clip_instance).__name__,
                    close_error,
                )
        logger.info(
            "[generate_quran_reel_video] Cleanup complete. Pipeline finished."
        )


def publish_to_webhook(
    output_video_path: Path,
    webhook_url: str,
    surah_number: int,
    start_ayah: int,
    end_ayah: int,
) -> None:
    """
    Publish the completed reel video to a remote webhook URL using multipart
    form-data HTTP POST. Includes metadata fields alongside the video binary.

    This function logs results but does not raise exceptions to avoid blocking
    the main generation pipeline on webhook errors.
    """
    logger.info(
        "[publish_to_webhook] Sending reel to webhook: %s", webhook_url
    )

    if not output_video_path.exists():
        logger.error(
            "[publish_to_webhook] Video file not found: %s. Cannot publish.",
            output_video_path,
        )
        return

    response_object: Optional[requests.Response] = None
    video_file_handle = None

    try:
        video_file_handle = open(output_video_path, "rb")
        multipart_payload: Dict[str, Any] = {
            "video": (
                output_video_path.name,
                video_file_handle,
                "video/mp4",
            ),
        }
        metadata_fields: Dict[str, str] = {
            "surah": str(surah_number),
            "start_ayah": str(start_ayah),
            "end_ayah": str(end_ayah),
            "source": "Quran Reels Maker",
            "generated_at": str(int(time.time())),
        }

        response_object = requests.post(
            webhook_url,
            files=multipart_payload,
            data=metadata_fields,
            timeout=HTTP_DOWNLOAD_TIMEOUT_SECONDS,
        )
        response_object.raise_for_status()

        logger.info(
            "[publish_to_webhook] Webhook published successfully. "
            "HTTP %d response from %s",
            response_object.status_code,
            webhook_url,
        )

    except requests.exceptions.Timeout:
        logger.error(
            "[publish_to_webhook] Webhook request timed out for: %s", webhook_url
        )
    except requests.exceptions.ConnectionError as webhook_conn_error:
        logger.error(
            "[publish_to_webhook] Connection error to webhook: %s", webhook_conn_error
        )
    except requests.exceptions.HTTPError as webhook_http_error:
        logger.error(
            "[publish_to_webhook] HTTP error from webhook: %s", webhook_http_error
        )
    except OSError as file_open_error:
        logger.error(
            "[publish_to_webhook] Cannot open video file for upload: %s",
            file_open_error,
        )
    except Exception as webhook_unexpected_error:
        logger.error(
            "[publish_to_webhook] Unexpected webhook error: %s\n%s",
            webhook_unexpected_error,
            traceback.format_exc(),
        )
    finally:
        if video_file_handle is not None:
            try:
                video_file_handle.close()
            except Exception:
                pass
        if response_object is not None:
            try:
                response_object.close()
            except Exception:
                pass


if __name__ == "__main__":
    logger.info("[video_engine] Running standalone engine test...")
    test_result: Dict[str, Any] = generate_quran_reel_video(
        surah_number=55,
        start_ayah=1,
        end_ayah=4,
        reciter_name="Alafasy",
        ambient_effect="Rain",
        webhook_url="",
    )
    logger.info("[video_engine] Test result: %s", test_result)
