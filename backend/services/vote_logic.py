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