# 指定出口浓度反算两股进料比例
来源：项目教学整理；参考美国科罗拉多大学 Boulder LearnChemE 的 Material Balances for a Mixing Process：https://learncheme.com/screencasts/mass-energy-balances/；比例公式由组分守恒推导。

## 反算公式
两股流量 F_1、F_2 的质量分数分别为 w_1、w_2，要得到 w_T，有 F_1w_1+F_2w_2 = (F_1+F_2)w_T。因此 F_2/F_1 = (w_1-w_T)/(w_T-w_2)，也可先给定总流量再解各进料。

## 可行性与防错
要求稳态、无反应、无质量损失且 w_T 严格位于两种进料组成之间才能得到两个正流量。若 w_T = w_2 且 w_1 ≠ w_2，不能把分母为零当成可执行比例。此反算知识不表示当前混合工具自动支持未知进料求解。
