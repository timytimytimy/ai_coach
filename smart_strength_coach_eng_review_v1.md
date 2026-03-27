# 智能力量训练教练 App（ENG Review v1）

## 0. 目标与验收口径
目标：在 8–10 周内交付 MVP 闭环（录制→分析→建议→下次调整→趋势复盘），并把 AI 迭代变成“可版本化、可回归评测、可灰度发布”的工程流程。

验收口径（MVP）：
- 可用率：满足拍摄门槛后，`>= 85%` 的 set 能输出分析结果
- 一致性：同一视频重复分析，关键指标与评分偏差在阈值内（定义见 §6）
- 降级策略：不可用时只输出“原因+如何拍摄/补录”，不输出结论
- 混合推理：人体关键点与基础指标端侧完成；为保护自训练模型，杠铃检测/轨迹/速度计算在云端完成（返回结构化结果），云端也用于存储/配置/灰度

## 1. 系统拆分（可独立交付的 3 条链路）
- App 链路：训练日志 + 视频录制/回放 + 分析结果展示 + 趋势对比 + 离线缓存
- 端侧分析链路：Pose → 质量门控 → rep 切分 → 特征 → 发现（findings）→ 评分
- Server 链路：用户/设备/日志/计划版本、分析结果存储、规则/阈值配置下发、埋点与灰度

## 2. MVP 范围与里程碑
### Milestone 1（第 1–2 周）：日志与视频
交付：
- `WorkoutDay/ExerciseSet` 数据结构与本地存储
- 视频录制（统一 fps/分辨率）+ 回放 + set 绑定
- 基础 UI：今日训练、动作列表、组详情

### Milestone 2（第 3–5 周）：Pose + 质量门控 + rep 切分 + 技术指标
交付：
- 端侧接入 MediaPipe Pose 或 MoveNet（TFLite）
- 质量门控：侧面/入镜/遮挡/抖动/帧率；输出 `analysis_status`
- rep 切分（先可用版本）：基于髋/肩 y 位移峰谷或（如已具备）杠铃 y 位移
- 每动作 3–5 个基础指标与评分（可解释，见 §5）
- 说明：本 MVP 不做“边录像边实时语音指导”（作为 Phase 2 候选）

### Milestone 3（第 6–8 周）：速度（VBT）+ 疲劳 + 下次调整
交付：
- 标定：杠铃片直径/参考物（一次配置，多次复用）
- 云端杠铃检测：使用自训练 `YOLOv8n` 检测 `杠铃片` 与 `杠铃杆末端`（不在 App 端下发模型）
- 云端杠铃轨迹：检测结果 + 跟踪（Kalman/IOU/ByteTrack 的轻量实现）→ 生成连续轨迹
- 云端速度计算：速度曲线、平均/峰值速度、速度损失（Velocity Loss）
- 疲劳：速度损失 + 近 7 天负荷（sRPE/tonnage）
- 规则化建议：加减重量/组数/停止点（stop set）

### Milestone 4（第 9–10 周）：计划模块与版本化
交付：
- 模板微周期（1–4 周）+ 训练后自动调整 + 版本回滚
- 配置下发：`rule_version/thresholds` 灰度
- 内测工具页：关键点叠加、rep 边界、轨迹调试

## 3. 数据模型（服务端与端侧统一口径）
主键粒度：`rep`（`video_id + set_id + rep_index`），所有分析、评测、趋势围绕 rep 复用。

推荐实体：
- `User`：账号、订阅、偏好
- `AthleteProfile`：身高体重、训练目标、训练天数、器械
- `WorkoutDay`：日期、主观状态（睡眠/酸痛可选）、汇总
- `ExerciseSet`：动作、重量、reps、RPE/RIR、视频引用
- `VideoAsset`：fps、分辨率、时长、拍摄方向、`sha256`（用于幂等/复用）
- `AnalysisJob`：云端 pipeline 任务（queued/running/succeeded/failed，记录失败 stage）
- `FindingEvent`：结构化发现（label/severity/confidence/timeRangeMs/repIndex/metrics）
- `Report`：最终报告（Top3 详细 + 全量问题清单）
- `VbtAnalysis`：速度/轨迹产物（可选子对象，失败时为空）
- `PlanBlock/PlanSession`：计划与版本历史

必须版本字段（用于解释与回归）：
- `pose_model_version`
- `bar_model_version`（YOLOv8n 版本）
- `bar_tracker_version`
- `feature_version`
- `rule_version`
- `llm_prompt_version`（仅当 LLM 参与解释/总结）
- `app_version`

## 4. 分析流水线（混合推理，可控、可测、可降级）
### 4.1 端侧（技术问题与评分，低延迟）
1) `preprocess`：统一帧率/尺寸，抽帧策略（避免全帧高成本）
2) `pose`：输出关键点时序（含置信度）
3) `quality_gate`：侧面/遮挡/抖动/入镜检查 → 决定是否继续
4) `rep_segment`：自动切 rep + 向心/离心分段（v1：使用髋/肩 y 轨迹峰谷）
5) `features`：计算动作指标（角度/时序/稳定性等）
6) `findings`：规则/阈值触发 → 输出结构化 findings
7) `score`：聚合为 set 技术评分与当日趋势指标
8) `explain`（可选）：将结构化 findings 交给 Gemini 做自然语言解释（引用证据）

### 4.2 云端（VBT 速度与疲劳，保护模型）
1) `bar_detect`：YOLOv8n 检测 `杠铃片/杠铃杆末端`（从上传视频抽帧）
2) `bar_track`：跨帧关联并平滑轨迹
3) `bar_quality_gate`：目标可见率/置信度/轨迹跳变检查
4) `rep_segment_refine`：基于杠铃 y 轨迹峰谷细化 rep 与向心/离心边界（与端侧 rep 对齐或覆盖）
5) `velocity`：输出速度曲线、Avg/Peak、Velocity Loss

降级策略：
- 端侧质量门控失败：只输出拍摄改进建议
- 端侧 rep 切分失败：退回 set 级别提示（不做 rep 级结论）
- 云端杠铃检测失败/输出为空/置信度过低：速度模块不可用（仍保留端侧技术评分）
- 云端追踪失败/标定缺失/质量门控失败：速度模块不可用（给出原因与补录/标定建议）

## 5. 三大项首版“问题集”与指标（MVP）
原则：每项先 5 个问题，全部可由关键点/轨迹计算且可输出证据。

### 深蹲（Squat）
- 膝内扣趋势：`knee_valgus_delta_deg`（向心段）
- 前倾变化：`torso_angle_change_deg`
- 杠铃前后漂移：`bar_path_horizontal_drift_cm`（如有杠铃轨迹）
- 髋膝不同步：`hip_knee_timing_ms`
- 向心速度骤降：`concentric_velocity_drop_pct`

### 卧推（Bench Press）
- 前臂不垂直：`forearm_verticality_deg`
- 下放失控：`eccentric_velocity_peak` 或 `eccentric_smoothness`
- 触胸点漂移：`touch_point_drift_cm`
- 向心不均匀：`concentric_velocity_variance`
- 停顿缺失（如需）：`pause_duration_ms`

### 硬拉（Deadlift）
- 早提髋：`hip_rise_vs_shoulder_rise_ratio`
- 杠铃离身：`bar_distance_to_shin_cm`
- 背角度崩：`back_angle_change_deg`
- 起杠位置不佳：`start_hip_height_norm` / `shoulder_bar_offset_cm`
- 锁定路径异常：`lockout_bar_path_deviation_cm`

## 6. 一致性与阈值（回归测试口径）
- 关键指标偏差：同一输入重复跑 3 次，`P95(|delta|)` 低于阈值
- 评分偏差：同一输入重复跑 3 次，评分 `P95(|delta|) <= 5`（0–100 分制）
- findings 稳定性：同一输入的 top findings 重合率 `>= 80%`

（阈值初版可先偏宽，随着金标集扩大再收紧）

## 7. Gemini 使用规范（让 LLM 可控）
- 输入：结构化 `RepFindings` + 指标摘要 + 用户目标 + 当天训练上下文
- 输出：解释（why）+ 证据（metrics/rep/区间）+ 处方（cue/drill）+ 注意事项
- 约束：
  - 必须引用 `evidence.metrics`
  - 不允许凭空新增“看见了某细节”的断言
  - 低置信度时必须输出不确定性与补录指导

## 8. API 草案（v1）
说明：MVP 可以先本地优先，Server 侧以“同步/异步”两种方式兼容。

### 8.1 认证
- `POST /v1/auth/login`（可选，MVP 可先匿名本地）

### 8.2 上传与资源
- `POST /v1/videos`：创建视频资源（返回预签名上传地址）
- `PUT  {presigned_url}`：上传视频
- `POST /v1/videos/{videoId}/finalize`：完成上传，写入元数据（fps、尺寸、hash）

请求示例（finalize）：
```json
{
  "fps": 30,
  "width": 1080,
  "height": 1920,
  "durationMs": 18000,
  "sha256": "...",
  "capture": {"orientation": "portrait", "deviceModel": "iPhone"}
}
```

### 8.3 训练日志
- `POST /v1/workouts`：创建训练日
- `POST /v1/workouts/{workoutId}/sets`：创建 set（绑定动作、重量、reps、RPE、videoId）
- `GET  /v1/workouts?from=YYYY-MM-DD&to=YYYY-MM-DD`

`ExerciseSet` 创建示例：
```json
{
  "exercise": "squat",
  "weightKg": 140,
  "repsPlanned": 5,
  "repsDone": 5,
  "rpe": 8.5,
  "videoId": "vid_..."
}
```

### 8.4 分析结果
- `POST /v1/sets/{setId}/analysis`：上传端侧分析结果（features/findings/segments 的摘要或全量）
- `GET  /v1/sets/{setId}/analysis`：拉取分析结果（用于多端同步与回放）

端侧分析上报示例（摘要版）：
```json
{
  "analysisStatus": "ok",
  "versions": {
    "poseModel": "movenet-v3",
    "barTracker": "cvtrack-v1",
    "feature": "feat-v1",
    "rule": "rule-v1",
    "app": "1.0.0"
  },
  "repSegments": [
    {"repIndex": 0, "startFrame": 12, "endFrame": 95, "concentric": {"startFrame": 54, "endFrame": 95}},
    {"repIndex": 1, "startFrame": 104, "endFrame": 190, "concentric": {"startFrame": 142, "endFrame": 190}}
  ],
  "summaryMetrics": {
    "setScore": 78,
    "velocityLossPct": 18.2
  },
  "findings": [
    {
      "label": "squat_knee_valgus",
      "severity": "medium",
      "evidence": {"repIndex": 1, "tStartMs": 4700, "tEndMs": 5600, "metrics": {"kneeValgusDeltaDeg": 9.4}},
      "cue": "膝盖跟脚尖方向一致，向外推地",
      "drill": "暂停深蹲 2s（底部），轻重量 3x3"
    }
  ]
}
```

### 8.5 配置下发（规则/阈值/灰度）
- `GET /v1/config/analysis`：返回当前用户应使用的 `rule_version` 与阈值

示例：
```json
{
  "ruleVersion": "rule-v1",
  "thresholds": {
    "squat": {"kneeValgusDeltaDeg": 8.0}
  },
  "rollout": {"bucket": 12}
}
```

### 8.6 VBT（速度）云端异步任务（CPU-only）
- `POST /v1/sets/{setId}/vbt-jobs`：创建 VBT 任务（幂等：`videoSha256 + calibration`）
- `GET  /v1/vbt-jobs/{jobId}`：查询任务状态（queued/running/succeeded/failed）
- `GET  /v1/sets/{setId}/vbt`：获取该 set 的 VBT 结果（未完成则返回状态与失败原因）

说明：输入强约束（建议 `30–45s`），且 App 端侧也做转码/压缩，服务端仍统一转码到标准格式后抽帧。

## 9. 埋点与可观测性（MVP 必须）
- `analysis_job_created/analysis_job_finished`：排队时长、运行时长、阶段耗时（transcode/pose/yolo/track/segment/findings/llm_render）
- `analysis_job_failed`：失败原因枚举（video_decode、quality_gate、pose_failed、bar_detect_empty、bar_track_lost、timeout、llm_output_invalid、unknown）
- `user_feedback`：有用/没用/不确定/疼痛（用于主动学习抽样）

## 9.1 性能与容量规划（云端 CPU-only，目标 10 QPS）
- 输入强约束：建议 `30–45s`，超标拒绝或截断
- App 端侧转码/压缩：降低带宽与服务端解码成本
- 服务端统一转码：统一编码与尺寸后再抽帧（避免奇怪编码拖垮 CPU）
- 推理采样：YOLO 检测 `4–6 fps`，中间帧用跟踪补齐轨迹；Pose 可按需抽帧以控成本
- 背压：队列超阈值返回 `429`，任务硬超时（例如 60–120s）后降级
- 幂等与复用：基于 `sha256 + pipeline_versions + calibration` 复用已成功的分析报告

## 10. 任务看板（可直接搬进 Jira）
### Epic A：App（Flutter）
- A1：训练日志数据结构（本地存储）
- A2：视频录制与 set 绑定 + 端侧转码/压缩（30–45s）
- A3：上传与任务状态轮询（analysis-job）
- A4：结果页：Top3 详细 + 全量问题清单（含 mm:ss 区间）+ 失败降级文案
- A5：复训对比（同动作/同重量的对比卡片）
- A6：设置页（标定、目标、训练频率）

### Epic B：规则与报告（共享逻辑/配置）
- B1：FindingEvent schema（label/severity/confidence/timeRange/metrics）
- B2：Top3 排序规则（确定性、同 label 去重）
- B3：LLM 渲染约束（必须引用 timeRange+metrics；失败回退模板）

### Epic C：Server（CPU-only pipeline）
- C1：workouts/sets CRUD
- C2：videos 预签名上传、finalize（sha256）+ 统一转码
- C3：analysis-job API：创建/状态/报告查询（幂等与复用）
- C4：托管队列 + worker：transcode→pose→yolo→track→segment→findings→llm_render
- C5：背压与限流（429）、任务超时（60–120s）、失败降级与可观测性
- C6：config 下发（rule_version/thresholds/灰度）

### Epic D：Data（评测与迭代）
- D1：金标集规范与抽样策略
- D2：回归评测脚本（规则/阈值/一致性）
- D3：主动学习抽样：失败原因/反馈 → 待复核队列 → 每周回归报告

## 11. Phase 2 TODO
- 实时语音指导（录制中实时提示 + 语音播报）：复杂度与成本更高，CPU-only 下需要严格限帧与背压，MVP 先不做