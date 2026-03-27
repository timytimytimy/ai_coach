# TODO

## App：视频轨迹叠加（杠铃轨迹与视频同步显示）

- [ ] 选定视频播放方案：本地文件还是网络 URL（对应 `VideoPlayerController.file` / `.networkUrl`）
- [ ] 约定轨迹数据来源：从 `/v1/sets/{setId}/report` 的 `meta.barbell.result` 读取（或拆分成独立 endpoint）
- [ ] 服务端补充轨迹坐标系元数据：原始 `frameWidth/frameHeight` + 是否做了旋转归一（`rotation`/`normalized`）
- [ ] Flutter UI 结构：`Stack(VideoPlayer + CustomPaint)`，并用同一个 `AspectRatio` 保证叠加尺寸一致
- [ ] 时间对齐：用 `controller.value.position.inMilliseconds` → 在轨迹 `frames[*].timeMs` 中查找相邻点并做线性插值
- [ ] 坐标映射：把原始像素坐标按 `frameWidth/frameHeight` 缩放到当前渲染尺寸（处理 letterbox/contain 情况）
- [ ] 缺失点策略：`end/plate == null` 时隐藏点、保持上一帧、或断线（产品策略确定）
- [ ] 轨迹渲染样式：点（当前帧）、尾迹折线（最近 N 秒）、end/plate 开关
- [ ] 性能：用 `addListener` + 节流（例如 30fps 或 60fps）避免每毫秒 setState；绘制端做最小重绘
- [ ] 验证：用固定视频 + 固定 JSON 对齐，确认轨迹不漂移（尺寸、旋转、裁剪都正确）