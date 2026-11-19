# 辅具系列可用性证据与复测排期

这是用于家用辅具体验资料分析的本地工作区。样例资料为合成数据，不代表真实参与者或产品试验结果。工作区包含 Python 3.11+ 命令入口和 JSON 记录，可离线查看与核验。

## 运行

无需安装第三方依赖。设置 `PYTHONPATH=src` 后运行 `python3 -m household-panel-evidence` 可查看工作区版本。运行现有基线检查：`PYTHONPATH=src python3 -m unittest discover -s tests -v`。

## 资料

`data/sample.json` 保存小型合成记录，顶层键分别为 devices, participants, observations, sessions。

`data/two_stores.json` 是两家门店的现场记录。`devices` 是期初样机部件；`component_notices` 提供现场生效时刻与收件时刻，字段只覆盖通知列出的部件。`assignments` 是分派名册，`observations` 以分派号关联实际样机。`contact_notices` 记录额外接触事件，示范也算接触。同意以动作族为单位；`failed` 为观察到的失败，`not_observed` 没有可判断的结果。`study` 中区间置信水平和每组每臂最低观察人数以同一分析人群为准；非劣界是独立完成率差的百分点界。`claim_requests` 是拟刊说明，`slots` 是门店预约，只有 `confirmed` 属于已确认占用。

`data/training_register.json` 保存同一批熟练使用者的交叉分派，以及门店此前发行的卡片台账。`training_enrolments.devices` 的顺序是分派的阶段顺序，`practice.attempt` 在同一个人、动作及阶段内计数，`observations` 是练习阶段结束后的正式观察。`issued_cards.source_observations` 可以引用门店记录或熟练组记录，引用按观察编号；发行登记不是对卡片适用性的证明。

`data/home_followup.json` 保存同批的家庭回访、已发行的家庭使用说明及下一轮候选安排。`visit_plan` 列约定的日期和样机配置、动作同意范围以及计划覆盖的动作，缺回访不代表没有邀请。`observations` 中 `coached` 代表在当次有人提示，即使最后完成，也不是无提示独立操作。`mat` 表示当次实际防滑垫，`none` 是明确没有使用。`corrections` 只更正指定的观察字段。`additional_contacts` 是能追到实际观看动作族的补报，`known` 记录体验组获知的时间。家庭的 `joint` 声明针对同一次指定回访中的整套动作。`return_slots` 中已确认的回访保留位置；`future_sessions` 记录样机及可与之配套的回访位置，同店同一时段的同台资源不可重复用。
