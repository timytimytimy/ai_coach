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
- 膝轨迹 / 膝内扣
- 上背张力
- 底部张力衔接

卧推高频：
- 桥
- 肩胛
- 手腕
- 下肢支撑
- 左右不平衡
- 离心控制
- 触胸稳定
- 锁定质量

硬拉高频：
- 启动
- 张力
- 锁定
- 重心
- 抬臀 / 飘杠
- 过膝衔接
- 核心刚性
- 锁定耸肩 / 过度后仰

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
- `whatYouSee`
- `likelyTechnicalMeaning`
- `whatToDo`
- `screeningPoints`
- `visualSignals`
- `kinematicSignals`
- `negativeChecks`
- `cue`
- `drills`
- `loadAdjustmentHint`

### 1.4 对“不能直接看见本体”的问题，如何判断
有一类技术问题，视频里很难直接看见本体本身，只能通过外在动作表现去推断，例如：
- 肩胛控制丢失 / 肩胛没有稳定收紧
- 上背支撑不足 / 上背平台松掉
- 桥塌陷
- 躯干 brace 丢失
- 腋下没有把杠真正锁住

这类问题的判断原则：
- 不要假装“直接看见了肩胛、上背或核心本体”，而要明确这是基于外在表现做出的推断
- 优先看一组连续表现，而不是依赖单帧姿势：
  - 动作前后的平台是否稳定
  - 杠铃路径是否突然变差
  - 左右是否失衡
  - 触胸、触底、过膝、锁定这些关键阶段是否出现张力断裂
- 如果同一个推断同时得到视频、杠路径、速度变化、pose 或左右时序的支持，才允许升高置信度
- 如果只能看到轻微趋势，或者机位、遮挡、衣物让细节不清楚，优先输出为 `possible` 或“继续观察”
- 不要把“相关现象”直接等同于“根因”：
  - 桥塌不一定等于肩胛没收紧
  - 起立前倾变大不一定等于上背支撑不足
  - 杠路径变差不一定等于核心完全松掉

推荐给模型的说法：
- “从视频里的外在表现看，很像……”
- “更接近……的模式”
- “当前更像……，但还需要继续观察”

不推荐的说法：
- “明确看见肩胛没有收紧”
- “确定是上背没发力”
- “直接证明核心松掉了”

### 1.5 推荐写法：先说现象，再说推断，最后给动作建议
为了让这份手册更适合 App 里的教练反馈，建议每个问题都按同一层次组织：
- `whatYouSee`：用户能在视频里被指出来的现象，尽量具体，不要太抽象
- `likelyTechnicalMeaning`：更可能的技术原因或动作模式，允许用“更像”“通常与……有关”这种推断口径
- `whatToDo`：下一组最该优先做的动作调整，必须是用户能执行的 cue

推荐表达：
- 先说“看到什么变差了”
- 再说“这更像什么技术问题”
- 最后说“下一组先做什么”

例如：
- 不要只写：“胸口不要掉”
- 更推荐写：
  - `whatYouSee`: 触底后胸口先掉，背角比下放到底时更快变大
  - `likelyTechnicalMeaning`: 这更像上背支撑和躯干刚性没有持续住
  - `whatToDo`: 下一组先把胸背顶住杠，再让髋膝一起展开

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
- `whatYouSee`: 起立整体拖长，尤其后半组每一下站起来都更费力、更磨。
- `likelyTechnicalMeaning`: 这更像向心阶段连续发力不足，或者疲劳后动作模板守不住，而不只是“单纯没力”。
- `whatToDo`: 下一组先把目标放在每一下都持续加速站起，不要到底部发力一下就泄掉。
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
- `summary`: 触底后到中段出现明显减速或短暂停滞，说明发力连续性不足。
- `whatYouSee`: 触底后不是一路顺着站起，而是在中段卡一下、重新找力再继续上。
- `likelyTechnicalMeaning`: 这更像底部到中段的力传导断了一拍，常和胸背没顶住、髋膝不同步或底部张力接不上有关。
- `whatToDo`: 下一组优先练“触底后继续推地 through 中段”，不要把动作做成两段式发力。
- `screeningPoints`:
  - 观察底部刚起立后是否在中段“卡一下”
  - 观察是否存在两段式发力
  - 观察是否需要明显二次加速才能完成
- `visualSignals`:
  - 杠铃上升不连贯
  - 中段速度明显掉下来
  - 触底后有“卡住再上”的感觉
- `kinematicSignals`:
  - `stickingRegion.durationMs` 较长
  - 中段速度显著低于该 rep 其余区间
- `negativeChecks`:
  - 如果从底部到锁定全程都慢，更优先归为 `slow_concentric_speed`
- `cue`: 触底后继续推地，不要在中段泄力
- `drills`:
  - pause squat
  - tempo squat
- `loadAdjustmentHint`: 先保持当前重量，把中段连续发力练顺

## 3.3 `rep_to_rep_velocity_drop`
- `title`: 后续重复明显掉速
- `phase`: set_level
- `severity`: medium
- `summary`: 后续 reps 明显比前面慢，说明疲劳下动作质量下降。
- `whatYouSee`: 前几次还能维持模板，后几次明显更慢、更磨，动作一致性开始散。
- `likelyTechnicalMeaning`: 这更像组内容量超过了你当前能稳定控制的范围，疲劳把发力和姿态问题一起放大了。
- `whatToDo`: 下一组优先保住每一下的同一模板；如果后半组明显磨速，就减少 1 到 2 次，或小幅降重。
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
- `whatYouSee`: 杠不是稳稳在中足上方上下，而是起立时开始往前跑或整条路径不干净。
- `likelyTechnicalMeaning`: 这更像重心管理、上背稳定性或起立路线出了偏差，不一定只是单纯速度慢。
- `whatToDo`: 下一组先让人和杠一起稳在中足上方，再去追更快的起立速度。
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
- `whatYouSee`: 触底后胸口有下掉趋势，背角变化比正常模板更大。
- `likelyTechnicalMeaning`: 这更像胸背没有一直顶住杠，或者髋先走、膝后跟，导致躯干姿态被带散。
- `whatToDo`: 下一组先把胸背顶住杠，再让髋膝一起展开，不要让胸口在起立初段先掉下去。
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

## 3.5.1 `upper_back_support_loss`
- `title`: 上背支撑不足
- `phase`: ascent
- `severity`: medium
- `summary`: 触底到起立初段上背没有持续把杠稳稳顶住，胸口和杠位关系开始变差，后面更容易出现前倾变大、路径前漂或先抬臀。
- `whatYouSee`: 触底后胸口先掉、杠像把人往前压，上半身没有把杠稳稳托住。
- `likelyTechnicalMeaning`: 这更像上背支撑和胸背对杠的稳定性没有持续住，通常和躯干刚性、起立节奏、髋膝协同一起出问题，但它是根据外在表现做出的推断，不是直接看见上背肌肉本体。
- `whatToDo`: 下一组先把“上背顶住杠”当成起立前半段的首要任务，先稳住胸背，再让髋膝一起展开。
- `screeningPoints`:
  - 观察触底后胸口是否突然掉下去
  - 观察杠位和上半身关系是否在起立初段明显变差
  - 观察是否伴随前倾变大、路径前漂、先抬臀或中段卡顿
- `visualSignals`:
  - 起立初段胸口下掉
  - 杠像把人往前压
  - 上半身支撑看起来先散掉
- `kinematicSignals`:
  - 常与 `torsoLeanDeltaDeg` 偏大、`barPathDriftCm` 增大、`mid_ascent_sticking_point` 同时出现
  - 当前项目更适合做“视频 + 路径 + 节奏”的联合支持，不适合单靠某一个数值直接下结论
- `negativeChecks`:
  - 低杆深蹲允许一定前倾，不应把所有前倾都判成上背没顶住
  - 如果主问题更明显是重心前跑、先抬臀或单纯速度慢，应优先输出那些更直接的现象问题
  - 机位太斜、遮挡严重、只看到下半身时不应高置信输出
- `cue`: 起立时先把上背顶住杠，胸口别先掉，再让髋膝一起把杠送上去
- `drills`:
  - pause squat
  - pin squat
  - tempo squat
- `loadAdjustmentHint`: 如果一触底就明显被杠压散，先把重量降一点，把上背支撑和胸背节奏守住

## 3.5.2 `trunk_brace_loss_in_squat`
- `title`: 躯干刚性不足
- `phase`: descent_ascent
- `severity`: medium
- `summary`: 整个 rep 里胸廓到骨盆这段刚性没有持续守住，导致下到底后到起立阶段更容易散、漏气、重心跑偏。
- `whatYouSee`: 下去前看起来有准备，但到底后躯干像突然变软，胸廓、骨盆和杠位的关系开始变差。
- `likelyTechnicalMeaning`: 这更像 brace 没有持续到动作后半段，胸背、腰腹和下肢没有一直连成一个整体；它是根据外在姿态和节奏去推断的，不是直接看见“核心没收紧”。
- `whatToDo`: 下一组先把“下去前锁住、起来时别松”当成主任务，先守住胸廓到骨盆这段整体刚性，再去追速度和深度。
- `screeningPoints`:
  - 观察离心前半程还稳，但到底后是否突然变散
  - 观察起立时胸廓和骨盆关系是否明显变化
  - 观察是否伴随重心前跑、上背支撑不足、中段卡顿或先抬臀
- `visualSignals`:
  - 到底后像“漏气”
  - 胸廓和骨盆关系开始散
  - 人和杠不再像一个整体起立
- `kinematicSignals`:
  - 常与 `torsoLeanDeltaDeg` 偏大、`barPathDriftCm` 增大、`mid_ascent_sticking_point` 同时出现
  - 当前项目更适合通过视频、路径、节奏联合支持，不适合把某个单独数值直接等同于 brace 丢失
- `negativeChecks`:
  - 不要把所有前倾都判成躯干刚性不足
  - 如果主要问题更明显是重心前跑、上背支撑不足或先抬臀，应优先输出那些更直接的问题
  - 宽松衣物、遮挡和侧面信息不足时不应高置信输出
- `cue`: 下去前锁住，起来时别松，让胸廓到骨盆一直像一整块
- `drills`:
  - pause squat
  - tempo squat
  - front squat
- `loadAdjustmentHint`: 如果底部一到起立就明显散，先把重量降一点，把躯干刚性守住

## 3.6 `pelvic_wink`
- `title`: 底部骨盆眨眼
- `phase`: bottom
- `severity`: medium
- `summary`: 深蹲底部出现骨盆后倾与腰椎曲度变化，底部稳定性不足。
- `whatYouSee`: 到底时骨盆和腰椎关系开始变，像是为了更深把底部稳定让掉了。
- `likelyTechnicalMeaning`: 这更像底部深度、髋结构、躯干控制三者没有找到稳定平衡，而不是单纯“蹲得不够深”。
- `whatToDo`: 下一组优先守住底部中立和稳定，不要为了更深把骨盆和腰椎姿态一起放掉。
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
- `whatYouSee`: 下放或起立时像在脚底来回找支点，整个人看起来没稳稳压在中足上。
- `likelyTechnicalMeaning`: 这更像足底支撑没有持续住，后面就容易连带出现重心前跑、膝轨迹散和路径不稳。
- `whatToDo`: 下一组先把注意力放在全脚掌均匀受力，稳稳踩住中足，再去追速度和深度。
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
- `whatYouSee`: 动作不是某个点明显错，而是整套模板怎么看都别扭、很难顺着发力。
- `likelyTechnicalMeaning`: 这更像站距、脚尖方向或杠下站位和你的结构、发力路线不匹配。
- `whatToDo`: 下一组先在中等重量下把站距和脚尖方向调到最自然稳定，再去追更多重量和次数。
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
- `whatYouSee`: 下放像掉下去，不是带着张力到底；到底后也更难顺着起。
- `likelyTechnicalMeaning`: 这更像离心控制和底部准备没有做好，导致底部接不上力，而不是单纯想蹲快。
- `whatToDo`: 下一组先把下放控制住，让张力一路带到底，再从稳定底部起立。
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
- `whatYouSee`: 触底后先看到臀位往上跑，胸口和杠位没有一起稳稳抬起来。
- `likelyTechnicalMeaning`: 这更像髋膝不同步、胸背没顶住杠，动作从“深蹲起立”变成了更像早安式硬顶。
- `whatToDo`: 下一组先把胸口和背撑住杠，再让髋膝一起往上展开，不要先抬臀再补站起。
- `screeningPoints`:
  - 观察触底后臀位是否先明显上升
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
- `cue`: 触底时先把胸口和背撑住，让髋膝一起向上展开
- `drills`:
  - pause squat
  - box squat
- `loadAdjustmentHint`: 抬臀明显时先稳住当前重量，不急着继续加重

## 3.11 `forward_weight_shift`
- `title`: 深蹲重心前跑
- `phase`: descent_and_ascent
- `severity`: medium
- `summary`: 离心或起立过程中整体重心压到前脚掌，导致路径、膝压和节奏都变差。
- `whatYouSee`: 下放或起立时人和杠整体往前追，压力更像一直跑向前脚掌。
- `likelyTechnicalMeaning`: 这更像中足没有被稳稳守住，后面就会连带出现前跪、胸口掉和杠铃前漂。
- `whatToDo`: 下一组先把重心稳回中足，不要用前脚掌去追杠或追速度。
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

## 3.12 深蹲补充观察点（非稳定 code）

以下条目先作为知识库补充观察点使用，用来增强 LLM 的教练式判断，不直接作为当前稳定 taxonomy code 输出：

### 3.12.1 膝轨迹控制不足 / 膝内扣趋势
- 教练常见说法：
  - 膝盖没有持续跟着脚尖方向走
  - 触底后膝往里收，脚底没踩住
  - 不是单纯“外旋不够”，而是整条腿和足底支撑没有接住
- 观察重点：
  - 离心到底后膝是否明显向内塌
  - 起立初段膝和脚尖方向是否脱节
  - 是否伴随足底压力丢失、重心前跑、髋转移
- 常见原因：
  - 足底三点支撑弱
  - 髋外展/外旋张力没有持续住
  - 疲劳后下肢协同变差
- 常见误解：
  - 不是所有膝往里一点都算问题，要看幅度、持续时间和是否影响发力
  - 不要把“提醒膝盖外推”理解成全程硬顶到外侧
- 纠正方向：
  - 先稳住脚底，再谈膝轨迹
  - cue 优先是“脚踩住、膝跟脚尖同向推开”

### 3.12.2 上背张力丢失
- 教练常见说法：
  - 杠压下来以后上背没顶住
  - 胸口掉了、背散了
  - 不是腿没力，而是上半身没把杠稳住
- 观察重点：
  - 起立初段胸口是否突然掉下去
  - 杠位是否在触底后显得“不稳”
  - 是否伴随飞肘、手腕压力异常、躯干角度突然变化
- 判断边界：
  - 这是通过胸口位置、杠位稳定性、躯干变化去推断“上背支撑不足”，不是直接看见上背肌肉本体
  - 如果只是低杆深蹲本来就允许更大前倾，不要机械判成上背散掉
  - 如果主要问题是重心前跑或先抬臀，应先把它们作为更直接的问题输出
- 常见原因：
  - 入杠和起杠时上背准备不足
  - 下放过程中把张力丢掉
  - 疲劳后上背对抗杠铃能力下降
- 不要高置信输出的情况：
  - 机位太斜，看不清胸口和杠位相对关系
  - 遮挡严重，只看到下半身节奏变化
  - 只有单次轻微胸口波动，没有持续模式
- 纠正方向：
  - 把“上背顶杠”作为起立前半段的优先任务
  - 在 cue 上优先强调“胸背顶住杠，再站起来”

### 3.12.3 底部张力丢失 / 触底衔接差
- 教练常见说法：
  - 到底太松，起来时接不上
  - 底部像掉进去，触底靠反弹找路
  - 离心没有把张力带到底部
- 观察重点：
  - 下放后底部是否显得“塌一下”
  - 触底第一下是否像重新找发力
  - 是否伴随中段卡顿、起立节奏断裂
- 常见原因：
  - 离心过快
  - 底部重心失控
  - 呼吸与躯干刚性维持不足
- 纠正方向：
  - 先补底部控制和离心张力
  - 暂停深蹲、慢离心深蹲优先级会更高

### 3.12.4 低头 / 含胸导致重心和背部一起散
- 教练常见说法：
  - 一低头，胸口和重心就一起跑了
  - 不是头本身的问题，是头带着胸背姿态一起掉
- 观察重点：
  - 起立时头颈位置变化是否伴随胸口下掉
  - 是否和重心前跑、上背散开同步出现
- 纠正方向：
  - 不强调僵硬抬头，而是保持头颈和胸廓整体稳定
  - cue 更适合说“眼神固定、胸口别掉”

### 3.12.5 躯干刚性不足 / 腰腹松掉
- 教练常见说法：
  - 下去前有气，起来时中间散掉了
  - 腰腹没把杠铃和下肢连起来
  - 不是单纯核心弱，而是 brace 没有持续到动作后半段
- 观察重点：
  - 下放前半程躯干是否稳定，但到底后突然变软
  - 起立时腰腹是否像“漏气”，胸廓和骨盆关系是否明显变化
  - 是否伴随重心前跑、上背张力丢失、中段卡顿
- 判断边界：
  - 这是通过胸廓、骨盆、杠位、起立节奏的变化去推断 brace 没有持续住，不是直接看见“核心没收紧”
  - 如果只是正常的低杆前倾或个体风格差异，不要直接判成核心松掉
  - 如果更明显的是重心前跑、先抬臀、上背散掉，应先输出那些更直接的现象问题
- 常见原因：
  - 吸气和 brace 只做在起杠前，没有维持到整个 rep
  - 离心过程为了找深度把腹压主动放掉
  - 疲劳后下肢还在发力，躯干先守不住
- 常见误解：
  - 不要把所有前倾都理解成核心松掉
  - 也不要把“憋气”简单等同于“躯干刚性够”
- 不要高置信输出的情况：
  - 机位看不清胸廓和骨盆关系
  - 宽松衣物把腹部和躯干变化全部遮掉
  - 只有单次轻微姿态变化，没有持续模式
- 纠正方向：
  - cue 更适合说“下去前锁住，起来时别松”
  - 先保住胸廓到骨盆的整体刚性，再谈更快节奏

### 3.12.6 入杠与杠位准备不足
- 教练常见说法：
  - 不是蹲的时候才坏，是从入杠开始就没准备好
  - 杠位不稳，后面整组都在补救
  - 手腕、飞肘、上背对抗，其实是一整套问题
- 观察重点：
  - 入杠后上背是否已经形成对杠铃的对抗
  - 起杠后站稳时重心是否已经偏前偏后
  - 是否伴随手腕压力大、飞肘、胸口难抬、背部松散
- 常见原因：
  - 杠位不合适
  - 握距和上背准备不匹配
  - 起杠太急，没把人和杠的关系先锁定
- 纠正方向：
  - 先把入杠、起杠、站稳这三步模板化
  - 不把所有问题都推到下蹲和起立阶段

### 3.12.7 离心犹豫 / 节奏不连贯
- 教练常见说法：
  - 下去的时候还在犹豫，节奏不统一
  - 不是慢离心，而是一路在找位置
  - 离心募集没做好，底部自然接不上
- 观察重点：
  - 下放过程是否一段一段地找位置
  - 是否存在明显停顿、改重心、再继续下放
  - 是否导致底部衔接差、起立第一下发力不顺
- 常见原因：
  - 站位和重心不够确定
  - 对离心路线没有清晰意识
  - 对底部深度和姿态没有把握
- 纠正方向：
  - 建立“同样路线下去、同样位置到底”的节奏感
  - 慢离心不是目的，稳定离心才是目的

---

## 4. 卧推 Taxonomy

## 4.1 `bench_head_lift`
- `title`: 卧推抬头
- `phase`: descent_press
- `severity`: medium
- `summary`: 卧推过程中头部抬起，往往伴随桥被压塌和整体张力丢失。
- `whatYouSee`: 推起或离心中头离开凳面，整个平台像被带散了。
- `likelyTechnicalMeaning`: 这更像桥、上背平台和下肢张力没有一直接住，而不是单纯头的位置问题。
- `whatToDo`: 下一组先守住头、上背和桥的整体稳定，不要让头一抬就把平台一起抬散。
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
- `whatYouSee`: 杠一下到胸附近，胸廓高度就被压塌，平台不再像 setup 时那么稳。
- `likelyTechnicalMeaning`: 这更像桥和上背平台没一直守住，或者腿驱动没有把平台持续顶起来。
- `whatToDo`: 下一组先把胸骨高度和脚下张力守住，让桥在离心和推起里都别塌。
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
  - 桥塌是从胸廓高度、整个平台张力、触胸前后变化去推断，不是直接“看见桥没了”
  - 如果主问题更像肩胛控制丢失或腿驱动没有接上，不要把所有平台问题都归成桥塌
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
- `whatYouSee`: 脚下像没提前接住，推起时底盘不稳，桥和上背也跟着松。
- `likelyTechnicalMeaning`: 这更像腿驱动没有和桥、上背连成一个平台，而不是单纯“脚乱动”。
- `whatToDo`: 下一组先在离心前把脚踩稳、腿部张力接好，再去推起，不要等到离胸才想起用腿。
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
- `whatYouSee`: 整个平台不稳，触胸前后上背像松了一下，杠的路线和承重线也开始变差。
- `likelyTechnicalMeaning`: 这更像上背平台稳定性下降，通常和肩带控制、桥的维持、承重线管理一起有关。
- `whatToDo`: 下一组优先把上背和腋下先收紧、贴稳凳面，再去做离心和推起。
- `screeningPoints`:
  - 观察肩胛是否稳定
  - 观察背部是否贴实凳面
- `visualSignals`:
  - 圆肩
  - 肩胛不稳
- `kinematicSignals`:
  - 当前暂无直接量化，更多依赖视频中的平台稳定性、轨迹重复性、左右一致性共同支持
- `negativeChecks`:
  - 这通常是“从外在表现推断上背平台不稳”，不是直接看见上背本体
  - 如果主问题更像桥塌、手腕承重线散掉或左右发力不一致，不要把所有现象都归到上背
  - 单次轻微抖动或肩部活动不应高置信输出
- `cue`: 肩胛下回旋，腋下和背同时收紧
- `drills`:
  - spoto press
  - paused bench

## 4.4 `bench_wrist_stack_break`
- `title`: 手腕承重线不稳
- `phase`: setup_descent_press
- `severity`: low_to_medium
- `summary`: 手腕过度背伸或承重线不稳定，会把压力传到整条手臂和肩带。
- `whatYouSee`: 杠没有稳稳压在掌根和前臂正下方，手腕开始后折，整条手臂承重线变散。
- `likelyTechnicalMeaning`: 这更像手腕和前臂堆叠没有守住，后面会连带影响肩带稳定和路径。
- `whatToDo`: 下一组先把杠稳稳压回掌根承重线上，让前臂始终堆在杠正下方。
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
- `whatYouSee`: 每次触胸的位置不一样，离心像在一路找落点。
- `likelyTechnicalMeaning`: 这更像上背平台、手腕堆叠或离心路线没固定住，导致后面推起轨道也跟着飘。
- `whatToDo`: 下一组先把每次离心都落到同一触胸点，再从那个点稳定发力。
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
- `whatYouSee`: 肘、腕、杠这条承重线看起来不顺，离心和推起的肘部路线也不稳定。
- `likelyTechnicalMeaning`: 这更像当前开肘方式和你的握距、承重线或肩部结构不匹配，不一定是“开肘本身错了”。
- `whatToDo`: 下一组先把肘、腕、杠调回同一条顺的承重线，不要为了模板硬套角度。
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
- `whatYouSee`: 两边不是一起推上去的，一侧更慢、更抖，或者锁定总在等另一边。
- `likelyTechnicalMeaning`: 这更像双侧平台稳定性、肩带控制或弱侧承重线没有跟上。
- `whatToDo`: 下一组先把双侧 setup 做对称，推起时优先追求两边同步，不要只盯总重量。
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
- `whatYouSee`: 触胸前后平台开始松，肩带位置跑掉，杠路线和左右稳定性也跟着变差。
- `likelyTechnicalMeaning`: 这更像肩带稳定性下降，通常与肩胛保持不足、上背平台松掉或桥没守住有关，但它是基于外在表现的推断。
- `whatToDo`: 下一组先把肩带和上背平台稳住，整次离心和推起都别让肩的位置先跑掉。
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
  - 这是根据肩带位置、上背平台、杠路径和左右时序推断肩胛控制，不是直接看见肩胛骨本体
  - 如果视频里更明显的是桥塌、抬头或弱侧锁定慢，应先输出那些更直接的问题
- `cue`: 让肩胛下沉后稳定贴住凳面，整次离心和推起都别丢控制
- `drills`:
  - paused bench
  - spoto press

### 4.8.1 关于“肩胛收紧 / 上背支撑”类问题的统一说明
- 这类问题通常不能通过单帧直接下结论，而要看完整过程：
  - 离心开始前平台有没有先搭好
  - 触胸前后平台有没有松掉
  - 推起时肩带和上背有没有继续稳住
- 高置信判断更依赖这些组合信号：
  - 桥高度变化
  - 触胸点漂移
  - 左右时序差异
  - 杠路径回不来
  - 推起后半程肩部位置明显变化
- 如果只能说“看起来像”，优先放进“继续观察”，不要硬判成主问题

## 4.9 卧推补充观察点（非稳定 code）

### 4.9.1 离心不受控
- 教练常见说法：
  - 杠是砸下去的，不是带着张力落下去的
  - 下放太快，触胸点和桥都接不住
- 观察重点：
  - 离心速度是否明显快于可控制范围
  - 触胸前是否已经开始丢桥、丢肩胛、丢手腕承重线
- 常见原因：
  - 只想快推，不愿意控制下放
  - 上背和下肢张力没有提前接好
- 纠正方向：
  - 先保证离心可控，再追求更强反弹和推起速度

### 4.9.2 推起路径回不来
- 教练常见说法：
  - 离心下去的位置和推起来的路线接不上
  - 不是单纯没力，是力线没回到优势轨道
- 观察重点：
  - 触胸后的第一段是否顺利回到肩上方
  - 是否伴随肘腕承重线散掉、触胸点漂移
- 常见原因：
  - 触胸点不稳定
  - 手腕、前臂、肘的堆叠关系不好
- 纠正方向：
  - 先把离心落点固定，再谈推起路径

### 4.9.3 锁定质量差
- 教练常见说法：
  - 杠推上去了，但锁得不干净
  - 末端发力像在“找完成”，不是稳稳锁住
- 观察重点：
  - 最后几厘米是否抖、偏、左右不同步
  - 是否伴随肩胛上浮、桥塌、手腕角度散掉
- 纠正方向：
  - 先确保上背平台和手腕承重线稳定，再补锁定段力量

### 4.9.4 桥和下肢张力没有真正连通
- 教练常见说法：
  - 起桥是起了，但没把腿和桥接起来
  - 看着有桥，实际上平台还是松的
  - 脚下和胸廓像两套系统，没形成力传导
- 观察重点：
  - 离心前脚是否已经踩稳、腿部张力是否提前建立
  - 推起时桥、腿驱动和上背是否同步稳定
  - 是否伴随桥塌、抬头、下肢乱动
- 常见原因：
  - 只会“起桥”，不会把桥和腿驱动连成一体
  - 下肢发力时机过晚
  - 脚的位置不适合当前桥和躯干结构
- 纠正方向：
  - 先让脚、臀、上背、胸骨形成统一平台，再去追更强推起

### 4.9.5 触胸后反弹依赖过强
- 教练常见说法：
  - 一离开反弹就不会推了
  - 不是卧推强，是吃触胸弹性
  - 一暂停就暴露问题
- 观察重点：
  - 触胸后是否必须靠明显反弹才能启动
  - 暂停或轻停时路径和发力是否明显变差
  - 是否伴随触胸点漂移、桥塌、肩胛控制丢失
- 常见原因：
  - 离心控制不足
  - 触胸点不稳定
  - 底部张力和上背平台不够稳
- 纠正方向：
  - 先让触胸可控、暂停可推，再追求更大的连续节奏

### 4.9.6 弱侧锁定更慢
- 教练常见说法：
  - 不是整体没力，是一边先掉队
  - 最后锁定像一边在等另一边
- 观察重点：
  - 推起到锁定阶段是否一侧更慢、更抖或更不稳
  - 是否和肩胛控制、手腕承重线、肘部展开方式有关
- 常见原因：
  - 弱侧上背和肩胛控制不足
  - 两侧下肢和桥张力不对称
  - 握距或手腕承重线两边不一致
- 纠正方向：
  - 先把双侧平台做对称，再讨论更高强度下的输出

### 4.9.7 手腕和前臂堆叠不稳定带来的肩前压力
- 教练常见说法：
  - 手腕一散，整条手臂到肩前都会跟着吃力
  - 表面看是手腕问题，实际上会把路径和肩带一起带偏
- 观察重点：
  - 手腕是否明显后折
  - 前臂是否稳定堆在杠下
  - 是否伴随触胸点飘、肩前压力、推起路径偏移
- 纠正方向：
  - 先把杠稳稳压在掌根和前臂堆叠线上，再去调整肘和路径

---

## 5. 传统硬拉 / 相扑硬拉 Taxonomy

## 5.1 `hip_shoot_at_start`
- `title`: 启动抬臀
- `phase`: floor_break
- `severity`: medium
- `summary`: 启动瞬间臀位先上去，说明腿部驱动没有真正接上。
- `whatYouSee`: 杠还没真正离地，臀就先往上跑，动作更像先把身体拉成硬拉姿势再去起杠。
- `likelyTechnicalMeaning`: 这更像腿没有先把地蹬开，启动变成髋先走、腿后跟。
- `whatToDo`: 下一组先把腿蹬满、把杠接住，再让臀和胸一起启动，不要一上来先抬臀。
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
- `whatYouSee`: 起拉前像是抓住杠就直接拉，身体没有先和杠形成稳定对抗。
- `likelyTechnicalMeaning`: 这更像启动前张力没有预先接通，人和杠还没连成一个整体就开始离地。
- `whatToDo`: 下一组先把预拉做完整，感觉到自己把杠“接住”以后再让杠离地。
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
  - 这是根据准备动作、杠离地前的身体对抗、离地瞬间是否散掉去推断张力预设不足，不是直接看见“张力本体”
  - 不要把所有快速、简洁的启动都判成没张力；关键是有没有先接住杠
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
- `whatYouSee`: 一离地就更像髋在拽杠，腿没有同时把地蹬开。
- `likelyTechnicalMeaning`: 这更像髋膝联动没接上，启动少了腿的参与，后面路径和节奏也更难稳。
- `whatToDo`: 下一组先让膝和髋一起参与启动，不要只用髋把杠拽起来。
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
- `whatYouSee`: 杠离身、往前飘，路径不像是贴身直上。
- `likelyTechnicalMeaning`: 这更像腋下没锁住、重心前跑或启动路线本身就偏前。
- `whatToDo`: 下一组先把杠贴住身体拉起来，让路径先干净，再谈更快离地。
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
- `whatYouSee`: 杠离地前后都不够贴身，手臂像在主动拉，身体没有把杠稳稳压回自己身上。
- `likelyTechnicalMeaning`: 这更像腋下和上背没有先把杠锁住，但它仍是根据外在表现做出的推断，不是直接看见背阔本体。
- `whatToDo`: 下一组先把腋下压住杠、把杠贴回身体，再让腿和髋去完成启动。
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
  - 这是通过杠是否贴身、手臂是否代偿、上背是否形成压杠感来推断“腋下没把杠锁住”，不是直接看见背阔肌本体
  - 如果主要问题是离地路径偏前或启动抬臀，不要把所有现象都归成腋下没锁住
- `cue`: 先把腋下压住杠，再让腿和髋去完成启动
- `drills`:
  - straight-arm lat activation
  - paused deadlift

## 5.5.1 `deadlift_trunk_brace_loss`
- `title`: 硬拉躯干刚性不足
- `phase`: floor_break_to_knee
- `severity`: medium
- `summary`: 起拉到过膝这段胸廓、腰腹和骨盆没有一直守成一个整体，导致路径、贴身感和后段发力都变差。
- `whatYouSee`: 起拉前像有准备，但杠一离地躯干就开始散，胸廓、骨盆和杠的关系不再稳定。
- `likelyTechnicalMeaning`: 这更像 brace 只做在起拉前，没有持续守到离地和过膝阶段；它是通过姿态变化、路径和节奏去推断的，不是直接看见“核心松掉”。
- `whatToDo`: 下一组先把目标改成“从预拉到过膝都守住同一个躯干壳子”，不要只在起拉前憋一下。
- `screeningPoints`:
  - 观察起拉前有张力，但离地后是否迅速变散
  - 观察胸廓、腰椎、骨盆关系是否在离地或过膝前明显变化
  - 观察是否伴随重心前移、飘杠、抬臀或过膝衔接差
- `visualSignals`:
  - 离地后像“塌了一截”
  - 人和杠不再像一体上升
  - 路径和贴身感一起变差
- `kinematicSignals`:
  - 常与 `bar_drift`、`hip_shoot_at_start`、`deadlift_knee_hip_desync` 同时出现
  - 当前项目更适合用视频过程、路径和阶段节奏联合支持，不适合单靠一个角度就高置信定性
- `negativeChecks`:
  - 不要把所有腰背形态变化都直接判成躯干刚性不足
  - 如果主问题更明显是启动抬臀、飘杠或预设张力不足，应优先输出那些更直接的现象问题
  - 机位太斜或遮挡严重时不应高置信输出
- `cue`: 从预拉到过膝都把躯干锁成一整块，别让杠一离地身体就先散
- `drills`:
  - paused deadlift
  - block pull
  - setup tension drill
- `loadAdjustmentHint`: 如果一离地躯干就明显守不住，先把重量降一点，把整段刚性和贴身感练住

## 5.6 `lower_back_rounding`
- `title`: 下背弯曲
- `phase`: setup_floor_break
- `severity`: medium_to_high
- `summary`: 启动瞬间腰椎失去中立，常与腿部驱动不足和联动错误相关。
- `whatYouSee`: 离地瞬间腰部形态变差，身体像先被拉散再去起杠。
- `likelyTechnicalMeaning`: 这更像启动前张力和腿部驱动没接好，导致躯干在最早阶段先失去稳定。
- `whatToDo`: 下一组先把张力和腿部驱动接上，别在杠还没离地时先把腰拉散。
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
- `whatYouSee`: 杠起来了，但锁定终点不干净，身体末端姿态看起来松、散、没站直到位。
- `likelyTechnicalMeaning`: 这更像末端平台和锁定顺序没做好，不一定是单纯“后背弱”。
- `whatToDo`: 下一组先把终点做成干净站直，不要靠额外耸肩、圆肩或补动作去找完成。
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
- `whatYouSee`: 相扑准备位看起来像宽站传统拉，臀位太高，腿没有真正接上。
- `likelyTechnicalMeaning`: 这更像当前臀位和背角没有把相扑应有的股四、髋和楔入优势用出来。
- `whatToDo`: 下一组先把臀位调到能同时接上髋和腿的位置，不要一上来把相扑做成宽站传统拉。
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
- `whatYouSee`: 启动前整个人还是松的，没有真正把自己楔进杠和地面之间。
- `likelyTechnicalMeaning`: 这更像相扑的预发力和楔入时序没做完整，导致离地第一下就不顺。
- `whatToDo`: 下一组先把脚、髋、腋下和杠楔成一个整体，再让杠离地。
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
- `whatYouSee`: 杠已经到位了，人还在继续往后顶，锁定像靠后仰补出来。
- `likelyTechnicalMeaning`: 这更像把“站直到位”做成了“继续后仰找完成”，末端力线和姿态都不够干净。
- `whatToDo`: 下一组先把终点理解成站直到位，不要再额外后仰去找锁定感。
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

## 5.11 硬拉补充观察点（非稳定 code）

### 5.11.0 关于“张力 / brace / 锁杠”类问题的统一说明
- 这类问题通常不能通过单帧直接下结论，而要看完整准备到启动的过程：
  - 起拉前有没有先把人和杠接起来
  - 离地瞬间有没有先散掉再硬拉
  - 杠是否能贴身离地并保持受力线干净
- 高置信判断更依赖这些组合信号：
  - 启动前是否有明确对抗
  - 杠离地第一下是否贴身
  - 启动后路径是否立刻前飘
  - 手臂是否明显代偿
  - 过膝前躯干和骨盆关系是否突然散掉
- 如果只能说“看起来没接住杠”或“像是张力没守住”，优先放进“继续观察”，不要直接上升为根因定论

### 5.11.1 过膝衔接差
- 教练常见说法：
  - 能离地，但过膝发不上去
  - 地面那一下还行，真正难的是过膝和锁定前的衔接
- 观察重点：
  - 杠到膝附近是否明显减速
  - 是否伴随杠离身、腋下松、髋提前顶上去
- 常见原因：
  - 起杠后背阔和身体贴杠能力不足
  - 地面驱动和后段伸髋衔接不好
- 纠正方向：
  - 不只练离地，还要补过膝保持贴身和持续发力

### 5.11.2 核心刚性丢失
- 教练常见说法：
  - 不是单纯下背弯，而是整个躯干像桥墩塌了一截
  - 启动前有张力，离地后没守住
- 观察重点：
  - 胸廓、腰椎、骨盆关系是否在启动或过膝后明显变散
  - 是否伴随重心前移、抬臀、飘杠
- 常见原因：
  - 呼吸与 brace 没有持续住
  - 张力预设只做在开始，没延续到动作中段
- 纠正方向：
  - 强调“全程守住躯干刚性”，不是只在起拉前憋一下

### 5.11.3 锁定耸肩 / 手臂代偿
- 教练常见说法：
  - 锁定时靠耸肩、屈肘、手臂抢活去凑完成
  - 不是髋锁定不好，而是末端路径和张力分配乱了
- 观察重点：
  - 锁定阶段是否出现明显耸肩或手臂额外拉杠
  - 是否和锁定后仰、杠离身同时出现
- 纠正方向：
  - 先把髋锁定做干净，再要求肩和手臂保持稳定

### 5.11.4 重心前后切换过大
- 教练常见说法：
  - 启动时重心太前，后面又猛往后找锁定
  - 整条力线不连续
- 观察重点：
  - 离地时是否压在前脚掌
  - 锁定时是否明显往后倒去“找完成”
- 纠正方向：
  - 让启动到锁定的重心迁移更平滑，而不是前后两头跑

### 5.11.5 离地前就把杠往前拉
- 教练常见说法：
  - 还没离地，杠就已经被你拉离身体了
  - 不是离地慢，是力线一开始就错
- 观察重点：
  - 预拉和离地瞬间杠是否已经脱离理想贴身路线
  - 是否伴随腋下松、重心前移、手臂主动拉
- 常见原因：
  - 预设张力方向不对
  - 上背和腋下没有把杠“锁到身上”
- 纠正方向：
  - 先把预拉方向做对，再去追求更快离地

### 5.11.6 锁定时先顶腰，不是先伸髋
- 教练常见说法：
  - 末端在用腰找完成，不是在用髋站直到位
  - 锁定不是站直，是顶过去
- 观察重点：
  - 锁定时是否骨盆和胸廓关系被拉散
  - 是否先出现腰椎伸展，再出现真正站直到位
- 常见原因：
  - 后段伸髋能力不足
  - 锁定概念错误，误以为需要“再往后送”
- 纠正方向：
  - 强调“站直到位就够”，不要再额外做后仰补偿

## 5.12 相扑硬拉补充观察点（非稳定 code）

### 5.12.1 楔入时序不对
- 教练常见说法：
  - 不是真的楔进去，而是人先下去、杠还没接住
  - 看着做了动作，实际上没有形成有效楔入
- 观察重点：
  - 脚、膝、髋、腋下是否在启动前形成同一个方向的张力
  - 是否出现先蹲下去、再临时找张力的过程
- 常见原因：
  - 过于追求低臀位
  - 对“楔入”理解成单纯下沉身体
- 纠正方向：
  - 强调“先把身体和杠接上，再把自己楔进去”

### 5.12.2 外展打开不足，导致相扑像宽站传统拉
- 教练常见说法：
  - 站得很宽，但髋和膝没有真正打开
  - 表面上是相扑，实际力线更像宽站传统
- 观察重点：
  - 膝是否持续向脚尖方向打开
  - 足底是否还能维持足中发力
  - 离地后是否立即变成更传统的背角和重心
- 常见原因：
  - 下肢准备不足
  - 只追求站宽，没有建立对应张力
- 纠正方向：
  - 先把脚、膝、髋的打开和足底压力统一，再决定站宽

### 5.12.3 手臂不垂直 / 受力线不干净
- 教练常见说法：
  - 手臂没垂直，力线就不干净
  - 杠铃没在最省力的线上被拉起来
- 观察重点：
  - 手臂是否尽量垂直到杠
  - 是否因为重心、臀位或楔入问题导致手臂斜拉
- 常见原因：
  - 重心摆放不对
  - 臀位和背角不匹配
  - 上肢准备不足
- 纠正方向：
  - 先把重心、臀位、楔入做对，再看手臂是否自然垂直

### 5.12.4 锁定时用后仰替代站直
- 教练常见说法：
  - 相扑后段不是站直，是往后甩
  - 看着完成了，其实是锁定策略有问题
- 观察重点：
  - 过膝后是否通过明显后仰去找锁定
  - 是否伴随耸肩、顶腰、胸廓与骨盆关系被拉散
- 纠正方向：
  - 把相扑锁定理解成“髋伸直到位”，而不是“身体继续往后顶”

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
- 如果主要是触底后到中段有明显卡顿，再继续上升，优先判 `mid_ascent_sticking_point`
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
