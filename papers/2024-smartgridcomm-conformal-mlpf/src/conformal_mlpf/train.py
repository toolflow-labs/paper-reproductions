from __future__ import annotations

import copy
import random
from dataclasses import dataclass

import numpy as np
import torch
from torch import nn
from torch.utils.data import DataLoader

from .data import WindowArrays, WindowDataset
from .models import mixed_l1_l2_loss, pinball_loss


def seed_everything(seed: int) -> None:
    random.seed(seed)
    np.random.seed(seed)
    torch.manual_seed(seed)
    if torch.cuda.is_available():
        torch.cuda.manual_seed_all(seed)


def resolve_device(name: str) -> torch.device:
    if name == "auto":
        return torch.device("cuda" if torch.cuda.is_available() else "cpu")
    return torch.device(name)


@dataclass
class FitConfig:
    epochs: int
    batch_size: int
    learning_rate: float
    weight_decay: float
    l1_l2_lambda: float
    num_workers: int = 0


def _make_loader(arrays: WindowArrays, batch_size: int, shuffle: bool, num_workers: int) -> DataLoader:
    return DataLoader(WindowDataset(arrays), batch_size=batch_size, shuffle=shuffle, num_workers=num_workers)


def fit_point_model(model: nn.Module, train: WindowArrays, cfg: FitConfig, device: torch.device) -> nn.Module:
    model = model.to(device)
    loader = _make_loader(train, cfg.batch_size, True, cfg.num_workers)
    opt = torch.optim.Adam(model.parameters(), lr=cfg.learning_rate, weight_decay=cfg.weight_decay)
    milestones = sorted({max(1, int(cfg.epochs * 0.75)), max(1, int(cfg.epochs * 0.90))})
    sched = torch.optim.lr_scheduler.MultiStepLR(opt, milestones=milestones, gamma=0.1)

    model.train()
    for _ in range(cfg.epochs):
        for past, future, target in loader:
            past, future, target = past.to(device), future.to(device), target.to(device)
            opt.zero_grad(set_to_none=True)
            pred = model(past, future)
            loss = mixed_l1_l2_loss(pred, target, cfg.l1_l2_lambda)
            loss.backward()
            opt.step()
        sched.step()
    return model


def fit_quantile_model(
    model: nn.Module,
    train: WindowArrays,
    cfg: FitConfig,
    device: torch.device,
    quantiles: list[float],
) -> nn.Module:
    model = model.to(device)
    loader = _make_loader(train, cfg.batch_size, True, cfg.num_workers)
    opt = torch.optim.Adam(model.parameters(), lr=cfg.learning_rate, weight_decay=cfg.weight_decay)
    milestones = sorted({max(1, int(cfg.epochs * 0.75)), max(1, int(cfg.epochs * 0.90))})
    sched = torch.optim.lr_scheduler.MultiStepLR(opt, milestones=milestones, gamma=0.1)

    model.train()
    for _ in range(cfg.epochs):
        for past, future, target in loader:
            past, future, target = past.to(device), future.to(device), target.to(device)
            opt.zero_grad(set_to_none=True)
            pred = model(past, future)
            loss = pinball_loss(pred, target, quantiles)
            loss.backward()
            opt.step()
        sched.step()
    return model


@torch.no_grad()
def predict_point(model: nn.Module, arrays: WindowArrays, batch_size: int, device: torch.device) -> np.ndarray:
    model.eval()
    loader = _make_loader(arrays, batch_size, False, 0)
    out = []
    for past, future, _ in loader:
        out.append(model(past.to(device), future.to(device)).cpu().numpy())
    return np.concatenate(out, axis=0)


@torch.no_grad()
def predict_quantiles(model: nn.Module, arrays: WindowArrays, batch_size: int, device: torch.device) -> np.ndarray:
    model.eval()
    loader = _make_loader(arrays, batch_size, False, 0)
    out = []
    for past, future, _ in loader:
        out.append(model(past.to(device), future.to(device)).cpu().numpy())
    return np.concatenate(out, axis=0)


@torch.no_grad()
def predict_mc_dropout(
    model: nn.Module,
    arrays: WindowArrays,
    batch_size: int,
    device: torch.device,
    n_samples: int,
    alpha: float,
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    # Keep dropout active while leaving BatchNorm statistics frozen.
    model.eval()
    for module in model.modules():
        if isinstance(module, nn.Dropout):
            module.train()

    draws = []
    loader = _make_loader(arrays, batch_size, False, 0)
    for _ in range(n_samples):
        batch_draws = []
        for past, future, _ in loader:
            batch_draws.append(model(past.to(device), future.to(device)).cpu().numpy())
        draws.append(np.concatenate(batch_draws, axis=0))
    draws = np.asarray(draws)
    point = draws.mean(axis=0)
    lower = np.quantile(draws, alpha / 2.0, axis=0)
    upper = np.quantile(draws, 1.0 - alpha / 2.0, axis=0)
    return point, lower, upper
