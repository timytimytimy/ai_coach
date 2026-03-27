import 'dart:async';
import 'dart:ui';

import 'package:flutter/material.dart';
import 'package:video_player/video_player.dart';

import 'api.dart';
import 'platform_video_source.dart';
import 'screens/stubs/analysis_screen.dart';
import 'screens/stubs/plan_screen.dart';
import 'screens/stubs/profile_screen.dart';

void main() {
  WidgetsFlutterBinding.ensureInitialized();
  runApp(const SmartStrengthCoachApp());
}

class SmartStrengthCoachApp extends StatelessWidget {
  const SmartStrengthCoachApp({super.key});

  @override
  Widget build(BuildContext context) {
    return MaterialApp(
      title: 'Smart Strength Coach',
      theme: ThemeData.dark(useMaterial3: true),
      home: const RootTabs(),
    );
  }
}

class RootTabs extends StatefulWidget {
  const RootTabs({super.key});

  @override
  State<RootTabs> createState() => _RootTabsState();
}

class _RootTabsState extends State<RootTabs> {
  int _index = 0;

  @override
  Widget build(BuildContext context) {
    final pages = <Widget>[
      const TrainingScreen(),
      const AnalysisScreen(),
      const PlanScreen(),
      const ProfileScreen(),
    ];

    return Scaffold(
      body: pages[_index],
      bottomNavigationBar: NavigationBar(
        selectedIndex: _index,
        onDestinationSelected: (i) => setState(() => _index = i),
        destinations: const [
          NavigationDestination(icon: Icon(Icons.fitness_center), label: 'VBT'),
          NavigationDestination(icon: Icon(Icons.analytics), label: '分析'),
          NavigationDestination(icon: Icon(Icons.calendar_month), label: '计划'),
          NavigationDestination(icon: Icon(Icons.person), label: '我的'),
        ],
      ),
    );
  }
}

int _clampInt(int v, int min, int max) => v < min ? min : (v > max ? max : v);

class _AnalysisProgress {
  const _AnalysisProgress({
    required this.label,
    required this.value,
  });

  final String label;
  final double? value;
}

class TrainingScreen extends StatefulWidget {
  const TrainingScreen({super.key});

  @override
  State<TrainingScreen> createState() => _TrainingScreenState();
}

class _TrainingScreenState extends State<TrainingScreen> {
  final _api = Api(const String.fromEnvironment('SSC_API',
      defaultValue: 'http://localhost:8000'));

  String? _workoutId;
  String? _lastSetId;
  String? _lastJobId;
  PickedVideo? _pickedVideo;
  bool _isAnalyzing = false;
  bool _debugVisible = false;
  String _status = '';
  _AnalysisProgress? _analysisProgress;
  _VbtLive? _vbtLive;
  _OverlayDebug? _overlayDebug;
  _PlaybackUiState _playbackUi =
      const _PlaybackUiState(isPlaying: false, isCompleted: false);

  Future<void> _pollJob(String jobId) async {
    final started = DateTime.now();
    const timeout = Duration(seconds: 180);

    while (DateTime.now().difference(started) < timeout) {
      final job = await _api.getJob(jobId);
      final status = job['status'] as String;
      final progress = job['progress'] as Map<String, dynamic>?;
      final stage = progress?['stage'] as String?;
      final pct = progress?['pct'] as num?;
      setState(() {
        _status = 'Job: $status ${stage ?? ''} ${(pct ?? 0) * 100 ~/ 1}%';
        _analysisProgress = _progressForStage(stage, pct?.toDouble());
      });
      if (status == 'succeeded') return;
      if (status == 'failed') {
        final failedStage = job['failedStage'];
        final failureReason = job['failureReason'];
        final suffix = [
          if (failedStage is String && failedStage.isNotEmpty) failedStage,
          if (failureReason is String && failureReason.isNotEmpty)
            failureReason,
        ].join(': ');
        throw Exception(suffix.isEmpty ? 'Job failed' : 'Job failed: $suffix');
      }
      await Future<void>.delayed(const Duration(milliseconds: 600));
    }

    throw Exception('Job timeout');
  }

  Future<void> _pickVideoAndAnalyze() async {
    try {
      setState(() {
        _isAnalyzing = true;
        _status = '选择视频…';
        _analysisProgress = const _AnalysisProgress(label: '选择视频', value: null);
        _lastJobId = null;
        _lastSetId = null;
        _pickedVideo = null;
        _vbtLive = null;
        _playbackUi =
            const _PlaybackUiState(isPlaying: false, isCompleted: false);
      });

      final pv = await pickVideo();
      if (pv == null) {
        if (!mounted) return;
        setState(() => _status = '已取消');
        return;
      }

      setState(() {
        _status = '创建训练…';
        _analysisProgress = const _AnalysisProgress(label: '创建训练', value: null);
        _pickedVideo = pv;
      });

      final workoutId = await _api
          .createWorkout(DateTime.now().toIso8601String().substring(0, 10));

      setState(() {
        _workoutId = workoutId;
        _status = '注册视频…';
        _analysisProgress = const _AnalysisProgress(label: '注册视频', value: null);
      });

      final video = await _api.createVideoStub();
      final requestedVideoId = video['videoId'] as String;

      setState(() {
        _status = '上传视频…';
        _analysisProgress = const _AnalysisProgress(label: '上传视频', value: null);
      });

      final up =
          await _api.uploadVideo(videoId: requestedVideoId, pickedVideo: pv);
      final canonicalVideoId = (up['videoId'] as String?) ?? requestedVideoId;
      final serverSha = (up['sha256'] as String?) ?? pv.sha256;

      await _api.finalizeVideoStub(
        videoId: canonicalVideoId,
        sha256: serverSha,
        durationMs: _clampInt(pv.durationMs, 0, 3600000),
        fps: 30,
        width: _clampInt(pv.width, 1, 10000),
        height: _clampInt(pv.height, 1, 10000),
      );

      setState(() {
        _status = '创建训练组…';
        _analysisProgress =
            const _AnalysisProgress(label: '创建训练组', value: null);
      });

      final setId = await _api.createSet(
        workoutId: workoutId,
        exercise: 'squat',
        weightKg: 140,
        repsDone: 5,
        videoId: canonicalVideoId,
      );

      setState(() {
        _lastSetId = setId;
        _status = '排队分析…';
        _analysisProgress = const _AnalysisProgress(label: '排队分析', value: 0.0);
      });

      final job =
          await _api.createAnalysisJob(setId: setId, videoSha256: serverSha);
      final jobId = job['jobId'] as String;

      setState(() {
        _lastJobId = jobId;
        _status = '分析中…';
        _analysisProgress = const _AnalysisProgress(label: '分析中', value: 0.0);
      });

      await _pollJob(jobId);

      if (!mounted) return;
      setState(() {
        _status = '完成';
        _analysisProgress = null;
      });
    } catch (e) {
      if (!mounted) return;
      setState(() {
        _status = 'Error: $e';
        _analysisProgress = null;
      });
    } finally {
      if (!mounted) return;
      setState(() => _isAnalyzing = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    final hasVideo = _pickedVideo != null && _lastSetId != null;
    final showBottomBar =
        !hasVideo || !_playbackUi.isPlaying || _playbackUi.isCompleted;

    return Scaffold(
      backgroundColor: Colors.black,
      body: Stack(
        fit: StackFit.expand,
        children: [
          if (hasVideo)
            TrajectoryOverlayScreen(
              api: _api,
              setId: _lastSetId!,
              pickedVideo: _pickedVideo!,
              analysisProgress: _analysisProgress,
              compact: true,
              onVbtLive: (v) {
                if (!mounted) return;
                setState(() => _vbtLive = v);
              },
              onDebug: (d) {
                if (!mounted) return;
                setState(() => _overlayDebug = d);
              },
              onPlaybackState: (s) {
                if (!mounted) return;
                setState(() => _playbackUi = s);
              },
            )
          else
            Container(
              decoration: const BoxDecoration(
                gradient: LinearGradient(
                  colors: [Color(0xFF101316), Color(0xFF050607)],
                  begin: Alignment.topCenter,
                  end: Alignment.bottomCenter,
                ),
              ),
              child: const Center(
                child: Icon(Icons.play_circle_outline,
                    size: 88, color: Colors.white24),
              ),
            ),
          if (hasVideo)
            Positioned(
              left: 14,
              right: 14,
              top: 10,
              child: SafeArea(
                bottom: false,
                child: Align(
                  alignment: Alignment.topLeft,
                  child: _MetricsPanel(live: _vbtLive),
                ),
              ),
            ),
          Positioned(
            right: 12,
            top: 78,
            child: GestureDetector(
              onTap: () => setState(() => _debugVisible = !_debugVisible),
              child: Container(
                width: 14,
                height: 14,
                decoration: BoxDecoration(
                  color:
                      _debugVisible ? const Color(0xFF25D3B8) : Colors.white24,
                  shape: BoxShape.circle,
                  border: Border.all(
                      color: Colors.black.withOpacity(0.35), width: 1),
                ),
              ),
            ),
          ),
          if (_debugVisible)
            Positioned(
              left: 12,
              right: 12,
              top: 96,
              child: _DebugOverlay(
                workoutId: _workoutId,
                setId: _lastSetId,
                jobId: _lastJobId,
                videoSha256: _pickedVideo?.sha256,
                uiStatus: _status,
                overlay: _overlayDebug,
                onClose: () => setState(() => _debugVisible = false),
              ),
            ),
          Positioned(
            left: 0,
            right: 0,
            bottom: 0,
            child: SafeArea(
              top: false,
              child: Padding(
                padding: const EdgeInsets.fromLTRB(16, 10, 16, 14),
                child: IgnorePointer(
                  ignoring: !showBottomBar,
                  child: AnimatedSlide(
                    offset: showBottomBar ? Offset.zero : const Offset(0, 0.24),
                    duration: const Duration(milliseconds: 220),
                    curve: Curves.easeOutCubic,
                    child: AnimatedOpacity(
                      opacity: showBottomBar ? 1 : 0,
                      duration: const Duration(milliseconds: 180),
                      curve: Curves.easeOut,
                      child: _BottomBar(
                        onImport: _isAnalyzing ? null : _pickVideoAndAnalyze,
                      ),
                    ),
                  ),
                ),
              ),
            ),
          ),
        ],
      ),
    );
  }
}

class _VbtHudEntry {
  const _VbtHudEntry({
    required this.repIndex,
    required this.totalReps,
    required this.avgVelocityMps,
  });

  final int repIndex;
  final int totalReps;
  final double avgVelocityMps;
}

class _VbtLive {
  const _VbtLive({required this.totalReps, required this.recentEntries});

  final int totalReps;
  final List<_VbtHudEntry> recentEntries;
}

class _PlaybackUiState {
  const _PlaybackUiState({required this.isPlaying, required this.isCompleted});

  final bool isPlaying;
  final bool isCompleted;
}

class _OverlayDebug {
  const _OverlayDebug({
    required this.reportStatus,
    required this.barbellError,
    required this.overlayError,
    required this.points,
    required this.totalFrames,
    required this.nowMs,
  });

  final String? reportStatus;
  final String? barbellError;
  final String? overlayError;
  final int points;
  final int totalFrames;
  final int nowMs;
}

class _MetricsPanel extends StatelessWidget {
  const _MetricsPanel({required this.live});

  final _VbtLive? live;

  @override
  Widget build(BuildContext context) {
    final live0 = live;
    final entries = live0?.recentEntries ?? const <_VbtHudEntry>[];

    return _MetricChip(
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          if (entries.isEmpty)
            _MetricRow(
              label: live0 == null ? 'Rep —' : 'Rep —/${live0.totalReps}',
              value: '— m/s',
              emphasized: true,
            )
          else
            for (var i = 0; i < entries.length; i++) ...[
              if (i > 0) const SizedBox(height: 8),
              _MetricRow(
                label: 'Rep ${entries[i].repIndex}/${entries[i].totalReps}',
                value: '${entries[i].avgVelocityMps.toStringAsFixed(2)} m/s',
                emphasized: i == entries.length - 1,
              ),
            ],
        ],
      ),
    );
  }
}

class _MetricChip extends StatelessWidget {
  const _MetricChip({required this.child});

  final Widget child;

  @override
  Widget build(BuildContext context) {
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 12),
      decoration: BoxDecoration(
        color: const Color(0xFF171A1F).withOpacity(0.68),
        borderRadius: BorderRadius.circular(18),
        border: Border.all(color: Colors.white.withOpacity(0.12)),
      ),
      child: child,
    );
  }
}

class _MetricRow extends StatelessWidget {
  const _MetricRow({
    required this.label,
    required this.value,
    required this.emphasized,
  });

  final String label;
  final String value;
  final bool emphasized;

  @override
  Widget build(BuildContext context) {
    final labelStyle = Theme.of(context).textTheme.labelMedium?.copyWith(
          color: Colors.white.withOpacity(emphasized ? 0.92 : 0.66),
          fontWeight: FontWeight.w600,
        );
    final valueStyle = Theme.of(context).textTheme.bodyMedium?.copyWith(
          color: Colors.white,
          fontWeight: emphasized ? FontWeight.w800 : FontWeight.w700,
        );

    return Row(
      mainAxisSize: MainAxisSize.min,
      children: [
        Text(label, style: labelStyle),
        const SizedBox(width: 12),
        Text(value, style: valueStyle),
      ],
    );
  }
}

_AnalysisProgress _progressForStage(String? stage, double? pct) {
  final value = pct == null ? null : pct.clamp(0.0, 1.0);
  switch (stage) {
    case 'queued':
      return _AnalysisProgress(label: '排队分析', value: value ?? 0.0);
    case 'transcode':
      return _AnalysisProgress(label: '处理视频', value: value ?? 0.10);
    case 'pose_infer':
      return _AnalysisProgress(label: '提取动作', value: value ?? 0.35);
    case 'bar_detect':
      return _AnalysisProgress(label: '识别杠铃', value: value ?? 0.60);
    case 'findings':
      return _AnalysisProgress(label: '生成结果', value: value ?? 0.80);
    case 'done':
      return _AnalysisProgress(label: '完成', value: 1.0);
    default:
      return _AnalysisProgress(label: '分析中', value: value);
  }
}

class _DebugOverlay extends StatelessWidget {
  const _DebugOverlay({
    required this.workoutId,
    required this.setId,
    required this.jobId,
    required this.videoSha256,
    required this.uiStatus,
    required this.overlay,
    required this.onClose,
  });

  final String? workoutId;
  final String? setId;
  final String? jobId;
  final String? videoSha256;
  final String uiStatus;
  final _OverlayDebug? overlay;
  final VoidCallback onClose;

  @override
  Widget build(BuildContext context) {
    final o = overlay;
    String line(String k, String? v) =>
        '$k: ${v == null || v.isEmpty ? '-' : v}';

    return Container(
      padding: const EdgeInsets.all(12),
      decoration: BoxDecoration(
        color: const Color(0xFF0F1113).withOpacity(0.86),
        borderRadius: BorderRadius.circular(12),
        border: Border.all(color: Colors.white.withOpacity(0.10)),
      ),
      child: DefaultTextStyle(
        style: Theme.of(context)
                .textTheme
                .bodySmall
                ?.copyWith(color: Colors.white.withOpacity(0.88)) ??
            TextStyle(color: Colors.white.withOpacity(0.88)),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.stretch,
          children: [
            Row(
              children: [
                const Expanded(child: Text('Debug')),
                IconButton(
                  onPressed: onClose,
                  icon: const Icon(Icons.close),
                  tooltip: 'Close',
                ),
              ],
            ),
            Text(line('workoutId', workoutId)),
            Text(line('setId', setId)),
            Text(line('jobId', jobId)),
            Text(line('sha256', videoSha256)),
            Text(line('uiStatus', uiStatus)),
            const SizedBox(height: 8),
            Text(line('reportStatus', o?.reportStatus)),
            Text(line('barbellError', o?.barbellError)),
            Text(line('overlayError', o?.overlayError)),
            Text(
                'points: ${o == null ? '-' : '${o.points}/${o.totalFrames}'}   nowMs: ${o?.nowMs ?? '-'}'),
          ],
        ),
      ),
    );
  }
}

class _BottomBar extends StatelessWidget {
  const _BottomBar({required this.onImport});

  final VoidCallback? onImport;

  @override
  Widget build(BuildContext context) {
    final fg = Colors.white.withOpacity(0.85);

    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 10),
      decoration: BoxDecoration(
        color: const Color(0xFF111316).withOpacity(0.92),
        borderRadius: BorderRadius.circular(18),
        border: Border.all(color: Colors.white.withOpacity(0.08)),
      ),
      child: Row(
        children: [
          Expanded(
            child: _BottomAction(
              icon: Icons.videocam_outlined,
              label: 'Record',
              enabled: false,
              onTap: null,
              color: fg,
            ),
          ),
          Expanded(
            child: _BottomAction(
              icon: Icons.photo_library_outlined,
              label: 'Import',
              enabled: onImport != null,
              onTap: onImport,
              color: fg,
            ),
          ),
        ],
      ),
    );
  }
}

class _BottomAction extends StatelessWidget {
  const _BottomAction(
      {required this.icon,
      required this.label,
      required this.enabled,
      required this.onTap,
      required this.color});

  final IconData icon;
  final String label;
  final bool enabled;
  final VoidCallback? onTap;
  final Color color;

  @override
  Widget build(BuildContext context) {
    final c = enabled ? color : Colors.white24;
    return InkWell(
      onTap: enabled ? onTap : null,
      borderRadius: BorderRadius.circular(12),
      child: Padding(
        padding: const EdgeInsets.symmetric(vertical: 6),
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            Icon(icon, color: c),
            const SizedBox(height: 4),
            Text(label,
                style:
                    Theme.of(context).textTheme.bodySmall?.copyWith(color: c)),
          ],
        ),
      ),
    );
  }
}

class _TrajectoryFrame {
  const _TrajectoryFrame({
    required this.timeMs,
    required this.point,
    required this.bbox,
    required this.conf,
    required this.segmentId,
  });

  final int timeMs;
  final Offset? point;
  final Rect? bbox;
  final double? conf;
  final int? segmentId;
}

class _OverlayStream {
  const _OverlayStream({
    required this.frameWidth,
    required this.frameHeight,
    required this.maxGapMs,
    required this.frames,
  });

  final int frameWidth;
  final int frameHeight;
  final int maxGapMs;
  final List<_TrajectoryFrame> frames;
}

_OverlayStream? _extractOverlayStream(Map<String, dynamic> report) {
  final meta = report['meta'];
  if (meta is! Map) return null;
  final overlay = meta['overlay'];
  if (overlay is! Map) return null;
  final w = overlay['frameWidth'];
  final h = overlay['frameHeight'];
  final gap = overlay['maxGapMs'];
  final frames = overlay['frames'];
  if (w is! num || h is! num || gap is! num || frames is! List) return null;

  final wi = w.toInt();
  final hi = h.toInt();
  final gi = gap.toInt();
  if (wi <= 0 || hi <= 0 || gi <= 0) return null;

  final out = <_TrajectoryFrame>[];
  for (final f in frames) {
    if (f is! Map) continue;
    final t = f['timeMs'];
    if (t is! num) continue;
    final segmentIdValue = f['segmentId'];
    final segmentId = segmentIdValue is num ? segmentIdValue.toInt() : null;
    final pointNode = f['point'];
    final bboxNode = f['bbox'];
    final point = pointNode is Map
        ? _extractPoint(pointNode.cast<String, dynamic>())
        : null;
    final bbox = bboxNode is Map ? _extractBbox({'bbox': bboxNode}) : null;
    final confValue = f['conf'];
    final conf = confValue is num ? confValue.toDouble() : null;
    out.add(
      _TrajectoryFrame(
        timeMs: t.toInt(),
        point: point,
        bbox: bbox,
        conf: conf,
        segmentId: segmentId,
      ),
    );
  }

  out.sort((a, b) => a.timeMs.compareTo(b.timeMs));
  return _OverlayStream(
      frameWidth: wi, frameHeight: hi, maxGapMs: gi, frames: out);
}

Offset? _extractPoint(Map<String, dynamic>? node) {
  if (node == null) return null;
  final x = node['x'];
  final y = node['y'];
  if (x is! num || y is! num) return null;
  return Offset(x.toDouble(), y.toDouble());
}

Rect? _extractBbox(Map<String, dynamic>? node) {
  if (node == null) return null;
  final b = node['bbox'];
  if (b is! Map) return null;
  final x1 = b['x1'];
  final y1 = b['y1'];
  final x2 = b['x2'];
  final y2 = b['y2'];
  if (x1 is! num || y1 is! num || x2 is! num || y2 is! num) return null;
  return Rect.fromLTRB(
      x1.toDouble(), y1.toDouble(), x2.toDouble(), y2.toDouble());
}

String? _extractOverlayError(Map<String, dynamic>? report) {
  if (report == null) return null;
  final meta = report['meta'];
  if (meta is! Map) return null;
  final overlay = meta['overlay'];
  if (overlay is! Map) return null;
  final err = overlay['error'];
  if (err is! String || err.isEmpty) return null;
  return err;
}

_TrajectoryFrame? _sampleNearestFrame(List<_TrajectoryFrame> frames, int nowMs,
    {required int maxGapMs}) {
  if (frames.isEmpty) return null;

  var lo = 0;
  var hi = frames.length - 1;
  while (lo < hi) {
    final mid = (lo + hi + 1) >> 1;
    if (frames[mid].timeMs <= nowMs) {
      lo = mid;
    } else {
      hi = mid - 1;
    }
  }

  var best = lo;
  if (best + 1 < frames.length) {
    final a = frames[best];
    final b = frames[best + 1];
    if ((b.timeMs - nowMs).abs() < (nowMs - a.timeMs).abs()) {
      best = best + 1;
    }
  }

  for (var step = 0; step < 30; step += 1) {
    final i0 = best - step;
    if (i0 >= 0) {
      final f0 = frames[i0];
      if ((f0.point != null || f0.bbox != null) &&
          f0.segmentId != null &&
          (f0.timeMs - nowMs).abs() <= maxGapMs) {
        return f0;
      }
    }
    final i1 = best + step;
    if (i1 < frames.length) {
      final f1 = frames[i1];
      if ((f1.point != null || f1.bbox != null) &&
          f1.segmentId != null &&
          (f1.timeMs - nowMs).abs() <= maxGapMs) {
        return f1;
      }
    }
  }

  return null;
}

Offset? _sampleTrajectoryPoint(List<_TrajectoryFrame> frames, int nowMs,
    {required int maxGapMs}) {
  if (frames.isEmpty) return null;

  var lo = 0;
  var hi = frames.length - 1;
  while (lo < hi) {
    final mid = (lo + hi + 1) >> 1;
    if (frames[mid].timeMs <= nowMs) {
      lo = mid;
    } else {
      hi = mid - 1;
    }
  }

  int i0 = lo;
  while (
      i0 >= 0 && (frames[i0].point == null || frames[i0].segmentId == null)) {
    i0 -= 1;
  }
  if (i0 < 0) return null;

  int i1 = i0 + 1;
  while (i1 < frames.length &&
      (frames[i1].point == null || frames[i1].segmentId == null)) {
    i1 += 1;
  }

  if (i1 >= frames.length) {
    final last = frames[i0];
    return (nowMs - last.timeMs).abs() <= maxGapMs ? last.point : null;
  }

  final a = frames[i0];
  final b = frames[i1];
  if (a.segmentId == null || b.segmentId == null || a.segmentId != b.segmentId)
    return null;
  if (nowMs <= a.timeMs)
    return (nowMs - a.timeMs).abs() <= maxGapMs ? a.point : null;
  if (nowMs >= b.timeMs)
    return (nowMs - b.timeMs).abs() <= maxGapMs ? b.point : null;

  final denom = (b.timeMs - a.timeMs).toDouble();
  if (denom <= 0 || denom > maxGapMs) return null;
  final t = (nowMs - a.timeMs) / denom;
  final p0 = a.point!;
  final p1 = b.point!;
  return Offset(p0.dx + (p1.dx - p0.dx) * t, p0.dy + (p1.dy - p0.dy) * t);
}

class TrajectoryOverlayScreen extends StatefulWidget {
  const TrajectoryOverlayScreen({
    super.key,
    required this.api,
    required this.setId,
    required this.pickedVideo,
    this.analysisProgress,
    this.compact = false,
    this.onVbtLive,
    this.onDebug,
    this.onPlaybackState,
  });

  final Api api;
  final String setId;
  final PickedVideo pickedVideo;
  final _AnalysisProgress? analysisProgress;
  final bool compact;
  final ValueChanged<_VbtLive>? onVbtLive;
  final ValueChanged<_OverlayDebug>? onDebug;
  final ValueChanged<_PlaybackUiState>? onPlaybackState;

  @override
  State<TrajectoryOverlayScreen> createState() =>
      _TrajectoryOverlayScreenState();
}

class _TrajectoryOverlayScreenState extends State<TrajectoryOverlayScreen> {
  Object? _err;
  Map<String, dynamic>? _report;
  List<_TrajectoryFrame> _frames = const [];
  VideoPlayerController? _vc;

  int _nowMs = 0;
  int _lastTickMs = 0;
  String _lastDebugSig = '';
  String _lastVbtSig = '';
  String _lastPlaybackSig = '';

  Size? _serverFrameSize;
  int _overlayMaxGapMs = 180;

  Timer? _pollTimer;
  Timer? _playbackControlTimer;
  List<_VbtRep> _vbtReps = const [];
  bool _showPlaybackControl = true;

  @override
  void initState() {
    super.initState();
    unawaited(_load());
  }

  @override
  void dispose() {
    _pollTimer?.cancel();
    _playbackControlTimer?.cancel();
    _vc?.removeListener(_onVideoTick);
    _vc?.dispose();
    unawaited(widget.pickedVideo.dispose());
    super.dispose();
  }

  void _emitDebug() {
    final report = _report;

    String? reportStatus;
    String? barbellError;
    if (report != null) {
      reportStatus =
          (report['status'] is String) ? report['status'] as String : null;
      final meta = report['meta'];
      if (meta is Map) {
        final barbell = meta['barbell'];
        if (barbell is Map) {
          final err = barbell['error'];
          if (err is String && err.isNotEmpty) {
            barbellError = err;
          }
        }
      }
    }

    final overlayError = _err?.toString() ?? _extractOverlayError(report);
    final points = _frames.where((f) => f.point != null).length;
    final total = _frames.length;

    final sig =
        '${reportStatus ?? '-'}|${barbellError ?? '-'}|${overlayError ?? '-'}|$points|$total|$_nowMs';
    if (sig == _lastDebugSig) return;
    _lastDebugSig = sig;

    final cb = widget.onDebug;
    if (cb == null) return;
    cb(
      _OverlayDebug(
        reportStatus: reportStatus,
        barbellError: barbellError,
        overlayError: overlayError,
        points: points,
        totalFrames: total,
        nowMs: _nowMs,
      ),
    );
  }

  void _emitVbt() {
    final cb = widget.onVbtLive;
    if (cb == null) return;

    final recentEntries = _recentCompletedEntries(_vbtReps, _nowMs);
    final sig = '${_vbtReps.length}|'
        '${recentEntries.map((e) => '${e.repIndex}:${e.avgVelocityMps.toStringAsFixed(3)}').join('|')}';
    if (sig == _lastVbtSig) return;
    _lastVbtSig = sig;

    cb(_VbtLive(totalReps: _vbtReps.length, recentEntries: recentEntries));
  }

  void _emitPlaybackState() {
    final cb = widget.onPlaybackState;
    final vc = _vc;
    if (cb == null || vc == null) return;

    final value = vc.value;
    final state = _PlaybackUiState(
      isPlaying: value.isPlaying,
      isCompleted: _isPlaybackCompleted(value),
    );
    final sig = '${state.isPlaying}|${state.isCompleted}';
    if (sig == _lastPlaybackSig) return;
    _lastPlaybackSig = sig;
    cb(state);
  }

  void _armPlaybackControlFade() {
    _playbackControlTimer?.cancel();
    final vc = _vc;
    if (vc == null) return;
    final value = vc.value;
    if (!value.isPlaying || _isPlaybackCompleted(value)) return;
    _playbackControlTimer = Timer(const Duration(milliseconds: 900), () {
      if (!mounted) return;
      setState(() => _showPlaybackControl = false);
    });
  }

  void _revealPlaybackControl({bool scheduleFade = false}) {
    _playbackControlTimer?.cancel();
    if (!mounted) return;
    if (!_showPlaybackControl) {
      setState(() => _showPlaybackControl = true);
    }
    if (scheduleFade) {
      _armPlaybackControlFade();
    }
  }

  void _handleSurfaceTap() {
    final vc = _vc;
    if (vc == null || _showPlaybackControl) return;
    _revealPlaybackControl(
        scheduleFade: vc.value.isPlaying && !_isPlaybackCompleted(vc.value));
  }

  void _onVideoTick() {
    final vc = _vc;
    if (vc == null) return;
    if (!mounted) return;

    final now = DateTime.now().millisecondsSinceEpoch;
    if (now - _lastTickMs < 33) return;
    _lastTickMs = now;

    final value = vc.value;
    final shouldShowControl = !value.isPlaying || _isPlaybackCompleted(value);
    setState(() {
      _nowMs = value.position.inMilliseconds;
      if (shouldShowControl) {
        _showPlaybackControl = true;
      }
    });
    if (shouldShowControl) {
      _playbackControlTimer?.cancel();
    }

    _emitVbt();
    _emitDebug();
    _emitPlaybackState();
  }

  Future<void> _load() async {
    try {
      final vc0 = _vc;
      if (vc0 == null) {
        final vc = await widget.pickedVideo.createController();
        vc.addListener(_onVideoTick);
        if (!mounted) {
          await vc.dispose();
          return;
        }
        setState(() {
          _vc = vc;
          _nowMs = 0;
          _showPlaybackControl = true;
        });
        _emitPlaybackState();
      }

      final rep = await widget.api.getReport(widget.setId);
      final overlay = _extractOverlayStream(rep);
      final frames = overlay?.frames ?? const <_TrajectoryFrame>[];
      final vbtReps = _extractVbtReps(rep);
      final serverSize = overlay == null
          ? null
          : Size(overlay.frameWidth.toDouble(), overlay.frameHeight.toDouble());

      if (!mounted) return;

      setState(() {
        _err = null;
        _report = rep;
        _frames = frames;
        _vbtReps = vbtReps;
        _serverFrameSize = serverSize;
        _overlayMaxGapMs = overlay?.maxGapMs ?? 180;
      });

      _emitVbt();
      _emitDebug();
      _emitPlaybackState();

      final status = rep['status'];
      if (status == 'pending') {
        final vc = _vc;
        if (vc != null && vc.value.isPlaying) {
          unawaited(vc.pause());
        }
        _revealPlaybackControl();
        _emitPlaybackState();

        _pollTimer ??= Timer.periodic(const Duration(seconds: 1), (_) {
          if (!mounted) return;
          unawaited(_load());
        });
      } else {
        _pollTimer?.cancel();
        _pollTimer = null;

        final vc = _vc;
        if (vc != null && !vc.value.isPlaying) {
          unawaited(vc.play());
          _revealPlaybackControl(scheduleFade: true);
        }
        _emitPlaybackState();
      }
    } catch (e) {
      if (!mounted) return;
      setState(() => _err = e);
    }
  }

  Future<void> _toggle() async {
    final vc = _vc;
    if (vc == null) return;
    final report = _report;
    final status = report != null && report['status'] is String
        ? report['status'] as String
        : null;
    if (status == null || status == 'pending') return;
    try {
      if (_isPlaybackCompleted(vc.value)) {
        await vc.seekTo(Duration.zero);
        await vc.play();
        _revealPlaybackControl(scheduleFade: true);
      } else if (vc.value.isPlaying) {
        await vc.pause();
        _revealPlaybackControl();
      } else {
        await vc.play();
        _revealPlaybackControl(scheduleFade: true);
      }
      if (!mounted) return;
      setState(() {});
      _emitPlaybackState();
    } catch (e) {
      if (!mounted) return;
      setState(() => _err = e);
    }
  }

  bool _isPlaybackCompleted(VideoPlayerValue value) {
    final duration = value.duration;
    if (duration <= Duration.zero) return false;
    return value.position >= duration - const Duration(milliseconds: 120);
  }

  String _playbackActionLabel(VideoPlayerValue value) {
    if (_isPlaybackCompleted(value)) return '重播';
    return value.isPlaying ? '暂停' : '播放';
  }

  IconData _playbackActionIcon(VideoPlayerValue value) {
    if (_isPlaybackCompleted(value)) return Icons.replay_rounded;
    return value.isPlaying ? Icons.pause_rounded : Icons.play_arrow_rounded;
  }

  @override
  Widget build(BuildContext context) {
    final vc = _vc;
    final report = _report;
    final reportStatus = report != null && report['status'] is String
        ? report['status'] as String
        : null;
    final progress = widget.analysisProgress;
    final isAnalysisLoading =
        progress != null || reportStatus == null || reportStatus == 'pending';

    String? barbellError;
    final overlayError = _extractOverlayError(report);
    if (report != null) {
      final meta = report['meta'];
      if (meta is Map) {
        final barbell = meta['barbell'];
        if (barbell is Map) {
          final err = barbell['error'];
          if (err is String && err.isNotEmpty) {
            barbellError = err;
          }
        }
      }
    }

    if (vc == null) {
      return _err == null
          ? const Center(child: CircularProgressIndicator())
          : Center(child: Text('Error: $_err'));
    }

    final sourceSize = _serverFrameSize ??
        ((vc.value.size.width > 0 && vc.value.size.height > 0)
            ? vc.value.size
            : Size(widget.pickedVideo.width.toDouble(),
                widget.pickedVideo.height.toDouble()));
    final playbackLabel = _playbackActionLabel(vc.value);
    final playbackIcon = _playbackActionIcon(vc.value);
    final controlLabel =
        isAnalysisLoading ? (progress?.label ?? '分析中') : playbackLabel;

    final player = Center(
      child: AspectRatio(
        aspectRatio: vc.value.aspectRatio,
        child: Listener(
          behavior: HitTestBehavior.translucent,
          onPointerDown: (_) => _handleSurfaceTap(),
          child: Stack(
            fit: StackFit.expand,
            children: [
              VideoPlayer(vc),
              CustomPaint(
                painter: _TrajectoryPainter(
                  frames: _frames,
                  nowMs: _nowMs,
                  sourceSize: sourceSize,
                  maxGapMs: _overlayMaxGapMs,
                ),
              ),
              Center(
                child: IgnorePointer(
                  ignoring: !_showPlaybackControl || isAnalysisLoading,
                  child: AnimatedOpacity(
                    opacity: _showPlaybackControl ? 1 : 0,
                    duration: const Duration(milliseconds: 220),
                    curve: Curves.easeOut,
                    child: Tooltip(
                      message: controlLabel,
                      child: isAnalysisLoading
                          ? ClipRRect(
                              borderRadius: BorderRadius.circular(28),
                              child: BackdropFilter(
                                filter:
                                    ImageFilter.blur(sigmaX: 18, sigmaY: 18),
                                child: Container(
                                  width: widget.compact ? 164 : 148,
                                  padding:
                                      const EdgeInsets.fromLTRB(16, 16, 16, 14),
                                  decoration: BoxDecoration(
                                    color: const Color(0x66F3F6FA),
                                    borderRadius: BorderRadius.circular(28),
                                    border: Border.all(
                                      color: Colors.white.withOpacity(0.30),
                                    ),
                                    boxShadow: [
                                      BoxShadow(
                                        color: Colors.black.withOpacity(0.08),
                                        blurRadius: 24,
                                        offset: const Offset(0, 10),
                                      ),
                                    ],
                                  ),
                                  child: Column(
                                    mainAxisSize: MainAxisSize.min,
                                    crossAxisAlignment:
                                        CrossAxisAlignment.stretch,
                                    children: [
                                      Row(
                                        children: [
                                          SizedBox(
                                            width: 18,
                                            height: 18,
                                            child: CircularProgressIndicator(
                                              strokeWidth: 2.2,
                                              valueColor:
                                                  const AlwaysStoppedAnimation<
                                                      Color>(Colors.white),
                                              backgroundColor: Colors.white
                                                  .withOpacity(0.22),
                                            ),
                                          ),
                                          const SizedBox(width: 10),
                                          Expanded(
                                            child: Text(
                                              controlLabel,
                                              style: Theme.of(context)
                                                  .textTheme
                                                  .labelLarge
                                                  ?.copyWith(
                                                    color: Colors.white,
                                                    fontWeight: FontWeight.w700,
                                                  ),
                                            ),
                                          ),
                                          if (progress?.value != null)
                                            Text(
                                              '${((progress!.value!) * 100).round()}%',
                                              style: Theme.of(context)
                                                  .textTheme
                                                  .labelMedium
                                                  ?.copyWith(
                                                    color: Colors.white
                                                        .withOpacity(0.88),
                                                    fontWeight: FontWeight.w700,
                                                  ),
                                            ),
                                        ],
                                      ),
                                      const SizedBox(height: 12),
                                      ClipRRect(
                                        borderRadius:
                                            BorderRadius.circular(999),
                                        child: LinearProgressIndicator(
                                          minHeight: 6,
                                          value: progress?.value,
                                          backgroundColor:
                                              Colors.white.withOpacity(0.18),
                                          valueColor:
                                              const AlwaysStoppedAnimation<
                                                  Color>(Color(0xFFF6F8FB)),
                                        ),
                                      ),
                                    ],
                                  ),
                                ),
                              ),
                            )
                          : Material(
                              color: Colors.black.withOpacity(0.22),
                              shape: const CircleBorder(),
                              clipBehavior: Clip.antiAlias,
                              child: InkWell(
                                onTap: _toggle,
                                customBorder: const CircleBorder(),
                                child: SizedBox(
                                  width: widget.compact ? 74 : 68,
                                  height: widget.compact ? 74 : 68,
                                  child: Icon(
                                    playbackIcon,
                                    color: Colors.white,
                                    size: widget.compact ? 38 : 34,
                                  ),
                                ),
                              ),
                            ),
                    ),
                  ),
                ),
              ),
              if (widget.compact)
                Positioned(
                  left: 10,
                  bottom: 10,
                  child: Container(
                    padding:
                        const EdgeInsets.symmetric(horizontal: 10, vertical: 6),
                    decoration: BoxDecoration(
                      color: Colors.black.withOpacity(0.55),
                      borderRadius: BorderRadius.circular(10),
                    ),
                    child: Text(
                      '${(_nowMs / 1000).toStringAsFixed(2)}s',
                      style: Theme.of(context)
                          .textTheme
                          .bodySmall
                          ?.copyWith(color: Colors.white),
                    ),
                  ),
                ),
            ],
          ),
        ),
      ),
    );

    if (widget.compact) {
      return player;
    }

    return Padding(
      padding: const EdgeInsets.all(8),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          Expanded(child: player),
          const SizedBox(height: 8),
          Text(
              'reportStatus: ${report == null ? '-' : report['status'] ?? '-'}'),
          if (barbellError != null) Text('barbellError: $barbellError'),
          if (overlayError != null || _err != null)
            Text('overlayError: ${overlayError ?? _err}'),
          const SizedBox(height: 12),
          Row(
            children: [
              FilledButton.tonal(
                onPressed: isAnalysisLoading ? null : _toggle,
                child: Text(controlLabel),
              ),
              const SizedBox(width: 12),
              Text('${(_nowMs / 1000).toStringAsFixed(2)}s'),
              const Spacer(),
              Text(
                  'points: ${_frames.where((f) => f.point != null).length}/${_frames.length}'),
            ],
          ),
          const SizedBox(height: 8),
          const Text('绿色轨迹来自服务端返回的 canonical overlay（按时间同步）。'),
        ],
      ),
    );
  }
}

class _VbtRep {
  const _VbtRep(
      {required this.repIndex,
      required this.startMs,
      required this.endMs,
      required this.avgVelocityMps});

  final int repIndex;
  final int startMs;
  final int endMs;
  final double avgVelocityMps;
}

List<_VbtRep> _extractVbtReps(Map<String, dynamic> report) {
  final meta = report['meta'];
  if (meta is! Map) return const [];
  final vbt = meta['vbt'];
  if (vbt is! Map) return const [];
  final reps = vbt['reps'];
  if (reps is! List) return const [];

  final out = <_VbtRep>[];
  for (final r in reps) {
    if (r is! Map) continue;
    final idx = r['repIndex'];
    final tr = r['timeRangeMs'];
    final avg = r['avgVelocityMps'];
    if (idx is! num || tr is! Map || avg is! num) continue;
    final s = tr['start'];
    final e = tr['end'];
    if (s is! num || e is! num) continue;
    out.add(_VbtRep(
        repIndex: idx.toInt(),
        startMs: s.toInt(),
        endMs: e.toInt(),
        avgVelocityMps: avg.toDouble()));
  }

  out.sort((a, b) => a.startMs.compareTo(b.startMs));
  return out;
}

List<_VbtHudEntry> _recentCompletedEntries(List<_VbtRep> reps, int nowMs,
    {int maxEntries = 10}) {
  final completed = <_VbtRep>[];
  for (final rep in reps) {
    if (rep.endMs > nowMs) break;
    completed.add(rep);
  }

  if (completed.isEmpty) return const [];

  final start =
      completed.length > maxEntries ? completed.length - maxEntries : 0;
  return [
    for (final rep in completed.sublist(start))
      _VbtHudEntry(
        repIndex: rep.repIndex,
        totalReps: reps.length,
        avgVelocityMps: rep.avgVelocityMps,
      ),
  ];
}

class _TrajectoryPainter extends CustomPainter {
  _TrajectoryPainter({
    required this.frames,
    required this.nowMs,
    required this.sourceSize,
    required this.maxGapMs,
  });

  final List<_TrajectoryFrame> frames;
  final int nowMs;
  final Size sourceSize;
  final int maxGapMs;

  @override
  void paint(Canvas canvas, Size size) {
    if (frames.isEmpty) return;
    if (sourceSize.width <= 0 || sourceSize.height <= 0) return;

    final sx = size.width / sourceSize.width;
    final sy = size.height / sourceSize.height;

    Offset toCanvas(Offset p) {
      return Offset(p.dx * sx, p.dy * sy);
    }

    Rect toCanvasRect(Rect r) {
      return Rect.fromLTRB(
          r.left * sx, r.top * sy, r.right * sx, r.bottom * sy);
    }

    const tailWindowMs = 2500;
    final startMs = nowMs - tailWindowMs;

    final path = Path();
    var started = false;
    int? activeSegmentId;

    for (final f in frames) {
      if (f.timeMs < startMs) continue;
      if (f.timeMs > nowMs) break;
      final p = f.point;
      if (p == null || f.segmentId == null) {
        started = false;
        activeSegmentId = null;
        continue;
      }
      final sp = toCanvas(p);
      if (!started || activeSegmentId != f.segmentId) {
        path.moveTo(sp.dx, sp.dy);
        started = true;
        activeSegmentId = f.segmentId;
      } else {
        path.lineTo(sp.dx, sp.dy);
      }
    }

    final tailPaint = Paint()
      ..color = Colors.greenAccent
      ..style = PaintingStyle.stroke
      ..strokeWidth = 4.0
      ..strokeCap = StrokeCap.round
      ..strokeJoin = StrokeJoin.round;

    canvas.drawPath(path, tailPaint);

    final nearest = _sampleNearestFrame(frames, nowMs, maxGapMs: maxGapMs);
    final bbox = nearest?.bbox;
    if (bbox != null) {
      final boxPaint = Paint()
        ..color = Colors.lightBlueAccent
        ..style = PaintingStyle.stroke
        ..strokeWidth = 3.0;
      canvas.drawRect(toCanvasRect(bbox), boxPaint);
    }

    final cur = _sampleTrajectoryPoint(frames, nowMs, maxGapMs: maxGapMs);
    if (cur != null) {
      final cp = toCanvas(cur);

      final dot = Paint()..color = Colors.redAccent;
      canvas.drawCircle(cp, 6.0, dot);
    }
  }

  @override
  bool shouldRepaint(covariant _TrajectoryPainter oldDelegate) {
    return oldDelegate.nowMs != nowMs ||
        oldDelegate.frames != frames ||
        oldDelegate.sourceSize != sourceSize;
  }
}
