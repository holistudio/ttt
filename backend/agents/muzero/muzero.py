import math
import copy
import random
import os
import numpy as np

import torch
import torch.nn as nn
import torch.nn.functional as F

def min_max_normalize(state):
    """
    min-max normalize hidden state to [0, 1] elementwise per row,
    matching the action input range (Appendix G)
    """
    s_min = state.min(dim=-1, keepdim=True)[0]
    s_max = state.max(dim=-1, keepdim=True)[0]
    scale = s_max - s_min
    scale = torch.where(scale < 1e-5, scale + 1e-5, scale)
    return (state - s_min) / scale

"""NEURAL NETS"""
class StateFunction(nn.Module):
    """
    representation function, h
    
    input: observation/state of current environment (tic-tac-toe board)
    output: hidden representation of initial observation for subsequent MCTS
    """
    def __init__(self, input_size, output_size, hidden_size):
        super().__init__()
        self.lin1 = nn.Linear(input_size, hidden_size)
        self.lin2 = nn.Linear(hidden_size, hidden_size)
        self.lin3 = nn.Linear(hidden_size, hidden_size)
        self.lin4 = nn.Linear(hidden_size, hidden_size)
        self.lin5 = nn.Linear(hidden_size, output_size)
        self.apply(self._init_weights)
        pass

    def _init_weights(self, module):
        if isinstance(module, nn.Linear):
            torch.nn.init.kaiming_normal_(module.weight, nonlinearity='relu')
            if module.bias is not None:
                torch.nn.init.zeros_(module.bias)

    def forward(self, obs):
        x = self.lin1(obs)
        x = F.gelu(x)
        x = self.lin2(x)
        x = F.gelu(x)
        x = self.lin3(x)
        x = F.gelu(x)
        x = self.lin4(x)
        x = F.gelu(x)
        x = self.lin5(x)
        s = min_max_normalize(x)
        return s

class DynamicsFunction(nn.Module):
    """
    dynamics function, g
    
    input: hidden state representation, s_t, and candidate action, a
    output: predict next hidden state, s_t+1, and reward, r_t+1
    """
    def __init__(self, input_size, output_size, hidden_size):
        super().__init__()
        self.lin1 = nn.Linear(input_size, hidden_size)
        self.lin2 = nn.Linear(hidden_size, hidden_size)
        self.lin3 = nn.Linear(hidden_size, hidden_size)
        self.lin4 = nn.Linear(hidden_size, hidden_size)
        self.state_head = nn.Linear(hidden_size, output_size)
        self.reward_head = nn.Linear(hidden_size, 1)
        self.apply(self._init_weights)
        torch.nn.init.normal_(self.reward_head.weight, mean=0.0, std=0.01)
        torch.nn.init.zeros_(self.reward_head.bias)
        pass

    def _init_weights(self, module):
        if isinstance(module, nn.Linear):
            torch.nn.init.kaiming_normal_(module.weight, nonlinearity='relu')
            if module.bias is not None:
                torch.nn.init.zeros_(module.bias)

    def forward(self, s_prev, a):
        # concatenate along dimension 1 to support batch processing
        x = torch.cat((s_prev, a), dim=1)
        x = self.lin1(x)
        x = F.gelu(x)
        x = self.lin2(x)
        x = F.gelu(x)
        x = self.lin3(x)
        x = F.gelu(x)
        x = self.lin4(x)
        x = F.gelu(x)
        s = self.state_head(x)
        s = min_max_normalize(s)
        r = self.reward_head(x)
        return s, r
    
class PredictionFunction(nn.Module):
    """
    prediction function, f
    
    input: hidden state representation, s_t
    output: policy logits, p_t, and value, v_t
    """
    def __init__(self, input_size, output_size, hidden_size):
        super().__init__()
        self.lin1 = nn.Linear(input_size, hidden_size)
        self.lin2 = nn.Linear(hidden_size, hidden_size)
        self.lin3 = nn.Linear(hidden_size, hidden_size)
        self.lin4 = nn.Linear(hidden_size, hidden_size)
        self.policy_head = nn.Linear(hidden_size, output_size)
        self.value_head = nn.Linear(hidden_size, 1)
        self.apply(self._init_weights)
        torch.nn.init.normal_(self.policy_head.weight, mean=0.0, std=0.01)
        torch.nn.init.zeros_(self.policy_head.bias)
        torch.nn.init.normal_(self.value_head.weight, mean=0.0, std=0.01)
        torch.nn.init.zeros_(self.value_head.bias)
        pass

    def _init_weights(self, module):
        if isinstance(module, nn.Linear):
            torch.nn.init.kaiming_normal_(module.weight, nonlinearity='relu')
            if module.bias is not None:
                torch.nn.init.zeros_(module.bias)

    def forward(self, s):
        x = self.lin1(s)
        x = F.gelu(x)
        x = self.lin2(x)
        x = F.gelu(x)
        x = self.lin3(x)
        x = F.gelu(x)
        x = self.lin4(x)
        x = F.gelu(x)
        p = self.policy_head(x)
        v = self.value_head(x)
        return p, v

"""MCTS DATA STRUCTURES"""
class Node(object):
    """
    MCTS node 
    """
    def __init__(self, prior):
        """
        prior: initial probability (from the policy network) 
        of selecting the action that leads to this node from parent node
        """
        self.state = None # hidden state representation
        self.value_sum = 0 # NOT Q-value (see mean_value)
        self.N = 0 # number of node visits
        self.P = prior # policy 
        self.R = 0 # immediate reward

        # track the player whose turn it is at this node
        # ex: to_play = 0, player X's turn is at this node, player O has already made a move
        # ex: to_play = 1, player O's turn is at this node, player X has already made a move
        self.to_play = -1

        # child nodes
        self.children = {}
        pass

    def expanded(self):
        """
        check if its a leaf node with no children or not
        """
        return len(self.children.items()) > 0
    
    def mean_value(self):
        """
        return the mean value Q
        """
        if self.N > 0:
            return  self.value_sum / self.N # Q-value
        else:
            return 0

"""MUZERO"""
class MuZeroAgent(object):
    """
    MuZero agent class
    """
    def __init__(self, config, load=False, load_dir=None):
        self.obs_size = torch.Size([9])
        self.action_size = 9
        self.device = torch.device("cuda" if torch.cuda.is_available() else "cpu")

        # neural networks
        self.state_function = StateFunction(self.obs_size[0],
                                            config['state_size'],
                                            config['hidden_size'])
        
        self.dynamics_function = DynamicsFunction(config['state_size']+self.action_size,
                                                  config['state_size'],
                                                  config['hidden_size'])
        
        self.prediction_function = PredictionFunction(config['state_size'],
                                                      self.action_size,
                                                      config['hidden_size'])
        # move to CUDA device, if available
        self.state_function.to(self.device)
        self.dynamics_function.to(self.device)
        self.prediction_function.to(self.device)

        all_function_params = (list(self.state_function.parameters()) +
                               list(self.dynamics_function.parameters()) +
                               list(self.prediction_function.parameters()))

        self.min_Q = float('inf')
        self.max_Q = -float('inf')
        self.max_iters = config['max_iters']
        self.gamma = config['gamma']
        self.k_unroll_steps = config['k_unroll_steps']

        self.root_value = 0
        self.action_probs = torch.zeros(self.action_size)
        self.temperature = config['temperature']
        self.episodes_played = 0 # temperature schedule based on episodes
        self.dirichlet_alpha = config['dirichlet_alpha']
        self.root_exploration_fraction = config['root_exploration_fraction']


        self.state_function.eval()
        self.dynamics_function.eval()
        self.prediction_function.eval()

        if load:
            self.load_model(load_dir)
        pass
    
    """model utilities"""

    def load_model(self, filepath=None):
        """
        load neural network and optimizer parameters

        filepath: directory containing the saved params
        """

        base_dir = os.path.dirname(os.path.abspath(__file__))
        if filepath is not None:
            base_dir = os.path.join(base_dir, filepath)

        paths = {
            'state': os.path.join(base_dir, 'mu_state_rep_params.pth.tar'),
            'dynamics': os.path.join(base_dir, 'mu_dyn_func_params.pth.tar'),
            'prediction': os.path.join(base_dir, 'mu_pred_func_params.pth.tar')
        }

        if os.path.exists(paths['state']):
            self.state_function.load_state_dict(torch.load(paths['state'], map_location=self.device))
        if os.path.exists(paths['dynamics']):
            self.dynamics_function.load_state_dict(torch.load(paths['dynamics'], map_location=self.device))
        if os.path.exists(paths['prediction']):
            self.prediction_function.load_state_dict(torch.load(paths['prediction'], map_location=self.device))
        print("MuZero models loaded.")
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


    """MuZero search functions"""

    def update_min_max_Q(self, node_mean_value):
        """
        keep track of min and max over entire search tree
        """
        if node_mean_value > self.max_Q:
            self.max_Q = node_mean_value
        if node_mean_value < self.min_Q:
            self.min_Q = node_mean_value
        pass

    def expansion(self, last_node, state, reward, policy_logits, actions):
        """
        expansion phase of MuZero search
        add child nodes to a given leaf node based on legal actions
        and initialize them with policy priors based on the prediction network
        """
        # print('expansion()')

        last_node.state = state
        last_node.R = reward

        # Since networks now process batches, squeeze the batch dimension for single inferences
        policy_logits = policy_logits.squeeze(0)

        # mask illegal actions and normalize the policy over legal moves
        # Use .item() to convert tensor logits to float for math.exp
        # Subtract max logit for numerical stability to prevent ZeroDivisionError
        max_logit = max(policy_logits[a].item() for a in actions)
        policy = {a: math.exp(policy_logits[a].item() - max_logit) for a in actions}
        policy_sum = sum(policy.values())
        for a in actions:
            child = Node(policy[a]/policy_sum)
            child.to_play = 1 - last_node.to_play
            last_node.children[a] = child
        pass

    def pUCT(self, node, sum_visits):
        """
        upper confidence bound computed for a given candidate action node
        refer to Equation 2, Appendix B

        sum_visits: total number of visits to the parent node
        (same as sum of visits across all parent's child nodes)
        """
        # print('pUCT()')
        
        c1 = 1.25
        c2 = 19652
        N = node.N
        if N > 0:
            # child values are stored from player's perspective
            # the parent is the opposing player, so negate value
            # before using to select parent action
            # normalize the full backed-up action value R + gamma*V,
            # not just the raw mean value (Eq. 5 / Appendix B)
            Q = node.R + self.gamma * (-node.mean_value())
            if self.max_Q > self.min_Q:
                Q = (Q - self.min_Q) / (self.max_Q - self.min_Q)
        else:
            Q = 0
        P = node.P
        N_sum = sum_visits
        return (Q + (P*math.sqrt(N_sum)/(1+N))*(c1+math.log((N_sum+c2+1)/c2)))

    def select_child(self, node):
        """
        select the next child node during simulation/search

        (NOT for selecting the next action in the game)
        """
        # print('select_child()')
        
        # parent node visits same as sum of visits across all parent's child nodes
        sum_visits = node.N

        best_uct = -float('inf')
        best_child = None
        best_action = None
        for a, child_node in node.children.items():
            uct = self.pUCT(child_node, sum_visits)
            if uct > best_uct:
                best_uct = uct
                best_action = a
                best_child = child_node
        return best_child, best_action

    def selection(self, node):
        """
        selection phase of MuZero search

        return:
        - unexpanded leaf node
        - latest search path and action history
        """
        # print('selection()')

        search_path = [node]
        action_history = []

        while node.expanded():
            node, action = self.select_child(node)
            search_path.append(node)
            action_history.append(action)
        return node, search_path, action_history

    def backup(self, value, search_path):
        """
        backup phase of MuZero search
        update mean value based on simulated game outcomes 
        and node visit counts during simulation
        """
        # print('backup()')

        to_play = search_path[-1].to_play
        G = value
        for i in range(len(search_path) - 1, -1, -1):
            current_node = search_path[i]
            current_node.value_sum += G if current_node.to_play == to_play else -G
            current_node.N += 1
            # track the range of the same backed-up quantity used in pUCT:
            # R + gamma*V, not the raw mean value
            self.update_min_max_Q(current_node.R + self.gamma * (-current_node.mean_value()))
            if i > 0:
                parent = search_path[i - 1]
                R = current_node.R
                G = (R if parent.to_play == to_play else -R) + self.gamma * G
        pass

    def select_action(self, node, temperature):
        """
        select the next action to take in the game
        given tree search root node and softmax sampling temperature
        """
        # print('select_action()')

        # sample action based on visit counts and temperature
        sum_visits = node.N
        self.action_probs = torch.zeros(self.action_size)
        
        # account for visit counts for each action
        visits = []
        actions = []
        for a, child_node in node.children.items():
            visits.append(child_node.N)
            actions.append(a)
            self.action_probs[a] = child_node.N / sum_visits

        if temperature == 0:
            # greedy selection (argmax)
            max_visits = -1
            best_action = None
            for a, v in zip(actions, visits):
                if v > max_visits:
                    max_visits = v
                    best_action = a
            return best_action
        else:
            # softmax sampling with temperature
            # P(a) = (N(a)^(1/T)) / sum(N(b)^(1/T))
            visits_tensor = torch.tensor(visits, dtype=torch.float32)
            scaled_visits = visits_tensor.pow(1.0 / temperature)
            probs = scaled_visits / scaled_visits.sum()
            
            # sample from multinomial distribution
            action_idx = torch.multinomial(probs, 1).item()
            return actions[action_idx]
        
    def add_exploration_noise(self, node):
        """
        add Dirichlet noise to root node's child node policy priors
        to encourage exploration of different actions during MuZero search/simulation
        """
        actions = list(node.children.keys())
        if not actions:
            return
        noise = torch.distributions.Dirichlet(torch.full((len(actions),), self.dirichlet_alpha)).sample()
        for a, n in zip(actions, noise):
            node.children[a].P = node.children[a].P * (1 - self.root_exploration_fraction) + n * self.root_exploration_fraction
            
    def search(self, obs, temperature, add_noise=True):
        """
        overall MuZero search algorithm
        
        given:
        - obs: tensor representation of current game environment observation state
        - temperature: softmax sampling temperature

        return: next action to play in the game
        """
        print('\n\nsearch()')

        # ensure inference mode
        with torch.no_grad():
            # value normalization statistics are local to one search tree
            self.min_Q = float('inf')
            self.max_Q = -float('inf')

            # initialize tree root node
            # to_play is only meaningful relative to other nodes in this search tree,
            # so 0 is an arbitrary but consistent reference point for this call
            root_node = Node(0)
            root_node.to_play = 0

            # encode observation into a hidden state represnetation
            initial_state = self.state_function(obs.to(self.device).unsqueeze(0))

            # predict initial policy logits and value
            policy_logits, value = self.prediction_function(initial_state)

            # get list of current available legal actions
            root_actions = torch.where(obs == 0)[0].tolist()

            # expand root node
            self.expansion(root_node, initial_state, 0, policy_logits, root_actions)
            
            # add exploration noise to root node's children
            if add_noise:
                self.add_exploration_noise(root_node)

            for i in range(self.max_iters):
                print(f"\niter={i}")
                # select leaf node
                last_node, search_path, action_history = self.selection(root_node)

                # get leaf node's parent
                parent_node = search_path[-2]

                # get latest candidate action as a tensor
                latest_action = F.one_hot(
                    torch.tensor([action_history[-1]], device=self.device),
                    num_classes=self.action_size,
                ).float()  # shape (1, action_size)

                # dynamics function predicts next state
                # reward output is unused and the reward head
                # is never trained
                state, _ = self.dynamics_function(parent_node.state, latest_action)

                # prediciton function estimates policy logits and value based on next state
                policy_logits, value = self.prediction_function(state)

                # expand leaf node with child nodes for each legal action
                # board games have no intermediate rewards
                self.expansion(last_node, state, 0.0, policy_logits, list(range(self.action_size)))
                
                # update node mean values back up to the root node
                self.backup(value.item(), search_path)
            
            # store the mean value of the root node
            self.root_value = root_node.mean_value()

        # return the next action based on node visits and softmax sampling temperature
        return self.select_action(root_node, temperature)
    
    """RL agent standard functions"""

    def current_temperature(self):
        """
        get current softmax sampling temperature
        based on constant or variable temperature annealing schedule
        """
        if not self.temp_schedule:
            return self.temperature
        for threshold, temp in self.temp_schedule:
            if self.episodes_played < threshold:
                return temp
        return self.temp_schedule[-1][1]
    
    def step(self, observation):
        """
        select next action to play in the game
        with softmax temperature sampling
        """
        # print('step()')

        obs = self.preprocess_obs(observation)
        
        # simple temperature annealing for tic-tac-toe:
        # if both players have placed two pieces (5 or fewer blank spaces), 
        # there is likely a single move to exploit
        # that is best to block of connect 3 in a row
        # blanks = torch.where(obs == 0)[0].tolist()
        # if len(blanks) > 5:
        #     action = self.search(obs, self.current_temperature())
        # else:
        #     action = self.search(obs, 0.0)
        
        action = self.search(obs, self.current_temperature())

        return action
    
    def act(self, observation):
        """
        select next action to play in the game
        with neural nets doing inference 
        """
        # print('act()')

        # neural nets should be in evaluation mode
        self.state_function.eval()
        self.dynamics_function.eval()
        self.prediction_function.eval()
        
        obs = self.preprocess_obs(observation)
        action = self.search(obs, 0.0, add_noise=False)
        return action