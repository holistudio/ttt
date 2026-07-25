type Mark = "X" | "O";

interface GameState {
  board: (Mark | null)[];
  turn: Mark;
  winner: Mark | null;
  over: boolean;
}

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

async function postReset(): Promise<GameState> {
  const res = await fetch("/api/reset", { method: "POST" });
  return res.json();
}

function render(): void {
  const boardEl = document.getElementById("board") as HTMLDivElement;
  boardEl.classList.toggle("over", state.over);

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

async function handleCellClick(index: number): Promise<void> {
  if (state.over) {
    state = await postReset();
    render();
    return;
  }
  if (state.board[index]) {
    return;
  }
  state = await postMove(index);
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
  state = await fetchState();
  render();
}

init();
