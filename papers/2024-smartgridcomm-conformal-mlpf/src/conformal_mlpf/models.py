from __future__ import annotations

import torch
from torch import nn


def _activation(name: str) -> nn.Module:
    name = name.lower()
    if name == "silu":
        return nn.SiLU()
    if name == "relu":
        return nn.ReLU()
    if name == "gelu":
        return nn.GELU()
    raise ValueError(f"Unsupported activation: {name}")


class MLPEncoder(nn.Module):
    def __init__(self, input_dim: int, hidden_dim: int, hidden_layers: int, activation: str, dropout: float):
        super().__init__()
        layers: list[nn.Module] = [nn.LayerNorm(input_dim)]
        in_dim = input_dim
        for _ in range(hidden_layers):
            layers.extend([
                nn.Linear(in_dim, hidden_dim),
                nn.BatchNorm1d(hidden_dim),
                _activation(activation),
                nn.Dropout(dropout),
            ])
            in_dim = hidden_dim
        self.net = nn.Sequential(*layers)

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        return self.net(x)


class DualEncoderBackbone(nn.Module):
    """Clean-room approximation of the paper's past/future MLP encoder design."""

    def __init__(
        self,
        lookback: int,
        horizon: int,
        past_dim: int,
        future_dim: int,
        hidden_dim: int = 256,
        hidden_layers: int = 2,
        activation: str = "silu",
        dropout: float = 0.0,
    ):
        super().__init__()
        self.horizon = horizon
        self.past_encoder = MLPEncoder(lookback * past_dim, hidden_dim, hidden_layers, activation, dropout)
        self.future_encoder = MLPEncoder(horizon * future_dim, hidden_dim, hidden_layers, activation, dropout)
        self.fusion = nn.Sequential(nn.LayerNorm(hidden_dim), _activation(activation))

    def encode(self, past: torch.Tensor, future: torch.Tensor) -> torch.Tensor:
        p = past.flatten(start_dim=1)
        f = future.flatten(start_dim=1)
        return self.fusion(self.past_encoder(p) + self.future_encoder(f))


class PointForecaster(DualEncoderBackbone):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        hidden_dim = kwargs.get("hidden_dim", 256)
        self.head = nn.Linear(hidden_dim, self.horizon)

    def forward(self, past: torch.Tensor, future: torch.Tensor) -> torch.Tensor:
        return self.head(self.encode(past, future))


class QuantileForecaster(DualEncoderBackbone):
    def __init__(self, *args, quantiles: list[float], **kwargs):
        super().__init__(*args, **kwargs)
        self.quantiles = list(quantiles)
        hidden_dim = kwargs.get("hidden_dim", 256)
        self.head = nn.Linear(hidden_dim, self.horizon * len(self.quantiles))

    def forward(self, past: torch.Tensor, future: torch.Tensor) -> torch.Tensor:
        out = self.head(self.encode(past, future))
        return out.view(out.shape[0], self.horizon, len(self.quantiles))


def mixed_l1_l2_loss(pred: torch.Tensor, target: torch.Tensor, l2_weight: float) -> torch.Tensor:
    err = target - pred
    return (l2_weight * err.square() + (1.0 - l2_weight) * err.abs()).mean()


def pinball_loss(pred: torch.Tensor, target: torch.Tensor, quantiles: list[float]) -> torch.Tensor:
    q = torch.tensor(quantiles, dtype=pred.dtype, device=pred.device).view(1, 1, -1)
    err = target.unsqueeze(-1) - pred
    return torch.maximum(q * err, (q - 1.0) * err).mean()
