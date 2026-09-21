# Paper Reproductions

Clean-room reproductions of research papers, with an emphasis on end-to-end pipelines: data acquisition, preprocessing, experiments, metrics, and figures.

## Tutorials

- [pandapower 入门：把“潮流仿真”理解成一次网络状态计算](tutorials/pandapower_power_flow_intro.ipynb) — 从一个小型 0.4 kV 辐射台区出发，依次理解 bus / load / sgen / storage / runpp / res_*，再衔接 PV 反向潮流、BESS、时间序列 AC 回放和 IEEE 33-bus。

## Reproductions

| Year | Paper | Status |
|---|---|---|
| 2024 | [Conformal Multilayer Perceptron-Based Probabilistic Net-Load Forecasting for Low-Voltage Distribution Systems with Photovoltaic Generation](papers/2024-smartgridcomm-conformal-mlpf/) | Initial reproduction |
| 2025 | [Mamba based adaptive conformal inference for probabilistic short-term load forecasting](papers/2025-kbs-mamba-aci/) | ACI core-method reproduction on SPS-UK |
| 2025 | [Source-network-load-storage collaborated two-stage power dispatch of active distribution network with conditional value-at-risk](papers/2025-ijepes-cvar-adn/) | Method-level CVaR/ESS risk-dispatch reproduction |

Each paper folder separates paper-specified settings from assumptions required when the publication leaves implementation details unspecified.
