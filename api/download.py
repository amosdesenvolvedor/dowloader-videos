import importlib.util
import json
import subprocess
import sys
from dataclasses import dataclass
from http.server import BaseHTTPRequestHandler


YT_DLP_TIMEOUT_SECONDS = 8


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

    title = run_yt_dlp(["--no-playlist", "--print", "%(title).180B", url]).strip()
    extension = "m4a" if media_format == "audio" else "mp4"

    command = ["--no-playlist", "-g"]
    if media_format == "audio":
        command.extend(["-f", "bestaudio[ext=m4a]/bestaudio/best"])
    else:
        command.extend(["-f", "best[ext=mp4]/best"])
    command.append(url)

    direct_urls = [line.strip() for line in run_yt_dlp(command).splitlines() if line.strip()]
    if not direct_urls:
        raise DownloadError("Não foi possível gerar um link direto para esse vídeo.")

    direct_url = direct_urls[0]
    if not direct_url.startswith(("http://", "https://")):
        raise DownloadError("Não foi possível gerar um link direto para esse vídeo.")

    return {
        "name": f"{title or 'video'}.{extension}",
        "size": 0,
        "url": direct_url,
        "external": True,
    }


def run_yt_dlp(arguments):
    try:
        completed = subprocess.run(
            [sys.executable, "-m", "yt_dlp", *arguments],
            capture_output=True,
            text=True,
            timeout=YT_DLP_TIMEOUT_SECONDS,
            check=False,
        )
    except subprocess.TimeoutExpired as exc:
        raise DownloadError("O site demorou demais para responder. Tente outro link.") from exc

    if completed.returncode != 0:
        message = completed.stderr.strip().splitlines()[-1:] or ["yt-dlp não conseguiu ler esse link."]
        raise DownloadError(clean_error(message[0]))

    return completed.stdout


def clean_error(message):
    if "Unsupported URL" in message:
        return "Esse site ou link não é compatível com o downloader."
    if "Video unavailable" in message or "This video is unavailable" in message:
        return "Esse vídeo não está disponível para download."
    if "Sign in to confirm" in message or "cookies" in message.lower():
        return "Esse vídeo exige login/cookies e não pode ser resolvido pela função serverless."
    return message
