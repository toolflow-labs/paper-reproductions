# ANU 1287 户分布式光伏数据情况

## 1. 官方基本信息

- 数据集：**Distributed PV power data for three cities in Australia**
- 数据提供方：Australian National University
- DOI：`10.25911/5ca6a0640869a`
- Zenodo：https://zenodo.org/records/2635887
- 主要地区：
  - ACT / Canberra：**363** 个光伏系统
  - SA / Adelaide：**393** 个光伏系统
  - WA / Perth：**531** 个光伏系统
  - 合计：**1,287** 个居民光伏系统
- 时间范围：2016 年 9 月至 2017 年 3 月
- 时间分辨率：10 分钟
- 数据来源：真实逆变器报告的光伏功率
- 官方数据版本：原始测量（raw）、质量控制后（QC）、tuned，以及模拟 clear-sky 功率
- 每个站点都有配套 metadata，包括地理位置、装机容量、安装日期、朝向、倾角和估计参数等。

## 2. 许可限制

这套数据采用自定义科研使用条款，并不是允许自由镜像的普通开放许可证。

官方明确要求：

- 数据仅用于研究用途，不用于商业使用；
- **原始数据不得重新分发**；
- 数据应从作者指定的官方入口获取；
- 使用数据的论文和成果需要按官方要求进行引用；
- 使用 QC / tuned 版本时，还需引用相应的 QCPV 和 tuning 方法论文。

因此，本仓库不提交 `data.zip` 或任何解压后的原始测量数据。

本目录只保留：

- 一键官方下载脚本；
- MD5 校验；
- 数据格式和结构说明；
- 本地生成的数据结构摘要；
- 后续研究处理代码。

## 3. 已实际验证的官方下载

2026-09-29 使用本目录脚本在 GitHub Actions 中实际下载并验证：

- `data.zip`
  - Zenodo 页面标称：538.8 MB
  - 实际下载：**513.80 MiB**
  - MD5：`281aa841f57217fe316ec225470b18b8`
  - 校验结果：**通过**
- `license and metadata.txt`
  - MD5：`5d772b6504c17f6bdb67526dc60d15d9`
  - 校验结果：**通过**

`data.zip` 解压后：

- 文件数：**18**
- 全部为 CSV
- 解压总大小：约 **1.86 GiB**

## 4. 压缩包实际结构

每个地区有 6 类文件，共 3 × 6 = 18 个 CSV。

| 类型 | ACT | SA | WA | 含义 |
|---|---|---|---|---|
| metadata | `metadata_final_ACT.csv` | `metadata_final_SA.csv` | `metadata_final_WA.csv` | 每个 PV 系统的站点属性 |
| timestamp | `unixtime_final_ACT.csv` | `unixtime_final_SA.csv` | `unixtime_final_WA.csv` | UTC / 本地时间，10 分钟分辨率 |
| raw PV | `PVpow_trim_ACT.csv` | `PVpow_trim_SA.csv` | `PVpow_trim_WA.csv` | 原始逆变器功率 |
| QC PV | `PVpow_qc_trim_ACT.csv` | `PVpow_qc_trim_SA.csv` | `PVpow_qc_trim_WA.csv` | QCPV 质量控制后的功率 |
| tuned PV | `PVpow_tuned_ACT.csv` | `PVpow_tuned_SA.csv` | `PVpow_tuned_WA.csv` | tuning 后的功率 |
| clear-sky | `PVpow_cs_trim_ACT.csv` | `PVpow_cs_trim_SA.csv` | `PVpow_cs_trim_WA.csv` | 模拟 clear-sky 功率 |

实际文件大小：

| 文件 | 解压后大小 |
|---|---:|
| `metadata_final_ACT.csv` | 29.35 KiB |
| `metadata_final_SA.csv` | 31.46 KiB |
| `metadata_final_WA.csv` | 39.54 KiB |
| `PVpow_cs_trim_ACT.csv` | 190.77 MiB |
| `PVpow_cs_trim_SA.csv` | 203.07 MiB |
| `PVpow_cs_trim_WA.csv` | 242.46 MiB |
| `PVpow_qc_trim_ACT.csv` | 146.89 MiB |
| `PVpow_qc_trim_SA.csv` | 96.23 MiB |
| `PVpow_qc_trim_WA.csv` | 164.67 MiB |
| `PVpow_trim_ACT.csv` | 185.78 MiB |
| `PVpow_trim_SA.csv` | 105.32 MiB |
| `PVpow_trim_WA.csv` | 182.46 MiB |
| `PVpow_tuned_ACT.csv` | 133.61 MiB |
| `PVpow_tuned_SA.csv` | 93.31 MiB |
| `PVpow_tuned_WA.csv` | 159.31 MiB |
| `unixtime_final_ACT.csv` | 1.85 MiB |
| `unixtime_final_SA.csv` | 1.85 MiB |
| `unixtime_final_WA.csv` | 1.85 MiB |

## 5. 数据格式

论文说明 CSV 使用**分号**分隔，缺失或被 QC 剔除的值使用字符串 `NA`。

### metadata

实际表头：

```text
IDs;Longitude;Latitude;Capacity;Installation_Date;
Azimuth_Giv;Tilt_Giv;Azimuth_Sim;Tilt_Sim;LF
```

主要字段：

- `IDs`：站点 ID；
- `Longitude` / `Latitude`：经纬度；
- `Capacity`：装机容量，kWp；
- `Installation_Date`：安装日期；
- `Azimuth_Giv` / `Tilt_Giv`：用户报告的方位角和倾角；
- `Azimuth_Sim` / `Tilt_Sim`：根据功率曲线估计的方位角和倾角；
- `LF`：loss factor。

### timestamp

实际表头：

```text
Unixtime;GMT
```

每一行对应 PV 功率文件中的同一行时间点，分辨率为 10 分钟。

### PV 功率矩阵

- 每一列对应一个 PV 系统；
- 第一行是站点 ID，可与 metadata 中的 `IDs` 对齐；
- 每一行对应 timestamp 文件中的同一时间点；
- 功率不是直接的 kW，而是归一化后的 **kW/kWp**；
- 若需要恢复站点实际功率，需要乘以 metadata 中相应站点的装机容量 `Capacity`。

这一点对后续聚合研究很重要：不同容量站点不能直接把归一化功率相加，应先恢复为 kW 或统一定义聚合指标。

## 6. 原始、QC、tuned、clear-sky 四类功率

论文给出的四类功率含义为：

- `PVpow_trim_*`：原始测量功率；
- `PVpow_qc_trim_*`：经过 QCPV 质量控制的数据；
- `PVpow_tuned_*`：进一步 tuning 后的数据；
- `PVpow_cs_trim_*`：模拟 clear-sky PV 功率。

论文还报告了 QCPV 后保留的数据量：

- ACT：原始有效点约 9,157,671，QC 后 5,707,504，约 **62.3%**；
- SA：2,619,416 → 1,829,595，约 **69.9%**；
- WA：6,763,084 → 4,897,408，约 **72.4%**。

因此后续正式建模时不宜简单认为 1287 个站点都有完整连续数据，应该单独做缺失率、有效站点和连续时间窗口筛选。

## 7. 对“分布式光伏调控”论文的价值

这套数据最大的价值不是单个站点，而是**大量空间分布的真实居民 PV 同期功率序列**。

比较适合研究：

1. 不同聚合规模下的 PV 空间平滑效应；
2. 50 / 100 / 300 / 500 / 1000 户资源池的聚合波动；
3. 多站点 PV 聚合功率预测；
4. available PV power 的不确定性建模；
5. Conformal / Adaptive Conformal 形成可信可调能力区间；
6. 从预测区间进一步转化为 VPP / 聚合商能够承诺的向下调节容量；
7. 按城市、装机容量、空间位置构造不同类型的资源池。

一个比较自然的研究链路是：

```text
真实多站点 PV
→ 未来可用 PV 功率预测
→ 不确定性 / Conformal 区间
→ 可信向下调节能力
→ 限发容量承诺 / 设备选择
→ IEEE 123-bus 或 SMART-DS AC 潮流验证
```

## 8. 数据本身做不了什么

这套数据没有：

- 实际配电网拓扑；
- 逆变器下发控制指令；
- 限发 setpoint；
- 实际控制响应标签；
- 台区电压、电流、线路潮流。

因此它非常适合解决“**聚合光伏可用功率与可信调节能力**”，但如果要完整研究“**调控执行和配电网效果**”，还需要与 IEEE 123-bus、SMART-DS、CANVAS 等数据或仿真平台结合。

## 9. 下载

运行：

```bash
python datasets/anu-distributed-pv-1287/download_and_profile.py
```

脚本会：

1. 直接从官方 Zenodo 下载；
2. 校验官方 MD5；
3. 保存到本地 `raw/`；
4. 自动生成 `DATASET.local.md`；
5. 因 `.gitignore` 规则，不会把受许可限制的数据误提交到 Git。

## 10. 引用

至少应引用：

Bright, J. M., Killinger, S., & Engerer, N. A. (2019). *Data article: Distributed PV power data for three cities in Australia*. Journal of Renewable and Sustainable Energy, 11(3), 035504. DOI: 10.1063/1.5094059.

使用 QC / tuned 数据时，应继续按照官方 `license and metadata.txt` 的要求补充引用相关 QCPV 和 tuning 文献。
