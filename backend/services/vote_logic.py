# backend/services/vote_logic.py
# --- config import con triple fallback ---
try:
    from backend.core.config import VOTES_FILE as VOTES_PATH, SONG_STATES_FILE
except Exception:
    try:
        from ..core.config import VOTES_FILE as VOTES_PATH, SONG_STATES_FILE  # type: ignore
    except Exception:
        import os, json
        CORE_DIR = os.environ.get("CORE_DIR", "/opt/render/project/src/backend/core")
        if not os.path.isdir(CORE_DIR):
            CORE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "core"))
        os.makedirs(CORE_DIR, exist_ok=True)
        VOTES_PATH = os.path.join(CORE_DIR, "votes.json")
        SONG_STATES_FILE = os.path.join(CORE_DIR, "song_states.json")
        # Inicializa si faltan
        for p, default in [(VOTES_PATH, {}), (SONG_STATES_FILE, {"now_playing": None, "played": []})]:
            try:
                if not os.path.exists(p):
                    with open(p, "w", encoding="utf-8") as f:
                        json.dump(default, f)
            except Exception:
                pass
        print(f"[vote_logic fallback] CORE_DIR={CORE_DIR}", flush=True)

import os
import json
from collections import Counter
from backend.core.config import VOTES_FILE as VOTES_PATH

VOTES_FILE = VOTES_PATH

SONG_STATES_FILE = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'core', 'song_states.json'))
print(">> PATH ABSOLUTO DE STATES:", SONG_STATES_FILE)

def load_votes():
    try:
        with open(VOTES_FILE, 'r') as f:
            return json.load(f)
    except FileNotFoundError:
        return {}

def save_votes(states):
    print(">> save_votes llamado con:", states)
    with open(VOTES_FILE, 'w') as f:
        json.dump(states, f)

def count_votes(states):
    return dict(Counter(states.values()))

def load_states():
    try:
        with open(SONG_STATES_FILE, 'r') as f:
            return json.load(f)
    except FileNotFoundError:
        return {}

def save_states(states):
    print(">> save_states llamado con:", states)
    with open(SONG_STATES_FILE, 'w') as f:
        json.dump(states, f, indent=2)
