import importlib.util
import json
from dataclasses import dataclass
from http.server import BaseHTTPRequestHandler


YT_DLP_TIMEOUT_SECONDS = 45


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

    url = str(payload.get("url", "")).strip()
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
    }

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
        return "Esse vídeo exige login/cookies e não pode ser resolvido pela função serverless."
    return message
