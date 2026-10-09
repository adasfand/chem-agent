# 常见比热单位中的数值等价
来源：项目教学整理，依据 NIST 单位前缀定义及 IUPAC 质量比热容定义；https://www.nist.gov/pml/owm/metric-si-prefixes ，https://goldbook.iupac.org/terms/view/S05800

## 两个前缀同时换算
1 J/(g·K) = 1 kJ/(kg·K) = 1000 J/(kg·K)。第一组数值相同，因为分子从 J 到 kJ、分母从 g 到 kg 同时改变 1000 倍，两个因子相互抵消。

## 错误防范
1 J/(kg·K) 并不等于 1 kJ/(kg·K)。应分别换算分子与分母，最后检查量纲。温差单位 K 与 °C 的数值可以对应，但绝对温度不能由此混用。资料中的单位等价不保证计算接口接受 g 基准的字符串。
