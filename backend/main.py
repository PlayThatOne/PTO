print(">> main.py iniciado")

import sys
import os
import json
import csv
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

import eventlet
eventlet.monkey_patch()

from flask import Flask, send_from_directory, jsonify, request
print(">> Flask importado")

from backend.api.websockets import socketio
print(">> socketio importado")

from backend.services.vote_logic import load_votes, count_votes, save_votes, load_states

# --- import robusto de rutas de persistencia (evita fallo si falta backend.core.config) ---
try:
    from backend.core.config import VOTES_FILE, SONG_STATES_FILE
except Exception:
    try:
        from .core.config import VOTES_FILE, SONG_STATES_FILE  # type: ignore
    except Exception:
        CORE_DIR = os.environ.get("CORE_DIR", "/opt/render/project/src/backend/core")
        if not os.path.isdir(CORE_DIR):
            CORE_DIR = os.path.join(os.path.dirname(__file__), "core")
        VOTES_FILE = os.path.join(CORE_DIR, "votes.json")
        SONG_STATES_FILE = os.path.join(CORE_DIR, "song_states.json")

def create_app():
    print(">> creando app")
    app = Flask(__name__, static_folder='../frontend/public')

    socketio.init_app(app, cors_allowed_origins="*")
    print(">> socketio registrado")

    @app.route('/')
    def index():
        return send_from_directory(app.static_folder, 'index.html')

    @app.route('/catalog/<path:filename>')
    def catalog(filename):
        return send_from_directory(os.path.join(app.static_folder, 'catalog'), filename)

    @app.route('/inter.html')
    def inter():
        return send_from_directory(app.static_folder, 'inter.html')

    @app.route('/addsong.html')
    def addsong():
        return send_from_directory(app.static_folder, 'addsong.html')

    @app.route('/ran.html')
    def ran():
        return send_from_directory(app.static_folder, 'ran.html')

    @app.route('/songs/tabs/<filename>')
    def serve_tab(filename):
        tabs_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "songs", "tabs"))
        return send_from_directory(tabs_dir, filename)

    @app.route('/songs/lyrics/<filename>')
    def serve_lyrics(filename):
        lyrics_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "songs", "lyrics"))
        return send_from_directory(lyrics_dir, filename)

    @app.route('/songs/images/<path:filename>')
    def serve_images(filename):
        images_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "songs", "images"))
        return send_from_directory(images_dir, filename)

    @app.route('/core/votes.json')
    def votes():
        core_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "core"))
        return send_from_directory(core_dir, 'votes.json')

    @app.route('/votes/counts.json')
    def vote_counts():
        raw_votes = load_votes()
        counts = count_votes(raw_votes)
        return jsonify(counts)

    @app.route('/votes/reset')
    def reset_votes():
        from backend.services.vote_logic import save_states
        save_votes({})
        save_states({})
        socketio.emit("update", {})
        socketio.emit("session_reset")
        return jsonify({"status": "ok", "message": "Votes reset"})

    @app.route('/songStates.js')
    def song_states_js():
        return send_from_directory(app.static_folder, 'songStates.js')

    @app.route('/favicon.ico')
    def favicon():
        return '', 204

    @app.route('/add-song', methods=['POST'])
    def add_song():
        try:
            data = request.get_json()
            song_id = data.get("id", "").strip()
            if not song_id:
                return "ID de canción no especificado", 400

            base_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
            lyrics_path = os.path.join(base_dir, "songs", "lyrics", f"{song_id}.txt")
            tabs_path = os.path.join(base_dir, "songs", "tabs", f"TAB{song_id}.txt")
            base_dir2 = os.path.abspath(os.path.dirname(__file__))
            catalog_csv = os.path.join(base_dir2, "core", "catalog_postgres.csv")

            print(">> add_song recibido")
            print(">> ID recibido:", song_id)
            print(">> Ruta lyrics esperada:", lyrics_path)
            print(">> Ruta tabs esperada:", tabs_path)
            print(">> Ruta CSV esperada:", catalog_csv)
            print(">> ¿Lyrics existe?:", os.path.exists(lyrics_path))
            print(">> ¿Tabs existe?:", os.path.exists(tabs_path))
            print(">> ¿CSV existe?:", os.path.exists(catalog_csv))

            if os.path.exists(lyrics_path):
                return "Ya existe una canción con ese ID.", 400

            if not os.path.exists(catalog_csv):
                return f"Archivo CSV no encontrado en: {catalog_csv}", 500

            with open(catalog_csv, "a", newline="", encoding="utf-8") as csvfile:
                writer = csv.writer(csvfile, delimiter=';')
                writer.writerow([
                    data.get("id", ""),
                    data.get("name", ""),
                    data.get("artist", ""),
                    data.get("year", ""),
                    data.get("language", ""),
                    data.get("genre", ""),
                    data.get("duration", ""),
                    data.get("mood", ""),
                    data.get("key", ""),
                    data.get("tempo", "")
                ])

            os.makedirs(os.path.dirname(lyrics_path), exist_ok=True)
            os.makedirs(os.path.dirname(tabs_path), exist_ok=True)

            with open(lyrics_path, "w", encoding="utf-8") as f:
                f.write(data.get("lyrics", "").strip())

            with open(tabs_path, "w", encoding="utf-8") as f:
                f.write(data.get("tab", "").strip())

            return "✅ Canción añadida correctamente."

        except Exception as e:
            return f"❌ Error al añadir canción: {str(e)}", 500

    @app.route('/votes/now_playing', methods=['POST'])
    def set_now_playing():
        from backend.services.vote_logic import save_states
        data = request.get_json()
        new_id = data.get("songId")
        if not new_id:
            return jsonify({"status": "error", "message": "
