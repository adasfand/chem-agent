# 循环返回流与排放流的分配
来源：项目教学整理；参考美国科罗拉多大学 Boulder LearnChemE 的循环排放教学说明：https://learncheme.com/quiz-yourself/interactive-self-study-modules/purge-stream-in-a-system-with-recycle/purge-stream-in-a-system-with-recycle-summary/；流量公式由理想分流推导。

## 分配关系
分流前循环候选流为 S，定义排放比例 p = B/S，则排放 B = pS、返回 R = (1-p)S。当 0 < p < 1 时，R/B = (1-p)/p；均匀单相理想分流时，返回流与排放流组成相同。

## 错误防范
排放比例分母是 S，不是新鲜进料。p = 0 表示无排放，不能再计算 R/B；p = 1 表示全排放且无返回。降低排放可能增加杂质积累，应结合杂质去向判断，而不是单独追求较大的循环流量。
