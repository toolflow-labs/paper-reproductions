# 微电网储能滚动调度：CVaR 与 Worst-case CVaR

Raheleh Khodabakhsh and Shahin Sirouspour, **Optimal Control of Energy Storage in a Microgrid by Minimizing Conditional Value-at-Risk**, *IEEE Transactions on Sustainable Energy*, 7(3), 1264–1273, July 2016. [DOI: 10.1109/TSTE.2016.2543024](https://doi.org/10.1109/TSTE.2016.2543024)。卷期页信息亦见[作者所在机构的论文记录](https://experts.mcmaster.ca/scholarly-works/148210)。

本目录实现论文的储能线性模型、场景 CVaR、价格预算鲁棒项和滚动时域执行流程。随附实验使用可重复生成的合成净负荷，属于**方法级复现**。原始 Burlington Hydro 时序数据与部分实验参数未随论文提供，因此这里的输出不能用于声称复现了原文的 20%–25% 成本改善或运行时间。

## 已实现内容

| 控制器名称 | 优化输入与目标 | 对应关系 |
|---|---|---|
| `nominal` | 单条名义需求、名义电价轨迹，最小化运行成本 | 论文的 non-robust MPC 对照 |
| `cvar` | 相关需求/买价场景，最小化完整运行成本的 CVaR | 论文式 (7)、(15)–(25) |
| `wcvar` | 需求场景，加买卖价格的联合预算不确定集，最小化逐场景最坏成本的 CVaR | 论文式 (29)–(37) |
| `mean` | 与 `cvar` 相同的场景，最小化场景平均成本 | 可选扩展；用来区分“考虑不确定性”与“额外重视尾部”的作用 |
| `no_storage` | 在同一实际需求/电价路径上计算无储能账单 | 评价参考，不求解调度模型 |

`cvar` 和 `wcvar` 均为纯 CVaR 目标，没有混入期望成本权重。每次优化中的充电、放电和 SOC 轨迹由所有场景共享；场景专属变量用于购售电与电网形状成本。未来各步动作会在下一次更新时重新优化。

预测时域保留论文的 14 个非均匀时段：

```python
hours = [0.5, 0.5, 0.5, 0.5, 1, 1, 2, 2, 2, 2, 3, 3, 3, 3]
```

合计 24 小时。输入采用半小时分辨率，每次将未来 48 行聚合为 14 个区间平均功率/价格，求解后只执行第一段的 **0.5 小时**，更新 SOC 与上一时刻功率，再滚动一次。

## 运行

需要 Python 3.10 或更新版本。以下命令在本目录执行：

```bash
python -m pip install -r requirements.txt
python -m pytest tests -q
python reproduction.py --smoke --include-mean --out results/smoke
```

Smoke 每条实际路径执行 4 个半小时，使用 2 次独立重复、16 个 CVaR/mean 场景、8 个 WCVAR 场景；它保留完整 24 小时优化时域，仅缩短实际执行期。该模式用于验证整条计算流程，不能据其样本尾部比较控制器优劣。

默认的一天实验运行 48 次更新、3 条独立实际路径、60 个 CVaR 场景和 50 个 WCVAR 场景：

```bash
python reproduction.py --out results/day
```

增加同场景的风险中性对照，并在固定预测不确定性下改变实际误差强度：

```bash
python reproduction.py --include-mean --replications 20 \
  --actual-scales 0,0.5,1,1.5,2,2.5 --out results/uncertainty-sweep
```

下面的配置将执行期、Monte Carlo 重复次数及两种风险控制器的场景数量设为接近论文表 I 和月度实验的规模：

```bash
python reproduction.py --days 30 --replications 1000 \
  --scenarios 300 --wcvar-scenarios 50 \
  --actual-scales 0,0.5,1,1.5,2,2.5 --out results/month-scale
```

这只是规模参数对齐，计算非常昂贵：三个控制器合计约 2,592 万次 LP 求解，当前脚本还会在内存中保留所有轨迹行。不要把它当作常规快速命令；大规模运行应先评估硬件与存储资源，必要时将实验分批运行。原文表 I 的 20%–25% 行采用 CVaR `N=400`；这里的 `N=300` 对应另一行，且任何场景数都不保证在替代数据上得到原文改善幅度。当前 `--actual-scales` 同时缩放需求和买价误差，也不同于原文图 2 分别扫描两个误差轴的实验。

常用参数还有 `--beta`（默认 `0.9`）、`--seed`（默认 `2016`）、`--model-scale`（默认 `1`）、`--gamma`（默认 `2*sqrt(14)`）、`--config` 和 `--nominal-csv`。可用 `python reproduction.py --help` 查看完整列表。

完整默认物理与成本配置见 [configs/default.json](configs/default.json)，可复制修改后通过 `--config` 传入。默认配置也可显式指定为 `--config configs/default.json`。

## 接入名义预测 CSV

```bash
python reproduction.py --nominal-csv nominal_forecasts.csv \
  --days 1 --replications 20 --include-mean --out results/custom
```

CSV 必须包含下列列名；额外列会被忽略：

| 列名 | 含义与单位 |
|---|---|
| `timestamp` | ISO 8601 时间戳，严格连续、间隔 30 分钟 |
| `net_load_kw` | 已知名义净需求预测，kW；负值表示净发电 |
| `buy_price_per_kwh` | 名义购电价格，美元/kWh |
| `sell_price_per_kwh` | 名义售电价格，美元/kWh |

```csv
timestamp,net_load_kw,buy_price_per_kwh,sell_price_per_kwh
2016-01-04T00:00:00,7.5,0.062,0
2016-01-04T00:30:00,7.4,0.062,0
```

这是格式示例，不能单独用于运行。若执行期为 `steps` 个半小时，至少需要 **`steps + 47` 行**，保证最后一次仍有完整的 24 小时预测窗口：默认一天需 95 行，smoke 需 51 行，30 天需 1,487 行。

文件按**名义预测序列**解释，不是实际未来观测；脚本在其上独立生成优化场景与实际评估路径。直接把历史真实值当作事先可用预测，会改变实验的信息条件。读取器不补缺、不重采样、不丢弃坏行：数值必须有限，价格须满足 `buy >= sell >= 0`，时间戳必须连续且使用一致的 UTC 偏移；无时区时间戳也必须前后一致。输入文件名、行数与 SHA-256 会记录到输出。

## 输出与解读

| 文件 | 内容 |
|---|---|
| `dispatch.csv` | 每个实际半小时的负荷、电价、充放电、SOC、电网功率、成本分量、预测目标及求解时间 |
| `trajectory_metrics.csv` | 每条完整执行路径的账单、综合成本、库存价值修正、期末 SOC 和耗时 |
| `summary.json` | 跨独立路径的均值、CVaR、标准差，以及配置、随机种子、软件版本、数据来源和价格截断计数 |
| `dispatch.png` | 第一个误差强度、第一条实际路径的电网功率、储能功率与能量 |
| `costs.png` | 各误差强度下，库存修正后的平均账单及综合成本 CVaR |

评价 CVaR 的样本单位是**一条完整执行路径的总成本**，不是将不同日期或半小时的成本混在一起排序。电网峰值与最大/最小功率差每个日历日计费一次；短运行只使用已执行的部分日。输出同时保留原始账单、综合运行成本和库存修正后的指标。

每次 24 小时优化要求终端能量为 25 kWh，但滚动执行期结束时不一定恰好为 25 kWh。因此所有控制器使用共同的库存价值 `0.062/0.95` 美元/内部储存 kWh，加入 `价值 × (初始能量 − 期末能量)` 的评价修正，并单独报告期末 SOC。这是声明的比较约定，不是执行了一次期末充电，也不是论文报告的现金流。

默认与 smoke 运行的实际路径数量很少，适合检查可运行性。判断 CVaR 是否改善尾部成本，需要增加独立重复、检查参数敏感性，并同时查看平均成本、尾部成本及能量状态；本实现不预设风险控制器必然优于其他控制器。

## 文件与复现边界

- `model.py`：SciPy/HiGHS 稀疏 LP、精确离散 CVaR、预算支持函数，以及独立物理/目标验算。
- `scenarios.py`：合成名义数据、严格 CSV 读取、时域聚合、相关误差和独立随机流。
- `reproduction.py`：半小时滚动执行、路径评价、CSV/JSON 与图形输出。
- `configs/default.json`：完整默认设备参数、成本权重、初始状态和共同库存价值。
- `tests/`：解析套利、分数尾质量、预算支持函数、非均匀时步、误差输入和非物理充放电反例等测试。
- [REPRODUCTION_NOTES.md](REPRODUCTION_NOTES.md)：公式映射、数据替代、参数假设和评价约定。

关键边界包括：论文式 (19) 的功率符号矛盾需要修正；价格扰动须先按论文使用的“分”与区间积分系数开平方，再转换为美元/kWh；买价样本会在售价处截断，改变原高斯分布的矩与相关性；LP 松弛若出现实质同时充放电会拒绝返回结果。具体推导和处理均记录在复现说明中。
