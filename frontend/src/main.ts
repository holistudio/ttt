type Mark = "X" | "O";
type AgentType = "human" | "muzero";

interface GameState {
  board: (Mark | null)[];
  turn: Mark;
  winner: Mark | null;
  over: boolean;
  players: Record<Mark, AgentType | null>;
  started: boolean;
}

const AGENT_MOVE_DELAY_MS = 500;

let state: GameState;

async function fetchState(): Promise<GameState> {
  const res = await fetch("/api/state");
  return res.json();
}

async function postMove(index: number): Promise<GameState> {
  const res = await fetch("/api/move", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ index }),
  });
  return res.json();
}

async function postAgentMove(): Promise<GameState> {
  const res = await fetch("/api/agent-move", { method: "POST" });
  return res.json();
}

async function postReset(players: Record<Mark, AgentType>): Promise<GameState> {
  const res = await fetch("/api/reset", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ players }),
  });
  return res.json();
}

async function postSoftReset(): Promise<GameState> {
  const res = await fetch("/api/reset", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({}),
  });
  return res.json();
}

function sleep(ms: number): Promise<void> {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

function getSelects(): { selectX: HTMLSelectElement; selectO: HTMLSelectElement } {
  return {
    selectX: document.getElementById("select-x") as HTMLSelectElement,
    selectO: document.getElementById("select-o") as HTMLSelectElement,
  };
}

function updateNewGameVisibility(): void {
  const newGameEl = document.getElementById("new-game") as HTMLButtonElement;
  const { selectX, selectO } = getSelects();
  const ready = Boolean(selectX.value) && Boolean(selectO.value);
  newGameEl.classList.toggle("hidden", !ready);
}

function render(): void {
  const boardEl = document.getElementById("board") as HTMLDivElement;
  const topbarEl = document.getElementById("topbar") as HTMLElement;
  const gameOverTitleEl = document.getElementById("game-over-title") as HTMLHeadingElement;
  const playAgainEl = document.getElementById("play-again") as HTMLButtonElement;

  topbarEl.classList.toggle("hidden", state.over);
  gameOverTitleEl.classList.toggle("hidden", !state.over);
  playAgainEl.classList.toggle("hidden", !state.over);
  boardEl.classList.toggle("disabled", !state.started || state.over);

  if (state.over) {
    gameOverTitleEl.innerHTML = "";
    if (state.winner) {
      const icon = document.createElement("img");
      icon.className = "overlay-icon";
      icon.src = state.winner === "X" ? "static/img/cross.png" : "static/img/circle.png";
      gameOverTitleEl.appendChild(icon);
      gameOverTitleEl.appendChild(document.createTextNode(" Wins!"));
    } else {
      gameOverTitleEl.textContent = "Draw";
    }
  }

  for (let i = 0; i < 9; i++) {
    const existing = boardEl.querySelector<HTMLImageElement>(`.piece[data-idx="${i}"]`);
    const mark = state.board[i];

    if (!mark) {
      existing?.remove();
      continue;
    }

    const src = mark === "X" ? "static/img/cross.png" : "static/img/circle.png";
    if (existing) {
      existing.src = src;
    } else {
      const img = document.createElement("img");
      img.className = "piece";
      img.dataset.idx = String(i);
      img.src = src;
      boardEl.appendChild(img);
    }
  }
}

async function advanceAgentTurns(): Promise<void> {
  while (state.started && !state.over && state.players[state.turn] === "muzero") {
    await sleep(AGENT_MOVE_DELAY_MS);
    state = await postAgentMove();
    render();
  }
}

async function handleCellClick(index: number): Promise<void> {
  if (
    !state.started ||
    state.over ||
    state.board[index] ||
    state.players[state.turn] !== "human"
  ) {
    return;
  }
  state = await postMove(index);
  render();
  await advanceAgentTurns();
}

async function handleNewGame(): Promise<void> {
  const { selectX, selectO } = getSelects();
  const playerX = selectX.value as AgentType;
  const playerO = selectO.value as AgentType;
  if (!playerX || !playerO) {
    return;
  }
  state = await postReset({ X: playerX, O: playerO });
  render();
  await advanceAgentTurns();
}

async function handlePlayAgain(): Promise<void> {
  state = await postSoftReset();
  const { selectX, selectO } = getSelects();
  selectX.value = "";
  selectO.value = "";
  updateNewGameVisibility();
  render();
}

async function init(): Promise<void> {
  const boardEl = document.getElementById("board") as HTMLDivElement;
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

  state = await fetchState();

  if (state.players.X) selectX.value = state.players.X;
  if (state.players.O) selectO.value = state.players.O;
  updateNewGameVisibility();

  render();
  await advanceAgentTurns();
}

init();
