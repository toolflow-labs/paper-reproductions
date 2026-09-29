# Connecticut ESS Virtual Power Plant 数据

本目录保存美国康涅狄格州 **Energy Storage Solutions (ESS)** 项目的公开数据快照，重点用于虚拟电厂（VPP）、分布式储能聚合、可调能力评估和调度研究。

## 目录结构

- `raw/`：从 Connecticut Open Data 官方接口直接下载的数据快照。
- `DATASET.md`：根据实际下载文件自动生成的数据说明，包括字段、行数、文件大小、SHA256、缺失情况和可识别的时间范围。
- `download_and_profile.py`：重新下载官方数据并生成 `DATASET.md` 的脚本。

## 当前收录

1. **ESS Aggregate Loadshape**
   - Connecticut ESS 虚拟电厂内已接入储能的聚合功率时间序列。
   - 官方说明为 15 分钟时间分辨率。
   - 正值表示充电，负值表示向本地负荷或电网放电。
   - 官方数据集 ID：`jjyf-pk6e`。

2. **ESS Enrollment**
   - ESS 项目匿名化后的已批准项目清单。
   - 包含系统规模、成本、参与承包商等申请阶段信息。
   - 官方数据集 ID：`uy2c-bbdw`。

## 为什么值得保留

这套数据和普通家庭负荷/光伏数据不同：它直接包含真实 VPP 储能资源的聚合运行结果，并且配套有项目层面的装机与成本信息。因此可以用于研究：

- 聚合储能的实际可调功率与额定装机规模之间的差异；
- 不同时间尺度下的 VPP 可用容量/灵活性评估；
- 聚合功率预测与不确定性量化；
- 容量承诺、响应可靠性和偏差风险；
- 与 Ausgrid 一类家庭级负荷/光伏数据结合，构造“微观仿真 + 真实聚合数据验证”的实验链路。

## 数据来源

- Aggregate Loadshape: https://catalog.data.gov/dataset/energy-storage-solutions-ess-aggregate-loadshape
- Enrollment: https://catalog.data.gov/dataset/energy-storage-solutions-ess-enrollment
- ESS Performance Report: https://energystoragect.com/ess-performance-report/

> 注意：官方明确说明遥测历史数据仍会持续进行质量控制，过去数据可能被修订。因此本仓库保存的是一次固定快照；复现实验时应记录文件 SHA256，避免不同时间下载的数据发生静默变化。
