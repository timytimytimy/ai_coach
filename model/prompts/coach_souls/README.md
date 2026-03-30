# Coach Souls

这些文件定义了几种可切换的“教练灵魂 / 教练风格”。它们不是技术知识库本身，而是模型在组织观察顺序、说话方式、抓问题主次、给纠错提示时要遵循的口吻与偏好。

当前可用风格：

- `balanced`
  - 均衡、稳健，默认风格
- `direct`
  - 更直接、更像现场立刻纠错
- `analytical`
  - 更强调结构、对位、力线和因果链
- `competition`
  - 更像比赛复盘和做组复盘
- `plainspoken`
  - 更大白话、更接地气

当前服务端通过环境变量选择：

```bash
SSC_COACH_SOUL=balanced
SSC_COACH_SOUL=direct
SSC_COACH_SOUL=analytical
SSC_COACH_SOUL=competition
SSC_COACH_SOUL=plainspoken
```

默认值是 `balanced`。
