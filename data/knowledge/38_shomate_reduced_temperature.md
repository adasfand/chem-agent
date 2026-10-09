# Shomate 热容公式的缩放温度
来源：项目教学整理，依据 NIST Chemistry WebBook 水页面的 Shomate 公式；https://webbook.nist.gov/cgi/cbook.cgi?ID=C7732185&Mask=201

## 变量与单位
Shomate 写法 C_p,m° = A + Bt + Ct² + Dt³ + E/t²，其中 t = T(K)/1000，C_p,m° 用 J/(mol·K)。t 是缩放后的温度变量，不能直接把摄氏温度或未除以 1000 的 K 数值代入。

## 错误防范
系数、相态、温区与单位必须从同一数据表取用；标准态摩尔热容不是任意压力下的质量比热容。不可把表中焓公式的 kJ/mol 与热容的 J/(mol·K) 混为一套数值单位。当前后端没有 Shomate 求值工具。
