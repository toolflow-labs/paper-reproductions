# Datasets

本目录保存论文复现与后续研究需要的公开数据、可复现下载脚本和数据说明。

## 当前数据源

| 目录 | 数据/项目 | 主要用途 | 原始数据是否入库 |
|---|---|---|---|
| `connecticut-ess-vpp/` | Connecticut Energy Storage Solutions | VPP 储能聚合功率、装机与项目属性 | 是 |
| `anu-distributed-pv-1287/` | ANU 1287 户分布式 PV | 大规模真实多站点 PV、聚合功率、available power / flexibility | 否；许可禁止再分发，提供官方下载脚本 |
| `unsw-canvas-solar-curtailment/` | UNSW CANVAS Solar Curtailment | tripping、V-Watt、V-VAr、expected power、curtailed energy 的定义与算法 baseline | 否；上游数据链接当前不可用 |

## 分布式光伏调控研究建议

ANU 与 CANVAS 建议组合使用，而不是互相替代：

```text
ANU 1287-site PV
→ 多站点真实功率 / 聚合 / available power
→ 不确定性预测与可信 flexibility

CANVAS
→ curtailment 机理与识别基线
→ tripping / V-Watt / V-VAr
→ expected-vs-actual / curtailed energy

IEEE 123-bus / SMART-DS
→ 把可信可调能力进入控制
→ 限发分配 / AC 潮流 / 电压约束验证
```

当前阶段，ANU 可以作为主数据集；CANVAS 主要负责给“什么叫光伏限发、怎样估计未限发功率、怎样识别逆变器电压响应”提供真实项目依据和可复用基线。
