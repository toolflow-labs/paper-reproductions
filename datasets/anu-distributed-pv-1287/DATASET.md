# ANU 1287 户分布式光伏数据情况

## 官方基本信息

- 数据集：Distributed PV power data for three cities in Australia
- 数据提供方：Australian National University
- 站点规模：1,287 个居民光伏系统
- 主要城市：Canberra、Perth、Adelaide
- 时间范围：2016 年 9 月至 2017 年 3 月
- 分辨率：10 分钟
- 数据：真实逆变器报告的光伏功率，以及站点元数据
- 官方提供版本：raw、quality-controlled (QC)、tuned
- DOI：10.25911/5ca6a0640869a
- Zenodo 记录：https://zenodo.org/records/2635887
- `data.zip`：约 538.8 MB；Zenodo MD5 为 `281aa841f57217fe316ec225470b18b8`

## 许可限制

这套数据不是普通的可自由再分发开放许可证。作者允许科研使用，但明确限制原始数据的重新分发，并要求从官方入口获取。因此，本仓库不提交 `data.zip` 或解压后的测量数据。

运行：

```bash
python datasets/anu-distributed-pv-1287/download_and_profile.py
```

即可直接从官方 Zenodo 记录下载，并生成本地 `DATASET.local.md`。

## 对分布式光伏调控论文的价值

该数据的关键优势不是单个光伏系统持续时间特别长，而是同一时期存在大量空间分布的真实居民光伏系统。它特别适合研究：

- 不同聚合规模下的 PV 波动平滑效应；
- 多站点 PV 聚合功率预测；
- 区域级 PV available power 的不确定性；
- 将预测区间转化为“可信向下调节能力”；
- 对不同容量承诺水平计算短缺概率；
- 通过 Adaptive Conformal 等方法在线校准聚合灵活性区间。

这套数据本身没有电网拓扑，也没有调控指令和限发响应标签。因此，如果论文目标是“光伏调控”而非“光伏聚合预测”，建议后续与 IEEE 123-bus、SMART-DS 或其他配电网数据结合，构造：

```text
真实多站点 PV
→ 可用功率 / 可调能力预测
→ 不确定性区间
→ 光伏限发或容量承诺
→ 配电网潮流与电压约束验证
```

## 后续实际检查项

下载完成后，建议优先确认：

1. raw / QC / tuned 三类文件的实际组织方式；
2. 站点 metadata 的字段，包括经纬度、容量、朝向、倾角等；
3. 各城市实际站点数；
4. 单站点缺失率与连续可用时间段；
5. QC / tuned 数据能否方便地转换成统一的 `timestamp × site_id` 长表；
6. 是否适合直接按 50 / 100 / 300 / 500 / 1000 户构造聚合资源池。

本文件只记录官方元信息和研究用途判断；详细压缩包结构由下载脚本在本地生成，避免在仓库内重新分发受限制数据。
