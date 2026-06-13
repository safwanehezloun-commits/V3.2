"""
app.py — Quran Reels Maker: Flask Server Router Gateway
=========================================================
Initializes the Flask web server, configures CORS, and defines all API
endpoints for the Quran Reels Maker application.

Endpoints:
    GET  /           -> Renders the dashboard interface.
    POST /generate   -> Triggers the full video generation pipeline.
    GET  /outputs/<filename> -> Serves generated video files for preview.
"""

import os
import sys
import logging
import traceback

from pathlib import Path
from typing import Any, Dict, Tuple, Union

# ─── Flask and Extensions ────────────────────────────────────────────────────
try:
    from flask import (
        Flask,
        render_template,
        request,
        jsonify,
        send_from_directory,
        Response,
    )
except ImportError as flask_import_error:
    print(
        f"[app.py] FATAL: Flask is not installed. "
        f"Run: pip install flask  |  Error: {flask_import_error}"
    )
    sys.exit(1)

try:
    from flask_cors import CORS
except ImportError as cors_import_error:
    print(
        f"[app.py] WARNING: flask-cors is not installed. "
        f"CORS will not be configured. Run: pip install flask-cors  |  "
        f"Error: {cors_import_error}"
    )
    CORS = None

# ─── Internal Engine Import ───────────────────────────────────────────────────
try:
    from video_engine import generate_quran_reel_video, RECITER_MAP
except ImportError as engine_import_error:
    print(
        f"[app.py] FATAL: Cannot import video_engine. "
        f"Ensure video_engine.py is in the same directory.  "
        f"Error: {engine_import_error}"
    )
    sys.exit(1)

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
logger: logging.Logger = logging.getLogger("app")

# ─── Application Constants ───────────────────────────────────────────────────
BASE_DIR: Path = Path(__file__).resolve().parent
OUTPUTS_DIR: Path = BASE_DIR / "outputs"
TEMPLATES_DIR: Path = BASE_DIR / "templates"
STATIC_DIR: Path = BASE_DIR / "static"

VALID_AMBIENT_EFFECTS: list = ["None", "Rain", "Echo"]
MIN_SURAH: int = 1
MAX_SURAH: int = 114
MIN_AYAH: int = 1
MAX_AYAH_LIMIT: int = 286

# ─── Flask Application Factory ───────────────────────────────────────────────
def create_application() -> Flask:
    """
    Create, configure, and return the Flask application instance.
    Sets up CORS, output directories, and all route handlers.
    """
    app: Flask = Flask(
        __name__,
        template_folder=str(TEMPLATES_DIR),
        static_folder=str(STATIC_DIR),
    )

    app.config["SECRET_KEY"] = os.environ.get(
        "FLASK_SECRET_KEY", "quran-reels-dev-secret-2024"
    )
    app.config["MAX_CONTENT_LENGTH"] = 500 * 1024 * 1024
    app.config["JSON_AS_ASCII"] = False
    app.config["JSONIFY_MIMETYPE"] = "application/json; charset=utf-8"

    if CORS is not None:
        CORS(
            app,
            resources={r"/*": {"origins": "*"}},
            supports_credentials=False,
        )
        logger.info("[create_application] CORS configured for all origins.")
    else:
        logger.warning(
            "[create_application] flask-cors not available. "
            "CORS headers will not be set."
        )

    try:
        OUTPUTS_DIR.mkdir(parents=True, exist_ok=True)
        logger.info(
            "[create_application] Outputs directory verified: %s", OUTPUTS_DIR
        )
    except OSError as dir_error:
        logger.error(
            "[create_application] Failed to create outputs directory: %s",
            dir_error,
        )

    # ── Route: Dashboard ──────────────────────────────────────────────────────
    @app.route("/", methods=["GET"])
    def dashboard() -> Union[str, Tuple[str, int]]:
        """
        Render the unified Quran Reels Maker dashboard HTML interface.
        Passes the list of available reciters to the template context.
        """
        logger.info("[dashboard] GET / requested from %s", request.remote_addr)
        try:
            reciter_names: list = list(RECITER_MAP.keys())
            return render_template(
                "index.html",
                reciters=reciter_names,
                ambient_effects=VALID_AMBIENT_EFFECTS,
            )
        except Exception as render_error:
            logger.error(
                "[dashboard] Template render failed: %s\n%s",
                render_error,
                traceback.format_exc(),
            )
            return (
                "<h1>Server Error</h1><p>Dashboard template could not be rendered. "
                "Check logs for details.</p>",
                500,
            )

    # ── Route: Generate Video ─────────────────────────────────────────────────
    @app.route("/generate", methods=["POST"])
    def generate() -> Tuple[Response, int]:
        """
        Accept a JSON payload and trigger the video generation pipeline.

        Expected JSON body:
        {
            "surah":       int (1-114),
            "start_ayah":  int (>= 1),
            "end_ayah":    int (>= start_ayah),
            "reciter":     str (one of RECITER_MAP keys),
            "effect":      str ("None", "Rain", or "Echo"),
            "webhook_url": str (optional, empty string if unused)
        }

        Returns a JSON response with:
        {
            "success":     bool,
            "output_path": str,
            "message":     str
        }
        """
        client_ip: str = request.remote_addr or "unknown"
        logger.info("[generate] POST /generate from %s", client_ip)

        # ── Parse Request Body ────────────────────────────────────────────────
        incoming_data: Any = None
        try:
            incoming_data = request.get_json(force=True, silent=True)
        except Exception as json_parse_error:
            logger.warning(
                "[generate] JSON body parse error: %s", json_parse_error
            )

        if not isinstance(incoming_data, dict):
            logger.warning(
                "[generate] Invalid or missing JSON body from %s", client_ip
            )
            return (
                jsonify({
                    "success": False,
                    "output_path": "",
                    "message": (
                        "Invalid request body. "
                        "Expected a JSON object with keys: "
                        "surah, start_ayah, end_ayah, reciter, effect, webhook_url."
                    ),
                }),
                400,
            )

        # ── Extract and Validate Parameters ───────────────────────────────────
        raw_surah: Any = incoming_data.get("surah")
        raw_start_ayah: Any = incoming_data.get("start_ayah")
        raw_end_ayah: Any = incoming_data.get("end_ayah")
        raw_reciter: Any = incoming_data.get("reciter", "Alafasy")
        raw_effect: Any = incoming_data.get("effect", "None")
        raw_webhook_url: Any = incoming_data.get("webhook_url", "")

        logger.debug(
            "[generate] Raw params: surah=%s, start_ayah=%s, end_ayah=%s, "
            "reciter=%s, effect=%s, webhook_url=%s",
            raw_surah,
            raw_start_ayah,
            raw_end_ayah,
            raw_reciter,
            raw_effect,
            str(raw_webhook_url)[:60] if raw_webhook_url else "",
        )

        # Validate surah number
        try:
            surah_number: int = int(raw_surah)
        except (TypeError, ValueError):
            return (
                jsonify({
                    "success": False,
                    "output_path": "",
                    "message": f"Invalid 'surah' value: '{raw_surah}'. Must be an integer.",
                }),
                400,
            )

        if not (MIN_SURAH <= surah_number <= MAX_SURAH):
            return (
                jsonify({
                    "success": False,
                    "output_path": "",
                    "message": (
                        f"'surah' must be between {MIN_SURAH} and {MAX_SURAH}. "
                        f"Received: {surah_number}"
                    ),
                }),
                400,
            )

        # Validate start_ayah
        try:
            start_ayah: int = int(raw_start_ayah)
        except (TypeError, ValueError):
            return (
                jsonify({
                    "success": False,
                    "output_path": "",
                    "message": (
                        f"Invalid 'start_ayah' value: '{raw_start_ayah}'. "
                        "Must be an integer."
                    ),
                }),
                400,
            )

        if start_ayah < MIN_AYAH:
            return (
                jsonify({
                    "success": False,
                    "output_path": "",
                    "message": (
                        f"'start_ayah' must be >= {MIN_AYAH}. "
                        f"Received: {start_ayah}"
                    ),
                }),
                400,
            )

        # Validate end_ayah
        try:
            end_ayah: int = int(raw_end_ayah)
        except (TypeError, ValueError):
            return (
                jsonify({
                    "success": False,
                    "output_path": "",
                    "message": (
                        f"Invalid 'end_ayah' value: '{raw_end_ayah}'. "
                        "Must be an integer."
                    ),
                }),
                400,
            )

        if end_ayah < start_ayah:
            return (
                jsonify({
                    "success": False,
                    "output_path": "",
                    "message": (
                        f"'end_ayah' ({end_ayah}) must be >= 'start_ayah' ({start_ayah})."
                    ),
                }),
                400,
            )

        if end_ayah > MAX_AYAH_LIMIT:
            return (
                jsonify({
                    "success": False,
                    "output_path": "",
                    "message": (
                        f"'end_ayah' cannot exceed {MAX_AYAH_LIMIT}. "
                        f"Received: {end_ayah}"
                    ),
                }),
                400,
            )

        total_ayahs_requested: int = end_ayah - start_ayah + 1
        if total_ayahs_requested > 20:
            return (
                jsonify({
                    "success": False,
                    "output_path": "",
                    "message": (
                        f"Maximum 20 Ayahs per reel. "
                        f"Requested: {total_ayahs_requested}. "
                        f"Please reduce the range."
                    ),
                }),
                400,
            )

        # Validate reciter
        reciter_name: str = str(raw_reciter).strip()
        if reciter_name not in RECITER_MAP:
            logger.warning(
                "[generate] Unknown reciter '%s'. Defaulting to 'Alafasy'.",
                reciter_name,
            )
            reciter_name = "Alafasy"

        # Validate ambient effect
        ambient_effect: str = str(raw_effect).strip()
        if ambient_effect not in VALID_AMBIENT_EFFECTS:
            logger.warning(
                "[generate] Unknown effect '%s'. Defaulting to 'None'.",
                ambient_effect,
            )
            ambient_effect = "None"

        # Clean webhook URL
        webhook_url: str = str(raw_webhook_url).strip() if raw_webhook_url else ""

        logger.info(
            "[generate] Validated params: Surah=%d, Ayahs=%d-%d, "
            "Reciter='%s', Effect='%s', Webhook='%s'",
            surah_number,
            start_ayah,
            end_ayah,
            reciter_name,
            ambient_effect,
            webhook_url[:60] if webhook_url else "(none)",
        )

        # ── Execute Pipeline ──────────────────────────────────────────────────
        try:
            result: Dict[str, Any] = generate_quran_reel_video(
                surah_number=surah_number,
                start_ayah=start_ayah,
                end_ayah=end_ayah,
                reciter_name=reciter_name,
                ambient_effect=ambient_effect,
                webhook_url=webhook_url,
            )

            http_status: int = 200 if result.get("success") else 500
            logger.info(
                "[generate] Pipeline result: success=%s, HTTP %d, message='%s'",
                result.get("success"),
                http_status,
                result.get("message", ""),
            )
            return jsonify(result), http_status

        except Exception as pipeline_exception:
            error_message: str = (
                f"Internal server error during video generation: "
                f"{str(pipeline_exception)}"
            )
            logger.error(
                "[generate] Unhandled pipeline exception: %s\n%s",
                pipeline_exception,
                traceback.format_exc(),
            )
            return (
                jsonify({
                    "success": False,
                    "output_path": "",
                    "message": error_message,
                }),
                500,
            )

    # ── Route: Serve Output Videos ────────────────────────────────────────────
    @app.route("/outputs/<path:filename>", methods=["GET"])
    def serve_output_file(filename: str) -> Union[Response, Tuple[Response, int]]:
        """
        Serve a generated video file from the outputs/ directory.
        Validates the filename to prevent directory traversal attacks.
        """
        logger.info(
            "[serve_output_file] Serving file: '%s' to %s",
            filename,
            request.remote_addr,
        )

        safe_filename: str = Path(filename).name
        if safe_filename != filename or ".." in filename or filename.startswith("/"):
            logger.warning(
                "[serve_output_file] Suspicious filename rejected: '%s'", filename
            )
            return (
                jsonify({"success": False, "message": "Invalid filename."}),
                400,
            )

        try:
            return send_from_directory(
                str(OUTPUTS_DIR),
                safe_filename,
                mimetype="video/mp4",
                as_attachment=False,
            )
        except FileNotFoundError:
            logger.warning(
                "[serve_output_file] File not found in outputs: '%s'", safe_filename
            )
            return (
                jsonify({
                    "success": False,
                    "message": f"Output file not found: {safe_filename}",
                }),
                404,
            )
        except Exception as serve_error:
            logger.error(
                "[serve_output_file] Error serving '%s': %s", safe_filename, serve_error
            )
            return (
                jsonify({
                    "success": False,
                    "message": "Error serving the requested file.",
                }),
                500,
            )

    # ── Route: Health Check ───────────────────────────────────────────────────
    @app.route("/health", methods=["GET"])
    def health_check() -> Tuple[Response, int]:
        """
        Simple health check endpoint. Returns application status and
        available reciters for monitoring and readiness probes.
        """
        logger.debug("[health_check] Health check requested.")
        return (
            jsonify({
                "status": "healthy",
                "application": "Quran Reels Maker",
                "version": "1.0.0",
                "available_reciters": list(RECITER_MAP.keys()),
                "available_effects": VALID_AMBIENT_EFFECTS,
            }),
            200,
        )

    # ── Error Handlers ────────────────────────────────────────────────────────
    @app.errorhandler(404)
    def handle_not_found(error: Any) -> Tuple[Response, int]:
        """Return a JSON 404 error response."""
        logger.warning("[handle_not_found] 404: %s", request.url)
        return (
            jsonify({
                "success": False,
                "message": f"Endpoint not found: {request.path}",
            }),
            404,
        )

    @app.errorhandler(405)
    def handle_method_not_allowed(error: Any) -> Tuple[Response, int]:
        """Return a JSON 405 error response."""
        logger.warning(
            "[handle_method_not_allowed] 405: %s %s",
            request.method,
            request.url,
        )
        return (
            jsonify({
                "success": False,
                "message": (
                    f"Method '{request.method}' not allowed for path: {request.path}"
                ),
            }),
            405,
        )

    @app.errorhandler(413)
    def handle_request_too_large(error: Any) -> Tuple[Response, int]:
        """Return a JSON 413 error response for oversized uploads."""
        logger.warning("[handle_request_too_large] 413: Request entity too large.")
        return (
            jsonify({
                "success": False,
                "message": "Request payload too large.",
            }),
            413,
        )

    @app.errorhandler(500)
    def handle_internal_error(error: Any) -> Tuple[Response, int]:
        """Return a JSON 500 error response for unhandled server exceptions."""
        logger.error(
            "[handle_internal_error] 500 Internal Server Error: %s", error
        )
        return (
            jsonify({
                "success": False,
                "message": "An internal server error occurred. Check server logs.",
            }),
            500,
        )

    logger.info(
        "[create_application] Flask application created successfully. "
        "Routes registered: /, /generate, /outputs/<filename>, /health"
    )
    return app


# ─── Application Entry Point ─────────────────────────────────────────────────
application: Flask = create_application()

if __name__ == "__main__":
    host: str = os.environ.get("FLASK_HOST", "0.0.0.0")
    port_str: str = os.environ.get("FLASK_PORT", "5000")
    debug_mode: bool = os.environ.get("FLASK_DEBUG", "false").lower() == "true"

    try:
        port_number: int = int(port_str)
    except ValueError:
        logger.warning(
            "[main] Invalid FLASK_PORT '%s'. Defaulting to 5000.", port_str
        )
        port_number = 5000

    logger.info(
        "[main] Starting Quran Reels Maker server on %s:%d (debug=%s)",
        host,
        port_number,
        debug_mode,
    )

    try:
        application.run(
            host=host,
            port=port_number,
            debug=debug_mode,
            use_reloader=False,
            threaded=False,
        )
    except OSError as server_startup_error:
        logger.error(
            "[main] Failed to start server on port %d: %s",
            port_number,
            server_startup_error,
        )
        sys.exit(1)
    except KeyboardInterrupt:
        logger.info("[main] Server shutdown requested via keyboard interrupt.")
        sys.exit(0)
