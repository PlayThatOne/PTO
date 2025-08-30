
from flask_socketio import SocketIO, emit
import json
import os
from backend.services.vote_logic import count_votes, save_votes, load_votes
from backend.core.config import VOTES_FILE

socketio = SocketIO(cors_allowed_origins="*")
song_states = load_votes()

@socketio.on('vote')
def handle_vote(data):
    device_id = data['deviceId']
    song_id = data['songId']

    prev = song_states.get(device_id)
    if prev == song_id:
        return

    song_states[device_id] = song_id
    save_votes(song_states)

    vote_counts = count_votes(song_states)
    socketio.emit('update', vote_counts)
