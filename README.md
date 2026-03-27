# Smart Strength Coach

Smart Strength Coach 是一个面向深蹲、卧推、硬拉的视频分析原型项目。当前仓库已经打通了从视频导入、上传、异步分析，到杠铃轨迹叠加和 VBT 展示的主链路，适合继续往“技术问题识别 + 训练建议”方向扩展。

## 当前能力
- Flutter 多端前端，支持导入视频、上传、轮询分析结果、播放分析视频
- FastAPI 后端，支持异步分析任务、SQLite 持久化、本地视频存储
- 杠铃检测、tracking、overlay 生成
- VBT 计算与 rep 级结果输出
- 分析结果以 `report.meta_json` 形式持久化，便于继续扩展 pose、phase、features、fusion

## 仓库结构

```text
trae_projects/
├── app/        Flutter 客户端
├── server/     FastAPI 服务端、分析任务、SQLite、本地视频
├── model/      本地模型文件
├── test/       Python 回归测试
├── DESIGN.md   设计系统说明
└── powerlifting_analysis_implementation_plan_v1.md
```

## 技术栈
- 前端：Flutter
- 后端：FastAPI、Pydantic、Uvicorn
- CV：Ultralytics YOLO、OpenCV
- 存储：SQLite、本地文件目录

## 本地启动

### 1. 启动服务端
项目已经约定使用 `server/.venv`。

```bash
cd /Users/liumiao/Documents/trae_projects
./server/run.sh
```

默认行为：
- 端口：`8000`
- 设备：`mps`
- 杠铃检测采样率：`SSC_BAR_DETECT_FPS=30`

可选环境变量：

```bash
SSC_YOLO_DEVICE=cpu
SSC_LOG_LEVEL=INFO
SSC_BAR_DETECT_FPS=24
```

### 2. 启动前端

```bash
cd /Users/liumiao/Documents/trae_projects/app
flutter run -d chrome
```

调试时常用：
- `r`：hot reload
- `R`：hot restart
- `q`：退出

## 依赖安装

### 服务端
如果需要重建虚拟环境：

```bash
cd /Users/liumiao/Documents/trae_projects
python3.11 -m venv server/.venv
source server/.venv/bin/activate
pip install -r server/requirements.txt
```

### 前端

```bash
cd /Users/liumiao/Documents/trae_projects/app
flutter pub get
```

## 测试

### Python

```bash
cd /Users/liumiao/Documents/trae_projects
server/.venv/bin/python -m unittest discover -s test -p 'test_*.py'
```

### Dart

```bash
cd /Users/liumiao/Documents/trae_projects/app
dart analyze
```

## 当前实现边界
- 当前重点仍然是视频上传、杠铃轨迹、VBT
- 动作问题识别仍处于逐步建设阶段
- 人体姿态检测、动作阶段分割、证据融合还没有完整接入主链路

## 相关文档
- [设计系统](./DESIGN.md)
- [UI 规格](./smart_strength_coach_ui_spec_v1.md)
- [项目 Pitch](./smart_strength_coach_pitch_v1.md)
- [力量举技术分析实现方案](./powerlifting_analysis_implementation_plan_v1.md)
