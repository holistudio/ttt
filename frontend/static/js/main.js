"use strict";
// width of "10,000", the highest count a board state can reach in training
const BOARD_STATE_COUNT_WIDTH = 6;
const AGENT_MOVE_DELAY_MS = 500;
// game state lives in the browser, not on the server: the backend is
// stateless and just computes the next state from whatever we send it
const STORAGE_KEY = "ttt-game-state";
let state;
function loadStoredState() {
    const raw = localStorage.getItem(STORAGE_KEY);
    if (!raw) {
        return null;
    }
    try {
        return JSON.parse(raw);
    }
    catch {
        return null;
    }
}
function saveState(next) {
    localStorage.setItem(STORAGE_KEY, JSON.stringify(next));
    return next;
}
async function fetchState() {
    const stored = loadStoredState();
    if (stored) {
        return stored;
    }
    const res = await fetch("/api/state");
    return saveState(await res.json());
}
async function postMove(index) {
    const res = await fetch("/api/move", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ index, state }),
    });
    return saveState(await res.json());
}
async function postAgentMove() {
    const res = await fetch("/api/agent-move", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ state }),
    });
    return saveState(await res.json());
}
async function postReset(players) {
    const res = await fetch("/api/reset", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ players }),
    });
    return saveState(await res.json());
}
async function postSoftReset() {
    const res = await fetch("/api/reset", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({}),
    });
    return saveState(await res.json());
}
function sleep(ms) {
    return new Promise((resolve) => setTimeout(resolve, ms));
}
function getSelects() {
    return {
        selectX: document.getElementById("select-x"),
        selectO: document.getElementById("select-o"),
    };
}
function updateNewGameVisibility() {
    const newGameEl = document.getElementById("new-game");
    const { selectX, selectO } = getSelects();
    const ready = Boolean(selectX.value) && Boolean(selectO.value);
    newGameEl.classList.toggle("hidden", !ready);
}
function render() {
    const boardEl = document.getElementById("board");
    const topbarEl = document.getElementById("topbar");
    const gameOverTitleEl = document.getElementById("game-over-title");
    const playAgainEl = document.getElementById("play-again");
    const nextMoveEl = document.getElementById("next-move");
    topbarEl.classList.toggle("hidden", state.over);
    gameOverTitleEl.classList.toggle("hidden", !state.over);
    playAgainEl.classList.toggle("hidden", !state.over);
    nextMoveEl.classList.toggle("hidden", state.over || !state.started || !isAgentVsAgent());
    boardEl.classList.toggle("disabled", !state.started);
    boardEl.classList.toggle("locked", state.over);
    if (state.over) {
        gameOverTitleEl.innerHTML = "";
        if (state.winner) {
            const icon = document.createElement("img");
            icon.className = "overlay-icon";
            icon.src = state.winner === "X" ? "static/img/cross.png" : "static/img/circle.png";
            gameOverTitleEl.appendChild(icon);
            gameOverTitleEl.appendChild(document.createTextNode(" Wins!"));
        }
        else {
            gameOverTitleEl.textContent = "Draw";
        }
    }
    for (let i = 0; i < 9; i++) {
        const existing = boardEl.querySelector(`.piece[data-idx="${i}"]`);
        const mark = state.board[i];
        if (!mark) {
            existing?.remove();
            continue;
        }
        const src = mark === "X" ? "static/img/cross.png" : "static/img/circle.png";
        if (existing) {
            existing.src = src;
        }
        else {
            const img = document.createElement("img");
            img.className = "piece";
            img.dataset.idx = String(i);
            img.src = src;
            boardEl.appendChild(img);
        }
    }
    renderProbsLabel("probs-x-label", "X");
    renderProbsBoard("probs-x", "X");
    renderBoardStateCount("probs-x-count", "X");
    renderProbsLabel("probs-o-label", "O");
    renderProbsBoard("probs-o", "O");
    renderBoardStateCount("probs-o-count", "O");
}
function isRlAgent(agent) {
    return agent !== null && agent !== "human";
}
// when neither player is human, agent moves are stepped one at a time via
// the "Next Move" button rather than auto-playing
function isAgentVsAgent() {
    return isRlAgent(state.players.X) && isRlAgent(state.players.O);
}
function hasActionProbs(agent) {
    return agent !== null && agent !== "human" && agent !== "random";
}
function renderProbsLabel(elId, mark) {
    const el = document.getElementById(elId);
    const show = hasActionProbs(state.players[mark]) && state.action_probs[mark] !== null;
    el.classList.toggle("hidden", !show);
}
function renderProbsBoard(elId, mark) {
    const el = document.getElementById(elId);
    const probs = state.action_probs[mark];
    const show = hasActionProbs(state.players[mark]) && probs !== null;
    el.classList.toggle("hidden", !show);
    el.innerHTML = "";
    if (!show || !probs) {
        return;
    }
    let maxIdx = -1;
    let maxP = -Infinity;
    for (let i = 0; i < 9; i++) {
        const p = probs[i];
        if (p !== null && p > maxP) {
            maxP = p;
            maxIdx = i;
        }
    }
    for (let i = 0; i < 9; i++) {
        const p = probs[i];
        if (p === null) {
            continue;
        }
        const cell = document.createElement("div");
        cell.className = i === maxIdx ? "prob-cell prob-cell-max" : "prob-cell";
        cell.dataset.idx = String(i);
        cell.textContent = p.toFixed(2);
        el.appendChild(cell);
    }
}
function formatBoardStateCount(count) {
    // right-align the number within a fixed-width field (padded with
    // non-breaking spaces, which don't collapse) so the surrounding text
    // doesn't shift horizontally as the digit count changes between moves
    const digits = count.toLocaleString("en-US");
    return digits.padStart(BOARD_STATE_COUNT_WIDTH, " ");
}
function renderBoardStateCount(elId, mark) {
    const el = document.getElementById(elId);
    const count = state.board_state_counts[mark];
    const show = state.players[mark] === "muzero" && count !== null;
    el.classList.toggle("hidden", !show);
    el.textContent = show ? `seen ${formatBoardStateCount(count)} times during training` : "";
}
async function advanceAgentTurns() {
    if (isAgentVsAgent()) {
        return;
    }
    while (state.started && !state.over && isRlAgent(state.players[state.turn])) {
        await sleep(AGENT_MOVE_DELAY_MS);
        state = await postAgentMove();
        render();
    }
}
async function handleNextMove() {
    if (!state.started || state.over || !isRlAgent(state.players[state.turn])) {
        return;
    }
    state = await postAgentMove();
    render();
}
async function handleCellClick(index) {
    if (!state.started ||
        state.over ||
        state.board[index] ||
        state.players[state.turn] !== "human") {
        return;
    }
    state = await postMove(index);
    render();
    await advanceAgentTurns();
}
async function handleNewGame() {
    const { selectX, selectO } = getSelects();
    const playerX = selectX.value;
    const playerO = selectO.value;
    if (!playerX || !playerO) {
        return;
    }
    state = await postReset({ X: playerX, O: playerO });
    render();
    await advanceAgentTurns();
}
async function handlePlayAgain() {
    state = await postSoftReset();
    const { selectX, selectO } = getSelects();
    selectX.value = "";
    selectO.value = "";
    updateNewGameVisibility();
    render();
}
async function init() {
    const boardEl = document.getElementById("board");
    for (let i = 0; i < 9; i++) {
        const cell = document.createElement("div");
        cell.className = "cell";
        cell.addEventListener("click", () => handleCellClick(i));
        boardEl.appendChild(cell);
    }
    const { selectX, selectO } = getSelects();
    selectX.addEventListener("change", updateNewGameVisibility);
    selectO.addEventListener("change", updateNewGameVisibility);
    document.getElementById("new-game")?.addEventListener("click", handleNewGame);
    document.getElementById("play-again")?.addEventListener("click", handlePlayAgain);
    document.getElementById("next-move")?.addEventListener("click", handleNextMove);
    state = await fetchState();
    if (state.players.X)
        selectX.value = state.players.X;
    if (state.players.O)
        selectO.value = state.players.O;
    updateNewGameVisibility();
    render();
    await advanceAgentTurns();
}
init();
