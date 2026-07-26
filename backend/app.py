from pathlib import Path
import numpy as np

from flask import Flask, jsonify, request, send_from_directory

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

game = {
    "board": [None] * 9,
    "turn": "X",
    "winner": None,
    "over": False,
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

agent = muzero.MuZeroAgent(config=muzero_config,load=True)

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
    return jsonify(game)


@app.route("/api/move", methods=["POST"])
def make_move():
    data = request.get_json(silent=True) or {}
    index = data.get("index")

    if game["over"] or not isinstance(index, int) or not (0 <= index < 9) or game["board"][index] is not None:
        return jsonify(game), 400

    game["board"][index] = game["turn"]

    result = check_result(game["board"])

    if result == "draw":
        game["over"] = True
        game["winner"] = None
    elif result:
        game["over"] = True
        game["winner"] = result
    else:
        game["turn"] = "O" if game["turn"] == "X" else "X"

        if game["turn"] == "O":
            board_vals = np.array(game["board"]).reshape(3,3).T
            observation = np.empty((3,3,2), dtype=np.int8)
            observation[:,:,0] = np.equal(board_vals, "O")
            observation[:,:,1] = np.equal(board_vals, "X")
            obs_dict = {
                'observation': observation
            }
            action = agent.act(obs_dict)
            # action indexes board_vals (board.reshape(3,3).T) in row-major order,
            # so convert back to the flat board index the frontend uses
            agent_index = (action % 3) * 3 + (action // 3)
            game["board"][agent_index] = "O"

            result = check_result(game["board"])
            if result == "draw":
                game["over"] = True
                game["winner"] = None
            elif result:
                game["over"] = True
                game["winner"] = result
            else:
                game["turn"] = "X"

    return jsonify(game)


@app.route("/api/reset", methods=["POST"])
def reset():
    game["board"] = [None] * 9
    game["turn"] = "X"
    game["winner"] = None
    game["over"] = False
    return jsonify(game)


if __name__ == "__main__":
    app.run(debug=True, port=5000)
