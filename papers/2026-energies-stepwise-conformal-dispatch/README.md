# Jiang et al. (2026) — Stepwise Conformal + Rolling Dispatch 复现

论文：

> Yibo Jiang, Chanxia Zhu, Fenghua Zou, Lei Zhang, Xiaomao Yu, Chaoyi Pan, Siyang Liao.  
> **Stepwise Conformal Prediction for Multi-Step Net Load Forecasting in Microgrids Under Renewable Energy Variability**.  
> *Energies*, 19, 2297 (2026). DOI: `10.3390/en19102297`.

## 定位

这是一个 **clean-room / method-level reproduction**，重点不是复现论文表格中的原始数值，而是把论文最值得后续研究复用的闭环真正跑起来：

```text
多步净负荷分位数预测
        ↓
逐 horizon 的 CQR / Stepwise Conformal 校准
        ↓
PV ramping 低/中/高波动日分类
        ↓
Ideal / Point / Interval 三种 rolling BESS dispatch
        ↓
PICP、PINAW、运行成本、峰值购电、SOC/可行性
```

这篇论文对当前仓库最重要的价值，是把已有的“多步概率预测”和“储能调度”之间补上一个非常明确的接口：**每个预测步长单独校准，然后把校准后的上界直接作为保守净负荷输入。**

## 与论文一致的部分

实现保留了论文明确给出的关键结构：

- 15 min 时间分辨率；
- 历史窗口 `L=96`（24 h）；
- 1 h / 4 h 对应 4 / 16 个预测步；
- 90% 预测区间（0.05 / 0.50 / 0.95 分位数）；
- 对每个 horizon 独立计算 nonconformity score 和校准量；
- `score = max(lower-y, y-upper, 0)`；
- 校准区间 `lower-q_hat_h, upper+q_hat_h`；
- PV ramping 使用相邻时刻 PV 绝对变化并按日聚合，阈值只由训练阶段确定；
- 三类调度输入：真实未来值、预测中位数、校准区间上界；
- 评价 PICP / PINAW / 峰值购电 / SOC violation / infeasible case。

## 复现假设

论文的真实东部中国微电网数据不公开，并且没有完整披露多分位数网络结构和调度优化目标。因此这里明确采用两类替代：

1. **预测模型替代**：使用 `HistGradientBoostingRegressor(loss="quantile")` 作为黑盒多 horizon 分位数模型。Stepwise CQR 本身是 model-agnostic 的，所以这不会改变要复现的核心校准机制。
2. **调度模型替代**：使用一个小型线性规划，目标为购电成本 + 峰值惩罚 + 很小的循环惩罚；储能满足功率、能量和效率约束。论文只明确了“upper bound 作为保守调度输入”，没有公开完整目标函数，因此这里不声称数值级复现 Table 6。

默认数据由代码生成一个确定性的高光伏 15-min 微电网序列，使 CI 和学习环境无需私有数据也能端到端运行。

## 运行

```bash
cd papers/2026-energies-stepwise-conformal-dispatch
pip install -r requirements.txt
python reproduction.py --smoke
```

完整默认实验：

```bash
python reproduction.py --out results/demo
```

输出：

```text
results/demo/
├── summary.json
└── horizon_metrics.csv
```

`horizon_metrics.csv` 很适合直接检查论文最关键的现象：不同 forecast horizon 的 raw coverage、校准后 coverage、区间宽度和 `q_hat_h` 是否存在明显差异。

## 和后续课题的衔接

当前实现故意保留为固定校准：

```text
validation/calibration set
      ↓
固定 q_hat[h]
      ↓
整个 test 期间不再更新
```

因此后续可以非常直接地把 `stepwise_cqr()` 替换成每个 horizon 独立更新的 ACI：

```text
q_hat[h] / alpha[h]
        ↓ 每个新观测到来后更新
horizon-wise Adaptive Conformal
        ↓
rolling BESS dispatch
```

这正好形成 Jiang et al. (2026) 的固定 stepwise calibration 与后续 horizon-wise adaptive calibration 的干净 baseline 对照。
