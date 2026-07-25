"use strict";
let state;
async function fetchState() {
    const res = await fetch("/api/state");
    return res.json();
}
async function postMove(index) {
    const res = await fetch("/api/move", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ index }),
    });
    return res.json();
}
async function postReset() {
    const res = await fetch("/api/reset", { method: "POST" });
    return res.json();
}
function render() {
    const boardEl = document.getElementById("board");
    const overlayEl = document.getElementById("game-over");
    const overlayTitleEl = document.getElementById("game-over-title");
    boardEl.classList.toggle("over", state.over);
    overlayEl.classList.toggle("hidden", !state.over);
    if (state.over) {
        overlayTitleEl.textContent = state.winner ? `${state.winner} Wins!` : "Draw";
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
}
async function handleCellClick(index) {
    if (state.over || state.board[index]) {
        return;
    }
    state = await postMove(index);
    render();
}
async function handleReset() {
    state = await postReset();
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
    document.getElementById("new-game")?.addEventListener("click", handleReset);
    document.getElementById("play-again")?.addEventListener("click", handleReset);
    state = await fetchState();
    render();
}
init();
