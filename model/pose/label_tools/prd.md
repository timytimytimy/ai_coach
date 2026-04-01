# 🏋️ 力量举动作 Pose 标注系统 PRD

## 一、项目背景

本项目用于构建一个**本地部署的标注系统**，用于标注力量举（深蹲 / 硬拉）视频中的关键帧图像，并生成用于训练 **YOLO Pose 模型**的数据。

当前用户具备：

* 视频数据
* VBT（速度）检测能力
* 能从视频中提取关键帧

目标是：

> 构建一个高效、低成本、可迭代的数据标注系统（支持后续伪标签纠偏）

---

## 二、系统总体架构

### 架构模式

* 前端：浏览器（单页应用）
* 后端：本地服务（Python / Node.js 均可）
* 数据存储：文件系统（无数据库）

### 核心流程

```text
用户设置输入/输出路径
        ↓
后端读取图片文件夹
        ↓
前端逐张展示图片
        ↓
用户标注关键点
        ↓
前端提交标注
        ↓
后端写入 JSON 文件（与图片同名）
```

---

## 三、目录结构约定

### 输入目录（图片）

```text
input_images/
  video1_frame_0001.jpg
  video1_frame_0002.jpg
  ...
```

### 输出目录（标注）

```text
labels/
  video1_frame_0001.json
  video1_frame_0002.json
```

要求：

* JSON 文件名必须与图片同名
* 一张图对应一个 JSON 文件
* 可重复写入（覆盖更新）

---

## 四、关键点定义（固定）

本系统只支持一套固定关键点：

```text
1. bar_center
2. upper_back_center
3. pelvis_center
4. left_knee
5. right_knee
6. left_foot_mid
7. right_foot_mid
```

每个点包含：

```json
{
  "x": number | null,
  "y": number | null,
  "visibility": "visible" | "occluded" | "unreliable"
}
```

---

## 五、后端设计

### 1. 接口设计

#### 1.1 获取图片列表

```http
GET /api/images?input_dir=xxx
```

返回：

```json
{
  "images": [
    {
      "file_name": "frame_001.jpg",
      "width": 1080,
      "height": 1920
    }
  ]
}
```

---

#### 1.2 获取单张标注（用于伪标签纠偏）

```http
GET /api/label?image_name=xxx&output_dir=xxx
```

* 如果 JSON 存在 → 返回内容
* 如果不存在 → 返回空结构

---

#### 1.3 保存标注

```http
POST /api/save
```

请求体：

```json
{
  "image_name": "frame_001.jpg",
  "output_dir": "xxx",
  "data": { ...完整标注数据... }
}
```

行为：

* 写入：`output_dir/frame_001.json`
* 覆盖旧文件

---

### 2. 后端核心逻辑

#### 图片读取

* 扫描 input_dir
* 过滤 jpg/png
* 按文件名排序

#### JSON 写入

* 文件名 = 图片名替换后缀
* 支持覆盖
* 自动创建目录

---

## 六、前端设计

## 1. 页面结构

```text
顶部：路径设置 + 控制按钮
---------------------------------
左侧：图片标注区域（canvas）
---------------------------------
右侧：点列表 + 状态 + 控制面板
```

---

## 2. 核心功能

### 2.1 路径设置（必须）

输入：

* 图片目录路径
* 标注输出路径

按钮：

* 加载数据

行为：

* 请求后端读取图片列表

---

### 2.2 图片浏览

功能：

* 上一张 / 下一张
* 显示索引（如 12/300）
* 自动保存当前标注再切图

---

### 2.3 关键点标注（核心）

#### 顺序标注（强制）

按顺序：

```text
bar → upper_back → pelvis → left_knee → right_knee → left_foot → right_foot
```

行为：

* 点击画布 → 设置当前点
* 自动跳到下一个点

---

#### 点操作

支持：

* 点击设置
* 拖动修改
* 删除当前点
* 覆盖旧点

---

#### visibility 设置

快捷键：

* 1 → visible
* 2 → occluded
* 3 → unreliable

允许：

* 无坐标，仅状态

---

### 2.4 快捷键（必须）

```text
Tab             → 下一个点
Shift + Tab     → 上一个点
Space / Enter   → 下一张图
← / →           → 切图
Delete          → 删除当前点
1/2/3           → visibility
Ctrl/Cmd + Z    → 撤销
```

---

### 2.5 可视化

要求：

* 点有颜色区分
* 当前点高亮
* 显示简写：

  * BC / UB / PC / LK / RK / LF / RF

---

### 2.6 右侧面板

显示：

```text
bar_center        ✅
upper_back_center ✅
pelvis_center     ✅
left_knee         occluded
right_knee        ❌
...
```

支持点击跳转该点。

---

### 2.7 缩放与平移

* 鼠标滚轮缩放
* 拖动画布平移
* 自适应窗口

---

### 2.8 局部放大镜（推荐）

* 鼠标附近放大区域
* 用于精确点位

---

### 2.9 自动加载已有标注（关键）

切换图片时：

* 自动读取 JSON
* 显示已有点
* 允许直接修改（伪标签纠偏）

---

## 七、标注数据格式

每张图一个 JSON：

```json
{
  "image": "frame_001.jpg",
  "width": 1080,
  "height": 1920,
  "points": {
    "bar_center": { "x": 320, "y": 180, "visibility": "visible" },
    "upper_back_center": { "x": 265, "y": 255, "visibility": "visible" },
    "pelvis_center": { "x": 255, "y": 390, "visibility": "visible" },
    "left_knee": { "x": null, "y": null, "visibility": "occluded" },
    "right_knee": { "x": 248, "y": 540, "visibility": "visible" },
    "left_foot_mid": { "x": 250, "y": 690, "visibility": "visible" },
    "right_foot_mid": { "x": null, "y": null, "visibility": "unreliable" }
  }
}
```

---

## 八、标注样本采样策略（关键）

## 1. 总目标

标注 300 张高价值样本，而不是随机抽帧。

---

## 2. 基于 VBT 的抽样策略

### 每个 rep 抽 5 帧：

#### 必选帧（4个）

* bottom（最低点）
* v_min（最低速度）
* dv/dt 最大（变化最大）
* setup（起始）

#### 随机帧（1个）

* 增加泛化能力

---

## 3. 多样性约束

必须覆盖：

* 不同人
* 不同重量
* 不同视角（正面 / 侧面 / 45°）
* 不同环境
* 不同动作质量（好 + 错误）

---

## 4. 数据分布建议

```text
200 张：关键帧（VBT）
50 张：随机帧
50 张：问题动作（人工挑）
```

---

## 5. 禁止行为

* 不允许连续帧抽样
* 不允许单视频占比过高
* 不允许只标“好动作”

---

## 九、性能与体验要求

必须满足：

* 标注一张图 ≤ 5 秒
* 操作流畅无卡顿
* 切图自动保存
* 不丢数据

---

## 十、未来扩展（非本期）

* 自动 YOLO 格式导出
* 模型预测加载（伪标签）
* 视频直接标注
* 多用户协作

---

## 十一、验收标准

必须满足：

* 能读取本地图片目录
* 能标注 7 个关键点
* 能设置 visibility
* 能保存 JSON（同名）
* 能加载已有 JSON
* 支持快捷键
* 标注流畅可用（非 demo）

---

# ✅ 一句话总结

这是一个：

👉 **“VBT驱动数据采样 + 高效关键点标注 + 本地文件系统存储” 的工程工具**

目标是：

👉 **最小成本构建高质量训练数据闭环**
