# 两股同种液体混合的衡算假设
来源：MIT OpenCourseWare，10.492《Process Control by Design》，Lecture Notes 1 “Analyzing the Shower Process”，第 3–4 页式 (1-1) 至 (1-5)；https://ocw.mit.edu/courses/10-492-1-integrated-chemical-engineering-topics-i-process-control-by-design-fall-2004/13b3df56fb34060f78da643586a0277e_notes_1_shower.pdf

## 两入口一出口
对无反应、无泄漏且无积累的混合器，出口质量流量 ṁ_out = ṁ_h + ṁ_c。若混合的是同一种液体，并近似认为两股流体的密度和定压比热容相同、无外部热交换，出口温度 T_out = (ṁ_h T_h + ṁ_c T_c)/(ṁ_h + ṁ_c)。

## 适用边界
原讲义的简化例子依赖恒定物性和可忽略的混合容积储能。不同物质、放热混合、显著热损失、相变或物性随温度明显变化时，不能直接使用简单温度加权式；应重新列质量与能量衡算并补齐物性数据。
