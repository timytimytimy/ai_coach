# 力量举技术筛查手册 v2（App 结构化版）

> 用途：供视频分析 App 的融合层、规则层、前端问题卡、历史统计、训练建议统一使用  
> 语料来源：`/Users/liumiao/.openclaw/workspace/bilibili_powerlifting_coaches/subtitles` 中的力量举教学字幕语料  
> 设计目标：比通用教练笔记更结构化，比纯 taxonomy 更可解释

---

## 0. 语料覆盖概览

- 硬拉字幕：`127` 份
- 卧推字幕：`97` 份
- 深蹲字幕：`103` 份
- 相扑硬拉字幕：`23` 份
- 训练计划 / 其他 / 杂项：其余语料可作为辅助上下文，但不作为主 taxonomy 依据

### 0.1 当前高频主题

深蹲高频：
- 重心
- 骨盆 / 眨眼
- 离心控制
- 足底支撑
- 抬臀

卧推高频：
- 桥
- 肩胛
- 手腕
- 下肢支撑
- 左右不平衡

硬拉高频：
- 启动
- 张力
- 锁定
- 重心
- 抬臀 / 飘杠

### 0.2 对 App 的意义

- 深蹲：更适合做 `速度 / 路径 / 底部稳定性 / 站姿结构` 四层问题拆分
- 卧推：更适合做 `桥与张力系统 / 手腕承重线 / 左右对称 / 触胸与路径` 四层问题拆分
- 硬拉：更适合做 `启动机制 / 张力预设 / 杠路径 / 锁定姿态` 四层问题拆分

---

## 1. 使用原则

### 1.1 这份手册解决什么问题
- 给 LLM 一个稳定的技术分析框架
- 给后端一个稳定的 issue taxonomy
- 给前端一个可展示、可跳转、可做历史统计的问题字典

### 1.2 输出原则
- 同一条视频最多输出 `1-3` 个主要问题
- 问题必须绑定证据
- 没有足够证据时，允许“不下结论”
- 杠铃轨迹 / VBT 优先于 pose
- pose 只作为辅助证据，不单独决定结论

### 1.3 推荐字段
每个问题建议包含：
- `code`
- `title`
- `lift`
- `phase`
- `severity`
- `summary`
- `screeningPoints`
- `visualSignals`
- `kinematicSignals`
- `negativeChecks`
- `cue`
- `drills`
- `loadAdjustmentHint`

---

## 2. 通用严重度定义

### low
- 有趋势，但对当前动作完成影响有限
- 更适合作为“次要观察”

### medium
- 明确影响动作质量、稳定性或效率
- 适合作为主要问题

### high
- 明显影响安全、结构稳定或大重量完成
- 应优先处理，必要时建议降重

---

## 3. 深蹲 Taxonomy

## 3.1 `slow_concentric_speed`
- `title`: 起立速度偏慢
- `phase`: ascent
- `severity`: medium
- `summary`: 向心整体速度偏慢，起立节奏不够干脆，完成 rep 的效率下降。
- `screeningPoints`:
  - 观察起立阶段是否明显拖长
  - 观察最后几次是否比前几次慢很多
  - 观察是否存在起立“顶不上去但也没彻底卡住”的状态
- `visualSignals`:
  - 起立整体速度偏慢
  - 最后几次起立更费力
  - 站起过程时间明显变长
- `kinematicSignals`:
  - `avgVelocityMps` 偏低
  - `durationMs` 偏长
  - `velocityLossPct` 升高
- `negativeChecks`:
  - 如果只是中段某一小段减速，更优先归为 `mid_ascent_sticking_point`
  - 如果主要问题是路径跑偏，不要只归因速度慢
- `cue`: 起立时保持持续加速，不要只在底部发力一下就泄掉
- `drills`:
  - pause squat
  - squat doubles
- `loadAdjustmentHint`: 速度明显低于本组前几次时，下一组可考虑降重 2.5% 到 5%

## 3.2 `mid_ascent_sticking_point`
- `title`: 起立中段卡顿
- `phase`: ascent
- `severity`: medium
- `summary`: 出底后到中段出现明显减速或短暂停滞，说明发力连续性不足。
- `screeningPoints`:
  - 观察底部刚起立后是否在中段“卡一下”
  - 观察是否存在两段式发力
  - 观察是否需要明显二次加速才能完成
- `visualSignals`:
  - 杠铃上升不连贯
  - 中段速度明显掉下来
  - 出底后有“卡住再上”的感觉
- `kinematicSignals`:
  - `stickingRegion.durationMs` 较长
  - 中段速度显著低于该 rep 其余区间
- `negativeChecks`:
  - 如果从底部到锁定全程都慢，更优先归为 `slow_concentric_speed`
- `cue`: 出底后继续推地，不要在中段泄力
- `drills`:
  - pause squat
  - tempo squat
- `loadAdjustmentHint`: 先保持当前重量，把中段连续发力练顺

## 3.3 `rep_to_rep_velocity_drop`
- `title`: 后续重复明显掉速
- `phase`: set_level
- `severity`: medium
- `summary`: 后续 reps 明显比前面慢，说明疲劳下动作质量下降。
- `screeningPoints`:
  - 观察第 1 次与最后 1-2 次的起立节奏差异
  - 观察后段重复是否明显更吃力
- `visualSignals`:
  - 前几次还顺，后几次明显慢
  - 组内后段动作完成质量下降
- `kinematicSignals`:
  - `velocityLossPct` 升高
  - 后段 `durationMs` 显著增加
  - 最快和最慢 rep 差异明显
- `negativeChecks`:
  - 如果只有最后一次单独异常，优先作为单 rep 问题
- `cue`: 每次重复都按同样节奏发力，不要越做越散
- `drills`:
  - tempo squat
  - pause squat
- `loadAdjustmentHint`: 如果速度损失过快，优先减少组容量或提前止组

## 3.4 `bar_path_drift`
- `title`: 杠铃路径漂移
- `phase`: ascent
- `severity`: medium
- `summary`: 杠铃没有沿相对稳定的垂直路径运行，说明力线管理不足。
- `screeningPoints`:
  - 观察杠铃是否始终接近中足垂线
  - 观察起立中是否向前跑
- `visualSignals`:
  - 杠铃路径明显前漂或横向漂移
  - 起立时路径不稳定
- `kinematicSignals`:
  - `barPathDriftCm` 偏大
- `negativeChecks`:
  - 如果漂移很小但速度慢，优先归因为速度问题
- `cue`: 全程把杠稳在中足上方，别让杠往前跑
- `drills`:
  - tempo squat
  - pin squat
- `loadAdjustmentHint`: 路径明显失控时优先重复当前重量，不急着加重

## 3.5 `torso_position_shift`
- `title`: 起立时躯干角度变化偏大
- `phase`: ascent
- `severity`: low_to_medium
- `summary`: 起立时躯干姿态变化过大，说明胸背稳定或髋膝协同存在问题。
- `screeningPoints`:
  - 观察起立初段胸口是否掉下去
  - 观察背角是否突然变化
- `visualSignals`:
  - 胸背姿态不稳定
  - 起立时更像先抬臀再站起
- `kinematicSignals`:
  - `torsoLeanDeltaDeg` 偏大
- `negativeChecks`:
  - 如果视频侧面遮挡严重，pose 证据不足时不应高置信输出
- `cue`: 先把胸口和背顶住杠，再让髋膝一起展开
- `drills`:
  - pause squat
  - tempo squat
- `loadAdjustmentHint`: 先稳住姿态，再考虑提高负荷

## 3.6 `pelvic_wink`
- `title`: 底部骨盆眨眼
- `phase`: bottom
- `severity`: medium
- `summary`: 深蹲底部出现骨盆后倾与腰椎曲度变化，底部稳定性不足。
- `screeningPoints`:
  - 观察离心到底部的骨盆位置
  - 观察向心初段骨盆和腰椎曲度是否明显变化
- `visualSignals`:
  - 底部骨盆后倾
  - 腰椎曲度不稳定
- `kinematicSignals`:
  - 当前项目暂无高置信直接量化，优先以视觉证据 + 侧面姿态辅助判断
- `negativeChecks`:
  - 角度不对、遮挡重、衣物宽松时不应高置信下结论
- `cue`: 下蹲到底时保持骨盆和腰椎中立，不要为了更深而丢掉稳定
- `drills`:
  - pause squat
  - tempo squat
- `loadAdjustmentHint`: 先降一点重量，确保底部稳定后再回升

## 3.7 `unstable_foot_pressure`
- `title`: 足底重心不稳
- `phase`: descent_and_ascent
- `severity`: low_to_medium
- `summary`: 足底重心前后乱飘，导致深蹲路径和发力不稳定。
- `screeningPoints`:
  - 观察脚跟、前脚掌是否频繁切换
  - 观察是否出现明显前跪
- `visualSignals`:
  - 下蹲或起立时重心来回跑
  - 整体看起来“脚底没踩实”
- `kinematicSignals`:
  - 当前项目暂无直接量化，优先结合路径漂移和下放控制一起判断
- `negativeChecks`:
  - 单纯上身前倾不等于足底重心不稳
- `cue`: 全脚掌均匀受力，让重心稳稳压在中足
- `drills`:
  - slow eccentric squat
  - box squat
- `loadAdjustmentHint`: 以稳定感优先，不急着追重量

## 3.8 `stance_setup_mismatch`
- `title`: 站距站姿不匹配
- `phase`: setup
- `severity`: low_to_medium
- `summary`: 站距、脚尖角度或杠下站位不适合当前髋结构与发力模式。
- `screeningPoints`:
  - 观察站距是否过宽/过窄
  - 观察脚尖方向和下蹲轨迹是否匹配
- `visualSignals`:
  - 每个细节都对但动作整体就是别扭
  - 下蹲过程髋膝联动不顺
- `kinematicSignals`:
  - 当前项目暂无直接量化，更多是结构性解释问题
- `negativeChecks`:
  - 不要在单条视频上高置信输出，通常需要多次重复共同确认
- `cue`: 先找到最自然、最稳定的站距和脚尖方向，再去追求更大重量
- `drills`:
  - tempo squat
  - high bar squat
- `loadAdjustmentHint`: 保持中等重量，先找动作模板

## 3.9 `uncontrolled_descent`
- `title`: 下放速度失控
- `phase`: descent
- `severity`: low_to_medium
- `summary`: 离心过快或缺乏控制，导致底部反弹和起立质量下降。
- `screeningPoints`:
  - 观察下放速度是否明显快于可控制范围
  - 观察底部是否因为下放过快而失去稳定
- `visualSignals`:
  - 下放太快
  - 底部接不上力
- `kinematicSignals`:
  - 当前项目暂无单独离心速度稳定量化，优先结合底部控制和后续 sticking 判断
- `negativeChecks`:
  - 离心快但控制住了，不应机械判错
- `cue`: 下放保持控制，让身体带着张力到底
- `drills`:
  - slow eccentric squat
  - pause squat
- `loadAdjustmentHint`: 先把离心控制住，再考虑做更激进的反弹

## 3.10 `hip_shoot_in_squat`
- `title`: 深蹲起立先抬臀
- `phase`: ascent
- `severity`: medium
- `summary`: 起立初段臀部先明显上抬、胸口掉下去，动作更像早安式起立，说明髋膝协同和胸背稳定不足。
- `screeningPoints`:
  - 观察出底后臀位是否先明显上升
  - 观察胸口是否在同一时间掉下去
  - 观察是否伴随起立节奏断裂和中段卡顿
- `visualSignals`:
  - 起立像“先抬屁股再站起”
  - 躯干前倾突然变大
  - 胸背姿态被杠压垮
- `kinematicSignals`:
  - `torsoLeanDeltaDeg` 偏大
  - 常与 `mid_ascent_sticking_point`、`slow_concentric_speed` 同时出现
- `negativeChecks`:
  - 低杆深蹲允许一定前倾，不应把所有前倾都判成抬臀
  - 如果主要只是全程偏慢，更优先归为速度问题
- `cue`: 出底时先把胸口和背撑住，让髋膝一起向上展开
- `drills`:
  - pause squat
  - box squat
- `loadAdjustmentHint`: 抬臀明显时先稳住当前重量，不急着继续加重

## 3.11 `forward_weight_shift`
- `title`: 深蹲重心前跑
- `phase`: descent_and_ascent
- `severity`: medium
- `summary`: 离心或起立过程中整体重心压到前脚掌，导致路径、膝压和节奏都变差。
- `screeningPoints`:
  - 观察重心是否持续往前脚掌跑
  - 观察是否伴随前跪、胸口下掉或杠铃前漂
  - 观察底部后是否更难回到中足上方
- `visualSignals`:
  - 人和杠整体往前栽
  - 起立时像在追杠
  - 前脚掌压力过重
- `kinematicSignals`:
  - 常与 `bar_path_drift`、`unstable_foot_pressure` 同时出现
  - 可能伴随 `barPathDriftCm` 增大
- `negativeChecks`:
  - 不要把单次轻微前移高置信判错
  - 高杆和低杆的体态差异不等于重心前跑
- `cue`: 让人和杠一起稳在中足上方，不要把压力一路送到前脚掌
- `drills`:
  - box squat
  - slow eccentric squat
- `loadAdjustmentHint`: 如果重心明显前跑，优先重复中等重量把力线找回来

---

## 4. 卧推 Taxonomy

## 4.1 `bench_head_lift`
- `title`: 卧推抬头
- `phase`: descent_press
- `severity`: medium
- `summary`: 卧推过程中头部抬起，往往伴随桥被压塌和整体张力丢失。
- `screeningPoints`:
  - 观察离心阶段头部是否离凳
  - 观察桥是否塌掉
- `visualSignals`:
  - 抬头
  - 胸廓高度下降
- `kinematicSignals`:
  - 当前项目暂无专门量化，优先以视觉证据判断
- `cue`: 全程下巴去找胸骨，别让桥塌掉
- `drills`:
  - paused bench
  - spoto press
- `loadAdjustmentHint`: 先确保桥和头稳定，再提升强度

## 4.2 `bench_arch_collapse`
- `title`: 桥塌陷
- `phase`: descent_press
- `severity`: medium
- `summary`: 离心或推起过程中桥的高度明显下降，导致张力链断开。
- `screeningPoints`:
  - 观察离心阶段胸廓高度是否下降
  - 观察推起时桥是否被压塌
  - 观察是否伴随抬头或脚下乱动
- `visualSignals`:
  - 桥高度下降
  - 胸骨位置下降
  - 整个平台变松
- `kinematicSignals`:
  - 当前项目暂无直接量化，优先结合视觉证据与下肢张力问题共同判断
- `negativeChecks`:
  - 轻微桥变化不等于塌桥
  - 超轻重量热身不应机械判错
- `cue`: 保持胸骨抬高，让桥在离心和推起中都不被压塌
- `drills`:
  - paused bench
  - spoto press
- `loadAdjustmentHint`: 如果桥一压就塌，先降一点重量把稳定性练住

## 4.2 `bench_leg_drive_instability`
- `title`: 下肢张力不足
- `phase`: setup_press
- `severity`: medium
- `summary`: 下肢发力时机不对或脚下不稳，导致整个平台不稳定。
- `screeningPoints`:
  - 观察脚的位置和下肢晃动
  - 观察离心前是否已经建立腿部张力
- `visualSignals`:
  - 脚乱动
  - 推起时身体底盘不稳
- `cue`: 脚踩实地面，离心前就把腿部张力接上
- `drills`:
  - paused bench
  - leg drive setup practice

## 4.3 `bench_upper_back_instability`
- `title`: 上背稳定不足
- `phase`: setup_press
- `severity`: medium
- `summary`: 肩胛、腋下和上背张力不足，导致卧推轨迹和承重线不稳定。
- `screeningPoints`:
  - 观察肩胛是否稳定
  - 观察背部是否贴实凳面
- `visualSignals`:
  - 圆肩
  - 肩胛不稳
- `cue`: 肩胛下回旋，腋下和背同时收紧
- `drills`:
  - spoto press
  - paused bench

## 4.4 `bench_wrist_stack_break`
- `title`: 手腕承重线不稳
- `phase`: setup_descent_press
- `severity`: low_to_medium
- `summary`: 手腕过度背伸或承重线不稳定，会把压力传到整条手臂和肩带。
- `screeningPoints`:
  - 观察手腕是否明显后折
  - 观察前臂是否堆叠在杠铃正下方
- `visualSignals`:
  - 手腕角度过大
  - 杠铃没有稳稳压在掌根承重线上
- `kinematicSignals`:
  - 当前项目暂无稳定直接量化，优先以视觉证据判断
- `negativeChecks`:
  - 轻微个人差异不等于错误
  - 需结合疼痛史和承重效率一起看
- `cue`: 让杠压在掌根承重线上，别让手腕往后折太多
- `drills`:
  - paused bench
  - wrist stack setup practice
- `loadAdjustmentHint`: 手腕明显失稳时优先修正承重线，再增加强度

## 4.5 `bench_touchpoint_instability`
- `title`: 触胸点不稳定
- `phase`: descent
- `severity`: medium
- `summary`: 触胸位置漂移或每次离心落点不同，说明张力和路径管理不稳定。
- `screeningPoints`:
  - 观察每次离心的落点是否一致
  - 观察是否越做越偏
- `visualSignals`:
  - 触胸位置飘
  - 离心轨迹不稳定
- `kinematicSignals`:
  - 当前项目暂无直接量化，后续可结合杠路径与肘腕堆叠增加判断
- `negativeChecks`:
  - 单次轻微偏差不应高置信输出
- `cue`: 让每次离心都落到同一触胸点，再从那里稳定发力
- `drills`:
  - paused bench
  - spoto press
- `loadAdjustmentHint`: 触胸点不稳定时，先保持当前重量重复高质量动作

## 4.6 `bench_elbow_flare_mismatch`
- `title`: 开肘与承重线不匹配
- `phase`: descent_press
- `severity`: low_to_medium
- `summary`: 开肘角度与个人肩部结构、握距或路径不匹配，影响稳定和发力效率。
- `screeningPoints`:
  - 观察肘部在离心和推起时的展开方式
  - 观察是否伴随肩前压力或路径不顺
- `visualSignals`:
  - 肘部展开方式不稳定
  - 承重线和推起方向不顺
- `kinematicSignals`:
  - 当前暂无直接量化，优先做结构性解释
- `negativeChecks`:
  - 不要把所有开肘都判成错误，要结合肩部受力和路径看
- `cue`: 让肘、腕、杠的承重线统一，不要为了“固定模板”硬套角度
- `drills`:
  - paused bench
  - close-grip bench variation

## 4.7 `bench_left_right_imbalance`
- `title`: 卧推左右发力不一致
- `phase`: press
- `severity`: medium
- `summary`: 两侧推起节奏、锁定或稳定性不一致。
- `screeningPoints`:
  - 观察两侧推起是否对称
  - 观察一侧肩胛是否外翻
- `visualSignals`:
  - 两侧上升不同步
  - 一侧更抖或更慢
- `cue`: 优先找弱侧发力和肩胛稳定感，让两侧同步输出
- `drills`:
  - paused bench
  - unilateral accessory

## 4.8 `bench_scapular_control_loss`
- `title`: 肩胛控制丢失
- `phase`: setup_descent_press
- `severity`: medium
- `summary`: 卧推过程中肩胛前倾、翻起或下沉控制丢失，导致上背平台和承重线一起变差。
- `screeningPoints`:
  - 观察离心时肩胛是否被拉开或翻起
  - 观察推起时一侧肩胛是否先失去控制
  - 观察是否伴随桥塌、抬头、左右不平衡
- `visualSignals`:
  - 肩胛前倾
  - 上背平台松掉
  - 一侧肩胛位置明显跑掉
- `kinematicSignals`:
  - 当前项目暂无稳定直接量化，适合由视频和姿态证据支持
- `negativeChecks`:
  - 轻微肩胛活动不等于失控
  - 机位不好时不要高置信判定细微肩胛问题
- `cue`: 让肩胛下沉后稳定贴住凳面，整次离心和推起都别丢控制
- `drills`:
  - paused bench
  - spoto press

---

## 5. 传统硬拉 / 相扑硬拉 Taxonomy

## 5.1 `hip_shoot_at_start`
- `title`: 启动抬臀
- `phase`: floor_break
- `severity`: medium
- `summary`: 启动瞬间臀位先上去，说明腿部驱动没有真正接上。
- `screeningPoints`:
  - 观察离地瞬间臀位
  - 观察是否先抬臀再拉杠
- `visualSignals`:
  - 启动就抬臀
  - 重心前移
- `kinematicSignals`:
  - 当前项目暂无高置信硬拉专项量化，优先视觉判断
- `cue`: 先把腿蹬满，再让杠离地
- `drills`:
  - paused deadlift
  - quad-strength accessory

## 5.2 `deadlift_tension_preset_failure`
- `title`: 启动前张力预设不足
- `phase`: setup
- `severity`: medium
- `summary`: 启动前没有把手臂、腋下、躯干和腿部的张力链接通，导致离地瞬间散架。
- `screeningPoints`:
  - 观察拉杠前身体是否已经“接住杠铃”
  - 观察启动时是否先有明显松掉再硬拉
- `visualSignals`:
  - 启动前看起来是“抓住杠就直接拉”
  - 躯干与杠铃没有形成对抗
- `kinematicSignals`:
  - 当前项目暂无直接量化，适合由视频证据和手册逻辑共同支持
- `negativeChecks`:
  - 快速启动不等于没有预设张力
- `cue`: 拉之前先把自己和杠连成一个整体，再让杠离地
- `drills`:
  - paused deadlift
  - setup tension drill
- `loadAdjustmentHint`: 先把准备做完整，再去追求离地爆发

## 5.3 `deadlift_knee_hip_desync`
- `title`: 髋膝联动不足
- `phase`: floor_break
- `severity`: medium
- `summary`: 启动时只有髋或只有背在主导，膝没有同步接上，导致启动效率差。
- `screeningPoints`:
  - 观察离地瞬间膝是否参与
  - 观察是否只是伸髋、不蹬地
- `visualSignals`:
  - 一启动就更像髋主导把杠拽起来
  - 杠铃往前跑或离地不顺
- `kinematicSignals`:
  - 当前项目暂无高置信直接量化，适合结合杠路径与姿态共同判断
- `negativeChecks`:
  - 不同流派的启动风格有差异，不要机械化判断
- `cue`: 启动时让膝和髋一起参与，不要只用髋去拽杠
- `drills`:
  - paused deadlift
  - quad-dominant accessory

## 5.4 `bar_drift`
- `title`: 杠铃前飘
- `phase`: floor_break_to_knee
- `severity`: medium
- `summary`: 杠铃没有贴近身体垂直上升，导致力臂变长、完成难度增加。
- `screeningPoints`:
  - 观察杠铃是否贴腿
  - 观察是否斜向前上方移动
- `visualSignals`:
  - 飘杠
  - 杠离身
- `kinematicSignals`:
  - 当前项目可复用路径偏移相关量化
- `cue`: 让杠贴着身体上来，腋下先锁住再拉
- `drills`:
  - paused deadlift
  - banded deadlift

## 5.5 `lat_lock_missing`
- `title`: 腋下锁杠不足
- `phase`: setup_floor_break
- `severity`: medium
- `summary`: 腋下和肩胛没有提前把杠锁住，常导致飘杠和启动不稳。
- `screeningPoints`:
  - 观察启动前腋下是否已经“夹住杠”
  - 观察是否有明显二头代偿或手臂过度参与
- `visualSignals`:
  - 手臂在主动拉
  - 杠铃离腿
  - 上背没有形成稳定压杠感
- `kinematicSignals`:
  - 当前项目暂无直接量化，适合和 `bar_drift` 联合判断
- `negativeChecks`:
  - 单独的手臂紧张不一定等于腋下锁杠不足
- `cue`: 先把腋下压住杠，再让腿和髋去完成启动
- `drills`:
  - straight-arm lat activation
  - paused deadlift

## 5.6 `lower_back_rounding`
- `title`: 下背弯曲
- `phase`: setup_floor_break
- `severity`: medium_to_high
- `summary`: 启动瞬间腰椎失去中立，常与腿部驱动不足和联动错误相关。
- `screeningPoints`:
  - 观察启动瞬间腰部形态
  - 观察髋膝是否一起工作
- `visualSignals`:
  - 启动瞬间腰弯
  - 只有髋在动、膝没接上
- `cue`: 启动前先把腿蹬上张力，再把杠稳稳带离地面
- `drills`:
  - paused deadlift
  - quad-dominant accessory

## 5.7 `lockout_rounding`
- `title`: 锁定姿态不稳
- `phase`: lockout
- `severity`: low_to_medium
- `summary`: 锁定时圆肩、骨盆前倾或整体姿态不稳，影响完成质量。
- `screeningPoints`:
  - 观察锁定瞬间胸廓和肩位
  - 观察是否靠代偿完成锁定
- `visualSignals`:
  - 圆肩锁定
  - 身体末端姿态松散
- `cue`: 锁定时站直即可，不要靠过度后仰或耸肩完成动作
- `drills`:
  - banded deadlift
  - overload lockout work

## 5.8 `sumo_hip_height_mismatch`
- `title`: 相扑硬拉臀位过高
- `phase`: setup
- `severity`: medium
- `summary`: 相扑硬拉准备位臀位过高，动作更像宽站传统拉，重心和发力不理想。
- `screeningPoints`:
  - 观察臀位和背角
  - 观察是否变成“宽站传统拉”
- `visualSignals`:
  - 臀位过高
  - 背角过小
  - 重心偏后
- `kinematicSignals`:
  - 当前项目暂无专项量化，适合视频结构解释
- `negativeChecks`:
  - 个体身材差异较大，单条视频需谨慎高置信输出
- `cue`: 相扑准备位先找能把股四和髋同时接上的臀位，不要一上来就把臀抬太高
- `drills`:
  - high bar squat
  - bulgarian split squat

## 5.9 `sumo_wedge_missing`
- `title`: 相扑硬拉预发力不足
- `phase`: setup_floor_break
- `severity`: medium
- `summary`: 相扑硬拉启动前没有把脚、髋、躯干、腋下的楔入力做完整，离地不顺。
- `screeningPoints`:
  - 观察启动前是否已经把身体“楔进杠下”
  - 观察脚和膝是否向外主动打开
- `visualSignals`:
  - 启动前整个人松
  - 离地瞬间张力不足
- `kinematicSignals`:
  - 当前项目暂无专项量化，适合结合视频证据判断
- `negativeChecks`:
  - 不能把所有慢启动都归为预发力不足
- `cue`: 先把脚、髋、腋下和杠楔在一起，再让杠离地
- `drills`:
  - sumo wedge drill
  - paused sumo deadlift

## 5.10 `overextended_lockout`
- `title`: 锁定过度后仰
- `phase`: lockout
- `severity`: low_to_medium
- `summary`: 锁定时通过后仰、顶腰或把动作做过头来“凑完成”，而不是干净站直。
- `screeningPoints`:
  - 观察锁定时是否明显后仰
  - 观察是否用腰去顶而不是用髋完成
  - 观察是否伴随耸肩或圆肩锁定
- `visualSignals`:
  - 站起后还在继续往后顶
  - 胸廓和骨盆关系被拉散
  - 锁定终点不干净
- `kinematicSignals`:
  - 当前项目暂无专项直接量化，适合结合视觉证据判断
- `negativeChecks`:
  - 不要把正常的充分伸髋误判成过度后仰
- `cue`: 锁定只需要站直到位，不要再继续后仰去找完成感
- `drills`:
  - banded deadlift
  - paused deadlift

---

## 6. App 使用建议

### 6.1 问题卡优先级
- 第一优先：当前 rep 的主问题
- 第二优先：整组趋势问题
- 第三优先：结构性问题（姿态、站位、足底）

### 6.2 证据来源优先级
- `barbell / vbt`
- `pose`
- `manual / fusion explanation`

### 6.3 不应高置信下结论的情况
- 视频角度不对
- 遮挡严重
- 杠铃不完整
- pose 覆盖率低
- 单条视频不足以判断站距站姿类问题

### 6.4 推荐前端展示映射
- `code` 用于历史统计和聚类
- `title` 用于问题卡标题
- `summary` 用于问题卡解释
- `cue` 用于主建议
- `drills` 用于辅助训练推荐
- `loadAdjustmentHint` 用于下一组建议

---

## 7. 与当前后端的映射建议

### 可直接由规则层高置信输出
- `slow_concentric_speed`
- `mid_ascent_sticking_point`
- `rep_to_rep_velocity_drop`
- `bar_path_drift`
- `torso_position_shift`

### 适合 LLM 在手册约束下融合输出
- `pelvic_wink`
- `unstable_foot_pressure`
- `stance_setup_mismatch`
- `uncontrolled_descent`
- `bench_arch_collapse`
- `bench_head_lift`
- `bench_leg_drive_instability`
- `bench_upper_back_instability`
- `bench_wrist_stack_break`
- `bench_touchpoint_instability`
- `bench_elbow_flare_mismatch`
- `bench_scapular_control_loss`
- `bench_left_right_imbalance`
- `deadlift_tension_preset_failure`
- `deadlift_knee_hip_desync`
- `hip_shoot_at_start`
- `lat_lock_missing`
- `bar_drift`
- `lower_back_rounding`
- `lockout_rounding`
- `overextended_lockout`
- `sumo_hip_height_mismatch`
- `sumo_wedge_missing`
- `hip_shoot_in_squat`
- `forward_weight_shift`

---

## 8. 边界判定与去重规则

### 8.1 深蹲：`slow_concentric_speed` vs `mid_ascent_sticking_point`
- 如果整个向心阶段都慢，优先判 `slow_concentric_speed`
- 如果主要是出底后到中段有明显卡顿，再继续上升，优先判 `mid_ascent_sticking_point`
- 两者可以共存，但默认 `mid_ascent_sticking_point` 作为局部问题，`slow_concentric_speed` 作为整段问题

### 8.2 深蹲：`torso_position_shift` vs `hip_shoot_in_squat`
- 如果只是躯干角度变化偏大，优先判 `torso_position_shift`
- 如果明显表现为“屁股先起、胸口后跟”，优先判 `hip_shoot_in_squat`
- `hip_shoot_in_squat` 是更具体、更强烈的模式，不要和一般躯干变化重复报

### 8.3 深蹲：`unstable_foot_pressure` vs `forward_weight_shift`
- 如果是脚底前后左右乱飘、整体受力不稳，优先判 `unstable_foot_pressure`
- 如果是明显一路压到前脚掌、动作像在追杠，优先判 `forward_weight_shift`
- `forward_weight_shift` 可以被视为足底问题的更具体结果

### 8.4 深蹲：`bar_path_drift` vs `forward_weight_shift`
- 如果主要证据是杠铃路径偏离中足垂线，优先判 `bar_path_drift`
- 如果主要证据是人的整体重心前跑、导致动作前栽，优先判 `forward_weight_shift`
- 两者可共存，但不要把同一件事分别用“杠漂”和“重心跑”重复展开

### 8.5 卧推：`bench_arch_collapse` vs `bench_scapular_control_loss`
- 如果主问题是桥高度明显下降、平台整体被压塌，优先判 `bench_arch_collapse`
- 如果主问题是肩胛前倾、翻起、左右控制丢失，优先判 `bench_scapular_control_loss`
- 桥塌和肩胛失控经常一起出现，但应优先选择更接近根因的那一条做主问题

### 8.6 卧推：`bench_wrist_stack_break` vs `bench_touchpoint_instability`
- 如果核心问题是杠没压在掌根承重线上、手腕角度不稳，优先判 `bench_wrist_stack_break`
- 如果核心问题是每次落点不一样、触胸位置漂移，优先判 `bench_touchpoint_instability`
- 手腕不稳可能诱发落点不稳，但不要把两者机械绑定成双问题

### 8.7 卧推：`bench_elbow_flare_mismatch` vs `bench_left_right_imbalance`
- 如果问题是开肘/夹肘方式和承重线不匹配，优先判 `bench_elbow_flare_mismatch`
- 如果问题是左右两边时机、路径、锁定不一致，优先判 `bench_left_right_imbalance`
- 左右不平衡时允许在解释里提到一侧开肘更多，但不必重复单列

### 8.8 硬拉：`deadlift_tension_preset_failure` vs `lat_lock_missing`
- 如果主问题是整个人没有先“接住杠”、启动前张力链没连起来，优先判 `deadlift_tension_preset_failure`
- 如果主问题更集中在腋下和背阔没有锁住杠，优先判 `lat_lock_missing`
- `lat_lock_missing` 可以看成张力预设不足的一种子型，默认不要两条并列重复报

### 8.9 硬拉：`hip_shoot_at_start` vs `deadlift_knee_hip_desync`
- 如果离地一瞬间最明显的是臀位先上升，优先判 `hip_shoot_at_start`
- 如果更广义地表现为髋和膝没有同步参与，优先判 `deadlift_knee_hip_desync`
- `hip_shoot_at_start` 是更具体的视觉模式，优先级更高

### 8.10 硬拉：`lockout_rounding` vs `overextended_lockout`
- 如果锁定时是圆肩、姿态松散、没站直，优先判 `lockout_rounding`
- 如果已经站直但还继续后仰、顶腰去凑完成，优先判 `overextended_lockout`
- 这两条互斥，默认不同时输出

### 8.11 硬拉：`bar_drift` vs `lat_lock_missing`
- 如果最明显的是杠离身、前飘，优先判 `bar_drift`
- 如果最明显的是腋下没有锁住杠，导致贴腿和对抗感都差，优先判 `lat_lock_missing`
- `lat_lock_missing` 可作为 `bar_drift` 的解释，但不要强行拆成两个独立主问题

### 8.12 相扑：`sumo_hip_height_mismatch` vs `sumo_wedge_missing`
- 如果主问题是准备位臀位太高/太像宽站传统拉，优先判 `sumo_hip_height_mismatch`
- 如果主问题是启动前没有把脚、髋、腋下和杠楔在一起，优先判 `sumo_wedge_missing`
- 臀位不合适可能导致楔入失败，但默认先报更靠前的结构性问题

### 8.13 组内趋势问题的优先级
- `rep_to_rep_velocity_drop` 属于组级问题，不要和某一条单 rep 局部问题重复解释同一现象
- 如果第 5-6 次都慢，且整组后半段普遍掉速：
  - 主问题可报单 rep 的 `slow_concentric_speed` 或 `mid_ascent_sticking_point`
  - 次要问题再报 `rep_to_rep_velocity_drop`

### 8.14 证据不足时的规则
- 如果 pose 覆盖率低、遮挡重、机位偏差大：
  - 优先保留 `barbell / vbt` 问题
  - 不要高置信输出细粒度姿态问题
- 如果视频只提供单个角度：
  - `stance_setup_mismatch`、`bench_left_right_imbalance` 这类结构性问题默认降权

---

## 9. 备注

这份 v2 手册是为 **“视频分析 App 的技术判断链路”** 重写的，不再追求纯教学文章的完整性，而是优先保证：
- 问题定义稳定
- 证据结构清楚
- 便于 LLM 消费
- 便于前端展示
- 便于后续做历史统计与训练建议
