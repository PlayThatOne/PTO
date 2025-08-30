print(">> main.py iniciado")

import sys
import os
import json
import csv
from pathlib import Path

# Para imports tipo `backend.*`
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

# === RUTA ABSOLUTA A frontend/public ===
PROJECT_ROOT = Path(__file__).resolve().parents[1]      # .../src
PUBLIC_DIR   = PROJECT_ROOT / "frontend" / "public"
print(f">> PUBLIC_DIR={PUBLIC_DIR}")

def create_app():
    print(">> creando app")

    # Sirve estáticos desde la raíz del sitio
    app = Flask(__name__, static_folder=str(PUBLIC_DIR), static_url_path="")

    # Log para confirmar que index existe
    idx = PUBLIC_DIR / "index.html"
    print(f">> index.html existe? {idx.exists()}  ({idx})")

    socketio.init_app(app, cors_allowed_origins="*")
    print(">> socketio registrado")

    # ===== RUTAS ESTÁTICAS BÁSICAS =====
    @app.route("/")
    def root():
        # Sirve /index.html
        return app.send_static_file("index.html")

    # Estos endpoints siguen sirviendo ficheros de apoyo (opcional: ya los serviría el estático)
    @app.route("/catalog/<path:filename>")
    def catalog(filename):
        return send_from_directory(str(PUBLIC_DIR / "catalog"), filename)

    @app.route("/inter.html")
    def inter():
        return send_from_directory(str(PUBLIC_DIR), "inter.html")

    @app.route("/addsong.html")
    def addsong():
        return send_from_directory(str(PUBLIC_DIR), "addsong.html")

    @app.route("/ran.html")
    def ran():
        return send_from_directory(str(PUBLIC_DIR), "ran.html")

    # ===== RUTAS SONGS (fuera de static) =====
    @app.route("/songs/tabs/<filename>")
    def serve_tab(filename):
        tabs_dir = Path(__file__).resolve().parents[1] / "songs" / "tabs"
        return send_from_directory(str(tabs_dir), filename)

    @app.route("/songs/lyrics/<filename>")
    def serve_lyrics(filename):
        lyrics_dir = Path(__file__).resolve().parents[1] / "songs" / "lyrics"
        return send_from_directory(str(lyrics_dir), filename)

    @app.route("/songs/images/<path:filename>")
    def serve_images(filename):
        images_dir = Path(__file__).resolve().parents[1] / "songs" / "images"
        return send_from_directory(str(images_dir), filename)

    # ===== API =====
    @app.route("/core/votes.json")
    def votes():
        core_dir = Path(__file__).resolve().parent / "core"
        return send_from_directory(str(core_dir), "votes.json")

    @app.route("/votes/counts.json")
    def vote_counts():
        raw_votes = load_votes()
        counts = count_votes(raw_votes)
        return jsonify(counts)

    @app.route("/votes/reset")
    def reset_votes():
        from backend.services.vote_logic import save_states
        save_votes({})
        save_states({})
        socketio.emit("update", {})
        socketio.emit("session_reset")
        return jsonify({"status": "ok", "message": "Votes reset"})

    @app.route("/songStates.js")
    def song_states_js():
        return send_from_directory(str(PUBLIC_DIR), "songStates.js")

    @app.route("/favicon.ico")
    def favicon():
        return "", 204

    @app.route("/add-song", methods=["POST"])
    def add_song():
        try:
            data = request.get_json()
            song_id = data.get("id", "").strip()
            if not song_id:
                return "ID de canción no especificado", 400

            base_dir = Path(__file__).resolve().parents[1]
            lyrics_path = base_dir / "songs" / "lyrics" / f"{song_id}.txt"
            tabs_path = base_dir / "songs" / "tabs" / f"TAB{song_id}.txt"
            catalog_csv = Path(__file__).resolve().parent / "core" / "catalog_postgres.csv"

            print(">> add_song recibido")
            print(">> ID:", song_id)
            print(">> lyrics:", lyrics_path)
            print(">> tabs:", tabs_path)
            print(">> CSV:", catalog_csv)

            if lyrics_path.exists():
                return "Ya existe una canción con ese ID.", 400
            if not catalog_csv.exists():
                return f"Archivo CSV no encontrado en: {catalog_csv}", 500

            with open(catalog_csv, "a", newline="", encoding="utf-8") as csvfile:
                writer = csv.writer(csvfile, delimiter=";")
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

            lyrics_path.parent.mkdir(parents=True, exist_ok=True)
            tabs_path.parent.mkdir(parents=True, exist_ok=True)

            with open(lyrics_path, "w", encoding="utf-8") as f:
                f.write(data.get("lyrics", "").strip())
            with open(tabs_path, "w", encoding="utf-8") as f:
                f.write(data.get("tab", "").strip())

            return "✅ Canción añadida correctamente."
        except Exception as e:
            return f"❌ Error al añadir canción: {str(e)}", 500

    @app.route("/votes/now_playing", methods=["POST"])
    def set_now_playing():
        from backend.services.vote_logic import save_states
        data = request.get_json()
        new_id = data.get("songId")
        if not new_id:
            return jsonify({"status": "error", "message": "Missing songId"}), 400

        states = load_states()
        for sid in list(states):
            if states[sid] == "now_playing":
                states[sid] = "played"
        states[new_id] = "now_playing"
        save_states(states)

        votes = load_votes()
        counts = count_votes(votes)
        by_device = {}
        for dev, song_id in votes.items():
            by_device.setdefault(song_id, []).append(dev)

        socketio.emit("update", {
            "counts": counts,
            "byDevice": by_device,
            "states": states
        })
        return jsonify({"status": "ok", "now_playing": new_id})

    @socketio.on("vote")
    def handle_vote(data):
        device = data.get("deviceId")
        song = data.get("songId")
        if not device or not song:
            return
        votes = load_votes()
        votes[device] = song
        save_votes(votes)

        counts = count_votes(votes)
        by_device = {}
        for dev, song_id in votes.items():
            by_device.setdefault(song_id, []).append(dev)
        states = load_states()

        print(">> update:", {"counts": counts, "byDevice": by_device, "states": states})

        socketio.emit("update", {"counts": counts, "byDevice": by_device, "states": states})

    @socketio.on("update_request")
    def handle_update_request():
        votes = load_votes()
        counts = count_votes(votes)
        states = load_states()
        socketio.emit("update", {"counts": counts, "byDevice": votes, "states": states})

    @app.route("/refresh-catalog", methods=["POST"])
    def refresh_catalog():
        import subprocess
        try:
            script_path = Path(__file__).resolve().parent / "catalog" / "gen_catalog.py"
            result = subprocess.run(["python", str(script_path)], capture_output=True, text=True)
            if result.returncode == 0:
                return "✅ Catálogo actualizado correctamente."
            else:
                return f"❌ Error al actualizar catálogo:\n{result.stderr}", 500
        except Exception as e:
            return f"❌ Excepción al actualizar catálogo: {str(e)}", 500

    @app.route("/missing-artist-photos")
    def missing_artist_photos():
        try:
            base_dir = Path(__file__).resolve().parents[1]
            catalog_path = base_dir / "frontend" / "public" / "catalog" / "catalog.json"
            images_dir = base_dir / "songs" / "images" / "artist"

            with open(catalog_path, "r", encoding="utf-8") as f:
                catalog = json.load(f)

            missing = []
            for song in catalog:
                artist = song.get("artist", "").strip()
                if not artist:
                    continue
                found = any((images_dir / f"{artist}{ext}").exists() for ext in [".jpg", ".jpeg", ".png"])
                if not found and artist not in missing:
                    missing.append(artist)

            return jsonify(missing)
        except Exception as e:
            return jsonify({"error": str(e)}), 500

    @app.route("/edit-catalog")
    def edit_catalog():
        from flask import send_file
        base_dir = Path(__file__).resolve().parents[1]
        catalog_csv = base_dir / "backend" / "core" / "catalog_postgres.csv"
        return send_file(str(catalog_csv), as_attachment=False)

    @app.route("/upload-catalog", methods=["POST"])
    def upload_catalog():
        try:
            file = request.files["catalog"]
            if not file:
                return "No se recibió ningún archivo", 400

            base_dir = Path(__file__).resolve().parents[1]
            save_path = base_dir / "backend" / "core" / "catalog_postgres.csv"
            file.save(str(save_path))
            return "✅ Catálogo actualizado correctamente."
        except Exception as e:
            return f"❌ Error al subir catálogo: {str(e)}", 500

    @app.route("/download-catalog")
    def download_catalog():
        from flask import send_file
        base_dir = Path(__file__).resolve().parents[1]
        catalog_csv = base_dir / "backend" / "core" / "catalog_postgres.csv"
        return send_file(str(catalog_csv), as_attachment=True)

    @app.route("/upload-logo", methods=["POST"])
    def upload_logo():
        try:
            file = request.files["logo"]
            if not file:
                return "No se recibió ningún archivo", 400

            base_dir = Path(__file__).resolve().parents[1]
            images_dir = base_dir / "songs" / "images"
            images_dir.mkdir(parents=True, exist_ok=True)

            ext = os.path.splitext(file.filename)[1].lower()
            if ext not in [".png", ".jpg", ".jpeg"]:
                return "Formato no permitido. Usa PNG o JPG.", 400

            save_path = images_dir / ("event-logo" + ext)
            file.save(str(save_path))
            return "✅ Logo actualizado correctamente."
        except Exception as e:
            return f"❌ Error al subir logo: {str(e)}", 500

    @app.route("/list-songs")
    def list_songs():
        try:
            base_dir = Path(__file__).resolve().parent
            catalog_csv = base_dir / "core" / "catalog_postgres.csv"
            songs = []
            with open(catalog_csv, newline="", encoding="utf-8") as f:
                reader = csv.DictReader(f, delimiter=";")
                for row in reader:
                    songs.append({"id": row["id"], "title": row["name"], "artist": row["artist"]})
            songs.sort(key=lambda x: x["title"].lower())
            return jsonify(songs)
        except Exception as e:
            return jsonify({"error": str(e)}), 500

    @app.route("/delete-songs", methods=["POST"])
    def delete_songs():
        try:
            data = request.get_json()
            ids = data.get("ids", [])
            if not ids:
                return "No se recibieron canciones a borrar.", 400

            base_dir = Path(__file__).resolve().parent
            catalog_csv = base_dir / "core" / "catalog_postgres.csv"
            temp_file = Path(str(catalog_csv) + ".tmp")

            deleted = []
            with open(catalog_csv, newline="", encoding="utf-8") as infile, open(temp_file, "w", newline="", encoding="utf-8") as outfile:
                reader = csv.DictReader(infile, delimiter=";")
                fieldnames = reader.fieldnames
                writer = csv.DictWriter(outfile, fieldnames=fieldnames, delimiter=";")
                writer.writeheader()
                for row in reader:
                    if row["id"] in ids:
                        deleted.append(row["id"])
                        # borrar archivos asociados
                        base_dir2 = Path(__file__).resolve().parents[1]
                        lyrics_path = base_dir2 / "songs" / "lyrics" / f"{row['id']}.txt"
                        tabs_path = base_dir2 / "songs" / "tabs" / f"TAB{row['id']}.txt"
                        for path in [lyrics_path, tabs_path]:
                            if path.exists():
                                path.unlink()
                        continue
                    writer.writerow(row)

            os.replace(temp_file, catalog_csv)
            return f"✅ Borradas: {', '.join(deleted)}"
        except Exception as e:
            return f"❌ Error al borrar canciones: {str(e)}", 500

    @app.route("/get-song-status")
    def get_song_status():
        try:
            base_dir = Path(__file__).resolve().parent
            catalog_csv = base_dir / "core" / "catalog_postgres.csv"
            songs = []
            with open(catalog_csv, newline="", encoding="utf-8") as f:
                reader = csv.DictReader(f, delimiter=";")
                for row in reader:
                    songs.append({
                        "id": row["id"],
                        "title": row["name"],
                        "artist": row["artist"],
                        "enabled": (row.get("enabled") or "Y").strip().upper()
                    })
            return jsonify(songs)
        except Exception as e:
            return jsonify({"error": str(e)}), 500

    @app.route("/update-enabled", methods=["POST"])
    def update_enabled_status():
        try:
            data = request.get_json()
            updates = data.get("enabled", {})
            if not updates:
                return "No se recibieron datos para actualizar.", 400

            base_dir = Path(__file__).resolve().parent
            catalog_csv = base_dir / "core" / "catalog_postgres.csv"
            temp_file = Path(str(catalog_csv) + ".tmp")

            with open(catalog_csv, newline="", encoding="utf-8") as infile, open(temp_file, "w", newline="", encoding="utf-8") as outfile:
                reader = csv.DictReader(infile, delimiter=";")
                fieldnames = reader.fieldnames
                writer = csv.DictWriter(outfile, fieldnames=fieldnames, delimiter=";")
                writer.writeheader()
                for row in reader:
                    if row["id"] in updates:
                        row["enabled"] = "Y" if updates[row["id"]] else "N"
                    writer.writerow(row)

            os.replace(temp_file, catalog_csv)
            return "✅ Estado actualizado correctamente."
        except Exception as e:
            return f"❌ Error al actualizar estado: {str(e)}", 500

    @app.route("/catalog/fields.json")
    def catalog_fields():
        try:
            from collections import defaultdict
            base_dir = Path(__file__).resolve().parent
            csv_path = base_dir / "core" / "catalog_postgres.csv"

            fields = ["artist", "year", "language", "genre", "mood", "key"]
            values = defaultdict(set)
            with open(csv_path, newline="", encoding="utf-8") as f:
                reader = csv.DictReader(f, delimiter=";")
                for row in reader:
                    for field in fields:
                        val = row.get(field, "").strip()
                        if val:
                            values[field].add(val)
            sorted_fields = {k: sorted(values[k]) for k in fields}
            return jsonify(sorted_fields)
        except Exception as e:
            return jsonify({"error": str(e)}), 500

    @app.route("/upload-artist-photo/<artist>", methods=["POST"])
    def upload_artist_photo(artist):
        try:
            if "photo" not in request.files:
                return "No se recibió ningún archivo", 400
            file = request.files["photo"]
            if file.filename == "":
                return "Nombre de archivo vacío", 400
            ext = os.path.splitext(file.filename)[1].lower()
            if ext not in [".jpg", ".jpeg", ".png", ".bmp"]:
                return "Formato no permitido", 400

            base_dir = Path(__file__).resolve().parents[1]
            images_dir = base_dir / "songs" / "images" / "artist"
            images_dir.mkdir(parents=True, exist_ok=True)

            safe_artist = artist.strip().replace("/", "_").replace("\\", "_")
            save_path = images_dir / (safe_artist + ext)
            file.save(str(save_path))
            return "✅ Imagen subida correctamente."
        except Exception as e:
            return f"❌ Error al subir imagen: {str(e)}", 500

    return app
