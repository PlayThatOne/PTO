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
from backend.core.config import VOTES_FILE

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
    def song_states():
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
            base_dir = os.path.abspath(os.path.dirname(__file__))
            catalog_csv = os.path.join(base_dir, "core", "catalog_postgres.csv")


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

    @socketio.on('vote')
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

        print(">> update:", {
            "counts": counts,
            "byDevice": by_device,
            "states": states
        })

        socketio.emit("update", {
            "counts": counts,
            "byDevice": by_device,
            "states": states
        })

    @socketio.on('update_request')
    def handle_update_request():
        votes = load_votes()
        counts = count_votes(votes)
        states = load_states()
        socketio.emit("update", {
            "counts": counts,
            "byDevice": votes,
            "states": states
        })

    @app.route('/refresh-catalog', methods=['POST'])
    def refresh_catalog():
        import subprocess
        try:
            script_path = os.path.abspath(os.path.join(os.path.dirname(__file__), 'catalog', 'gen_catalog.py'))
            result = subprocess.run(
                ['python', os.path.join(os.path.dirname(__file__), 'catalog', 'gen_catalog.py')],
                capture_output=True, text=True
            )
            if result.returncode == 0:
                return "✅ Catálogo actualizado correctamente."
            else:
                return f"❌ Error al actualizar catálogo:\n{result.stderr}", 500
        except Exception as e:
            return f"❌ Excepción al actualizar catálogo: {str(e)}", 500

    
    @app.route('/missing-artist-photos')
    def missing_artist_photos():
        try:
            base_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
            catalog_path = os.path.join(base_dir, "frontend", "public", "catalog", "catalog.json")
            images_dir = os.path.join(base_dir, "songs", "images", "artist")

            with open(catalog_path, "r", encoding="utf-8") as f:
                catalog = json.load(f)

            missing = []
            for song in catalog:
                artist = song.get("artist", "").strip()
                if not artist:
                    continue
                found = False
                for ext in [".jpg", ".jpeg", ".png"]:
                    if os.path.exists(os.path.join(images_dir, f"{artist}{ext}")):
                        found = True
                        break
                if not found and artist not in missing:
                    missing.append(artist)

            return jsonify(missing)
        except Exception as e:
            return jsonify({"error": str(e)}), 500


    
    @app.route('/edit-catalog')
    def edit_catalog():
        from flask import send_file
        base_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
        catalog_csv = os.path.join(base_dir, "backend", "core", "catalog_postgres.csv")
        return send_file(catalog_csv, as_attachment=False)


    
    @app.route('/upload-catalog', methods=['POST'])
    def upload_catalog():
        try:
            file = request.files['catalog']
            if not file:
                return "No se recibió ningún archivo", 400

            base_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
            save_path = os.path.join(base_dir, "backend", "core", "catalog_postgres.csv")
            file.save(save_path)

            return "✅ Catálogo actualizado correctamente."
        except Exception as e:
            return f"❌ Error al subir catálogo: {str(e)}", 500


    @app.route('/download-catalog')
    def download_catalog():
        from flask import send_file
        base_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
        catalog_csv = os.path.join(base_dir, "backend", "core", "catalog_postgres.csv")
        return send_file(catalog_csv, as_attachment=True)


    
    @app.route('/upload-logo', methods=['POST'])
    def upload_logo():
        try:
            file = request.files['logo']
            if not file:
                return "No se recibió ningún archivo", 400

            base_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
            images_dir = os.path.join(base_dir, "songs", "images")
            os.makedirs(images_dir, exist_ok=True)

            ext = os.path.splitext(file.filename)[1].lower()
            if ext not in ['.png', '.jpg', '.jpeg']:
                return "Formato no permitido. Usa PNG o JPG.", 400

            save_path = os.path.join(images_dir, "event-logo" + ext)
            file.save(save_path)

            return "✅ Logo actualizado correctamente."
        except Exception as e:
            return f"❌ Error al subir logo: {str(e)}", 500


    @app.route('/list-songs')
    def list_songs():
        try:
            base_dir = os.path.abspath(os.path.join(os.path.dirname(__file__)))
            catalog_csv = os.path.join(base_dir, "core", "catalog_postgres.csv")
            songs = []
            import csv
            with open(catalog_csv, newline='', encoding="utf-8") as f:
                reader = csv.DictReader(f, delimiter=';')
                for row in reader:
                    songs.append({
                        "id": row["id"],
                        "title": row["name"],
                        "artist": row["artist"]
                    })
            songs.sort(key=lambda x: x["title"].lower())
            print(songs)
            return jsonify(songs)
        except Exception as e:
            return jsonify({"error": str(e)}), 500

    @app.route('/delete-songs', methods=['POST'])
    def delete_songs():
        try:
            data = request.get_json()
            ids = data.get("ids", [])
            if not ids:
                return "No se recibieron canciones a borrar.", 400

            base_dir = os.path.abspath(os.path.join(os.path.dirname(__file__)))
            catalog_csv = os.path.join(base_dir, "core", "catalog_postgres.csv")
            temp_file = catalog_csv + ".tmp"

            deleted = []

            with open(catalog_csv, newline='', encoding="utf-8") as infile, \
                 open(temp_file, "w", newline='', encoding="utf-8") as outfile:
                reader = csv.DictReader(infile, delimiter=';')
                fieldnames = reader.fieldnames
                writer = csv.DictWriter(outfile, fieldnames=fieldnames, delimiter=';')
                writer.writeheader()

                for row in reader:
                    if row["id"] in ids:
                        deleted.append(row["id"])
                        # borrar archivos asociados
                        lyrics_path = os.path.join(base_dir, "songs", "lyrics", f"{row['id']}.txt")
                        tabs_path = os.path.join(base_dir, "songs", "tabs", f"TAB{row['id']}.txt")
                        for path in [lyrics_path, tabs_path]:
                            if os.path.exists(path):
                                os.remove(path)
                        continue
                    writer.writerow(row)

            os.replace(temp_file, catalog_csv)

            msg = f"✅ Borradas: {', '.join(deleted)}"
            return msg
        except Exception as e:
            return f"❌ Error al borrar canciones: {str(e)}", 500


    
    @app.route('/get-song-status')
    def get_song_status():
        try:
            base_dir = os.path.abspath(os.path.dirname(__file__))
            catalog_csv = os.path.join(base_dir, "core", "catalog_postgres.csv")
            songs = []
            with open(catalog_csv, newline='', encoding="utf-8") as f:
                reader = csv.DictReader(f, delimiter=';')
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

    @app.route('/update-enabled', methods=['POST'])
    def update_enabled_status():
        try:
            data = request.get_json()
            updates = data.get("enabled", {})
            if not updates:
                return "No se recibieron datos para actualizar.", 400

            base_dir = os.path.abspath(os.path.dirname(__file__))
            catalog_csv = os.path.join(base_dir, "core", "catalog_postgres.csv")
            temp_file = catalog_csv + ".tmp"

            with open(catalog_csv, newline='', encoding="utf-8") as infile,                  open(temp_file, "w", newline='', encoding="utf-8") as outfile:
                reader = csv.DictReader(infile, delimiter=';')
                fieldnames = reader.fieldnames
                writer = csv.DictWriter(outfile, fieldnames=fieldnames, delimiter=';')
                writer.writeheader()

                for row in reader:
                    if row["id"] in updates:
                        row["enabled"] = "Y" if updates[row["id"]] else "N"
                    writer.writerow(row)

            os.replace(temp_file, catalog_csv)
            return "✅ Estado actualizado correctamente."
        except Exception as e:
            return f"❌ Error al actualizar estado: {str(e)}", 500



    @app.route('/catalog/fields.json')
    def catalog_fields():
        try:
            import csv
            from collections import defaultdict

            base_dir = os.path.abspath(os.path.dirname(__file__))
            csv_path = os.path.join(base_dir, "core", "catalog_postgres.csv")

            fields = ["artist", "year", "language", "genre", "mood", "key"]
            values = defaultdict(set)

            with open(csv_path, newline='', encoding="utf-8") as f:
                reader = csv.DictReader(f, delimiter=';')
                for row in reader:
                    for field in fields:
                        val = row.get(field, "").strip()
                        if val:
                            values[field].add(val)

            sorted_fields = {k: sorted(values[k]) for k in fields}
            return jsonify(sorted_fields)

        except Exception as e:
            return jsonify({"error": str(e)}), 500

    @app.route('/upload-artist-photo/<artist>', methods=['POST'])
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

            base_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
            images_dir = os.path.join(base_dir, "songs", "images", "artist")
            os.makedirs(images_dir, exist_ok=True)

            safe_artist = artist.strip().replace("/", "_").replace("\\", "_")
            save_path = os.path.join(images_dir, safe_artist + ext)
            file.save(save_path)

            return "✅ Imagen subida correctamente."

        except Exception as e:
            return f"❌ Error al subir imagen: {str(e)}", 500

    return app

if __name__ == '__main__':
    import traceback
    try:
        print(">> entrando en main")
        app = create_app()
        print(">> app creada")
        socketio.run(app, host='0.0.0.0', port=5000, debug=True)
    except Exception:
        traceback.print_exc()