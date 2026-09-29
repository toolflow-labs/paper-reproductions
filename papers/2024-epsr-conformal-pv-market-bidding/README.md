# Renkema et al. (2024) — Conformal Prediction → Market Decision 复现

论文：

> Yvet Renkema, Nico Brinkel, Tarek AlSkaif.  
> **Conformal prediction for stochastic decision-making of PV power in electricity markets**.  
> *Electric Power Systems Research*, 234 (2024) 110750.  
> DOI: `10.1016/j.epsr.2024.110750`

## 定位

这篇论文的价值不在于“再做一次 PV 预测”，而在于它很干净地展示了：

```text
point forecast
      ↓
Conformal Prediction / CPS
      ↓
prediction interval / predictive CDF
      ↓
quantity bid
      ↓
DAM revenue + RTM imbalance
      ↓
profit / imbalance / risk trade-off
```

本目录做的是 **method-level clean-room reproduction**，重点理解“Conformal 输出怎样真正进入决策”。

## 对应论文 M1–M5

论文定义的五种 CP/CPS 方案均有实现：

| 方法 | 本实现 |
|---|---|
| M1 | Basic CP |
| M2 | CP + KNN uncertainty scalar |
| M3 | CP + KNN scalar + Mondrian binning |
| M4 | CPS + KNN scalar |
| M5 | CPS + KNN scalar + Mondrian binning |

其中：

- KNN uncertainty scalar：按 calibration feature 的近邻平均绝对残差估计局部难度；
- Mondrian：按 calibration point prediction 做等频分箱；
- CPS：使用 signed residual 而不是 absolute residual，形成不要求关于 point forecast 对称的经验 predictive distribution。

## 对应论文 bidding strategies

实现了：

- **Trust-the-forecast**
  - point model：直接使用 point forecast；
  - CP/CPS：使用 predictive median；
- **Worst-case**
  - 使用 q0.05 / 90% interval lower bound；
- **Newsvendor**
  - 使用 imbalance price delta：
    `tau = Delta_down / (Delta_down + Delta_up)`；
  - calibration RTM price delta 先聚成 price scenarios，再按 cluster weight 求目标 quantile；
- **Expected Utility Maximization (EUM)**
  - 从 conformal predictive distribution 生成 PV scenarios；
  - 与 historical RTM price clusters 组合；
  - 对 quantity bid 做一维 expected-profit search；
- **EUM + CVaR**
  - 在 expected profit 外加入 lower-tail profit CVaR；
  - 默认采用论文讨论中的 `gamma=0.6`、`beta=0.1`；
- **Perfect information**
  - bid = actual PV，作为利润上界参考。

## 与论文一致的关键设定

- point model 使用 Random Forest Regression；
- KNN 默认 `k=50`；
- Mondrian 默认 15 bins；
- RTM price scenarios 默认 20 clusters；
- CPS/EUM 默认构造 99 PV scenarios；
- PV 标幺化到 `[0,1]`；
- 评价 profit 与 energy imbalance。

默认 demo 使用 synthetic Dutch-style PV/weather/market data，因此不会复现论文的绝对欧元收益，但可以把 M1–M5 → bidding → profit/imbalance 的逻辑完整跑通。

## 运行

```bash
cd papers/2024-epsr-conformal-pv-market-bidding
pip install -r requirements.txt

python reproduction.py --smoke
python reproduction.py --out results/demo
```

输出：

```text
results/demo/
├── summary.json
├── uncertainty_metrics.csv
└── bidding_metrics.csv
```

## 对当前论文主线的价值

这篇和我们的场景不同：它是市场 bidding，而不是低压配电网 BESS 控制。

但它解决的抽象问题几乎完全一样：

> **统计不确定性不能停在 interval；必须定义一个明确的 decision mapping。**

因此后续可以把：

```text
CP/CPS distribution
→ Newsvendor / EUM / CVaR bid
```

替换成：

```text
horizon-wise ACI marginal
→ temporally coherent scenarios
→ CVaR rolling BESS dispatch
```

Renkema 的价值就是让“预测区间如何进入决策”这件事从概念变成一个非常清楚的可执行接口。
