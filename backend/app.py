import json
from pathlib import Path
import numpy as np

from flask import Flask, jsonify, request, send_from_directory

from agents.random import random_agent
from agents.muzero import muzero

FRONTEND_DIR = Path(__file__).resolve().parent.parent / "frontend"

app = Flask(
    __name__,
    static_folder=str(FRONTEND_DIR / "static"),
    static_url_path="/static",
)

WIN_LINES = [
    (0, 1, 2), (3, 4, 5), (6, 7, 8),
    (0, 3, 6), (1, 4, 7), (2, 5, 8),
    (0, 4, 8), (2, 4, 6),
]

AGENT_TYPES = {"human", "random", "muzero"}

# agent types whose act() probabilities are not worth displaying:
# humans don't produce any, and random's are uniform over legal moves
NO_DISPLAY_PROBS_AGENT_TYPES = {"human", "random"}

def default_state():
    return {
        "board": [None] * 9,
        "turn": "X",
        "winner": None,
        "over": False,
        "players": {"X": None, "O": None},
        "started": False,
        "action_probs": {"X": None, "O": None},
        "board_state_counts": {"X": None, "O": None},
    }

muzero_config = {
    'state_size': 16,
    'hidden_size': 64,
    'max_iters': 100,
    'gamma': 1.0,
    'k_unroll_steps': 5,
    'temperature': 1.0,
    'dirichlet_alpha': 1.0,
    'root_exploration_fraction': 0.4
}

muzero_agent = muzero.MuZeroAgent(config=muzero_config,load=True)
rand_agent = random_agent.RandomAgent()

RL_AGENTS = {
    "random": rand_agent,
    "muzero": muzero_agent,
}

MUZERO_BOARD_STATES_PATH = (
    Path(__file__).resolve().parent / "agents" / "muzero" / "board_states_eps9000-9999_log.json"
)
with open(MUZERO_BOARD_STATES_PATH) as f:
    muzero_board_state_counts = json.load(f)

def check_result(board):
    for a, b, c in WIN_LINES:
        if board[a] and board[a] == board[b] == board[c]:
            return board[a]
    if all(board):
        return "draw"
    return None


@app.route("/")
def index():
    return send_from_directory(str(FRONTEND_DIR), "index.html")


@app.route("/api/state")
def get_state():
    return jsonify(default_state())


def parse_state(data):
    """Extract and lightly validate the client-supplied game state.

    The frontend is the source of truth for game state (stored in
    localStorage), so each request carries its own state instead of the
    server holding one shared game in memory.
    """
    raw = data.get("state")
    if not isinstance(raw, dict):
        return None

    board = raw.get("board")
    if not isinstance(board, list) or len(board) != 9 or any(v not in (None, "X", "O") for v in board):
        return None

    turn = raw.get("turn")
    if turn not in ("X", "O"):
        return None

    players = raw.get("players")
    if not isinstance(players, dict):
        return None
    player_x, player_o = players.get("X"), players.get("O")
    if player_x not in AGENT_TYPES | {None} or player_o not in AGENT_TYPES | {None}:
        return None

    action_probs = raw.get("action_probs")
    if not isinstance(action_probs, dict):
        action_probs = {}

    board_state_counts = raw.get("board_state_counts")
    if not isinstance(board_state_counts, dict):
        board_state_counts = {}

    return {
        "board": list(board),
        "turn": turn,
        "winner": raw.get("winner"),
        "over": bool(raw.get("over")),
        "players": {"X": player_x, "O": player_o},
        "started": bool(raw.get("started")),
        "action_probs": {"X": action_probs.get("X"), "O": action_probs.get("O")},
        "board_state_counts": {"X": board_state_counts.get("X"), "O": board_state_counts.get("O")},
    }


def apply_move(state, index):
    state["board"][index] = state["turn"]

    result = check_result(state["board"])
    if result == "draw":
        state["over"] = True
        state["winner"] = None
    elif result:
        state["over"] = True
        state["winner"] = result
    else:
        state["turn"] = "O" if state["turn"] == "X" else "X"


def rl_action_to_index(action):
    # action indexes board.reshape(3,3).T in row-major order,
    # so convert back to the flat board index the frontend uses
    return (action % 3) * 3 + (action // 3)


def encode_muzero_board_state(board):
    # board_states log keys use the same index space as RL actions
    # (see rl_action_to_index), with 1/2/0 for X/O/empty
    chars = []
    for action in range(9):
        mark = board[rl_action_to_index(action)]
        chars.append("1" if mark == "X" else "2" if mark == "O" else "0")
    return "".join(chars)


@app.route("/api/move", methods=["POST"])
def make_move():
    data = request.get_json(silent=True) or {}
    index = data.get("index")
    state = parse_state(data)

    if (
        state is None
        or not state["started"]
        or state["over"]
        or state["players"].get(state["turn"]) != "human"
        or not isinstance(index, int)
        or not (0 <= index < 9)
        or state["board"][index] is not None
    ):
        return jsonify(state if state is not None else default_state()), 400

    apply_move(state, index)

    return jsonify(state)


@app.route("/api/agent-move", methods=["POST"])
def agent_move():
    data = request.get_json(silent=True) or {}
    state = parse_state(data)
    rl_agent = RL_AGENTS.get(state["players"].get(state["turn"])) if state is not None else None

    if state is None or not state["started"] or state["over"] or rl_agent is None:
        return jsonify(state if state is not None else default_state()), 400

    current_mark = state["turn"]
    opp_mark = "O" if current_mark == "X" else "X"

    board_vals = np.array(state["board"]).reshape(3, 3).T
    observation = np.empty((3, 3, 2), dtype=np.int8)
    observation[:, :, 0] = np.equal(board_vals, current_mark)
    observation[:, :, 1] = np.equal(board_vals, opp_mark)
    obs_dict = {"observation": observation}

    if state["players"].get(current_mark) == "muzero":
        board_state = encode_muzero_board_state(state["board"])
        count = muzero_board_state_counts.get(board_state, 0)
        print(f"[muzero] board state {board_state} seen {count} times during training")
        state["board_state_counts"][current_mark] = count
    else:
        state["board_state_counts"][current_mark] = None

    action, action_probs = rl_agent.act(obs_dict)
    index = rl_action_to_index(action)

    if state["players"].get(current_mark) not in NO_DISPLAY_PROBS_AGENT_TYPES:
        # rl_action_to_index is its own inverse (it's a matrix transpose),
        # so it also maps a board index back to its action index
        state["action_probs"][current_mark] = [
            float(action_probs[rl_action_to_index(i)]) if state["board"][i] is None else None
            for i in range(9)
        ]
    else:
        state["action_probs"][current_mark] = None

    apply_move(state, index)

    return jsonify(state)


@app.route("/api/reset", methods=["POST"])
def reset():
    data = request.get_json(silent=True) or {}
    players = data.get("players")

    # no players given: soft reset back to the initial, unconfigured state
    # (used by "Play Again" so a fresh agent choice is required for each game)
    if players is None:
        return jsonify(default_state())

    player_x = players.get("X")
    player_o = players.get("O")

    if player_x not in AGENT_TYPES or player_o not in AGENT_TYPES:
        return jsonify(default_state()), 400

    state = default_state()
    state["players"] = {"X": player_x, "O": player_o}
    state["started"] = True
    return jsonify(state)


if __name__ == "__main__":
    app.run(debug=True, port=5000)
