# 辅具系列可用性证据与复测排期

这是用于家用辅具体验资料分析的本地工作区。样例资料为合成数据，不代表真实参与者或产品试验结果。工作区包含 Python 3.11+ 命令入口和 JSON 记录，可离线查看与核验。

## 运行

无需安装第三方依赖。设置 `PYTHONPATH=src` 后使用：

```sh
PYTHONPATH=src python3 -m household-panel-evidence            # 完整报告
PYTHONPATH=src python3 -m household-panel-evidence store      # 门店首用（按原分派）
PYTHONPATH=src python3 -m household-panel-evidence trained    # 熟练交叉试验
PYTHONPATH=src python3 -m household-panel-evidence home       # 家庭回访与说明卡
PYTHONPATH=src python3 -m household-panel-evidence schedule   # 下一轮排期对照
PYTHONPATH=src python3 -m household-panel-evidence gaps       # 仍开放的证据空白
PYTHONPATH=src python3 -m household-panel-evidence report --json   # 机器可读输出
```

`--data-dir` 可指定其他数据目录。运行基线与规则检查：`PYTHONPATH=src python3 -m unittest discover -s tests -v`。

下一轮判定：把实际到场、预演、完成情况与补报接触写回对应 JSON 后重跑即可，无需重做全部试验。

## 判定规则

- 首用按动作族判定：示范、旁观、训练后退出都算已接触，与是否见过某型号无关；同一受试者不能填两条同族首用对照。
- 首用独立完成率按原分派评估；实操换组不改分派。实际部件以换件通知生效时刻重算，与登记或分派不一致的观察另列，不为未充分观察的新部件背书。
- 拒绝观察、没有完成记录、实际操作失败分列；撤回未来参与不抹去仍允许使用的历史观察。
- 熟练比较只纳入完成规定练习量的观察，保留个人内阶段次序；第二期迁移不可分离时，配对差不用于宣称新部件更好，只保留第一期同类人群对照。
- 声明按部件 × 动作 × 首用/熟练 × 能力分层核算；某层证据不足（每组每臂少于 2 个分派）就保留缺口，不以总体均值或其他动作补。换件不影响的动作，证据可沿用到未变化的操作条件。
- 家庭声明按户核算：有人提示不算无提示独立，垫配置以更正后实际为准，超出约定窗口不计；有授权未得结果与未获授权分列；同一人两次观察不算两户；联合声明要求同一户同一次回访整套完成，不可跨户拼合。
- 已发卡保留发出时依据；发现换件早于登记或漏记接触后，按真实部件与接触史重核，标出停止用于新销售的卡与不受影响的范围。引用遗漏范围内已观察住户/分派（尤其失败）即为依据缺陷。
- 已确认活动保留时段、设备与顺序；补报接触使志愿者失去首用资格的位置列为待协商，不算补足缺口，也不回到可分配池。候选安排挤占已确认活动、或对照只能落到不同能力人群时，不能按预期人头计为有效。家庭环境类声明即使多做店内试验也得不到证据。

## 资料

`data/sample.json` 保存小型合成记录，顶层键分别为 devices, participants, observations, sessions。

`data/two_stores.json` 是两家门店的现场记录。`devices` 是期初样机部件；`component_notices` 提供现场生效时刻与收件时刻，字段只覆盖通知列出的部件。`assignments` 是分派名册，`observations` 以分派号关联实际样机。`contact_notices` 记录额外接触事件，示范也算接触。同意以动作族为单位；`failed` 为观察到的失败，`not_observed` 没有可判断的结果。`study` 中区间置信水平和每组每臂最低观察人数以同一分析人群为准；非劣界是独立完成率差的百分点界。`claim_requests` 是拟刊说明，`slots` 是门店预约，只有 `confirmed` 属于已确认占用。

`data/training_register.json` 保存同一批熟练使用者的交叉分派，以及门店此前发行的卡片台账。`training_enrolments.devices` 的顺序是分派的阶段顺序，`practice.attempt` 在同一个人、动作及阶段内计数，`observations` 是练习阶段结束后的正式观察。`issued_cards.source_observations` 可以引用门店记录或熟练组记录，引用按观察编号；发行登记不是对卡片适用性的证明。

`data/home_followup.json` 保存同批的家庭回访、已发行的家庭使用说明及下一轮候选安排。`visit_plan` 列约定的日期和样机配置、动作同意范围以及计划覆盖的动作，缺回访不代表没有邀请。`observations` 中 `coached` 代表在当次有人提示，即使最后完成，也不是无提示独立操作。`mat` 表示当次实际防滑垫，`none` 是明确没有使用。`corrections` 只更正指定的观察字段。`additional_contacts` 是能追到实际观看动作族的补报，`known` 记录体验组获知的时间。家庭的 `joint` 声明针对同一次指定回访中的整套动作。`return_slots` 中已确认的回访保留位置；`future_sessions` 记录样机及可与之配套的回访位置，同店同一时段的同台资源不可重复用。
