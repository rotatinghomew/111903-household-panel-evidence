# 辅具系列可用性证据与复测排期

这是用于家用辅具体验资料分析的本地工作区。样例资料为合成数据，不代表真实参与者或产品试验结果。工作区包含 Python 3.11+ 命令入口和 JSON 记录，可离线查看与核验。

## 运行

无需安装第三方依赖。设置 `PYTHONPATH=src` 后运行 `python3 -m household-panel-evidence` 可查看工作区版本。运行现有基线检查：`PYTHONPATH=src python3 -m unittest discover -s tests -v`。

## 资料

`data/sample.json` 保存小型合成记录，顶层键分别为 devices, participants, observations, sessions。

`data/two_stores.json` 是两家门店的现场记录。`devices` 是期初样机部件；`component_notices` 提供现场生效时刻与收件时刻，字段只覆盖通知列出的部件。`assignments` 是分派名册，`observations` 以分派号关联实际样机。`contact_notices` 记录额外接触事件，示范也算接触。同意以动作族为单位；`failed` 为观察到的失败，`not_observed` 没有可判断的结果。`study` 中区间置信水平和每组每臂最低观察人数以同一分析人群为准；非劣界是独立完成率差的百分点界。`claim_requests` 是拟刊说明，`slots` 是门店预约，只有 `confirmed` 属于已确认占用。
