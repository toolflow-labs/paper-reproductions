# UNSW CANVAS Solar Curtailment

本目录整理 UNSW CEEM 的 **CANVAS（Curtailment and Network Voltage Analysis Study）Solar-Curtailment** 开源项目，作为分布式光伏调控研究的“限发机理、数据格式和算法基线”参考。

上游项目：

- GitHub: https://github.com/UNSW-CEEM/Solar-Curtailment
- PyPI: https://pypi.org/project/solarcurtailment/
- CANVAS 项目说明：https://www.ceem.unsw.edu.au/open-source-tools
- README 中原公开数据入口（Google Drive）：https://drive.google.com/drive/folders/1pQ3h7HCYYzm1rxQpw1sw4qD8-uZYcZ5R?usp=sharing

## 当前可用性状态

2026-09-29 实际验证：

- 上游 GitHub 仓库：**正常可访问**；
- `solarcurtailment` PyPI 包：**正常可安装**，最新版为 2.0.0；
- 仓库中的数据格式说明 `documentations/dataset information.docx`：**正常可访问**；
- README 指向的 Google Drive 公共数据文件夹：**当前返回 404，无法通过 gdown 获取**。

因此本目录**不声称已经保存 CANVAS 原始 Solar Analytics 数据**。这里保存的是：

1. 经上游数据字典核对后的数据结构说明；
2. CANVAS 的 curtailment 定义与算法基线说明；
3. 上游代码 / PyPI 环境配置；
4. 用于检查公开数据入口是否恢复的脚本。

## 为什么仍然值得保留

ANU 1287 户数据提供的是大规模真实分布式 PV 功率，适合做：

- 聚合功率预测；
- available PV power；
- 空间平滑效应；
- 聚合可调能力区间。

但 ANU 数据没有真实的：

- voltage；
- reactive power；
- V-Watt / V-VAr；
- tripping；
- curtailment 标签。

CANVAS 恰好补这部分。它公开了如何根据**电压、有功、无功、GHI、逆变器 AC/DC 容量**识别和量化：

- Tripping curtailment；
- V-VAr response / curtailment；
- V-Watt response / curtailment；
- Expected power；
- Curtailed energy。

所以建议把两套材料分工为：

```text
ANU 1287-site PV
    ↓
真实大规模 PV 聚合 / available power / uncertainty
    ↓
Conformal / Adaptive Conformal
    ↓
可信 downward flexibility
    ↓
CANVAS
    ↓
把“削减”具体化为 tripping / V-Watt / V-VAr / expected-vs-actual
    ↓
IEEE-123 / SMART-DS
    ↓
AC 配电网限发决策与电压验证
```

## 环境

CANVAS 官方 Python 包：

```bash
pip install solarcurtailment==2.0.0
```

本目录提供：

```bash
python check_upstream.py
```

默认检查上游 GitHub 和数据入口状态；如本地安装了 `gdown`，可使用：

```bash
python check_upstream.py --try-data
```

尝试从原官方 Google Drive 下载数据。如果链接未来恢复，数据会进入 `raw/`，该目录已被 Git 忽略。

## 注意

上游仓库的 MIT License 明确覆盖其软件和文档；但 README 外链的 Solar Analytics 数据没有在仓库中看到同等明确的再分发许可。本仓库因此不镜像那批原始数据。
