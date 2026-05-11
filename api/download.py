import importlib.util
import json
import subprocess
import sys
from http.server import BaseHTTPRequestHandler


class handler(BaseHTTPRequestHandler):
    def do_POST(self):
        try:
            payload = self.read_json()
            result = resolve_download(payload)
            self.send_json({"file": result})
        except ValueError as exc:
            self.send_json({"error": str(exc)}, status=400)
        except RuntimeError as exc:
            self.send_json({"error": str(exc)}, status=500)

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
    url = str(payload.get("url", "")).strip()
    media_format = payload.get("format", "best")
    quality = payload.get("quality", "best")

    if not url.startswith(("http://", "https://")):
        raise ValueError("Cole um link válido começando com http:// ou https://.")

    if importlib.util.find_spec("yt_dlp") is None:
        raise RuntimeError("yt-dlp não está disponível no runtime da Vercel.")

    title = run_yt_dlp(["--no-playlist", "--print", "%(title).180B", url]).strip()
    extension = "m4a" if media_format == "audio" else "mp4"

    command = ["--no-playlist", "-g"]
    if media_format == "audio":
        command.extend(["-f", "bestaudio[ext=m4a]/bestaudio/best"])
    elif quality != "best":
        command.extend(["-f", f"b[ext=mp4][height<={quality}]/best[height<={quality}]/best"])
    else:
        command.extend(["-f", "b[ext=mp4]/best"])
    command.append(url)

    direct_url = run_yt_dlp(command).strip().splitlines()[0]
    if not direct_url.startswith(("http://", "https://")):
        raise RuntimeError("Não foi possível gerar um link direto para esse vídeo.")

    return {
        "name": f"{title or 'video'}.{extension}",
        "size": 0,
        "url": direct_url,
        "external": True,
    }


def run_yt_dlp(arguments):
    completed = subprocess.run(
        [sys.executable, "-m", "yt_dlp", *arguments],
        capture_output=True,
        text=True,
        timeout=45,
        check=False,
    )

    if completed.returncode != 0:
        message = completed.stderr.strip().splitlines()[-1:] or ["yt-dlp não conseguiu ler esse link."]
        raise RuntimeError(message[0])

    return completed.stdout
