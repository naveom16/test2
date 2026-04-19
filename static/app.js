const socket = io();
let myPlayerId = null;
let myName = null;
let turnPlayerId = null;
let currentTemp = null;
let playerColor = "";
let cols = [];
let rows = [];

const localPlayerId = localStorage.getItem('animeBingoPlayerId');
const storedName = localStorage.getItem('animeBingoPlayerName');
function createPersistentId() {
    if (typeof crypto !== 'undefined' && crypto.randomUUID) {
        return crypto.randomUUID();
    }
    return `player-${Math.random().toString(36).substring(2, 10)}-${Date.now().toString(36)}`;
}
myPlayerId = localPlayerId || createPersistentId();
myName = storedName || '';

const loginOverlay = document.getElementById('loginOverlay');
const usernameInput = document.getElementById('username');
usernameInput.value = myName;

function setLoginVisible(visible) {
    loginOverlay.style.display = visible ? 'flex' : 'none';
}

function enterGame() {
    const name = document.getElementById('username').value.trim();
    if (!name) {
        usernameInput.focus();
        return;
    }
    myName = name;
    localStorage.setItem('animeBingoPlayerId', myPlayerId);
    localStorage.setItem('animeBingoPlayerName', myName);
    socket.emit('join_game', { player_id: myPlayerId, name: myName });
    setLoginVisible(false);
}

socket.on('connect', () => {
    console.debug('[client] connected', socket.id);
    if (myName && localPlayerId) {
        socket.emit('join_game', { player_id: myPlayerId, name: myName });
        setLoginVisible(false);
    }
});

socket.on('session_ready', (data) => {
    myPlayerId = data.player_id;
    myName = data.player.name;
    playerColor = data.player.color;
    cols = data.col_headers;
    rows = data.row_headers;
    localStorage.setItem('animeBingoPlayerId', myPlayerId);
    localStorage.setItem('animeBingoPlayerName', myName);
    buildGrid(data.claimed);
    updateGameState(data.state);
});

socket.on('session_error', (data) => {
    console.error('[client] session error', data?.message);
    alert(data?.message || 'เกิดข้อผิดพลาดในการเชื่อมต่อ');
    setLoginVisible(true);
});

socket.on('player_moving', (data) => {
    document.querySelectorAll('.cell.drop-zone').forEach(c => {
        c.innerHTML = '<span style="color:#888; font-size:2rem; font-weight:bold;">?</span>';
        c.style.borderColor = '#333';
        c.draggable = false;
    });
    if (data) {
        const cell = document.getElementById(`cell-${data.slot_id}`);
        if (cell) {
            cell.innerHTML = `<img src="${data.img}">`;
            cell.style.borderColor = data.color;
            cell.style.borderStyle = 'solid';
        }
    }
});

socket.on('slot_locked', (data) => {
    const cell = document.getElementById(`cell-${data.slot_id}`);
    if (cell) {
        setLockedCell(cell, data, data.slot_id);
    }
    if (myPlayerId === data.player_id) {
        currentTemp = null;
        document.getElementById('confirm').disabled = true;
    }
});

socket.on('dispute_update', (data) => {
    const badge = document.getElementById(`dispute-${data.slot_id}`);
    if (badge) {
        badge.textContent = `ค้าน ${data.count}`;
        badge.style.display = 'block';
    }
});

socket.on('update_game_state', (data) => {
    updateGameState(data);
});

socket.on('bingo_reset', (data) => {
    console.log('Bingo reset:', data.reason);
    alert('Bingo ใหม่ถูกสร้างแล้ว! เหตุผล: ' + data.reason);
    // Optionally reload or update UI
    location.reload(); // Simple reload for now
});

socket.on('connect_error', (error) => {
    console.error('[client] connect_error', error);
});

socket.on('disconnect', (reason) => {
    console.warn('[client] disconnected', reason);
});

function buildGrid(claimed) {
    const grid = document.getElementById('bingoGrid');
    grid.innerHTML = '';

    grid.appendChild(createHeaderCell('', true));
    cols.forEach((col) => grid.appendChild(createHeaderCell(col, false)));

    for (let r = 0; r < 5; r += 1) {
        grid.appendChild(createHeaderCell(rows[r], true, true));
        for (let c = 0; c < 5; c += 1) {
            const slotId = `${r}-${c}`;
            const cell = document.createElement('div');
            cell.id = `cell-${slotId}`;
            cell.className = 'cell';
            if (claimed?.[slotId]) {
                setLockedCell(cell, claimed[slotId], slotId);
            } else {
                cell.classList.add('drop-zone');
                cell.innerHTML = '<span style="color:#888; font-size:2rem; font-weight:bold;">?</span>';
                cell.ondragover = (e) => e.preventDefault();
                cell.ondrop = (e) => onDrop(e, slotId);
                cell.onclick = () => onQuickCancel(slotId);
                cell.ondragstart = (e) => onInternalDrag(e, slotId);
            }
            grid.appendChild(cell);
        }
    }
}

function createHeaderCell(text, isCorner = false, isRow = false) {
    const node = document.createElement('div');
    node.className = `cell ${isRow ? 'h-row' : 'h-col'}`;
    if (isCorner) {
        node.textContent = '';
        node.style.background = 'transparent';
        node.style.border = 'none';
    } else {
        node.textContent = text;
    }
    return node;
}

function onDrop(event, slotId) {
    event.preventDefault();
    if (turnPlayerId !== myPlayerId) {
        return;
    }
    const raw = event.dataTransfer.getData('text');
    if (!raw) {
        return;
    }
    const data = JSON.parse(raw);
    if (!data || !data.img || !data.name) {
        return;
    }
    if (currentTemp && currentTemp.slot_id !== slotId) {
        const previous = document.getElementById(`cell-${currentTemp.slot_id}`);
        if (previous && !previous.classList.contains('locked')) {
            previous.innerHTML = '<span style="color:#888; font-size:2rem; font-weight:bold;">?</span>';
            previous.style.borderColor = '#333';
            previous.draggable = false;
        }
    }

    const cell = document.getElementById(`cell-${slotId}`);
    if (!cell || cell.classList.contains('locked')) {
        return;
    }
    cell.innerHTML = `<img src="${data.img}">`;
    cell.style.borderColor = playerColor;
    cell.draggable = true;
    currentTemp = { slot_id: slotId, img: data.img, name: data.name };
    socket.emit('sync_temp_move', currentTemp);
    document.getElementById('confirm').disabled = false;
}

function onInternalDrag(event, slotId) {
    if (turnPlayerId !== myPlayerId || !currentTemp || currentTemp.slot_id !== slotId) {
        event.preventDefault();
        return;
    }
    event.dataTransfer.setData('text', JSON.stringify(currentTemp));
}

function onQuickCancel(slotId) {
    if (turnPlayerId !== myPlayerId || !currentTemp || currentTemp.slot_id !== slotId) {
        return;
    }
    const cell = document.getElementById(`cell-${slotId}`);
    if (!cell) {
        return;
    }
    cell.innerHTML = '<span style="color:#888; font-size:2rem; font-weight:bold;">?</span>';
    cell.style.borderColor = '#333';
    cell.draggable = false;
    currentTemp = null;
    socket.emit('sync_temp_move', null);
    document.getElementById('confirm').disabled = true;
}

function setLockedCell(element, data, slotId) {
    element.className = 'cell locked';
    element.innerHTML = `
        <img src="${data.img}">
        <button class="vote-btn" onclick="socket.emit('vote_dispute', { slot_id: '${slotId}' })">ค้าน!</button>
        <div id="dispute-${slotId}" class="dispute-badge" style="display:${data.disputes?.length ? 'block' : 'none'}">ค้าน ${data.disputes?.length || 0}</div>
    `;
    element.style.border = `4px solid ${data.color}`;
    element.style.boxShadow = `0 0 16px ${data.color}44`;
}

function updateGameState(data) {
    turnPlayerId = data.order[data.turn] || null;
    playerColor = data.players?.[myPlayerId]?.color || playerColor;
    const playerArea = document.getElementById('players');
    playerArea.innerHTML = '';

    Object.entries(data.players || {}).forEach(([playerId, player]) => {
        const isActive = playerId === turnPlayerId;
        const isDisconnected = !player.connected;
        const isSkull = player.hearts <= 0;
        const card = document.createElement('div');
        card.className = `player-card${isActive ? ' active' : ''}${isDisconnected ? ' disconnected' : ''}${isSkull ? ' skull' : ''}`;
        card.style.color = player.color;
        card.innerHTML = `
            <div class="p-dot" style="background:${player.color};"></div>
            <div class="player-name">${player.name}</div>
            <div class="hearts">${'❤️'.repeat(Math.max(0, player.hearts))}</div>
        `;
        playerArea.appendChild(card);
    });

    const indicator = document.getElementById('turnIndicator');
    if (myPlayerId === turnPlayerId) {
        indicator.textContent = '🎮 ตาของคุณแล้ว! เลือกตัวละครมาวางได้เลย';
        indicator.style.color = 'var(--success)';
    } else {
        indicator.textContent = '⌛ รอเพื่อนเล่น...';
        indicator.style.color = 'var(--muted)';
    }
    document.getElementById('skip').disabled = (myPlayerId !== turnPlayerId);

    // Auto-skip if current player is disconnected or has no hearts
    const currentPlayer = data.players?.[turnPlayerId];
    if (currentPlayer && (currentPlayer.hearts <= 0 || !currentPlayer.connected)) {
        setTimeout(() => {
            if (turnPlayerId === myPlayerId) {
                socket.emit('skip_turn');
            }
        }, 2000); // Wait 2 seconds before auto-skip
    }
}

let searchTimeout = null;
function onSearch() {
    clearTimeout(searchTimeout);
    searchTimeout = window.setTimeout(async () => {
        const query = document.getElementById('search').value.trim();
        if (query.length < 3) {
            document.getElementById('animeResultsLabel').style.display = 'none';
            document.getElementById('charResultsLabel').style.display = 'none';
            document.getElementById('animeResults').innerHTML = '';
            document.getElementById('charResults').innerHTML = '';
            return;
        }
        try {
            const response = await fetch(`https://api.jikan.moe/v4/anime?q=${encodeURIComponent(query)}&limit=12`);
            const payload = await response.json();
            renderAnimeResults(payload.data || []);
        } catch (error) {
            console.error('[search] anime lookup failed', error);
        }
    }, 300);
}

function renderAnimeResults(items) {
    const container = document.getElementById('animeResults');
    const label = document.getElementById('animeResultsLabel');
    const count = document.getElementById('animeCount');
    container.innerHTML = '';
    if (!items.length) {
        label.style.display = 'none';
        return;
    }
    label.style.display = 'flex';
    count.textContent = items.length;
    items.forEach((anime) => {
        const card = document.createElement('div');
        card.className = 'item-card';
        card.innerHTML = `
            <img src="${anime.images?.jpg?.image_url || ''}" alt="${anime.title}">
            <div class="item-name">${anime.title}</div>
        `;
        card.onclick = () => getChars(anime.mal_id, anime.title);
        container.appendChild(card);
    });
}

async function getChars(animeId, animeTitle) {
    try {
        const response = await fetch(`https://api.jikan.moe/v4/anime/${animeId}/characters`);
        const payload = await response.json();
        renderCharacterResults(payload.data || [], animeTitle);
    } catch (error) {
        console.error('[search] character fetch failed', error);
    }
}

function renderCharacterResults(characters, animeTitle) {
    const container = document.getElementById('charResults');
    const label = document.getElementById('charResultsLabel');
    const count = document.getElementById('charCount');
    container.innerHTML = '';
    if (!characters.length) {
        label.style.display = 'none';
        return;
    }
    label.style.display = 'flex';
    count.textContent = Math.min(characters.length, 20);
    characters.slice(0, 20).forEach((item) => {
        const character = item.character;
        const card = document.createElement('div');
        card.className = 'item-card';
        card.innerHTML = `
            <img src="${character.images?.jpg?.image_url || ''}" alt="${character.name}">
            <div class="item-name">${character.name}</div>
        `;
        card.draggable = true;
        card.ondragstart = (event) => {
            if (turnPlayerId !== myPlayerId) {
                event.preventDefault();
                return;
            }
            event.dataTransfer.setData('text', JSON.stringify({ name: character.name, img: character.images?.jpg?.image_url || '' }));
        };
        container.appendChild(card);
    });
}

function showConfirmModal() {
    if (!currentTemp) {
        return;
    }
    document.getElementById('cImg').innerHTML = `<img src="${currentTemp.img}" style="width:150px; height:150px; border-radius:20px; border:4px solid ${playerColor}; object-fit:cover;">`;
    document.getElementById('cText').textContent = `คุณแน่ใจหรือไม่ว่า "${currentTemp.name}" เหมาะสมกับช่องนี้?`;
    document.getElementById('confirmModal').classList.add('active');
}

function submitMove() {
    if (!currentTemp) {
        return;
    }
    socket.emit('confirm_final_claim', currentTemp);
    closeConfirm();
}

function closeConfirm() {
    document.getElementById('confirmModal').classList.remove('active');
}

window.enterGame = enterGame;
window.showConfirmModal = showConfirmModal;
window.submitMove = submitMove;
window.closeConfirm = closeConfirm;
window.onSearch = onSearch;

window.addEventListener('DOMContentLoaded', () => {
    if (myName && localPlayerId) {
        usernameInput.value = myName;
    }
    if (!myName) {
        setLoginVisible(true);
    }
});
