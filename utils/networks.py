import torch.nn as nn
import torch.nn.functional as F
import utils.vae as vae
from torch import nn, optim
import numpy as np
import torch

class MLPNetwork(nn.Module):
    """
    MLP network (can be used as value or policy)
    """
    def __init__(self, input_dim, out_dim, hidden_dim=64, nonlin=F.relu,
                 constrain_out=False, norm_in=True, discrete_action=True,
                 is_actor=False, comm_acs_space=None):
        """
        Inputs:
            input_dim (int): Number of dimensions in input
            out_dim (int): Number of dimensions in output
            hidden_dim (int): Number of hidden dimensions
            nonlin (PyTorch function): Nonlinearity to apply to hidden layers
            is_actor (True/False): Needed to initialize VAE if MLP is for actor policy
        """
        super(MLPNetwork, self).__init__()

        self.is_actor = is_actor
        self.comm_acs_space = comm_acs_space

        if is_actor:
            out_dim = out_dim - comm_acs_space

        if norm_in:  # normalize inputs
            self.in_fn = nn.BatchNorm1d(input_dim)
            self.in_fn.weight.data.fill_(1)
            self.in_fn.bias.data.fill_(0)
        else:
            self.in_fn = lambda x: x
        self.fc1 = nn.Linear(input_dim, hidden_dim)
        self.fc2 = nn.Linear(hidden_dim, hidden_dim)
        self.fc3 = nn.Linear(hidden_dim, out_dim)
        self.nonlin = nonlin
        if constrain_out and not discrete_action:
            # initialize small to prevent saturation
            self.fc3.weight.data.uniform_(-3e-3, 3e-3)
            self.out_fn = F.tanh
        else:  # logits for discrete action (will softmax later)
            self.out_fn = lambda x: x

        if is_actor:
            self.vae_model = vae.VAE(input_dim, hidden_dim, comm_acs_space)
            self.optimizer = optim.Adam(self.vae_model.parameters(), lr=1e-4)
            self.layernorm = vae.LayerNorm
            self.vae_loss = vae.loss_function

    def forward(self, X):
        """
        Inputs:
            X (PyTorch Matrix): Batch of observations
        Outputs:
            out (PyTorch Matrix): Output of network (actions, values, etc)
        """
        h1 = self.nonlin(self.fc1(self.in_fn(X)))
        h2 = self.nonlin(self.fc2(h1))
        out = self.out_fn(self.fc3(h2))

        # comm
        self.vae_model.train()
        train_loss = 0
        self.optimizer.zero_grad()
        recon, mu, logvar = self.vae_model(X)
        loss = self.vae_loss(recon, X, mu, logvar)
        loss.backward()
        train_loss += loss.item()
        self.optimizer.step()
        z = self.vae_model.z

        return torch.cat((out, z), 1)
