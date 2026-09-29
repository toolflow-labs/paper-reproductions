# Connecticut ESS VPP 数据说明

- 本次下载时间（UTC）：`2026-09-29T00:26:25.248602+00:00`
- 数据来源：Connecticut Open Data / Data.gov 官方公开数据。
- 说明：官方会持续对遥测历史数据做质量控制并可能修订，因此本目录应视为固定快照。

## ESS Aggregate Loadshape

- 官方数据集 ID：`jjyf-pk6e`
- 本地文件：`raw/ess_aggregate_loadshape.csv`
- 官方页面：https://catalog.data.gov/dataset/energy-storage-solutions-ess-aggregate-loadshape
- 官方 CSV：https://data.ct.gov/api/v3/views/jjyf-pk6e/export.csv?accessType=DOWNLOAD
- 官方说明：15 分钟聚合储能功率时间序列；正值表示充电，负值表示向本地负荷或电网放电。
- 数据行数（不含表头）：**234,633**
- 字段数：**4**
- 文件大小：**14.03 MiB**
- SHA256：`ac3d6b9abb9f8ddffa6729e87e166f861eb46eb260e1be1c5013cb885334d84e`

### 可识别时间范围

- `Date`：2022-09-15 00:00:00 ～ 2026-09-28 00:00:00

### 字段概览

| 字段 | 缺失数 | 缺失率 | 示例值 |
|---|---:|---:|---|
| `Date` | 0 | 0.00% | 07/10/2025 / 07/10/2025 / 07/10/2025 |
| `DateTime` | 0 | 0.00% | 2025 Jul 10 01:30:00 AM / 2025 Jul 10 01:30:00 AM / 2025 Jul 10 01:45:00 AM |
| `Aggregate Loadshape (kW)` | 0 | 0.00% | 41.06666666667 / 42.01162333333 / 31.70763666667 |
| `Sector` | 0 | 0.00% | C&I / Residential / Residential |

## ESS Enrollment

- 官方数据集 ID：`uy2c-bbdw`
- 本地文件：`raw/ess_enrollment.csv`
- 官方页面：https://catalog.data.gov/dataset/energy-storage-solutions-ess-enrollment
- 官方 CSV：https://data.ct.gov/api/v3/views/uy2c-bbdw/export.csv?accessType=DOWNLOAD
- 官方说明：匿名化的 ESS 已批准项目清单，包含系统规模、成本、参与承包商等申请信息。
- 数据行数（不含表头）：**1,873**
- 字段数：**111**
- 文件大小：**2.02 MiB**
- SHA256：`be147923d533ae6342b539395d7521c8b22d3ae8c559b55aaa97eef13dd6228a`

### 可识别时间范围

- `Application Date`：2022-01-14 00:00:00 ～ 2026-08-31 00:00:00
- `Submitted Date`：2022-01-14 00:00:00 ～ 2026-08-31 00:00:00
- `Approval Date`：2022-05-09 00:00:00 ～ 2026-08-31 00:00:00
- `Energize Date`：2018-02-21 00:00:00 ～ 2026-08-27 00:00:00
- `Completed Date`：2022-09-15 00:00:00 ～ 2026-07-16 00:00:00

### 字段概览

| 字段 | 缺失数 | 缺失率 | 示例值 |
|---|---:|---:|---|
| `Project Name` | 0 | 0.00% | ESS-03332 / ESS-03333 / ESS-03335 |
| `Project Counter` | 0 | 0.00% | 1 / 1 / 1 |
| `Stage` | 0 | 0.00% | Application Submitted / Application Submitted / Application Submitted |
| `Project Status` | 0 | 0.00% | Submitted / Submitted / Submitted |
| `Host City` | 1 | 0.05% | Bethel / Newtown / Bristol |
| `Host Zip` | 1 | 0.05% | 06801 / 06482 / 06010 |
| `Latitude` | 111 | 5.93% | 41.375638 / 41.430588 / 41.712966 |
| `Longitude` | 111 | 5.93% | -73.403176 / -73.31301 / -72.932547 |
| `Census Tract Code` | 111 | 5.93% | 200200.0 / 230100.0 / 405900.0 |
| `County` | 116 | 6.19% | Western Connecticut Planning Region / Western Connecticut Planning Region / Naugatuck Valley Planning Region |
| `COG Name` | 1 | 0.05% | Western CT / Western CT / Naugatuck Valley |
| `State House District` | 111 | 5.93% | State House District 2 / State House District 106 / State House District 77 |
| `State Senate District` | 111 | 5.93% | State Senate District 28 / State Senate District 28 / State Senate District 31 |
| `Congressional District` | 111 | 5.93% | CT5 / CT5 / CT1 |
| `Opportunity Zone` | 1,849 | 98.72% | Eligible / Eligible / Eligible |
| `USDA Rurality` | 1 | 0.05% | Eligible / Eligible / Not Eligible |
| `Cost Membership` | 1 | 0.05% | true / true / false |
| `Vintage MSA AMI Band` | 132 | 7.05% | 120+ / 120+ / 100-120 |
| `Vintage MSA SMI Band` | 132 | 7.05% | 120+ / 120+ / 80-100 |
| `Vintage MSA CRA AMI Band` | 132 | 7.05% | 80-120 / 120+ / 120+ |
| `Vintage MSA CRA SMI Band` | 132 | 7.05% | 80-120 / 120+ / 120+ |
| `Vintage Distressed` | 38 | 2.03% | Not Distressed / Not Distressed / Distressed |
| `Vintage EJ Poverty Level` | 0 | 0.00% | false / false / false |
| `Vintage Vulnerable Community` | 0 | 0.00% | Not Vulnerable / Not Vulnerable / Not Vulnerable |
| `Vulnerable Community Category` | 0 | 0.00% | None / None / None |
| `VintageEJCommunity` | 0 | 0.00% | Not EJ Community / Not EJ Community / Not EJ Community |
| `VintageJustice40` | 0 | 0.00% | Not Justice 40 / Not Justice 40 / Not Justice 40 |
| `CRA Qualified` | 0 | 0.00% | Not CRA / Not CRA / Not CRA |
| `LMI Qualified` | 0 | 0.00% | Not LMI / Not LMI / Not LMI |
| `CRA Qualified - SMI` | 0 | 0.00% | Not CRA / Not CRA / Not CRA |
| `LMI Qualified - SMI` | 0 | 0.00% | Not LMI / Not LMI / Not LMI |
| `Contractor Name` | 11 | 0.59% | Adam Golka DBA Phase Out Electric / Adam Golka DBA Phase Out Electric / Aegis Solar Energy |
| `Eligible System Owner` | 376 | 20.07% | Customer / Customer / Customer |
| `Third Party Owner` | 380 | 20.29% | Home Owner / Home Owner / Home Owner |
| `EDC` | 0 | 0.00% | Eversource / Eversource / Eversource |
| `Utility Rate Code` | 510 | 27.23% | Rate 1 / Rate 1 / Rate R |
| `Sector` | 0 | 0.00% | Residential / Residential / Residential |
| `Customer Type` | 0 | 0.00% | 1-4 Residential Units / 1-4 Residential Units / 1-4 Residential Units |
| `Customer Class` | 1,812 | 96.74% | Large C&I / Large C&I / Large C&I |
| `NAICS Code` | 1,811 | 96.69% | "61	Educational Services" / "54	Professional, Scientific, and Technical Services" / "31-33	Manufacturing" |
| `Resi Customer Type` | 0 | 0.00% | Resi Standard / Resi Standard / Resi Underserved |
| `Residential Sector` | 61 | 3.26% | 1-4 Units / 1-4 Units / 1-4 Units |
| `Priority Customer Indicator` | 0 | 0.00% | false / false / true |
| `Priority Customer` | 0 | 0.00% | N/A / N/A / Underserved Community |
| `Critical Facilities` | 1,808 | 96.53% | No / No / No |
| `Grid Edge` | 187 | 9.98% | true / true / false |
| `Small Business` | 0 | 0.00% | false / false / false |
| `Multifamily Affordable Housing` | 1,867 | 99.68% | No / No / No |
| `Low Income` | 98 | 5.23% | Yes / No / No |
| `Underserved` | 1 | 0.05% | No / No / Yes |
| `FCM Participant` | 1,831 | 97.76% | No / No / No |
| `On-Site Fossil Fuel Replacement` | 1,811 | 96.69% | No / No / No |
| `Pre-Existing Storage System` | 41 | 2.19% | true / true / true |
| `Program Dispatch` | 0 | 0.00% | Only Active / Only Active / Only Active |
| `Total System Power [kW]` | 13 | 0.69% | 10 / 16 / 16 |
| `Total System Power (MW)` | 0 | 0.00% | 0 / 0 / 0 |
| `Total System Power (Watts)` | 0 | 0.00% | 0 / 0 / 0 |
| `Total System Energy Capacity [kWh]` | 13 | 0.69% | 27 / 48 / 48 |
| `Total System Max Cont Discharge Rate kW` | 29 | 1.55% | 0.0 / 97.3 / 97.3 |
| `Total System Quantity` | 0 | 0.00% | 0 / 0 / 0 |
| `Annual Peak Demand (kW)` | 1,811 | 96.69% | 1,920 / 3,508 / 2,004 |
| `Installed Location` | 513 | 27.39% | Outdoors / Outdoors / Outdoors |
| `System Pairing Original` | 20 | 1.07% | Standalone (not paired with any generating source) / Paired with new on-site generation / Paired with new on-site generation |
| `System Pairing` | 0 | 0.00% | N/A / N/A / N/A |
| `Paired PV System Size` | 532 | 28.40% | 4.0 / 11.0 / 16.0 |
| `Up Front Incentive` | 532 | 28.40% | $6,240 / $6,240 / $6,750 |
| `Batteries/Storage Cost` | 6 | 0.32% | $0 / $0 / $0 |
| `Engineering and Design Cost` | 44 | 2.35% | $0 / $0 / $0 |
| `Installation Labor Cost` | 26 | 1.39% | $0 / $0 / $0 |
| `Interconnection Cost` | 42 | 2.24% | $0 / $0 / $0 |
| `Inverter Cost` | 20 | 1.07% | $0 / $0 / $0 |
| `Monitoring Cost` | 19 | 1.01% | $0 / $0 / $0 |
| `Permitting Cost` | 43 | 2.30% | $0 / $0 / $0 |
| `Solar PV/inverter(s) Cost` | 26 | 1.39% | $0 / $0 / $0 |
| `Balance of System Cost` | 47 | 2.51% | $0 / $0 / $0 |
| `Total Battery Cost` | 0 | 0.00% | $0 / $0 / $0 |
| `Total Solar PV Cost` | 694 | 37.05% | $13,000 / $27,425 / $44,068 |
| `Total Contract Price` | 0 | 0.00% | $0 / $0 / $0 |
| `Gross Cost` | 0 | 0.00% | $0 / $0 / $0 |
| `Total Capital Deployed` | 0 | 0.00% | $0 / $0 / $0 |
| `CGB Incentive Amount` | 532 | 28.40% | $6,240 / $6,240 / $6,750 |
| `Total CGB Investment` | 532 | 28.40% | $6,240 / $6,240 / $6,750 |
| `Total Private Investment` | 0 | 0.00% | $0 / $0 / $0 |
| `Total Investment` | 0 | 0.00% | $0 / $0 / $0 |
| `Incentive Step` | 72 | 3.84% | 5 / 5 / 1.2 |
| `Created Date` | 0 | 0.00% | 2025 Dec 05 09:38:45 PM / 2025 Dec 05 09:38:45 PM / 2025 Dec 05 09:38:45 PM |
| `Application Date` | 23 | 1.23% | 12/05/2025 / 08/06/2026 / 08/11/2026 |
| `Submitted Date` | 1 | 0.05% | 06/26/2025 / 06/26/2025 / 07/01/2025 |
| `Approval Date` | 54 | 2.88% | 03/05/2026 / 08/12/2026 / 08/24/2026 |
| `Energize Date` | 476 | 25.41% | 03/12/2026 / 09/10/2025 / 07/30/2025 |
| `Completed Date` | 740 | 39.51% | 07/16/2026 / 03/05/2026 / 11/04/2025 |
| `IndividualIncomeTaxesGenerated` | 61 | 3.26% | $0 / $580.36 / $399.61 |
| `CorporateTaxesGenerated` | 61 | 3.26% | $0 / $872.16 / $600.53 |
| `SalesTaxesGenerated` | 61 | 3.26% | $0 / $0 / $0 |
| `TotalTaxRevenueGenerated` | 0 | 0.00% | $0 / $0 / $0 |
| `Direct Jobs` | 61 | 3.26% | 0 / 0.1 / 0.07 |
| `Indirect and Induced Jobs` | 61 | 3.26% | 0 / 0.12 / 0.09 |
| `Total Jobs` | 0 | 0.00% | 0 / 0 / 0 |
| `ExpectedUsefulLife` | 0 | 0.00% | 25 / 25 / 25 |
| `kWh / kW` | 0 | 0.00% | 0 / 0 / 0 |
| `Cost / kW` | 0 | 0.00% | $0 / $0 / $0 |
| `Cost / kWh` | 0 | 0.00% | $0 / $0 / $0 |
| `Hybrid Sector Project` | 203 | 10.84% | false / false / false |
| `Residential Proportion Percentage Rate` | 1,871 | 99.89% | 48 / 48 |
| `Commercial Proportion Percentage Rate` | 0 | 0.00% | 0 / 0 / 0 |
| `Number of Residential Units` | 1,868 | 99.73% | 1 / 1 / 1 |
| `Commercial Incentive for Hybrid Project` | 1,871 | 99.89% | $955,500 / $955,500 |
| `Residential Incentive for Hybrid Project` | 1,871 | 99.89% | $882,000 / $882,000 |
| `Transfer from Connected Solutions` | 238 | 12.71% | No / No / No |
| `Combined BESS Models` | 16 | 0.85% | Tesla Inc. Powerwall 2 - 2 Modules [27 kWh] [27 kWh];Tesla Inc. Powerwall 2 [5 kW] / EG4 Electronics WallMount All Weather 314Ah [16 kWh];EG4 Electronics FlexBOSS21 [12 kW] / EG4 Electronics WallMount All Weather 314Ah [16 kWh];EG4 Electronics FlexBOSS21 [12 kW] |
| `Last Updated` | 0 | 0.00% | 2026 Jul 11 12:00:17 PM / 2026 Jul 11 12:00:17 PM / 2026 Jul 11 12:00:17 PM |

## 使用注意

1. **聚合负荷曲线不是单户 Powerwall 数据。** 它是 ESS VPP 内储能资源的聚合功率表现，不能直接反推出单个家庭的 SOC 或控制策略。
2. **功率正负号按官方定义解释。** 正值为充电，负值为向本地负荷或电网放电。
3. **Enrollment 是匿名化项目清单。** 不应假设它能与聚合曲线逐户一一关联，除非后续官方文档明确给出连接键。
4. **历史数据可能被回溯修订。** 论文实验应固定使用本目录快照并在实验记录中引用 SHA256。
5. **适合的论文问题**包括 VPP 可调容量评估、聚合功率预测、响应可靠性、容量承诺偏差、灵活性区间/概率建模，以及与合成微观储能群的交叉验证。
