import os
import re
import json
import tempfile
import subprocess

from flask import Flask, request, jsonify, send_file
from flask_cors import CORS

app = Flask(__name__)
CORS(app)

DOWNLOAD_DIR = tempfile.gettempdir()


def run_ytdlp(*args):
    result = subprocess.run(
        ['yt-dlp', *args],
        capture_output=True,
        text=True
    )
    return result.stdout, result.stderr, result.returncode


@app.route('/health')
def health():
    return jsonify({'status': 'ok'})


@app.route('/download', methods=['POST'])
def download():
    data = request.get_json(silent=True) or {}
    url = data.get('url', '').strip()
    fmt = data.get('format', 'mp4').lower()

    if not url:
        return jsonify({'error': 'URL requerida'}), 400

    is_instagram = 'instagram.com' in url

    output_template = os.path.join(DOWNLOAD_DIR, '%(title)s.%(ext)s')

    COMMON_ARGS = [
        '--user-agent', 'Mozilla/5.0',
        '--referer', 'https://www.instagram.com/'
    ]

    # ─── FORMATOS ─────────────────────

    if fmt in ['mp3', 'wav']:
        args = COMMON_ARGS + [
            '--extract-audio',
            '--audio-format', fmt,
            '--audio-quality', '0',
            '-o', output_template,
            '--no-playlist',
            url
        ]

    else:  # mp4
        if is_instagram:
            args = COMMON_ARGS + [
                '-f', 'best',
                '-o', output_template,
                '--no-playlist',
                url
            ]
        else:
            args = COMMON_ARGS + [
                '-f', 'bestvideo+bestaudio/best',
                '--merge-output-format', 'mp4',
                '-o', output_template,
                '--no-playlist',
                url
            ]

    # ─── NOMBRE ARCHIVO ─────────────────────
    stdout_print, _, _ = run_ytdlp('--get-filename', '-o', output_template, url)
    expected_path = stdout_print.strip().splitlines()[0] if stdout_print.strip() else None

    # ─── DESCARGA ─────────────────────
    _, stderr, code = run_ytdlp(*args)

    if code != 0:
        return jsonify({'error': stderr.strip() or 'Error al descargar'}), 500

    # ─── BUSCAR ARCHIVO ─────────────────────
    filepath = None

    if expected_path and os.path.exists(expected_path):
        filepath = expected_path
    else:
        files = [
            os.path.join(DOWNLOAD_DIR, f)
            for f in os.listdir(DOWNLOAD_DIR)
            if f.endswith(('.mp4','.mp3','.wav','.webm'))
        ]
        if files:
            filepath = max(files, key=os.path.getmtime)

    if not filepath:
        return jsonify({'error': 'Archivo no encontrado'}), 500

    return send_file(
        filepath,
        as_attachment=True,
        download_name=os.path.basename(filepath)
    )


if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)