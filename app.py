import eventlet
eventlet.monkey_patch()

import logging
import random
from flask import Flask, render_template, request
from flask_socketio import SocketIO, emit
from server.event_bus import EventBus
from server.player_session import PlayerSessionManager

logging.basicConfig(
    level=logging.INFO,
    format='[%(asctime)s] %(levelname)s: %(message)s',
)
logger = logging.getLogger(__name__)

app = Flask(__name__)
app.config['SECRET_KEY'] = 'anime_bingo_v7_final'
socketio = SocketIO(app, cors_allowed_origins='*', async_mode='eventlet')

PLAYER_COLORS = [
    '#FF4757', '#2ED573', '#1E90FF', '#ECCC68', '#A55EEA', '#FFA502', '#70A1FF', '#7BED9F'
]
TOPICS_SIDE = [
    'ค่าย MAPPA', 'ค่าย Ufotable', 'ผมขาว', 'ผมแดง', 'ใส่หน้ากาก', 'ผมทอง', 'ตัวเอก', 'ต่างโลก'
]
TOPICS_TOP = [
    'เป็นโจรสลัด', 'ใช้ดาบ', 'พลังไฟ', 'ตลก', 'ตายตอนจบ', 'เก่งเกินไป', 'ใส่หมวก', 'นินจา'
]

event_bus = EventBus()
session_manager = PlayerSessionManager(disconnect_timeout=10, event_bus=event_bus)

game_state = {
    'col_headers': random.sample(TOPICS_TOP, 5),
    'row_headers': random.sample(TOPICS_SIDE, 5),
    'claimed': {},
    'player_order': [],
    'current_turn_idx': 0,
}

@app.route('/')
def index():
    return render_template('index.html')

@socketio.on('connect')
def on_connect():
    logger.info('Socket connected: %s', request.sid)

@socketio.on('disconnect')
def on_disconnect():
    sid = request.sid
    logger.info('Socket disconnected: %s', sid)
    session_manager.detach_session(sid)
    broadcast_state()

@socketio.on('join_game')
def handle_join(data):
    sid = request.sid
    player_id = data.get('player_id')
    name = data.get('name', 'Player').strip()[:24] or 'Player'
    session = None
    reconnect = False

    if player_id:
        session = session_manager.get_by_player_id(player_id)
        if session:
            session = session_manager.attach_session(player_id, sid, name)
            reconnect = True

    if session is None:
        assigned_color = PLAYER_COLORS[len(session_manager.get_all_sessions()) % len(PLAYER_COLORS)]
        session = session_manager.register_new_player(name, sid, assigned_color)
        game_state['player_order'].append(session['player_id'])
        logger.info('New player joined: %s %s', session['player_id'], session['name'])

    if session['player_id'] not in game_state['player_order']:
        game_state['player_order'].append(session['player_id'])

    normalize_turn_index()
    emit('session_ready', {
        'player_id': session['player_id'],
        'player': {
            'name': session['name'],
            'color': session['color'],
            'hearts': session['hearts'],
            'connected': session['connected'],
        },
        'col_headers': game_state['col_headers'],
        'row_headers': game_state['row_headers'],
        'claimed': game_state['claimed'],
        'state': get_state_payload(),
        'reconnect': reconnect,
    })
    logger.info('Player %s joined or reconnected: sid=%s reconnect=%s', session['player_id'], sid, reconnect)
    broadcast_state()

@socketio.on('sync_temp_move')
def handle_temp_move(data):
    sid = request.sid
    session = session_manager.get_by_sid(sid)
    active_id = get_current_player_id()
    if not session or session['player_id'] != active_id:
        return
    payload = {**data, 'color': session['color']} if data else None
    emit('player_moving', payload, broadcast=True, include_self=False)

@socketio.on('confirm_final_claim')
def handle_confirm(data):
    sid = request.sid
    session = session_manager.get_by_sid(sid)
    active_id = get_current_player_id()
    if not session or session['player_id'] != active_id:
        emit('session_error', {'message': 'ไม่ใช่ตาของคุณในตอนนี้'})
        return

    slot_id = data.get('slot_id')
    if not slot_id or slot_id in game_state['claimed']:
        emit('session_error', {'message': 'ช่องนี้ไม่สามารถเลือกได้'})
        return

    game_state['claimed'][slot_id] = {
        'img': data['img'],
        'name': data['name'],
        'player_id': session['player_id'],
        'color': session['color'],
        'disputes': [],
    }

    logger.info('Slot claimed: %s by %s', slot_id, session['player_id'])
    advance_turn()
    emit('slot_locked', {
        **data,
        'player_id': session['player_id'],
        'color': session['color'],
    }, broadcast=True)
    broadcast_state()
    check_win_condition()

@socketio.on('vote_dispute')
def handle_vote(data):
    voter = session_manager.get_by_sid(request.sid)
    slot_id = data.get('slot_id')
    if not voter or not slot_id:
        return
    target = game_state['claimed'].get(slot_id)
    if not target or target['player_id'] == voter['player_id']:
        return
    if voter['player_id'] in target['disputes']:
        return
    target['disputes'].append(voter['player_id'])
    emit('dispute_update', {'slot_id': slot_id, 'count': len(target['disputes'])}, broadcast=True)
    logger.info('Vote dispute: %s by %s', slot_id, voter['player_id'])

    # Check if dispute votes exceed half the room
    total_players = len(session_manager.get_all_sessions())
    if total_players > 1 and len(target['disputes']) > total_players // 2:
        reset_bingo()
        emit('bingo_reset', {'reason': 'dispute_majority'}, broadcast=True)
        logger.info('Bingo reset due to dispute majority: %s votes out of %s', len(target['disputes']), total_players)


@socketio.on('skip_turn')
def handle_skip():
    session = session_manager.get_by_sid(request.sid)
    active_id = get_current_player_id()
    if not session or session['player_id'] != active_id:
        return
    session['hearts'] = max(0, session['hearts'] - 1)
    logger.info('Turn skipped by %s hearts=%s', session['player_id'], session['hearts'])
    advance_turn()
    broadcast_state()


def get_current_player_id():
    if not game_state['player_order']:
        return None
    idx = game_state['current_turn_idx']
    if idx < 0 or idx >= len(game_state['player_order']):
        return None
    return game_state['player_order'][idx]


def advance_turn():
    if not game_state['player_order']:
        game_state['current_turn_idx'] = 0
        return
    game_state['current_turn_idx'] = (game_state['current_turn_idx'] + 1) % len(game_state['player_order'])
    event_bus.publish('turn_changed', turn=game_state['current_turn_idx'])
    logger.info('Turn advanced to index %s', game_state['current_turn_idx'])
    check_tie_condition()


def normalize_turn_index():
    if not game_state['player_order']:
        game_state['current_turn_idx'] = 0
        return
    if game_state['current_turn_idx'] >= len(game_state['player_order']):
        game_state['current_turn_idx'] = 0


def get_state_payload():
    return {
        'players': session_manager.get_all_sessions(),
        'order': game_state['player_order'],
        'turn': game_state['current_turn_idx'],
    }


def broadcast_state():
    payload = get_state_payload()
    socketio.emit('update_game_state', payload, broadcast=True)
    event_bus.publish('state_updated', state=payload)


def reset_bingo():
    global game_state
    game_state['col_headers'] = random.sample(TOPICS_TOP, 5)
    game_state['row_headers'] = random.sample(TOPICS_SIDE, 5)
    game_state['claimed'] = {}
    game_state['current_turn_idx'] = 0
    # Reset hearts for all players
    for session in session_manager.get_all_sessions().values():
        session['hearts'] = 3
    logger.info('Bingo reset: new headers generated')


def check_win_condition():
    # Check if any player has completed a bingo (5 in a row/col/diagonal)
    # For simplicity, check if all slots are claimed
    if len(game_state['claimed']) >= 25:
        reset_bingo()
        emit('bingo_reset', {'reason': 'game_win'}, broadcast=True)
        logger.info('Bingo reset due to game win')


def check_tie_condition():
    # Check if there's a tie (e.g., multiple players with same score)
    # For now, simple check: if all players have 0 hearts
    active_sessions = [s for s in session_manager.get_all_sessions().values() if s['connected']]
    if all(s['hearts'] <= 0 for s in active_sessions):
        reset_bingo()
        emit('bingo_reset', {'reason': 'tie'}, broadcast=True)
        logger.info('Bingo reset due to tie')


@event_bus.subscribe('player_removed')
def handle_player_removed(player_id, session):
    if player_id not in game_state['player_order']:
        return
    position = game_state['player_order'].index(player_id)
    game_state['player_order'].pop(position)
    if position <= game_state['current_turn_idx']:
        game_state['current_turn_idx'] = max(0, game_state['current_turn_idx'] - 1)
    normalize_turn_index()
    logger.info('Player removed from game order: %s', player_id)
    broadcast_state()


@event_bus.subscribe('player_disconnected')
def handle_player_disconnected(player_id, session):
    logger.info('Player disconnected pending cleanup: %s', player_id)
    broadcast_state()


@event_bus.subscribe('player_created')
def handle_player_created(player_id, session):
    logger.info('Player created: %s %s', player_id, session['name'])


@event_bus.subscribe('player_reconnected')
def handle_player_reconnected(player_id, session):
    logger.info('Player reconnected: %s %s', player_id, session['name'])
    broadcast_state()


if __name__ == '__main__':
    socketio.run(app, host='0.0.0.0', port=5000)
