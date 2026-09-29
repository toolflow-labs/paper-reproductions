# Guo et al. (2026) — PV Forecast → Dispatch → Decision Value 实验骨架

论文：

> Shirong Guo, Xi Cui, Jingxuan Zhang, Rui Tang.  
> **Techno-economic assessment of the realisable economic value and value capture gap of probabilistic PV forecasting in PV-battery microgrid dispatch**.  
> *Sustainable Energy Technologies and Assessments*, 93 (2026) 105319.  
> DOI: `10.1016/j.seta.2026.105319`

作者同时公开了分析代码仓库：`shannongsr/PVForecast-Dispatch-Value`。本目录不是复制作者代码，而是围绕我们后续论文最需要的 **Decision Value 评价逻辑** 做一个独立、轻量、容易改造的 clean-room 骨架。

## 这篇最值得复现的不是预测器

它真正有价值的是把“预测变准”拆成：

```text
forecast
   ↓
advance battery commitment
   ↓
realized PV arrives
   ↓
grid recourse / export / curtailment / ENS
   ↓
realized operating cost
   ↓
persistence baseline
perfect-forecast upper bound
value capture ratio / value capture gap
```

所以本实现刻意把预测层做轻，把重点放在 **forecast → decision → ex-post value**。

## 已实现

`reproduction.py` 实现了：

- 15 min PV-battery microgrid runnable surrogate；
- 60 min-ahead persistence / point / q0.1–q0.9 / perfect commitments；
- 论文 Table 1 的中央场景参数：
  - BESS 200 kWh；
  - charge/discharge 150 kW；
  - efficiency 0.95；
  - SOC 10%–90%，首日 50%；
  - grid import 500 kW；
  - export 200 kW；
  - import 0.30 AUD/kWh；
  - export 0.08 AUD/kWh；
  - curtailment 0.02 AUD/kWh；
  - degradation 0.05 AUD/kWh；
  - VOLL 5 AUD/kWh；
- 日内 96 步 commitment LP；
- realized PV 到来后固定 battery commitment，仅重新计算 grid import/export、curtailment 和 ENS；
- 跨日 SOC carry-over；
- cost decomposition；
- persistence / point / probabilistic / perfect 的统一价值比较；
- `EV_vs_persistence`；
- `EV_vs_point`；
- perfect forecast value upper bound；
- **value capture ratio**；
- **value capture gap**；
- q0.1–q0.9 quantile scan；
- 0/50/150/500 kW import recourse × 1/5/20 AUD/kWh VOLL fixed-commitment boundary scan；
- islanded case 下重新优化 commitment；
- worst-5% daily cost `CVaR95`。

## 核心公式接口

论文的 Decision Value 逻辑在代码中集中为：

```python
value_metrics(costs)
```

其中：

```text
perfect value upper bound = C_persistence - C_perfect

economic value of method m
    = C_persistence - C_m

value capture ratio
    = (C_persistence - C_m)
      / (C_persistence - C_perfect)

value capture gap
    = C_m - C_perfect
```

这部分后面可以原封不动接你自己的预测/调度实验。

## 运行

```bash
cd papers/2026-seta-pv-forecast-dispatch-value
pip install -r requirements.txt

python reproduction.py --smoke
python reproduction.py --out results/demo
```

输出：

```text
results/demo/
├── summary.json
├── central_dispatch.csv
├── decision_value.csv
├── quantile_scan.csv
├── fixed_commitment_boundary.csv
└── islanded_reoptimized.csv
```

## 对当前课题最直接的复用方式

后面不需要保留这里的 synthetic PV forecast。真正应该迁移的是：

```text
你的 point / fixed CP / adaptive CP / scenario-CVaR dispatch
                  ↓
             battery action
                  ↓
       realized chronological replay
                  ↓
 persistence / perfect-information anchors
                  ↓
 cost + ENS + physical violation
                  ↓
 decision value / value capture ratio
```

也就是说，Guo 这篇更适合作为 **评价骨架**，而不是方法 baseline。
