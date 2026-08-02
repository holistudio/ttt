type Mark = "X" | "O";
type AgentType = "human" | "random" | "mcts" | "muzero";

interface GameState {
  board: (Mark | null)[];
  turn: Mark;
  winner: Mark | null;
  over: boolean;
  players: Record<Mark, AgentType | null>;
  started: boolean;
  action_probs: Record<Mark, (number | null)[] | null>;
  board_state_counts: Record<Mark, number | null>;
}

// width of "10,000", the highest count a board state can reach in training
const BOARD_STATE_COUNT_WIDTH = 6;

const AGENT_MOVE_DELAY_MS = 500;

// game state lives in the browser, not on the server: the backend is
// stateless and just computes the next state from whatever we send it
const STORAGE_KEY = "ttt-game-state";

let state: GameState;

function loadStoredState(): GameState | null {
  const raw = localStorage.getItem(STORAGE_KEY);
  if (!raw) {
    return null;
  }
  try {
    return JSON.parse(raw) as GameState;
  } catch {
    return null;
  }
}

function saveState(next: GameState): GameState {
  localStorage.setItem(STORAGE_KEY, JSON.stringify(next));
  return next;
}

async function fetchState(): Promise<GameState> {
  const stored = loadStoredState();
  if (stored) {
    return stored;
  }
  const res = await fetch("/api/state");
  return saveState(await res.json());
}

async function postMove(index: number): Promise<GameState> {
  const res = await fetch("/api/move", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ index, state }),
  });
  return saveState(await res.json());
}

async function postAgentMove(): Promise<GameState> {
  const res = await fetch("/api/agent-move", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ state }),
  });
  return saveState(await res.json());
}

async function postReset(players: Record<Mark, AgentType>): Promise<GameState> {
  const res = await fetch("/api/reset", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ players }),
  });
  return saveState(await res.json());
}

async function postSoftReset(): Promise<GameState> {
  const res = await fetch("/api/reset", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({}),
  });
  return saveState(await res.json());
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
  const nextMoveEl = document.getElementById("next-move") as HTMLButtonElement;

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

  renderProbsLabel("probs-x-label", "X");
  renderProbsBoard("probs-x", "X");
  renderBoardStateCount("probs-x-count", "X");
  renderProbsLabel("probs-o-label", "O");
  renderProbsBoard("probs-o", "O");
  renderBoardStateCount("probs-o-count", "O");
}

function isRlAgent(agent: AgentType | null): boolean {
  return agent !== null && agent !== "human";
}

// when neither player is human, agent moves are stepped one at a time via
// the "Next Move" button rather than auto-playing
function isAgentVsAgent(): boolean {
  return isRlAgent(state.players.X) && isRlAgent(state.players.O);
}

function hasActionProbs(agent: AgentType | null): boolean {
  return agent !== null && agent !== "human" && agent !== "random";
}

function renderProbsLabel(elId: string, mark: Mark): void {
  const el = document.getElementById(elId) as HTMLImageElement;
  const show = hasActionProbs(state.players[mark]) && state.action_probs[mark] !== null;
  el.classList.toggle("hidden", !show);
}

function renderProbsBoard(elId: string, mark: Mark): void {
  const el = document.getElementById(elId) as HTMLDivElement;
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

function formatBoardStateCount(count: number): string {
  // right-align the number within a fixed-width field (padded with
  // non-breaking spaces, which don't collapse) so the surrounding text
  // doesn't shift horizontally as the digit count changes between moves
  const digits = count.toLocaleString("en-US");
  return digits.padStart(BOARD_STATE_COUNT_WIDTH, " ");
}

function renderBoardStateCount(elId: string, mark: Mark): void {
  const el = document.getElementById(elId) as HTMLDivElement;
  const count = state.board_state_counts[mark];
  const show = state.players[mark] === "muzero" && count !== null;

  el.classList.toggle("hidden", !show);
  el.textContent = show ? `seen ${formatBoardStateCount(count as number)} times during training` : "";
}

async function advanceAgentTurns(): Promise<void> {
  if (isAgentVsAgent()) {
    return;
  }
  while (state.started && !state.over && isRlAgent(state.players[state.turn])) {
    await sleep(AGENT_MOVE_DELAY_MS);
    state = await postAgentMove();
    render();
  }
}

async function handleNextMove(): Promise<void> {
  if (!state.started || state.over || !isRlAgent(state.players[state.turn])) {
    return;
  }
  state = await postAgentMove();
  render();
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
  document.getElementById("next-move")?.addEventListener("click", handleNextMove);

  state = await fetchState();

  if (state.players.X) selectX.value = state.players.X;
  if (state.players.O) selectO.value = state.players.O;
  updateNewGameVisibility();

  render();
  await advanceAgentTurns();
}

init();
