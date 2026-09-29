# UNSW CANVAS Solar Curtailment 数据情况

## 1. 项目定位

CANVAS 是 UNSW、Solar Analytics、SA Power Networks、AGL 等参与的分布式光伏限发研究项目。其开源工具用于识别和量化三类由逆变器功率质量响应引起的 PV 削减：

1. **Tripping**：高电压等条件下逆变器停止运行；
2. **V-VAr**：逆变器吸收/注入无功，受视在功率限制时压缩可用有功；
3. **V-Watt**：电压升高后逆变器按曲线降低有功输出。

上游算法使用的主要时序量为：

- Voltage；
- Real power；
- Reactive power；
- Global Horizontal Irradiance (GHI)；
- PV / inverter DC、AC capacity。

## 2. 原始数据来源与规模

上游 README 说明，原始 D-PV 时序来自 **Solar Analytics**。

数据字典进一步说明：

- 原始月度文件中混有约 **500 个 PV 系统**；
- `details_site_id.csv`：500 行；
- `details_circuit_details.csv`：500 行；
- `UniqueCids.csv`：499 行；
- `UniqueCids500.csv`：500 行；
- 每个 `c_id` 在该数据里对应一个唯一 `site_id`；
- 原始监测数据存在极性接反的安装问题，因此 circuit metadata 中有 `polarity = 1 / -1`。

## 3. 关键 metadata

### `details_site_id.csv`

500 个站点，核心字段：

| 字段 | 含义 |
|---|---|
| `site_id` | 站点 ID |
| `ac_cap_w` | 逆变器 AC 有功额定容量，W |
| `dc_cap_w` | PV 阵列 DC 额定容量，W |

CANVAS 特别指出：若 `dc_cap_w` 显著高于 `ac_cap_w`，即使没有网络限发，也可能出现逆变器容量限制。

### `details_circuit_details.csv`

500 个 circuit，核心字段：

| 字段 | 含义 |
|---|---|
| `site_id` | 站点 ID |
| `c_id` | circuit / customer ID |
| `con_type` | connection type |
| `polarity` | 监测设备极性，1=正常，-1=反接 |

这个极性字段非常重要。CANVAS 文档明确说，部分监测设备安装时极性反了，导致有功和无功符号同时反转。

## 4. D-PV 时序数据格式

官方数据字典给出的单站点、单日样本文件为：

```text
data_sample_N.csv
```

典型样本约 1433 行，7 个字段：

| 字段 | 含义 |
|---|---|
| `Timestamp` | 已转换为 Adelaide 本地时间，例如 `2019-09-03 11:21:55+09:30` |
| `c_id` | circuit / PV system ID |
| `energy` | 原始能量字段；CANVAS 自身不直接使用，而是由 power 积分重新计算 |
| `power` | 平均有功功率，W |
| `reactive_power` | 平均无功功率，VAr |
| `voltage` | 平均电压，V |
| `duration` | 与相邻时间戳的间隔，秒；该数据中可能为 **5 s 或 60 s** |

README 同时提醒：由于原始监测设置问题，项目中的 raw VAr 数据在其特定数据上需要除以 60 才得到实际一分钟无功值。这个修正规则**不能未经验证直接迁移到其他数据集**。

## 5. GHI 数据

官方数据字典中的月度太阳辐照文件格式：

```text
sl_023034_YYYY_MM.txt
```

例如 `sl_023034_2019_01.txt`：

- 36 列；
- 单月样例约 40,320 行；
- 约 11.1 MB；
- 文档记录可用月份：**2019-01 ～ 2020-07**；
- 核心量为每分钟平均 Global Horizontal Irradiance，单位 W/m²。

CANVAS 的一个明显局限是：分析 499/500 个 PV 站点时只使用**一个 GHI 观测站**，因此局部云层可能导致“站点实际有云、GHI 站却判断为晴天”的错配。这个问题对后续设计新的算法非常值得注意。

## 6. 14 个公开示例的类别

数据字典记录在 2022-09-14 时共有 14 个单日样本，其中明确指出：

- sample 1：**Tripping curtailment — non-clear-sky day**
- sample 11：**Tripping curtailment — clear-sky day**
- sample 14：**V-VAr curtailment**
- sample 4：**V-Watt curtailment**
- sample 5：**Incomplete dataset**
- sample 9：**Clear-sky day without curtailment**

配套 GHI 样本形式为 `ghi_sample_N.csv`，单日通常 1440 个一分钟点。

这套标签体系很适合后续给 ANU / 仿真数据构造“限发事件定义”和算法 baseline。

## 7. CANVAS 如何定义 expected power 与 curtailed energy

核心关系：

```text
curtailed energy = expected generation without curtailment - actual generation
```

但难点在于如何估计“如果没有限发本来该发多少”。

CANVAS 基线：

- **晴天**：对筛选后的未削减功率点做二次 `polyfit`；
- **非晴天 + tripping**：对 trip 前后的功率做线性插值；
- **非晴天 + 非 tripping**：项目认为难以可靠区分云遮与 V-Watt / V-VAr，因此不贸然估计。

这个设计对新论文很有启发：第三篇真正可以改进的地方之一，就是用更系统的 available-power probabilistic estimation / conformal interval 取代这些较强的经验规则。

## 8. Tripping / V-VAr / V-Watt 基线

### Tripping

在日出至日落期间，有功从非零突然降到零，再恢复，被视为 trip；项目同时把 trip 前的下降段和恢复后的上升段纳入事件。

### V-VAr

CANVAS 根据 Q-V 散点拟合 V-VAr 曲线，并与 AS/NZS 4777.2 等规范曲线比较。上游实现使用约 100 VAr 的无功阈值过滤噪声。

### V-Watt

CANVAS 在晴天条件下寻找 P-V 散点是否贴合可能的 V-Watt 曲线。文档描述的候选 V3 threshold 范围为约 235–255 V，V4 为 265 V，并使用 buffer 和 compliance percentage 判定。

## 9. 当前公共数据可用性

2026-09-29 实测：

- GitHub 源码仓库：可访问；
- PyPI `solarcurtailment==2.0.0`：可访问；
- GitHub 内 `dataset information.docx`：可访问；
- README 中给出的 Google Drive 数据文件夹：
  `1pQ3h7HCYYzm1rxQpw1sw4qD8-uZYcZ5R`
  当前用 `gdown` 返回 **404**，未获得任何文件。

因此目前不能把“500 站点完整 Solar Analytics 原始时序”当成稳定、可直接下载的公共数据。

如果后续官方恢复该链接，可重新尝试：

```bash
pip install gdown
python datasets/unsw-canvas-solar-curtailment/check_upstream.py --try-data
```

## 10. 与 ANU 1287-site 数据的组合

两套数据不是重复关系：

| 能力 | ANU 1287-site | UNSW CANVAS |
|---|---|---|
| 大规模真实多站点 PV 功率 | **强** | 原始大样本目前不可下载 |
| 地理位置 / 容量 | **有** | 数据字典有 AC/DC capacity |
| 长时间聚合建模 | **适合** | 当前不稳定 |
| 电压 | 无 | **有** |
| 无功 | 无 | **有** |
| tripping | 无 | **有定义/示例** |
| V-Watt | 无 | **有定义/示例** |
| V-VAr | 无 | **有定义/示例** |
| expected-power 基线 | clear-sky/tuned 可参考 | **有明确算法** |
| curtailed-energy 基线 | 无 | **有明确算法** |

比较合理的使用方式：

```text
ANU
→ 建立多站点 available PV / aggregate flexibility 主模型

CANVAS
→ 定义和验证 curtailment detection / expected power / inverter response baseline

IEEE 123-bus / SMART-DS
→ 把“可信可调能力”进入配电网控制决策，做 AC 潮流与电压约束验证
```

## 11. 一个值得避免的误区

CANVAS 的公开工具解决的主要是：

> “从已经发生的电压和功率行为里，识别/估计发生了多少限发。”

而第三篇如果要形成更强的研究问题，应进一步走到：

> “未来某个时间窗口里，聚合 PV 能可靠提供多少向下调节能力，并据此做控制承诺和设备选择。”

因此 CANVAS 更适合作为**物理机理与算法 baseline**，而不是直接把它的 curtailment detection 再做一遍。
