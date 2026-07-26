import random

import torch

"""RANDOM AGENT"""
class RandomAgent(object):
    """
    Random agent class

    selects uniformly among legal actions;
    exposes the same essential interface as MuZeroAgent
    so it can be swapped in without changing caller code
    """
    def __init__(self, config=None):
        self.obs_size = torch.Size([9])
        self.action_size = 9
        pass

    """game environment helper functions"""
    def flatten(self, observation_space):
        """
        convert observation space
        """

        H, W, C = observation_space['observation'].shape
        # return observation space as a 1-D vector
        return torch.zeros(H*W)

    def preprocess_obs(self, observation):
        """
        convert environment observation dictionary
        into a canonical (player-relative) torch tensor for neural nets
        """
        current_player_plane = torch.tensor(observation["observation"][:, :, 0], dtype=torch.float32)
        opponent_plane = torch.tensor(observation["observation"][:, :, 1], dtype=torch.float32)
        obs = current_player_plane - opponent_plane
        return obs.reshape(-1)

    def display_board(self, obs):
        """
        display the board to the terminal
        """

        board = [
                [" "," "," "],
                [" "," "," "],
                [" "," "," "]]

        obs_grid = obs.reshape(3, 3)

        for i in range(3):
            for j in range(3):
                if obs_grid[i, j] == 1:
                    board[j][i] = "X"
                elif obs_grid[i, j] == -1:
                    board[j][i] = "O"

        print("BOARD")
        print("=====")
        for i,row in enumerate(board):
            row_disp = ("|").join(row)
            print(row_disp)
            if i < 2:
                print("-----")
        print("=====")
        print()

    """random search functions"""

    def search(self, obs):
        """
        select a uniformly random legal action

        given:
        - obs: tensor representation of current game environment observation state

        return: next action to play in the game
        """
        legal_actions = torch.where(obs == 0)[0].tolist()
        return random.choice(legal_actions)

    """RL agent standard functions"""

    def step(self, observation):
        """
        select next action to play in the game
        """
        obs = self.preprocess_obs(observation)
        action = self.search(obs)
        return action

    def act(self, observation):
        """
        select next action to play in the game
        """
        obs = self.preprocess_obs(observation)
        action = self.search(obs)
        return action
