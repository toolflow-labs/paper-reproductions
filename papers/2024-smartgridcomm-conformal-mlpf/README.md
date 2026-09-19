# Conformal-MLPF 论文复现（SmartGridComm 2024）

本目录用于复现下面这篇论文的核心方法与实验流程：

> Anthony Faustine and Lucas Pereira, **Conformal Multilayer Perceptron-Based Probabilistic Net-Load Forecasting for Low-Voltage Distribution Systems with Photovoltaic Generation**, IEEE SmartGridComm 2024, pp. 59–64. DOI: 10.1109/SmartGridComm60555.2024.10738106.

论文的核心思路很简单：先用多层感知机（Multilayer Perceptron, **MLP**）得到净负荷的**点预测（point forecast）**，再用分割式保形预测（Split Conformal Prediction, **SCP**）根据历史预测误差生成**预测区间（prediction interval）**，从而把普通的确定性预测转换为带不确定性的概率预测（probabilistic forecast）。

如果只想先理解整篇论文，可以先记住下面这条主线：

```text
历史净负荷 + 天气/时间特征
        ↓
MLP 点预测（point forecast）
        ↓
校准集（calibration set）上计算预测误差
        ↓
非一致性分数（non-conformity score）
        ↓
逐预测步长校准（horizon-wise calibration）
        ↓
预测区间（prediction interval）
        ↓
覆盖率、区间宽度等概率预测指标
```

## 推荐入口：单 Notebook

为了方便逐格阅读论文、数据和方法，现在优先推荐直接打开：

`Conformal_MLPF_SPS_UK_reproduction.ipynb`

这个 Notebook 不依赖本目录下的 `src/` 代码，数据下载、SPS-UK 预处理、MLPF clean-room 实现、Split Conformal、absolute/signed residual 实验、MLP-QR、MLP-MCD、NRMSE/PICP/NMPI 和结果图都放在同一个文件里。适合学习和逐步修改；现有模块化代码仍保留，作为早期复现记录。

## 已执行结果（SPS-UK）

当前仓库已经提交 SPS-UK 二进制数据包：

`data/SPS-UK_dataset.zip`

并完成了 7 个可行 expanding-window folds 的端到端运行。结果位于：

```text
results/sps-uk-executed/metrics_by_fold.csv
results/sps-uk-executed/metrics_summary.csv
results/sps-uk-executed/run_config.json
```

单 Notebook `Conformal_MLPF_SPS_UK_reproduction.ipynb` 已同步写入本次实际运行结果。当前属于方法级 clean-room reproduction，不声称数值级复现论文 Table I；关键未公开细节及运行假设均在 Notebook 中说明。

## 本复现项目做了什么

本目录不是只提供一个 Notebook，而是尽量把论文从数据到结果的流程完整串起来：

1. 下载公开的 Plymouth / SPS-UK 低压配电网数据集。
2. 将负荷（load）、光伏出力（PV generation）和天气数据对齐到 30 分钟时间粒度。
3. 按 `净负荷 = 负荷 - 光伏` 构造净负荷（net load）。
4. 构造历史输入窗口（lookback window）、未来协变量（future covariates）和 48 步预测目标。
5. 训练确定性 MLP 点预测模型（deterministic point forecaster）。
6. 在独立校准集（calibration set）上计算残差，并构造逐预测步长的 Split Conformal 预测区间。
7. 同时实现 MLP 分位数回归（Quantile Regression, **MLP-QR**）和蒙特卡洛 Dropout（Monte-Carlo Dropout, **MLP-MCD**）作为对照方法（baselines）。
8. 计算 NRMSE、PICP、NMPI 等指标，并生成预测区间图和方法对比图。

## 先理解几个核心术语

### 1. 点预测（Point Forecast）

普通预测模型通常只输出一个数字，例如：

```text
明天 12:00 净负荷预测值 = 800 kW
```

这就是点预测。记为：

```text
ŷ = f(x)
```

它告诉我们“模型认为最可能是多少”，但没有告诉我们“这个预测有多不确定”。

### 2. 校准集（Calibration Set）

训练集（training set）用于学习 MLP 参数；校准集（calibration set）则不再更新 MLP 参数，而是专门用于观察：

```text
模型过去到底错了多少？
```

例如：

```text
预测值 ŷ = 800 kW
真实值 y = 860 kW
预测误差 = 60 kW
```

这些历史误差会被用来确定未来预测区间应该放多宽。

### 3. 非一致性分数（Non-conformity Score）

论文最基本的一种非一致性分数就是绝对残差（absolute residual）：

```text
score = |y - ŷ|
```

误差越大，说明这个样本与模型预测越“不一致”，因此分数越大。

### 4. 保形校准（Conformal Calibration）

将校准集上的预测误差从小到大排列，再取一个高分位数（quantile）。

例如目标覆盖率是 90%，可以从历史误差中取接近 90% 分位的误差阈值 `ε`，然后把新的点预测扩展成：

```text
[ŷ - ε, ŷ + ε]
```

这一步就是本项目里所谓的**校准（calibration）**。

这里的“校准”不是把 800 kW 修正成 820 kW，而是：

> 根据历史上模型实际错了多少，为未来预测配一个可信的误差边界。

### 5. 预测区间（Prediction Interval）

例如模型输出：

```text
点预测：800 kW
90% 预测区间：[740, 860] kW
```

表示模型不仅给出一个中心预测值，也给出一个包含真实值的可能范围。

### 6. 覆盖率（Coverage / PICP）

预测区间覆盖概率（Prediction Interval Coverage Probability, **PICP**）表示：

```text
有多少比例的真实值落在预测区间里面？
```

如果目标是 90%，那么理想情况下长期 PICP 应该接近 0.90。

### 7. 区间宽度（Interval Width / NMPI）

区间不能无限宽。

比如：

```text
[-∞, +∞]
```

覆盖率一定是 100%，但完全没有实际价值。因此概率预测通常要同时考虑：

```text
覆盖率要足够高
+
区间要尽可能窄
```

归一化平均预测区间宽度（Normalized Mean Prediction Interval width, **NMPI**）就是用于评价区间宽窄的指标之一。

### 8. 逐预测步长校准（Horizon-wise Calibration）

这篇论文不是给所有未来时刻共用一个误差阈值，而是分别对每一个预测步长（forecast horizon）进行校准。

例如 30 分钟数据、预测未来 24 小时：

```text
h = 1   → 未来 30 分钟
h = 2   → 未来 1 小时
...
h = 48  → 未来 24 小时
```

每个 `h` 都可以拥有自己的误差阈值 `ε_h`：

```text
[ŷ_h - ε_h, ŷ_h + ε_h]
```

这样可以体现“短期预测通常更准、远期预测通常更不确定”的特点。

## 与论文原始实现的关系

这是一个**方法级复现（methodological reproduction）**，不是作者 SmartGridComm 原始代码的镜像。

论文只有 6 页，虽然明确给出了主要模型和实验设计，但部分实现细节沿用了作者前期工作，没有在本文中全部展开。因此，本仓库采用以下原则：

- 论文明确写出的设置：尽量原样保留。
- 能从公式直接推出的实现：按公式实现。
- 论文没有写清楚的细节：明确标记为复现假设（reproduction assumption），不假装是作者原始设置。

详细差异见：

```text
REPRODUCTION_NOTES.md
```

## 数据说明

论文使用两个真实低压配电网数据集：

- **MLVS-PT**：葡萄牙 Madeira 低压变电站数据。
- **SPS-UK**：英国 Plymouth / Stentaway 低压变电站数据。

### SPS-UK

当前默认复现流程使用 SPS-UK，因为其公开数据可以自动下载。

公开数据来源：

- Zenodo Record: `5500457`
- DOI: `10.5281/zenodo.5500457`

下载脚本只获取实验需要的 CSV 文件，原始数据不会提交到 Git 仓库。

需要注意：论文写明 SPS-UK 使用 MERRA-2 天气数据，而公开 Zenodo 数据集中同时包含一份小时级再分析天气（reanalysis weather）CSV，但无法从公开元数据确认它是否就是论文使用的同一份 MERRA-2 提取结果。

因此默认流程优先保证“可以端到端运行”，同时提供 `--weather-override` 参数，允许替换为自行准备的 MERRA-2 数据。

### MLVS-PT

代码支持读取：

```text
data/raw/mlvs_pt/MLVS-PT.parquet
```

但当前没有在本项目中声称存在稳定的官方自动下载地址。因此 MLVS-PT 暂时需要用户自行提供数据文件。

## 环境安装

进入论文目录：

```bash
cd papers/2024-smartgridcomm-conformal-mlpf
```

创建 Python 虚拟环境：

```bash
python -m venv .venv
```

Linux / macOS：

```bash
source .venv/bin/activate
```

Windows：

```powershell
.venv\Scripts\activate
```

安装依赖：

```bash
pip install -e .
```

## 最推荐的第一次运行方式

如果只是想确认代码、数据和模型流程是否全部能够跑通，先执行：

```bash
make smoke
```

`smoke` 是快速冒烟测试（smoke test），会使用较小的数据和训练规模，主要检查：

```text
数据读取
→ 特征构造
→ MLP 训练
→ 保形校准
→ 指标计算
```

是否能够完整执行。

确认没有问题后，再执行完整流程：

```bash
make all
```

它依次执行：

```text
make data
    ↓
make experiment
    ↓
make figures
```

即：

```text
数据下载/预处理
→ 模型训练与实验
→ 指标计算
→ 结果可视化
```

## 分步运行

### 第一步：下载数据

```bash
python scripts/01_download_data.py --dataset sps-uk
```

### 第二步：数据预处理

```bash
python scripts/02_prepare_data.py --dataset sps-uk
```

这一阶段主要负责：

```text
负荷数据
+ 光伏数据
+ 天气数据
        ↓
时间对齐（time alignment）
        ↓
30 分钟重采样（resampling）
        ↓
净负荷（net load）
        ↓
模型可用的数据集
```

如果已经准备了更接近论文设置的 MERRA-2 数据，可以使用：

```bash
python scripts/02_prepare_data.py --dataset sps-uk \
  --weather-override /path/to/merra2_halfhourly.csv
```

外部天气文件至少应包含：

- 时间戳（timestamp）；
- 温度类变量（temperature-like variable）；
- 辐射/太阳辐照度类变量（radiation / irradiance-like variable）。

### 第三步：运行实验

```bash
python scripts/03_run_experiments.py --dataset sps-uk
```

主要包括：

```text
MLP 点预测
→ Split Conformal 校准
→ MLP-QR 对照
→ MLP-MCD 对照
→ NRMSE / PICP / NMPI 等指标
```

### 第四步：可视化

```bash
python scripts/04_plot_results.py --dataset sps-uk
```

自动生成预测区间图和不同方法的指标对比图。

## 输出结果

运行完成后，结果默认位于：

```text
results/sps-uk/
├── metrics.csv
├── fold_predictions.npz
└── figures/
    ├── prediction_intervals.png
    └── metrics_comparison.png
```

其中：

- `metrics.csv`：模型评价指标。
- `fold_predictions.npz`：各个回测折（backtesting folds）的预测结果。
- `prediction_intervals.png`：真实净负荷、点预测和预测区间。
- `metrics_comparison.png`：不同概率预测方法的指标比较。

## 当前保留的论文设置

当前实现尽量保留论文明确写出的主要设置：

- SPS-UK 使用 30 分钟采样粒度。
- 默认预测未来 `H=48` 个半小时，即未来 24 小时。
- MLP 使用 2 个隐藏层（hidden layers）。
- 每个隐藏层 256 个神经元（units）。
- 激活函数使用 SiLU。
- 优化器使用 Adam。
- 初始学习率（learning rate）为 `1e-3`。
- 在训练进度达到 75% 和 90% 时降低学习率。
- 点预测损失使用 L1/L2 混合损失（mixed L1/L2 loss）。
- 使用 10 折扩展窗口回测（10-fold expanding-window backtesting）的思路。
- 每个训练窗口最后 10% 数据保留为校准集（calibration set）。
- 每个预测步长分别计算保形分数和预测区间（horizon-wise conformal intervals）。
- 比较绝对残差（absolute residual）和有符号残差（signed residual）两种非一致性分数。
- 与 MLP-QR 和 MC-Dropout 概率预测方法进行比较。

## 目前不要期待什么

当前版本的目标是**理解并跑通论文方法**，而不是直接保证复现出论文 Table I 一模一样的数字。

目前影响数值一致性的主要因素包括：

- SPS-UK 天气数据与论文所述 MERRA-2 数据可能存在差异；
- 论文未完整给出所有训练超参数；
- 部分 MLP 结构和训练细节引用了作者前作；
- CWE 的完整论文实现细节没有完全展开，因此当前代码中明确标记为近似实现（proxy）。

因此更合适的使用顺序是：

```text
第一阶段：跑通方法，理解 CP / calibration / coverage
第二阶段：对照论文 Fig. 4 和 Table I
第三阶段：逐项收紧数据与超参数
第四阶段：再尝试数值级复现
```

如果后续要继续学习自适应保形预测（Adaptive Conformal Prediction, **ACP**），这套实现也可以直接作为静态 Split CP 的基线（baseline）。
