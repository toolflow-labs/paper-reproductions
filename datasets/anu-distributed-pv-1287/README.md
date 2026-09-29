# ANU 1287 户分布式光伏数据

本目录用于复现和研究澳大利亚国立大学（ANU）公开的 **Distributed PV power data for three cities in Australia** 数据集。

该数据包含 **1,287 个真实居民光伏系统**的逆变器功率测量和站点元数据，主要分布在 Canberra、Perth 和 Adelaide；时间范围为 2016 年 9 月至 2017 年 3 月，时间分辨率为 10 分钟。官方同时提供 raw、quality-controlled (QC) 和 tuned 版本。

- DOI：10.25911/5ca6a0640869a
- Zenodo：https://zenodo.org/records/2635887
- ANU Data Commons：https://datacommons.anu.edu.au/DataCommons/rest/display/anudc%3A5953

## 重要：原始数据不能提交到本仓库

这套数据虽然可以免费用于科研，但作者采用了自定义使用条款，明确要求：

- 仅限研究使用，不用于商业用途；
- 原始数据不能重新分发；
- 数据应从作者指定的官方入口获取；
- 使用时应按作者要求引用数据论文及相应 QC / tuning 论文。

因此，本目录**不保存 data.zip 或解压后的原始数据文件**。请运行下载脚本直接从 Zenodo 官方记录获取；`raw/` 已被 `.gitignore` 排除。

## 使用方法

```bash
cd datasets/anu-distributed-pv-1287
python download_and_profile.py
```

脚本会：

1. 从 Zenodo 官方记录下载 `data.zip` 和 `license and metadata.txt`；
2. 校验 Zenodo 公布的 MD5；
3. 将文件保存到本地 `raw/`；
4. 生成本地数据结构摘要 `DATASET.local.md`。

如只想下载、不做数据结构扫描：

```bash
python download_and_profile.py --no-profile
```

## 为什么适合分布式光伏调控研究

相比单一电站光伏数据，这套数据最大的价值是**同一区域内大量分散户用 PV 的时空功率序列**。可以用于：

- 分布式 PV 聚合功率预测；
- 聚合规模增加后的空间平滑效应研究；
- PV available power / downward flexibility 的概率建模；
- Conformal Prediction / Adaptive Conformal 对聚合可调能力进行区间估计；
- 按城市、站点规模、空间位置构造不同聚合资源池；
- 与 IEEE 123-bus / SMART-DS 等配电网模型结合，进一步做限发分配与 AC 潮流验证。

## 与现有论文方向的区别

这里建议把研究问题放在“**聚合光伏到底有多少可信的可调能力**”，而不是只做传统光伏功率预测。

一个自然的后续链路是：

```text
多站点光伏功率
    ↓
未来可用光伏功率预测
    ↓
不确定性 / Conformal 区间
    ↓
可信向下调节能力
    ↓
光伏限发容量承诺 / 设备选择
    ↓
配电网 AC 潮流验证
```

## 引用

使用数据时至少应引用：

Bright, J. M., Killinger, S., & Engerer, N. A. (2019). *Data article: Distributed PV power data for three cities in Australia*. Journal of Renewable and Sustainable Energy, 11(3), 035504. DOI: 10.1063/1.5094059.

此外，使用 QC 或 tuned 数据时，还需要按照官方 `license and metadata.txt` 中的说明引用相应方法论文。
