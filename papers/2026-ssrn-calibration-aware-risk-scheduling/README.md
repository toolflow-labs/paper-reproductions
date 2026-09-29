# Xiao et al. (2026) — Calibration-Aware Risk Scheduling 复现

论文 / preprint：

> Yanqiu Xiao, Xiao Xiao, Mingyu Cheng, Wenbing Sun, Qianru Yang, Fan Wang, Wenfeng Hu, Shiquan Zhu, Tian Qi, Lei Yao, Wei Wei, Zihan Xue, Fuqun Ji, Chuanxiao Cheng.  
> **Calibration-Aware Risk Scheduling for PV–BESS–EV Charging Stations Using Monotonic Quantile Forecasting and Dependence-Preserving Scenarios**.  
> SSRN preprint, 2026, abstract `7267410`.

## 定位

这是一个 **clean-room / method-level reproduction**。它重点复现这篇文章真正有价值的“接口链”，而不是只复现某个预测模型：

```text
24 h 历史特征
    ↓
encoder-decoder Transformer
    ↓ cumulative-softplus
7 个非交叉 quantiles × EV/PV × 24 horizons
    ↓
interval scaling + CQR
    ↓
AR(1) 时间相关 + Gaussian Copula EV/PV 相关
    ↓
100 条连续 net-load scenarios
    ↓
scenario mean / upper-tail CVaR
    ↓
risk-adjusted net load
    ↓
100 kWh / 50 kW BESS scheduling
```

这正是“校准后的风险信息如何进入储能决策”的一个近邻实现。

## 已实现的核心组件

`reproduction.py` 中包含：

- 10 维输入特征（EV、PV、温度、云量、hour/dow 周期特征、24 h lag）；
- `L=24`、`H=24`；
- 7 个 quantile：`0.05, 0.10, 0.25, 0.50, 0.75, 0.90, 0.95`；
- encoder-decoder Transformer；
- cumulative-softplus monotonic quantile head；
- pinball loss、gradient clipping、ReduceLROnPlateau；
- 60% / 10% / 15% / 15% chronological Train / Validation / Calibration / Test；
- interval scaling；
- CQR posterior calibration；
- EV、PV 与 net load 的单独 calibration 层；
- AR(1) horizon dependence；
- Gaussian Copula contemporaneous EV–PV dependence；
- `S=100` net-load scenarios；
- upper-tail CVaR；
- `risk = mean + lambda * max(CVaR - mean, 0)`；
- 100 kWh BESS、50 kW charge/discharge、0.95 efficiency、10–100% SOC；
- deterministic / scenario mean / risk-aware / scenario-embedded stochastic proxy 四种调度输入。

## 为什么没有直接下载论文的全部原始数据

论文案例由三类公开来源拼接而成：Caltech ACN charging sessions、NASA POWER → pvlib 的 PV 模拟、CAISO NP15 day-ahead price。作者没有公开完整的、与论文预处理完全一致的统一训练文件；其中 gap cleaning、异常处理、插值、PV 仿真参数和时间对齐都会影响最终数值。

因此本目录默认使用一个确定性的 Caltech-like synthetic station surrogate，使以下**方法链可以稳定执行和测试**，同时不声称复现论文 Figure 4–9 的具体数字。

如果后面要做数值级复现，建议保持本目录的 forecasting/calibration/scenario/scheduling 代码不变，只把 `make_station_data()` 替换成 ACN + NASA POWER + CAISO 的正式数据管线。

## 一个需要特别注明的实现假设：interval scaling

preprint 多次说明使用了 `interval scaling followed by CQR`，但正文没有给出 interval-scaling 的明确公式或缩放因子求解方式。

这里采用一个透明的 clean-room 解释：对每个 horizon × target，在 calibration set 上围绕 median 对全部 quantile deviation 乘同一个最小系数，使 5%–95% 区间先达到目标 coverage；然后再执行标准 CQR 外扩。

这个假设在代码中集中在：

```python
fit_interval_scale()
apply_scale()
fit_cqr_delta()
apply_cqr_to_grid()
```

因此如果作者后续公开更具体的 scaling 公式，可以非常容易替换，而不会影响 scenario/CVaR/dispatch 部分。

## 运行

```bash
cd papers/2026-ssrn-calibration-aware-risk-scheduling
pip install -r requirements.txt
python reproduction.py --smoke
```

默认实验：

```bash
python reproduction.py --out results/demo
```

输出：

```text
results/demo/
├── summary.json
└── dispatch_metrics.csv
```

## 后续最值得复用的部分

对当前课题来说，不一定要把这个 Transformer 原样搬过去。更值得直接借的是：

```text
校准后的 horizon-wise marginal uncertainty
        ↓
保留 temporal dependence 的 trajectory scenarios
        ↓
CVaR / tail statistic
        ↓
固定维度 risk-adjusted trajectory
        ↓
rolling BESS optimizer
```

也就是说，后面完全可以把这里的原始 CQR 换成 horizon-wise ACI，同时保留 `generate_scenarios()`、`upper_cvar()` 和储能调度接口，形成自己的主实验链。
