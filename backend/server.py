"""
KOLD Downloader — Flask Backend
--------------------------------
Requisitos:
    pip install flask flask-cors yt-dlp

Uso:
    python server.py

El servidor corre en http://localhost:5000
"""

import os
import re
import json
import tempfile
import subprocess

from flask import Flask, request, jsonify, send_file
from flask_cors import CORS

app = Flask(__name__)
CORS(app)  # Permite peticiones desde el frontend local

DOWNLOAD_DIR = tempfile.gettempdir()


# ── Utilidades ────────────────────────────────────────────────────────────────

def sanitize(name: str, max_len: int = 80) -> str:
    """Limpia el nombre de archivo de caracteres inválidos."""
    return re.sub(r'[\\/:*?"<>|]', '_', name)[:max_len]


def run_ytdlp(*args) -> tuple[str, str, int]:
    """Ejecuta yt-dlp y devuelve (stdout, stderr, returncode)."""
    result = subprocess.run(
        ['yt-dlp', *args],
        capture_output=True,
        text=True
    )
    return result.stdout, result.stderr, result.returncode


# ── Endpoints ─────────────────────────────────────────────────────────────────

@app.route('/health')
def health():
    """El frontend lo usa para verificar que el backend está corriendo."""
    return jsonify({'status': 'ok', 'message': 'KOLD backend online'})


@app.route('/info', methods=['POST'])
def info():
    """Devuelve metadata del video sin descargarlo."""
    data = request.get_json(silent=True) or {}
    url  = data.get('url', '').strip()

    if not url:
        return jsonify({'error': 'URL requerida'}), 400

    stdout, stderr, code = run_ytdlp(
        '--dump-json',
        '--no-playlist',
        url
    )

    if code != 0:
        return jsonify({'error': stderr.strip() or 'No se pudo obtener información del video'}), 400

    try:
        meta = json.loads(stdout)
    except json.JSONDecodeError:
        return jsonify({'error': 'Respuesta inesperada de yt-dlp'}), 500

    duration_secs = meta.get('duration', 0)
    minutes, secs = divmod(int(duration_secs), 60)

    return jsonify({
        'title':    meta.get('title', 'Sin título'),
        'channel':  meta.get('uploader') or meta.get('channel', '—'),
        'duration': f'{minutes}:{secs:02d}',
        'views':    f"{meta.get('view_count', 0):,}",
        'thumb':    meta.get('thumbnail', ''),
    })


@app.route('/download', methods=['POST'])
def download():
    """Descarga el video/audio y lo envía al navegador."""
    data    = request.get_json(silent=True) or {}
    url     = data.get('url', '').strip()
    fmt     = data.get('format', 'mp4').lower()
    quality = data.get('quality', 'best')

    if not url:
        return jsonify({'error': 'URL requerida'}), 400

    # ── Construir argumentos de yt-dlp según formato y calidad ──
    output_template = os.path.join(DOWNLOAD_DIR, '%(title)s.%(ext)s')

    if fmt == 'mp3':
        args = [
            '--extract-audio',
            '--audio-format', 'mp3',
            '--audio-quality', '0',
            '-o', output_template,
            '--no-playlist',
            url
        ]

    elif fmt == 'wav':
        args = [
            '--extract-audio',
            '--audio-format', 'wav',
            '-o', output_template,
            '--no-playlist',
            url
        ]

    elif fmt == 'webm':
        if quality == 'best':
            fmt_str = 'bestvideo[ext=webm]+bestaudio[ext=webm]/best[ext=webm]/best'
        else:
            fmt_str = f'bestvideo[height<={quality}][ext=webm]+bestaudio[ext=webm]/best[height<={quality}]'
        args = [
            '-f', fmt_str,
            '-o', output_template,
            '--no-playlist',
            url
        ]

    else:  # mp4 (default)
        if quality == 'best':
            fmt_str = 'bestvideo[ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]/best'
        else:
            fmt_str = (
                f'bestvideo[height<={quality}][ext=mp4]+'
                f'bestaudio[ext=m4a]/best[height<={quality}][ext=mp4]/best[height<={quality}]'
            )
        args = [
            '-f', fmt_str,
            '--merge-output-format', 'mp4',
            '-o', output_template,
            '--no-playlist',
            url
        ]

    # Obtener el nombre real del archivo que yt-dlp va a crear
    stdout_print, _, _ = run_ytdlp('--get-filename', '-o', output_template, '--no-playlist', url)
    expected_path = stdout_print.strip().splitlines()[0] if stdout_print.strip() else None

    # Ejecutar descarga
    _, stderr, code = run_ytdlp(*args)

    if code != 0:
        return jsonify({'error': stderr.strip() or 'Error al descargar'}), 500

    # Buscar el archivo descargado
    filepath = None
    if expected_path and os.path.exists(expected_path):
        filepath = expected_path
    else:
        # Fallback: buscar el archivo más reciente en el directorio temporal
        files = [
            os.path.join(DOWNLOAD_DIR, f)
            for f in os.listdir(DOWNLOAD_DIR)
            if f.endswith(('.' + fmt, '.mp4', '.webm', '.mp3', '.wav'))
        ]
        if files:
            filepath = max(files, key=os.path.getmtime)

    if not filepath or not os.path.exists(filepath):
        return jsonify({'error': 'Archivo descargado no encontrado'}), 500

    mime_map = {
        'mp4':  'video/mp4',
        'webm': 'video/webm',
        'mp3':  'audio/mpeg',
        'wav':  'audio/wav',
    }
    mimetype = mime_map.get(fmt, 'application/octet-stream')

    return send_file(
        filepath,
        mimetype=mimetype,
        as_attachment=True,
        download_name=os.path.basename(filepath)
    )


# ── Main ──────────────────────────────────────────────────────────────────────

if __name__ == '__main__':
    print('─' * 48)
    print('  KOLD Downloader — Backend')
    print('  http://localhost:5000')
    print('─' * 48)
    app.run(host='0.0.0.0', port=5000, debug=True)
