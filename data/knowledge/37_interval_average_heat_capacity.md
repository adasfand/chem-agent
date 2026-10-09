# 温区平均比热不是任意中点值
来源：项目教学整理，依据 Cantera 官方物种热力学模型的热容积分关系；https://www.cantera.org/stable/reference/thermo/species-thermo.html

## 定义温区平均值
同一适用路径且 T_out ≠ T_in 时，c_p,avg = [∫ c_p(T) dT]/(T_out − T_in)，故 Δh = c_p,avg ΔT。若 c_p(T) = a + bT 且整个区间有效，该平均值恰等于两端比热的算术平均。

## 错误防范
一般非线性热容不能用中点比热或两端平均代替精确温区平均。ΔT = 0 时上述比值不能直接除零。需要真实物性关联和适用区间；软件接受一个恒比热值并不意味着它已验证这个平均值的来源。
