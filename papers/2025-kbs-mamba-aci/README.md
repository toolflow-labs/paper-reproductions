# Suresh et al. 2025 — ACI 核心实验复现（SPS-UK）

复现论文：

> Vishnu Suresh, Anshuman Swain, B. Sri Revathi, Josep M. Guerrero.  
> **Mamba based adaptive conformal inference for probabilistic short-term load forecasting**.  
> *Knowledge-Based Systems*, 328 (2025) 114222.  
> DOI: 10.1016/j.knosys.2025.114222

## 定位

这是一个 **method-level / learning-oriented reproduction**，重点复现论文的：

```text
LSTM point forecast
→ calibration residual
→ Static Split Conformal
→ Adaptive Conformal Inference (ACI)
→ Coverage / MIW / Winkler
```

不声称复现论文 Table VI 的原始数值。

原因是论文的 Tamil Nadu 数据仅说明可向作者申请，完整代码未公开；此外，论文未明确给出 ACI learning rate `γ`，LSTM 输入历史窗口也未完全写清。

## 为什么使用 SPS-UK？

本仓库上一项复现已经包含：

```text
papers/2024-smartgridcomm-conformal-mlpf/data/SPS-UK_dataset.zip
```

因此这里直接复用同一份公开数据，不重复提交二进制文件。

SPS-UK 原始分辨率为 30 min。本复现仅使用 demand，并重采样到 1 h，以贴近 Suresh et al. 的 **one-hour-ahead** 任务。

## 推荐入口

打开：

```text
Suresh_2025_ACI_SPS_UK_reproduction.ipynb
```

Notebook 逐步解释：

1. SPS-UK demand 读取；
2. 30 min → 1 h；
3. one-hour-ahead 样本构造；
4. chronological Train / Calibration / Test；
5. 2-layer LSTM 点预测；
6. Static Split CP；
7. ACI 在线更新；
8. Coverage、MIW、Winkler；
9. `alpha_t` 与 rolling coverage 可视化；
10. 如何从 single-horizon ACI 迁移到后续的 horizon-wise multi-horizon ACI。

## 主要复现假设

| 项目 | 论文 | 本复现 |
|---|---|---|
| 数据 | Tamil Nadu regional load | SPS-UK demand |
| 时间分辨率 | 1 h | SPS-UK 30 min 重采样为 1 h |
| Forecast horizon | 1 h ahead | 1 h ahead |
| LSTM | 2 layers, 5 cells/layer, 9 epochs, batch 24, lr 0.01 | 尽量保持一致 |
| Lookback | 未明确 | 24 h |
| Target coverage | 90% | 90% |
| ACI update | `alpha[t+1] = alpha[t] + gamma * (alpha - err[t])` | 同公式 |
| gamma | 未明确 | 0.01 |
| Test usage | 论文部分超参描述存在 test-set 调参歧义 | 严格 chronological split |
| CRPS | 论文报告 | 本复现不强行计算，因 ACI 区间不足以唯一确定完整 CDF |

## 环境

```bash
pip install -r requirements.txt
jupyter lab
```

如果从仓库根目录运行 Notebook，它也会自动搜索上一项复现中的 `SPS-UK_dataset.zip`。

## 本复现最重要的观察

不要把 ACI 理解成“另一个预测模型”。它更像一个覆盖率反馈器：

- 漏包 → `alpha_t` 降低 → residual quantile 变大 → 区间变宽；
- 连续覆盖 → `alpha_t` 升高 → 区间逐渐收窄。

这正是后续将 single-horizon ACI 扩展为 48-step horizon-wise ACI 的基础。
