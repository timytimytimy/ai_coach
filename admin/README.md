# Admin Workspace

这个目录预留给未来的后台管理网站，目标是让后台和现有的 Flutter `app/`、FastAPI `server/` 解耦，避免后面把管理功能塞回用户端代码里。

## 设计目标

- 后台作为独立前端工作区存在，不和移动端/用户端混在一起
- 优先复用现有 `server/` 的数据和分析结果，不重复造后端
- 为后续的运营、视频排查、LLM 成本统计、模型回归验证预留清晰入口

## 建议目录结构

```text
admin/
├── README.md
├── docs/
│   ├── routes.md
│   ├── permissions.md
│   └── metrics.md
├── shared/
│   ├── schemas/
│   │   ├── analysis.ts
│   │   ├── jobs.ts
│   │   └── usage.ts
│   └── types/
│       ├── api.ts
│       └── ui.ts
└── web/
    ├── app/
    │   ├── layout.tsx
    │   ├── page.tsx
    │   ├── videos/
    │   │   ├── page.tsx
    │   │   └── [setId]/page.tsx
    │   ├── jobs/
    │   │   └── page.tsx
    │   ├── llm-usage/
    │   │   └── page.tsx
    │   ├── datasets/
    │   │   └── page.tsx
    │   └── settings/
    │       └── page.tsx
    ├── components/
    │   ├── layout/
    │   ├── charts/
    │   ├── tables/
    │   └── video/
    ├── features/
    │   ├── analysis-review/
    │   ├── job-monitor/
    │   ├── llm-cost/
    │   ├── dataset-labeling/
    │   └── model-debug/
    ├── lib/
    │   ├── api/
    │   ├── format/
    │   ├── auth/
    │   └── constants/
    ├── styles/
    └── public/
```

## 为什么这样拆

### `admin/web/`
- 放后台前端本体
- 建议后续用 React 系技术栈做，因为表格、筛选、图表、视频回放、调试面板会很多
- `app/` 放路由页
- `components/` 放通用 UI
- `features/` 放业务块，避免所有逻辑都堆进页面
- `lib/api/` 统一对接 `server/` 的接口

### `admin/shared/`
- 放后台和未来可能共用的 schema / types
- 例如：
  - `analysis` 结果结构
  - `job` 状态结构
  - `llm usage` 统计结构
- 这样以后如果我们把部分管理视图接到别的地方，也能共用

### `admin/docs/`
- 放后台内部设计文档，不污染根目录
- 推荐后续把这些文档放进来：
  - 路由清单
  - 权限设计
  - 指标口径说明

## 第一阶段建议页面

### 1. 视频列表 `/videos`
- 查看所有上传视频
- 按日期、动作、状态筛选
- 快速看：
  - 视频缩略图
  - 分析状态
  - rep 数
  - 是否命中缓存
  - 是否使用 LLM

### 2. 视频详情 `/videos/[setId]`
- 回放原视频
- 显示杠铃轨迹 / pose overlay
- 显示 VBT、规则分析、LLM 分析、screening checklist
- 用于人工排查“为什么这条视频分析成这样”

### 3. 任务页 `/jobs`
- 看异步分析任务队列
- 看任务当前阶段
- 看失败原因
- 方便排查后端问题

### 4. LLM 用量页 `/llm-usage`
- 统计每个视频、每个模型、每天的 token 和时延
- 直接服务于成本核算
- 这个页面会直接吃我们刚加的 `llm_usage_logs`

### 5. 数据集页 `/datasets`
- 后续给 RTMPose/规则回归准备数据
- 先做成列表和标注入口占位即可

## 和现有后端的关系

- 后台前端先直接复用现有 `server/` API
- 未来需要补一组后台专用接口，例如：
  - `/v1/admin/videos`
  - `/v1/admin/jobs`
  - `/v1/admin/llm-usage`
  - `/v1/admin/datasets`

建议原则：
- 用户端接口继续服务移动端/Flutter
- 后台接口单独加 `admin` 前缀
- 不把后台特有字段硬塞给用户端接口

## 当前先不做的事

- 现在不在这个目录里锁死具体前端框架
- 现在不直接开工实现后台页面
- 现在不做权限系统

这一步的目标只是把后台网站的边界和结构先规划好，方便后面逐步填充。
