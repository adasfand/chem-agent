# 绝对温度与温差
source: 本工程自编教学说明；待业务审阅

绝对摄氏温度换算为开尔文时 T_K = T_degC + 273.15。温差没有该偏移：出口65摄氏度、入口25摄氏度时，delta_T=40 K。绝对25摄氏度对应298.15 K，不能拿298.15作为该过程温差。Pint单位写法：绝对摄氏温度degC，摄氏温差delta_degC；换算函数另外记录absolute_temperature或temperature_difference。
