# 复合单位的括号与乘除顺序
来源：项目教学整理，依据 NIST “SI Unit rules and style conventions checklist”；https://physics.nist.gov/cuu/Units/checklist.html

## 清楚写出分母
质量比热容写为 J/(kg·K) 或 J·kg⁻¹·K⁻¹，避免连续斜杠造成歧义。热负荷量纲检验为 (kg/s) × (kJ/(kg·K)) × K = kJ/s = kW；相同单位应成对消去。

## 错误防范
kg·K/J 是比热容的倒数，不能与 J/(kg·K) 互换。录入数据前先检查括号及量纲，再处理数值；即使数值看似合理，错误的物理量仍会产生错误结果。单位格式建议不表示输入解析器接受所有写法。
