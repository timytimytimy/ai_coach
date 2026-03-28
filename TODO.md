# TODO

- [ ] 将后端人体姿态方案从 `MediaPipe Pose` 迁移到 `RTMPose` 这类 `top-down` 单人姿态方案
  - 原因：当前力量举场景存在明显遮挡，`MediaPipe Pose` 在多人与杠铃架遮挡时稳定性不足，rep 中后段容易丢失或误跟其他人
  - 目标：通过 `person detector + RTMPose` 提升试举者锁定稳定性、遮挡鲁棒性和后续姿态特征可信度
  - 前置：先整理一批力量举评估视频，明确 `pose coverage / keypoint stability / issue precision` 的基线指标

- [ ] 重新设计视频分析页的信息布局，减少分析结果对视频画面的遮挡
  - 问题：当前 HUD、姿态开关、分析卡和底部栏叠加后，视频主体被遮挡过多，影响直接看动作和轨迹
  - 目标：以“视频优先”为原则，重新拆分信息层级，只保留必要常驻信息，其余结果改成更轻或可展开的结构
  - 约束：避免重复展示速度信息；问题卡去重；全部使用中文可读文案；每一块只承载一类信息

- [ ] 开始建设后台管理网站，按独立 `admin/` 工作区推进
  - 结构：已预留 `admin/web`、`admin/shared`、`admin/docs`
  - 第一批页面：`/videos`、`/videos/[setId]`、`/jobs`、`/llm-usage`、`/datasets`
  - 目标：支持视频排查、分析回放、任务监控、LLM 成本统计、数据集管理
  - 约束：后台前端和用户端 Flutter 解耦；后台接口单独走 `/v1/admin/*`；优先复用现有 `server/` 数据，不重复造后端
