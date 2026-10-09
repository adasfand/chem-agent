# 不反应杂质的稳态排放需求
来源：项目教学整理；参考美国科罗拉多大学 Boulder LearnChemE 的 Purge Stream in a System with Recycle：https://learncheme.com/quiz-yourself/interactive-self-study-modules/purge-stream-in-a-system-with-recycle/purge-stream-in-a-system-with-recycle-summary/；公式为明确假设下的组分守恒。

## 稳态关系
若杂质以新鲜进料 F、质量分数 z_F 进入，仅由排放 B、质量分数 z_B 离开且无反应，则 Fz_F = Bz_B。z_B > 0 时 B = Fz_F/z_B。允许杂质上限 z_max > 0 时，需 B ≥ Fz_F/z_max。

## 条件与防错
此下限只适用于杂质全部留在循环并只由排放移除的模型；产品带走或分离器去除杂质时应增加出口项。若 Fz_F > 0 而无任何杂质出口，不能声称存在稳态。该知识不代表当前工具已具备循环迭代求解。
