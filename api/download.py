import base64
import importlib.util
import json
import os
from dataclasses import dataclass
from http.server import BaseHTTPRequestHandler
from urllib.parse import parse_qsl, urlencode, urlparse, urlunparse


YT_DLP_TIMEOUT_SECONDS = 45
COOKIE_FILE_PATH = "/tmp/youtube-cookies.txt"


@dataclass
class DownloadError(Exception):
    message: str
    status: int = 200


class handler(BaseHTTPRequestHandler):
    def do_POST(self):
        try:
            payload = self.read_json()
            result = resolve_download(payload)
            self.send_json({"file": result})
        except ValueError as exc:
            self.send_json({"error": str(exc)}, status=400)
        except DownloadError as exc:
            self.send_json({"error": exc.message}, status=exc.status)
        except Exception:
            self.send_json(
                {"error": "Erro interno ao preparar o download. Confira os logs da Vercel."},
                status=500,
            )

    def do_OPTIONS(self):
        self.send_response(204)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.end_headers()

    def read_json(self):
        length = int(self.headers.get("content-length", "0"))
        if length <= 0:
            raise ValueError("Envie um link para baixar.")

        try:
            return json.loads(self.rfile.read(length))
        except json.JSONDecodeError as exc:
            raise ValueError("O pedido enviado pelo navegador é inválido.") from exc

    def send_json(self, payload, status=200):
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


def resolve_download(payload):
    if not isinstance(payload, dict):
        raise ValueError("O pedido enviado pelo navegador é inválido.")

    url = normalize_video_url(str(payload.get("url", "")).strip())
    media_format = payload.get("format", "best")

    if not url.startswith(("http://", "https://")):
        raise ValueError("Cole um link válido começando com http:// ou https://.")

    if media_format not in {"best", "audio"}:
        raise ValueError("Escolha um formato válido para o download.")

    if importlib.util.find_spec("yt_dlp") is None:
        raise DownloadError("yt-dlp não está disponível no runtime da Vercel.", status=503)

    if media_format == "audio":
        format_selector = "bestaudio[ext=m4a]/bestaudio/best"
        fallback_extension = "m4a"
    else:
        format_selector = "best[ext=mp4][vcodec!=none][acodec!=none]/best[vcodec!=none][acodec!=none]/best"
        fallback_extension = "mp4"

    info = extract_video_info(url, format_selector)
    direct_url = get_direct_url(info)
    if not direct_url:
        raise DownloadError("Não foi possível gerar um link direto para esse vídeo.")

    if not direct_url.startswith(("http://", "https://")):
        raise DownloadError("Não foi possível gerar um link direto para esse vídeo.")

    title = sanitize_filename(info.get("title") or "video")
    extension = clean_extension(info.get("ext") or fallback_extension)

    return {
        "name": f"{title}.{extension}",
        "size": 0,
        "url": direct_url,
        "external": True,
    }


def normalize_video_url(url):
    parsed = urlparse(url)
    host = parsed.netloc.lower().removeprefix("www.").removeprefix("m.")

    if host in {"youtube.com", "music.youtube.com"}:
        return normalize_youtube_url(parsed)

    if host == "youtu.be":
        return normalize_youtube_short_url(parsed)

    return url


def normalize_youtube_url(parsed):
    query = dict(parse_qsl(parsed.query, keep_blank_values=False))
    path = parsed.path.rstrip("/")

    if path == "/watch" and query.get("v"):
        clean_query = {"v": query["v"]}
        add_time_parameter(query, clean_query)
        return urlunparse(("https", "www.youtube.com", "/watch", "", urlencode(clean_query), ""))

    if path.startswith(("/shorts/", "/embed/", "/live/")):
        path_parts = path.strip("/").split("/")
        video_id = path_parts[1] if len(path_parts) > 1 else ""
        if video_id:
            clean_query = {"v": video_id}
            add_time_parameter(query, clean_query)
            return urlunparse(("https", "www.youtube.com", "/watch", "", urlencode(clean_query), ""))

    return urlunparse((parsed.scheme, parsed.netloc, parsed.path, "", "", ""))


def normalize_youtube_short_url(parsed):
    video_id = parsed.path.strip("/").split("/")[0]
    if not video_id:
        return urlunparse((parsed.scheme, parsed.netloc, parsed.path, "", "", ""))

    query = dict(parse_qsl(parsed.query, keep_blank_values=False))
    clean_query = {"v": video_id}
    add_time_parameter(query, clean_query)
    return urlunparse(("https", "www.youtube.com", "/watch", "", urlencode(clean_query), ""))


def add_time_parameter(source_query, target_query):
    start_time = source_query.get("t") or source_query.get("start")
    if start_time:
        target_query["t"] = start_time


def extract_video_info(url, format_selector):
    from yt_dlp import YoutubeDL
    from yt_dlp.utils import DownloadError as YtDlpDownloadError

    options = {
        "format": format_selector,
        "noplaylist": True,
        "quiet": True,
        "no_warnings": True,
        "socket_timeout": YT_DLP_TIMEOUT_SECONDS,
        "source_address": "0.0.0.0",
        "http_headers": {
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/124.0.0.0 Safari/537.36"
            )
        },
    }
    cookiefile = get_cookiefile()
    if cookiefile:
        options["cookiefile"] = cookiefile

    try:
        with YoutubeDL(options) as ydl:
            return ydl.extract_info(url, download=False)
    except TimeoutError as exc:
        raise DownloadError("O site demorou demais para responder. Tente outro link.") from exc
    except YtDlpDownloadError as exc:
        raise DownloadError(clean_error(str(exc))) from exc
    except Exception as exc:
        raise DownloadError(clean_error(str(exc))) from exc


def get_direct_url(info):
    if not isinstance(info, dict):
        return ""

    requested_downloads = info.get("requested_downloads")
    if isinstance(requested_downloads, list) and requested_downloads:
        direct_url = requested_downloads[0].get("url", "")
        if direct_url:
            return direct_url

    return info.get("url", "")


def get_cookiefile():
    cookies_base64 = os.environ.get("YOUTUBE_COOKIES_BASE64", "").strip()
    cookies_text = os.environ.get("YOUTUBE_COOKIES", "").strip()

    if cookies_base64:
        try:
            cookies_text = base64.b64decode(cookies_base64).decode("utf-8")
        except (ValueError, UnicodeDecodeError) as exc:
            raise DownloadError("A variável YOUTUBE_COOKIES_BASE64 está inválida.") from exc

    if not cookies_text:
        return ""

    with open(COOKIE_FILE_PATH, "w", encoding="utf-8") as cookie_file:
        cookie_file.write(cookies_text)
        if not cookies_text.endswith("\n"):
            cookie_file.write("\n")

    return COOKIE_FILE_PATH


def sanitize_filename(name):
    safe_name = "".join(char if char not in '<>:"/\\|?*\0' else "-" for char in name)
    safe_name = " ".join(safe_name.split()).strip(" .")
    return safe_name[:180] or "video"


def clean_extension(extension):
    extension = str(extension).lower().strip().lstrip(".")
    if extension and all(char.isalnum() for char in extension):
        return extension[:8]
    return "mp4"


def clean_error(message):
    lower_message = message.lower()

    if "timed out" in lower_message or "timeout" in lower_message:
        return "O site demorou demais para responder. Tente novamente ou use outro link."
    if "Unsupported URL" in message:
        return "Esse site ou link não é compatível com o downloader."
    if "Video unavailable" in message or "This video is unavailable" in message:
        return "Esse vídeo não está disponível para download."
    if "Sign in to confirm" in message or "cookies" in lower_message:
        return (
            "O YouTube bloqueou o servidor anônimo da Vercel. "
            "Configure YOUTUBE_COOKIES_BASE64 na Vercel para permitir esse vídeo."
        )
    return message
