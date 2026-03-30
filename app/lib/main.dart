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

class _AnalysisIssue {
  const _AnalysisIssue({
    required this.code,
    required this.name,
    required this.severity,
    required this.confidence,
    required this.evidenceSource,
    required this.timeLabel,
    required this.startMs,
    required this.endMs,
    required this.visualEvidence,
    required this.kinematicEvidence,
  });

  final String code;
  final String name;
  final String severity;
  final double confidence;
  final String evidenceSource;
  final String timeLabel;
  final int? startMs;
  final int? endMs;
  final String visualEvidence;
  final String kinematicEvidence;
}

class _AnalysisSummary {
  const _AnalysisSummary({
    required this.liftType,
    required this.recognizedLiftType,
    required this.analysisSource,
    required this.coachFocus,
    required this.coachWhy,
    required this.coachNextSet,
    required this.keepWatching,
    required this.cue,
    required this.drills,
    required this.repCount,
    required this.avgRepVelocityMps,
    required this.barPathDriftCm,
    required this.velocityLossPct,
    required this.phaseCount,
    required this.issues,
    required this.topFindings,
    required this.poseUsable,
    required this.poseConfidence,
    required this.posePrimarySide,
    required this.poseFrameCount,
    required this.maxTorsoLeanDeg,
    required this.avgTorsoLeanDeltaDeg,
    required this.minKneeAngleDeg,
    required this.overallScore,
    required this.overallGrade,
    required this.bestRepIndex,
    required this.weakestRepIndex,
    required this.repScores,
    required this.repPoseMetrics,
  });

  final String liftType;
  final String? recognizedLiftType;
  final String analysisSource;
  final String coachFocus;
  final String coachWhy;
  final String coachNextSet;
  final List<String> keepWatching;
  final String cue;
  final List<String> drills;
  final int repCount;
  final double? avgRepVelocityMps;
  final double? barPathDriftCm;
  final double? velocityLossPct;
  final int phaseCount;
  final List<_AnalysisIssue> issues;
  final List<_AnalysisIssue> topFindings;
  final bool poseUsable;
  final double? poseConfidence;
  final String? posePrimarySide;
  final int poseFrameCount;
  final double? maxTorsoLeanDeg;
  final double? avgTorsoLeanDeltaDeg;
  final double? minKneeAngleDeg;
  final int? overallScore;
  final String? overallGrade;
  final int? bestRepIndex;
  final int? weakestRepIndex;
  final Map<int, int> repScores;
  final List<_RepPoseMetrics> repPoseMetrics;
}

class _RepPoseMetrics {
  const _RepPoseMetrics({
    required this.repIndex,
    required this.startMs,
    required this.endMs,
    required this.hipKneeSyncScore,
    required this.hipLeadMs,
  });

  final int repIndex;
  final int? startMs;
  final int? endMs;
  final double? hipKneeSyncScore;
  final int? hipLeadMs;
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
  _AnalysisSummary? _analysisSummary;
  bool _repHudExpanded = false;
  int? _pendingSeekMs;
  String _selectedCoachSoul = 'balanced';
  bool _showPoseOverlay = false;
  bool _hasPoseOverlay = false;

  Future<void> _openSettings() async {
    await Navigator.of(context).push(
      MaterialPageRoute<void>(
        builder: (context) => _OverlaySettingsScreen(
          hasPose: _hasPoseOverlay,
          showPoseOverlay: _hasPoseOverlay && _showPoseOverlay,
          onPoseChanged: _hasPoseOverlay
              ? (value) {
                  if (!mounted) return;
                  setState(() => _showPoseOverlay = value);
                }
              : null,
          coachSoul: _selectedCoachSoul,
          onCoachSoulChanged: (value) {
            if (!mounted) return;
            setState(() => _selectedCoachSoul = value);
          },
        ),
      ),
    );
  }

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
        _analysisSummary = null;
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

      final job = await _api.createAnalysisJob(
        setId: setId,
        videoSha256: serverSha,
        coachSoul: _selectedCoachSoul,
      );
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
              onImport: _isAnalyzing ? null : _pickVideoAndAnalyze,
              coachSoul: _selectedCoachSoul,
              onCoachSoulChanged: (value) {
                if (!mounted) return;
                setState(() => _selectedCoachSoul = value);
              },
              showPoseOverlay: _showPoseOverlay,
              onPoseOverlayChanged: (value) {
                if (!mounted) return;
                setState(() => _showPoseOverlay = value);
              },
              onPoseAvailabilityChanged: (value) {
                if (!mounted) return;
                setState(() {
                  _hasPoseOverlay = value;
                  if (!value) _showPoseOverlay = false;
                });
              },
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
              onAnalysisSummary: (s) {
                if (!mounted) return;
                setState(() => _analysisSummary = s);
              },
              seekToMs: _pendingSeekMs,
              onSeekHandled: () {
                if (!mounted) return;
                setState(() => _pendingSeekMs = null);
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
              child: Center(
                child: _CenterImportButton(
                  onTap: _isAnalyzing ? null : _pickVideoAndAnalyze,
                ),
              ),
            ),
          Positioned(
            top: 10,
            right: 14,
            child: SafeArea(
              bottom: false,
              child: _SettingsLaunchButton(onTap: _openSettings),
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
                  child: _MetricsPanel(
                    live: _vbtLive,
                    summary: _analysisSummary,
                    expanded: _repHudExpanded,
                    onToggleExpanded: () {
                      final live = _vbtLive;
                      if (live == null || live.allEntries.isEmpty) return;
                      setState(() => _repHudExpanded = !_repHudExpanded);
                    },
                  ),
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
          if (hasVideo && _analysisSummary != null)
            Positioned(
              left: 14,
              right: 14,
              bottom: 86,
              child: SafeArea(
                top: false,
                child: _InsightCard(
                  summary: _analysisSummary!,
                  onJumpToMs: (ms) {
                    setState(() => _pendingSeekMs = ms);
                  },
                  onOpenDetails: () {
                    showModalBottomSheet<void>(
                      context: context,
                      isScrollControlled: true,
                      backgroundColor: Colors.transparent,
                      builder: (context) => _AnalysisDetailsSheet(
                        summary: _analysisSummary!,
                        onJumpToMs: (ms) {
                          Navigator.of(context).pop();
                          setState(() => _pendingSeekMs = ms);
                        },
                      ),
                    );
                  },
                ),
              ),
            ),
          Positioned(
            left: 0,
            right: 0,
            bottom: 24,
            child: SafeArea(
              top: false,
              child: Center(
                child: AnimatedOpacity(
                  opacity: 0,
                  duration: const Duration(milliseconds: 180),
                  child: IgnorePointer(
                    ignoring: true,
                    child: _CenterImportButton(
                      onTap: _isAnalyzing ? null : _pickVideoAndAnalyze,
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
  const _VbtLive({
    required this.totalReps,
    required this.recentEntries,
    required this.allEntries,
  });

  final int totalReps;
  final List<_VbtHudEntry> recentEntries;
  final List<_VbtHudEntry> allEntries;
}

class _OverlayDebug {
  const _OverlayDebug({
    required this.reportStatus,
    required this.barbellError,
    required this.overlayError,
    required this.points,
    required this.totalFrames,
    required this.nowMs,
    required this.screeningSummary,
    required this.screeningLines,
  });

  final String? reportStatus;
  final String? barbellError;
  final String? overlayError;
  final int points;
  final int totalFrames;
  final int nowMs;
  final String? screeningSummary;
  final List<String> screeningLines;
}

class _MetricsPanel extends StatelessWidget {
  const _MetricsPanel({
    required this.live,
    required this.summary,
    required this.expanded,
    required this.onToggleExpanded,
  });

  final _VbtLive? live;
  final _AnalysisSummary? summary;
  final bool expanded;
  final VoidCallback onToggleExpanded;

  @override
  Widget build(BuildContext context) {
    final live0 = live;
    final entries = live0?.recentEntries ?? const <_VbtHudEntry>[];
    final current = entries.isNotEmpty ? entries.last : null;
    final label = current == null
        ? (live0 == null ? 'Rep —/—' : 'Rep —/${live0.totalReps}')
        : 'Rep ${current.repIndex}/${current.totalReps}';
    final value = current == null
        ? '— m/s'
        : '${current.avgVelocityMps.toStringAsFixed(2)} m/s';
    final repScores = summary?.repScores ?? const <int, int>{};
    final currentRepScore =
        current == null ? null : repScores[current.repIndex];

    return _MetricChip(
      child: InkWell(
        onTap: onToggleExpanded,
        borderRadius: BorderRadius.circular(18),
        child: Column(
          mainAxisSize: MainAxisSize.min,
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Row(
              mainAxisSize: MainAxisSize.min,
              children: [
                Text(
                  label,
                  style: Theme.of(context).textTheme.titleMedium?.copyWith(
                        color: Colors.white,
                        fontWeight: FontWeight.w800,
                      ),
                ),
                Container(
                  width: 1,
                  height: 22,
                  margin: const EdgeInsets.symmetric(horizontal: 12),
                  color: Colors.white.withOpacity(0.16),
                ),
                Text(
                  value,
                  style: Theme.of(context).textTheme.titleMedium?.copyWith(
                        color: Colors.white.withOpacity(0.92),
                        fontWeight: FontWeight.w700,
                      ),
                ),
                Container(
                  width: 1,
                  height: 22,
                  margin: const EdgeInsets.symmetric(horizontal: 12),
                  color: Colors.white.withOpacity(0.16),
                ),
                Text(
                  currentRepScore == null ? '— 分' : '$currentRepScore 分',
                  style: Theme.of(context).textTheme.titleMedium?.copyWith(
                        color: Colors.white.withOpacity(0.88),
                        fontWeight: FontWeight.w700,
                      ),
                ),
                const SizedBox(width: 10),
                Icon(
                  expanded
                      ? Icons.keyboard_arrow_up_rounded
                      : Icons.keyboard_arrow_down_rounded,
                  color: Colors.white.withOpacity(0.82),
                  size: 22,
                ),
              ],
            ),
            if (expanded && live0 != null && live0.allEntries.isNotEmpty) ...[
              const SizedBox(height: 8),
              ConstrainedBox(
                constraints:
                    const BoxConstraints(maxHeight: 196, minWidth: 220),
                child: SingleChildScrollView(
                  child: Column(
                    mainAxisSize: MainAxisSize.min,
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      for (final entry in live0.allEntries)
                        Container(
                          margin: const EdgeInsets.only(bottom: 6),
                          padding: const EdgeInsets.symmetric(
                              horizontal: 10, vertical: 8),
                          decoration: BoxDecoration(
                            color: Colors.white.withOpacity(0.045),
                            borderRadius: BorderRadius.circular(12),
                            border: Border.all(
                              color: Colors.white.withOpacity(0.05),
                            ),
                          ),
                          child: Row(
                            children: [
                              Text(
                                'Rep ${entry.repIndex}',
                                style: Theme.of(context)
                                    .textTheme
                                    .labelLarge
                                    ?.copyWith(
                                      color: Colors.white.withOpacity(0.90),
                                      fontWeight: FontWeight.w700,
                                      letterSpacing: 0.1,
                                    ),
                              ),
                              const SizedBox(width: 8),
                              Text(
                                '/ ${entry.totalReps}',
                                style: Theme.of(context)
                                    .textTheme
                                    .labelMedium
                                    ?.copyWith(
                                      color: Colors.white.withOpacity(0.42),
                                      fontWeight: FontWeight.w600,
                                    ),
                              ),
                              const Spacer(),
                              Text(
                                '${entry.avgVelocityMps.toStringAsFixed(2)} m/s',
                                style: Theme.of(context)
                                    .textTheme
                                    .labelLarge
                                    ?.copyWith(
                                      color: Colors.white.withOpacity(0.78),
                                      fontWeight: FontWeight.w700,
                                    ),
                              ),
                              if (repScores[entry.repIndex] != null) ...[
                                const SizedBox(width: 10),
                                _MiniInfoPill(
                                  label: '${repScores[entry.repIndex]}分',
                                ),
                              ],
                            ],
                          ),
                        ),
                    ],
                  ),
                ),
              ),
            ],
          ],
        ),
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
      padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 11),
      decoration: BoxDecoration(
        color: const Color(0xFF171A1F).withOpacity(0.54),
        borderRadius: BorderRadius.circular(20),
        border: Border.all(color: Colors.white.withOpacity(0.12)),
      ),
      child: child,
    );
  }
}

class _InsightCard extends StatelessWidget {
  const _InsightCard({
    required this.summary,
    required this.onJumpToMs,
    required this.onOpenDetails,
  });

  final _AnalysisSummary summary;
  final ValueChanged<int> onJumpToMs;
  final VoidCallback onOpenDetails;

  List<_AnalysisIssue> _normalizedIssues() {
    final out = <_AnalysisIssue>[];
    for (final issue in summary.issues) {
      final skip = issue.code == 'grindy_ascent' &&
          out.any((e) =>
              e.code == 'slow_concentric_speed' &&
              e.timeLabel == issue.timeLabel);
      if (!skip) out.add(issue);
    }
    return out;
  }

  @override
  Widget build(BuildContext context) {
    final issues = _normalizedIssues();
    final primaryIssue = issues.isNotEmpty ? issues.first : null;
    final sourceLabel = summary.analysisSource == 'llm' ? 'AI 解读' : '规则';
    final focus = summary.coachFocus.trim().isEmpty
        ? (primaryIssue?.name ?? '分析完成后显示')
        : summary.coachFocus;
    final nextSet = summary.coachNextSet.trim().isEmpty
        ? (summary.cue.trim().isEmpty ? '查看分析详情' : summary.cue)
        : summary.coachNextSet;

    return Material(
      color: Colors.transparent,
      child: InkWell(
        onTap: onOpenDetails,
        borderRadius: BorderRadius.circular(20),
        child: ClipRRect(
          borderRadius: BorderRadius.circular(20),
          child: BackdropFilter(
            filter: ImageFilter.blur(sigmaX: 18, sigmaY: 18),
            child: Container(
              padding: const EdgeInsets.fromLTRB(14, 10, 14, 10),
              decoration: BoxDecoration(
                color: Colors.black.withOpacity(0.38),
                borderRadius: BorderRadius.circular(20),
                border: Border.all(color: Colors.white.withOpacity(0.10)),
              ),
              child: Column(
                mainAxisSize: MainAxisSize.min,
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Row(
                    children: [
                      if (summary.overallScore != null)
                        _MiniInfoPill(
                          label: summary.overallGrade == null ||
                                  summary.overallGrade!.isEmpty
                              ? '总分 ${summary.overallScore}'
                              : '总分 ${summary.overallScore} · ${summary.overallGrade}',
                        ),
                      const Spacer(),
                      if (summary.recognizedLiftType != null &&
                          summary.recognizedLiftType!.isNotEmpty) ...[
                        _MiniInfoPill(
                          label: _liftTypeLabel(summary.recognizedLiftType!),
                        ),
                        const SizedBox(width: 8),
                      ],
                      _MiniInfoPill(label: sourceLabel),
                    ],
                  ),
                  const SizedBox(height: 10),
                  _InsightRow(
                    title: '本次重点',
                    value: focus,
                    maxLines: 1,
                    onTap: primaryIssue?.startMs != null &&
                            primaryIssue?.endMs != null
                        ? () => onJumpToMs(
                              (primaryIssue!.startMs! + primaryIssue.endMs!) ~/
                                  2,
                            )
                        : null,
                    trailing: primaryIssue?.timeLabel,
                  ),
                  const SizedBox(height: 10),
                  _InsightRow(
                    title: '下组建议',
                    value: nextSet,
                    maxLines: 1,
                  ),
                ],
              ),
            ),
          ),
        ),
      ),
    );
  }
}

class _AnalysisDetailsSheet extends StatelessWidget {
  const _AnalysisDetailsSheet({
    required this.summary,
    required this.onJumpToMs,
  });

  final _AnalysisSummary summary;
  final ValueChanged<int> onJumpToMs;

  Color _severityColor(String severity) {
    switch (severity) {
      case 'high':
        return const Color(0xFFEF4444);
      case 'medium':
        return const Color(0xFFF59E0B);
      default:
        return const Color(0xFF60A5FA);
    }
  }

  String _sourceLabel(String source) {
    switch (source) {
      case 'pose':
        return '姿态';
      case 'barbell':
        return '杠铃';
      case 'vbt':
        return 'VBT';
      default:
        return '规则';
    }
  }

  List<_AnalysisIssue> _normalizedIssues() {
    final out = <_AnalysisIssue>[];
    for (final issue in summary.issues) {
      final skip = issue.code == 'grindy_ascent' &&
          out.any((e) =>
              e.code == 'slow_concentric_speed' &&
              e.timeLabel == issue.timeLabel);
      if (!skip) out.add(issue);
    }
    return out;
  }

  _RepPoseMetrics? _matchingPoseMetrics(_AnalysisIssue issue) {
    for (final metric in summary.repPoseMetrics) {
      if (metric.startMs == null ||
          metric.endMs == null ||
          issue.startMs == null ||
          issue.endMs == null) {
        continue;
      }
      final overlapStart =
          issue.startMs! > metric.startMs! ? issue.startMs! : metric.startMs!;
      final overlapEnd =
          issue.endMs! < metric.endMs! ? issue.endMs! : metric.endMs!;
      if (overlapEnd > overlapStart) {
        return metric;
      }
    }
    return null;
  }

  String _drillLabel(String raw) {
    switch (raw) {
      case 'pause squat':
        return '暂停深蹲';
      case 'tempo squat':
        return '节奏深蹲';
      case 'pin squat':
        return '架上蹲';
      case 'squat doubles':
        return '双次组深蹲';
      default:
        return raw;
    }
  }

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final issues = _normalizedIssues();
    final primaryIssue = issues.isNotEmpty ? issues.first : null;
    final primaryPoseMetrics =
        primaryIssue == null ? null : _matchingPoseMetrics(primaryIssue);
    final secondaryIssues = summary.keepWatching.isNotEmpty
        ? summary.keepWatching
        : (issues.length > 1
            ? issues
                .sublist(1, issues.length > 3 ? 3 : issues.length)
                .map((issue) => issue.startMs != null && issue.endMs != null
                    ? '${issue.name} · ${issue.timeLabel}'
                    : issue.name)
                .toList()
            : const <String>[]);
    final drillLabels = [
      for (final drill in summary.drills) _drillLabel(drill),
    ];

    return SafeArea(
      top: false,
      child: Padding(
        padding: const EdgeInsets.fromLTRB(12, 0, 12, 12),
        child: ClipRRect(
          borderRadius: BorderRadius.circular(24),
          child: BackdropFilter(
            filter: ImageFilter.blur(sigmaX: 18, sigmaY: 18),
            child: Container(
              padding: const EdgeInsets.fromLTRB(16, 14, 16, 18),
              decoration: BoxDecoration(
                color: const Color(0xFF111317).withOpacity(0.92),
                borderRadius: BorderRadius.circular(24),
                border: Border.all(color: Colors.white.withOpacity(0.10)),
              ),
              child: SingleChildScrollView(
                child: Column(
                  mainAxisSize: MainAxisSize.min,
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Center(
                      child: Container(
                        width: 44,
                        height: 4,
                        decoration: BoxDecoration(
                          color: Colors.white.withOpacity(0.18),
                          borderRadius: BorderRadius.circular(999),
                        ),
                      ),
                    ),
                    const SizedBox(height: 14),
                    Row(
                      children: [
                        Expanded(
                          child: Column(
                            crossAxisAlignment: CrossAxisAlignment.start,
                            children: [
                              Text(
                                '${_liftTypeLabel(summary.liftType)} · ${summary.repCount} 次',
                                style: theme.textTheme.titleMedium?.copyWith(
                                  color: Colors.white,
                                  fontWeight: FontWeight.w800,
                                ),
                              ),
                            ],
                          ),
                        ),
                        if (summary.overallScore != null) ...[
                          _MiniInfoPill(
                            label: summary.overallGrade == null ||
                                    summary.overallGrade!.isEmpty
                                ? '总分 ${summary.overallScore}'
                                : '总分 ${summary.overallScore} · ${summary.overallGrade}',
                          ),
                          const SizedBox(width: 8),
                        ],
                        if (summary.recognizedLiftType != null &&
                            summary.recognizedLiftType!.isNotEmpty) ...[
                          _MiniInfoPill(
                            label:
                                '识别为 ${_liftTypeLabel(summary.recognizedLiftType!)}',
                          ),
                          const SizedBox(width: 8),
                        ],
                        _MiniInfoPill(
                          label:
                              summary.analysisSource == 'llm' ? 'AI 解读' : '规则',
                        ),
                        const SizedBox(width: 8),
                        if (summary.posePrimarySide != null &&
                            summary.posePrimarySide!.isNotEmpty)
                          _MiniInfoPill(
                            label: summary.posePrimarySide == 'left'
                                ? '左侧视角'
                                : '右侧视角',
                          ),
                      ],
                    ),
                    if (summary.bestRepIndex != null ||
                        summary.weakestRepIndex != null) ...[
                      const SizedBox(height: 12),
                      Wrap(
                        spacing: 8,
                        runSpacing: 8,
                        children: [
                          if (summary.bestRepIndex != null)
                            _MiniInfoPill(
                              label: '最佳 Rep ${summary.bestRepIndex}',
                            ),
                          if (summary.weakestRepIndex != null)
                            _MiniInfoPill(
                              label: '待提升 Rep ${summary.weakestRepIndex}',
                            ),
                        ],
                      ),
                    ],
                    if (primaryIssue != null) ...[
                      const SizedBox(height: 14),
                      Text(
                        '本次重点',
                        style: theme.textTheme.labelMedium?.copyWith(
                          color: Colors.white.withOpacity(0.70),
                          fontWeight: FontWeight.w700,
                        ),
                      ),
                      const SizedBox(height: 8),
                      Container(
                        padding: const EdgeInsets.all(12),
                        decoration: BoxDecoration(
                          color: Colors.white.withOpacity(0.05),
                          borderRadius: BorderRadius.circular(14),
                        ),
                        child: Row(
                          crossAxisAlignment: CrossAxisAlignment.start,
                          children: [
                            Container(
                              width: 10,
                              height: 10,
                              margin: const EdgeInsets.only(top: 6),
                              decoration: BoxDecoration(
                                color: _severityColor(primaryIssue.severity),
                                shape: BoxShape.circle,
                              ),
                            ),
                            const SizedBox(width: 10),
                            Expanded(
                              child: Column(
                                crossAxisAlignment: CrossAxisAlignment.start,
                                children: [
                                  Text(
                                    summary.coachFocus.trim().isNotEmpty
                                        ? summary.coachFocus
                                        : primaryIssue.name,
                                    style: theme.textTheme.titleSmall?.copyWith(
                                      color: Colors.white,
                                      fontWeight: FontWeight.w800,
                                    ),
                                  ),
                                  const SizedBox(height: 6),
                                  Wrap(
                                    spacing: 8,
                                    runSpacing: 8,
                                    children: [
                                      _MiniInfoPill(
                                        label: _sourceLabel(
                                            primaryIssue.evidenceSource),
                                      ),
                                      if (primaryIssue.startMs != null &&
                                          primaryIssue.endMs != null)
                                        GestureDetector(
                                          onTap: () => onJumpToMs(
                                            (primaryIssue.startMs! +
                                                    primaryIssue.endMs!) ~/
                                                2,
                                          ),
                                          child: _MiniInfoPill(
                                            label: primaryIssue.timeLabel,
                                          ),
                                        ),
                                    ],
                                  ),
                                  if (primaryIssue.code ==
                                          'hip_shoot_in_squat' &&
                                      primaryPoseMetrics != null &&
                                      (primaryPoseMetrics.hipKneeSyncScore !=
                                              null ||
                                          primaryPoseMetrics.hipLeadMs !=
                                              null)) ...[
                                    const SizedBox(height: 8),
                                    Wrap(
                                      spacing: 8,
                                      runSpacing: 8,
                                      children: [
                                        if (primaryPoseMetrics
                                                .hipKneeSyncScore !=
                                            null)
                                          _MiniInfoPill(
                                            label:
                                                '同步分数 ${primaryPoseMetrics.hipKneeSyncScore!.toStringAsFixed(2)}',
                                          ),
                                        if (primaryPoseMetrics.hipLeadMs !=
                                            null)
                                          _MiniInfoPill(
                                            label:
                                                '髋领先 ${primaryPoseMetrics.hipLeadMs} ms',
                                          ),
                                      ],
                                    ),
                                  ],
                                  const SizedBox(height: 8),
                                  Text(
                                    summary.coachWhy.trim().isNotEmpty
                                        ? summary.coachWhy
                                        : primaryIssue.kinematicEvidence,
                                    style: theme.textTheme.bodyMedium?.copyWith(
                                      color: Colors.white.withOpacity(0.92),
                                      fontWeight: FontWeight.w700,
                                    ),
                                  ),
                                  const SizedBox(height: 4),
                                  Text(
                                    primaryIssue.visualEvidence,
                                    style: theme.textTheme.bodySmall?.copyWith(
                                      color: Colors.white.withOpacity(0.72),
                                    ),
                                  ),
                                ],
                              ),
                            ),
                            const SizedBox(width: 8),
                            Text(
                              '${(primaryIssue.confidence * 100).round()}%',
                              style: theme.textTheme.labelMedium?.copyWith(
                                color: Colors.white.withOpacity(0.78),
                                fontWeight: FontWeight.w700,
                              ),
                            ),
                          ],
                        ),
                      ),
                    ],
                    const SizedBox(height: 12),
                    Text(
                      '下组建议',
                      style: theme.textTheme.labelMedium?.copyWith(
                        color: Colors.white.withOpacity(0.70),
                        fontWeight: FontWeight.w700,
                      ),
                    ),
                    const SizedBox(height: 8),
                    Container(
                      width: double.infinity,
                      padding: const EdgeInsets.all(12),
                      decoration: BoxDecoration(
                        color: Colors.white.withOpacity(0.05),
                        borderRadius: BorderRadius.circular(14),
                      ),
                      child: Column(
                        crossAxisAlignment: CrossAxisAlignment.start,
                        children: [
                          Text(
                            summary.coachNextSet.trim().isNotEmpty
                                ? summary.coachNextSet
                                : summary.cue,
                            style: theme.textTheme.bodyMedium?.copyWith(
                              color: Colors.white,
                              fontWeight: FontWeight.w700,
                            ),
                          ),
                          if (drillLabels.isNotEmpty) ...[
                            const SizedBox(height: 8),
                            Text(
                              '优先练习',
                              style: theme.textTheme.bodySmall?.copyWith(
                                color: Colors.white.withOpacity(0.70),
                                fontWeight: FontWeight.w700,
                              ),
                            ),
                            const SizedBox(height: 8),
                            Wrap(
                              spacing: 8,
                              runSpacing: 8,
                              children: [
                                for (final drill in drillLabels)
                                  _MiniInfoPill(label: drill),
                              ],
                            ),
                          ],
                        ],
                      ),
                    ),
                    if (secondaryIssues.isNotEmpty) ...[
                      const SizedBox(height: 12),
                      Text(
                        '继续观察',
                        style: theme.textTheme.labelMedium?.copyWith(
                          color: Colors.white.withOpacity(0.70),
                          fontWeight: FontWeight.w700,
                        ),
                      ),
                      const SizedBox(height: 8),
                      for (final item in secondaryIssues)
                        Padding(
                          padding: const EdgeInsets.only(bottom: 6),
                          child: Row(
                            crossAxisAlignment: CrossAxisAlignment.start,
                            children: [
                              Container(
                                width: 6,
                                height: 6,
                                margin: const EdgeInsets.only(top: 7),
                                decoration: BoxDecoration(
                                  color: Colors.white.withOpacity(0.58),
                                  shape: BoxShape.circle,
                                ),
                              ),
                              const SizedBox(width: 8),
                              Expanded(
                                child: Text(
                                  item,
                                  style: theme.textTheme.bodySmall?.copyWith(
                                    color: Colors.white.withOpacity(0.84),
                                    fontWeight: FontWeight.w600,
                                  ),
                                ),
                              ),
                            ],
                          ),
                        ),
                    ],
                  ],
                ),
              ),
            ),
          ),
        ),
      ),
    );
  }
}

class _InsightRow extends StatelessWidget {
  const _InsightRow({
    required this.title,
    required this.value,
    this.trailing,
    this.onTap,
    this.maxLines = 1,
  });

  final String title;
  final String value;
  final String? trailing;
  final VoidCallback? onTap;
  final int maxLines;

  @override
  Widget build(BuildContext context) {
    final trailingWidget = trailing == null
        ? null
        : Padding(
            padding: const EdgeInsets.only(left: 10),
            child: Container(
              padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 6),
              decoration: BoxDecoration(
                color: Colors.white.withOpacity(0.08),
                borderRadius: BorderRadius.circular(999),
                border: Border.all(color: Colors.white.withOpacity(0.10)),
              ),
              child: Text(
                trailing!,
                style: Theme.of(context).textTheme.bodySmall?.copyWith(
                      color: Colors.white.withOpacity(0.82),
                      fontWeight: FontWeight.w700,
                    ),
              ),
            ),
          );

    final content = Row(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Text(
          title,
          style: Theme.of(context).textTheme.bodyMedium?.copyWith(
                color: Colors.white,
                fontWeight: FontWeight.w800,
              ),
        ),
        const SizedBox(width: 16),
        Expanded(
          child: Text(
            value,
            maxLines: maxLines,
            overflow: TextOverflow.ellipsis,
            style: Theme.of(context).textTheme.bodyMedium?.copyWith(
                  color: Colors.white.withOpacity(0.94),
                  fontWeight: FontWeight.w700,
                ),
          ),
        ),
        if (trailingWidget != null)
          onTap == null
              ? trailingWidget
              : GestureDetector(
                  behavior: HitTestBehavior.opaque,
                  onTap: onTap,
                  child: trailingWidget,
                ),
      ],
    );
    if (onTap == null) return content;
    return InkWell(
      onTap: onTap,
      borderRadius: BorderRadius.circular(12),
      child: Padding(
        padding: const EdgeInsets.symmetric(vertical: 2),
        child: content,
      ),
    );
  }
}

class _CenterImportButton extends StatelessWidget {
  const _CenterImportButton({required this.onTap});

  final VoidCallback? onTap;

  @override
  Widget build(BuildContext context) {
    final enabled = onTap != null;
    return Tooltip(
      message: '导入',
      child: Material(
        color: Colors.black.withOpacity(0.22),
        shape: const CircleBorder(),
        clipBehavior: Clip.antiAlias,
        child: InkWell(
          onTap: onTap,
          customBorder: const CircleBorder(),
          child: SizedBox(
            width: 74,
            height: 74,
            child: Icon(
              Icons.file_upload_outlined,
              color: enabled ? Colors.white : Colors.white38,
              size: 34,
            ),
          ),
        ),
      ),
    );
  }
}

class _TimelineOverlay extends StatelessWidget {
  const _TimelineOverlay({
    required this.nowMs,
    required this.durationMs,
    required this.onChanged,
    required this.onChangeEnd,
  });

  final int nowMs;
  final int durationMs;
  final ValueChanged<double> onChanged;
  final ValueChanged<double> onChangeEnd;

  @override
  Widget build(BuildContext context) {
    final safeDuration = durationMs <= 0 ? 1 : durationMs;
    final progress = (nowMs / safeDuration).clamp(0.0, 1.0);

    return Column(
      mainAxisSize: MainAxisSize.min,
      children: [
        Row(
          children: [
            Text(
              msToMmss(nowMs),
              style: Theme.of(context).textTheme.titleMedium?.copyWith(
                    color: Colors.white,
                    fontWeight: FontWeight.w600,
                  ),
            ),
            Expanded(
              child: SliderTheme(
                data: SliderTheme.of(context).copyWith(
                  trackHeight: 3,
                  thumbShape:
                      const RoundSliderThumbShape(enabledThumbRadius: 6),
                  overlayShape:
                      const RoundSliderOverlayShape(overlayRadius: 12),
                  activeTrackColor: Colors.white,
                  inactiveTrackColor: Colors.white.withOpacity(0.22),
                  thumbColor: Colors.white,
                  overlayColor: Colors.white.withOpacity(0.16),
                ),
                child: Slider(
                  value: progress,
                  onChanged: onChanged,
                  onChangeEnd: onChangeEnd,
                ),
              ),
            ),
            Text(
              msToMmss(durationMs),
              style: Theme.of(context).textTheme.titleMedium?.copyWith(
                    color: Colors.white.withOpacity(0.84),
                    fontWeight: FontWeight.w600,
                  ),
            ),
          ],
        ),
      ],
    );
  }
}

class _InlineImportButton extends StatelessWidget {
  const _InlineImportButton({required this.onTap});

  final VoidCallback? onTap;

  @override
  Widget build(BuildContext context) {
    final enabled = onTap != null;
    return Tooltip(
      message: '导入',
      child: Material(
        color: Colors.black.withOpacity(0.22),
        shape: const CircleBorder(),
        clipBehavior: Clip.antiAlias,
        child: InkWell(
          onTap: onTap,
          customBorder: const CircleBorder(),
          child: SizedBox(
            width: 74,
            height: 74,
            child: Icon(
              Icons.file_upload_outlined,
              color: enabled ? Colors.white : Colors.white38,
              size: 30,
            ),
          ),
        ),
      ),
    );
  }
}

class _SettingsLaunchButton extends StatelessWidget {
  const _SettingsLaunchButton({required this.onTap});

  final VoidCallback onTap;

  @override
  Widget build(BuildContext context) {
    return Material(
      color: Colors.transparent,
      child: InkWell(
        onTap: onTap,
        borderRadius: BorderRadius.circular(999),
        child: Container(
          padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 8),
          decoration: BoxDecoration(
            color: Colors.black.withOpacity(0.42),
            borderRadius: BorderRadius.circular(999),
            border: Border.all(color: Colors.white.withOpacity(0.12)),
          ),
          child: Row(
            mainAxisSize: MainAxisSize.min,
            children: [
              Icon(
                Icons.tune_rounded,
                size: 16,
                color: Colors.white.withOpacity(0.92),
              ),
              const SizedBox(width: 6),
              Text(
                '设置',
                style: Theme.of(context).textTheme.labelMedium?.copyWith(
                      color: Colors.white,
                      fontWeight: FontWeight.w700,
                    ),
              ),
            ],
          ),
        ),
      ),
    );
  }
}

class _OverlaySettingsScreen extends StatefulWidget {
  const _OverlaySettingsScreen({
    required this.hasPose,
    required this.showPoseOverlay,
    required this.onPoseChanged,
    required this.coachSoul,
    required this.onCoachSoulChanged,
  });

  final bool hasPose;
  final bool showPoseOverlay;
  final ValueChanged<bool>? onPoseChanged;
  final String coachSoul;
  final ValueChanged<String> onCoachSoulChanged;

  @override
  State<_OverlaySettingsScreen> createState() => _OverlaySettingsScreenState();
}

class _OverlaySettingsScreenState extends State<_OverlaySettingsScreen> {
  late String _selectedSoul;
  late bool _showPose;

  @override
  void initState() {
    super.initState();
    _selectedSoul = widget.coachSoul;
    _showPose = widget.showPoseOverlay;
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      backgroundColor: const Color(0xFF121417),
      body: SafeArea(
        child: Column(
          children: [
            Padding(
              padding: const EdgeInsets.fromLTRB(10, 8, 14, 8),
              child: Row(
                children: [
                  IconButton(
                    onPressed: () => Navigator.of(context).maybePop(),
                    icon: const Icon(Icons.arrow_back_ios_new_rounded),
                    color: Colors.white,
                    tooltip: '返回',
                  ),
                  Expanded(
                    child: Text(
                      '设置',
                      style: Theme.of(context).textTheme.titleLarge?.copyWith(
                            color: Colors.white,
                            fontWeight: FontWeight.w800,
                          ),
                    ),
                  ),
                ],
              ),
            ),
            Expanded(
              child: SingleChildScrollView(
                physics: const BouncingScrollPhysics(),
                padding: const EdgeInsets.fromLTRB(20, 12, 20, 28),
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Container(
                      decoration: BoxDecoration(
                        color: Colors.white.withOpacity(0.05),
                        borderRadius: BorderRadius.circular(18),
                        border:
                            Border.all(color: Colors.white.withOpacity(0.08)),
                      ),
                      child: SwitchListTile.adaptive(
                        value: widget.hasPose && _showPose,
                        onChanged: widget.onPoseChanged == null
                            ? null
                            : (value) {
                                setState(() => _showPose = value);
                                widget.onPoseChanged?.call(value);
                              },
                        activeColor: const Color(0xFF25D3B8),
                        title: Text(
                          '显示 Pose',
                          style:
                              Theme.of(context).textTheme.titleSmall?.copyWith(
                                    color: Colors.white,
                                    fontWeight: FontWeight.w700,
                                  ),
                        ),
                        subtitle: Text(
                          widget.hasPose ? '显示或隐藏姿态骨架叠加' : '当前视频暂无可用姿态数据',
                          style:
                              Theme.of(context).textTheme.bodySmall?.copyWith(
                                    color: Colors.white.withOpacity(0.66),
                                  ),
                        ),
                      ),
                    ),
                    const SizedBox(height: 20),
                    Text(
                      '教练风格',
                      style: Theme.of(context).textTheme.titleSmall?.copyWith(
                            color: Colors.white,
                            fontWeight: FontWeight.w800,
                          ),
                    ),
                    const SizedBox(height: 4),
                    Text(
                      '当前：${_coachSoulLabel(_selectedSoul)}',
                      style: Theme.of(context).textTheme.bodySmall?.copyWith(
                            color: Colors.white.withOpacity(0.62),
                          ),
                    ),
                    const SizedBox(height: 10),
                    Container(
                      decoration: BoxDecoration(
                        color: Colors.white.withOpacity(0.05),
                        borderRadius: BorderRadius.circular(18),
                        border:
                            Border.all(color: Colors.white.withOpacity(0.08)),
                      ),
                      child: Column(
                        mainAxisSize: MainAxisSize.min,
                        children: [
                          for (final soul in _coachSoulOptions)
                            RadioListTile<String>(
                              value: soul.$1,
                              groupValue: _selectedSoul,
                              onChanged: (value) {
                                if (value == null) return;
                                setState(() => _selectedSoul = value);
                                widget.onCoachSoulChanged(value);
                              },
                              activeColor: Colors.white,
                              title: Text(
                                soul.$2,
                                style: Theme.of(context)
                                    .textTheme
                                    .bodyLarge
                                    ?.copyWith(
                                      color: Colors.white,
                                      fontWeight: FontWeight.w600,
                                    ),
                              ),
                              subtitle: Text(
                                soul.$3,
                                style: Theme.of(context)
                                    .textTheme
                                    .bodySmall
                                    ?.copyWith(
                                      color: Colors.white.withOpacity(0.6),
                                    ),
                              ),
                              contentPadding:
                                  const EdgeInsets.symmetric(horizontal: 8),
                              dense: true,
                            ),
                        ],
                      ),
                    ),
                    const SizedBox(height: 10),
                    Text(
                      '新风格会在下次重新分析时生效。',
                      style: Theme.of(context).textTheme.bodySmall?.copyWith(
                            color: Colors.white.withOpacity(0.56),
                          ),
                    ),
                  ],
                ),
              ),
            ),
          ],
        ),
      ),
    );
  }
}

class _MiniInfoPill extends StatelessWidget {
  const _MiniInfoPill({required this.label});

  final String label;

  @override
  Widget build(BuildContext context) {
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 6),
      decoration: BoxDecoration(
        color: Colors.white.withOpacity(0.06),
        borderRadius: BorderRadius.circular(999),
        border: Border.all(color: Colors.white.withOpacity(0.08)),
      ),
      child: Text(
        label,
        style: Theme.of(context).textTheme.bodySmall?.copyWith(
              color: Colors.white.withOpacity(0.86),
              fontWeight: FontWeight.w600,
            ),
      ),
    );
  }
}

_AnalysisProgress _progressForStage(String? stage, double? pct) {
  final value = pct == null ? null : pct.clamp(0.0, 1.0);
  switch (stage) {
    case 'queued':
      return _AnalysisProgress(label: '排队分析', value: value ?? 0.0);
    case 'preprocessing':
    case 'transcode':
      return _AnalysisProgress(label: '处理视频', value: value ?? 0.10);
    case 'classifying_lift':
      return _AnalysisProgress(label: '识别动作', value: value ?? 0.18);
    case 'pose_detecting':
    case 'pose_infer':
      return _AnalysisProgress(label: '提取动作', value: value ?? 0.72);
    case 'barbell_detecting':
    case 'bar_detect':
      return _AnalysisProgress(label: '识别杠铃', value: value ?? 0.60);
    case 'extracting_features':
      return _AnalysisProgress(label: '提取特征', value: value ?? 0.80);
    case 'generating_analysis':
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
            const SizedBox(height: 8),
            Text(line('screening', o?.screeningSummary)),
            if (o != null && o.screeningLines.isNotEmpty) ...[
              const SizedBox(height: 4),
              for (final lineText in o.screeningLines)
                Text(
                  lineText,
                  style: Theme.of(context).textTheme.bodySmall?.copyWith(
                        color: Colors.white.withOpacity(0.78),
                      ),
                ),
            ],
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

class _PoseFrame {
  const _PoseFrame({
    required this.timeMs,
    required this.keypoints,
    required this.tracked,
  });

  final int timeMs;
  final Map<String, _PosePoint> keypoints;
  final bool tracked;
}

class _PosePoint {
  const _PosePoint({
    required this.offset,
    required this.visibility,
  });

  final Offset offset;
  final double visibility;
}

class _PoseOverlay {
  const _PoseOverlay({
    required this.frameWidth,
    required this.frameHeight,
    required this.sampleFps,
    required this.frames,
    required this.skeleton,
  });

  final int frameWidth;
  final int frameHeight;
  final double sampleFps;
  final List<_PoseFrame> frames;
  final List<List<String>> skeleton;
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

_PoseOverlay? _extractPoseOverlay(Map<String, dynamic> report) {
  final meta = report['meta'];
  if (meta is! Map) return null;
  final pose = meta['pose'];
  if (pose is! Map) return null;
  final overlay = pose['overlay'];
  if (overlay is! Map) return null;
  final w = overlay['frameWidth'];
  final h = overlay['frameHeight'];
  final sampleFps = overlay['sampleFps'];
  final frames = overlay['frames'];
  final skeleton = overlay['skeleton'];
  if (w is! num || h is! num || sampleFps is! num || frames is! List) {
    return null;
  }

  final outFrames = <_PoseFrame>[];
  for (final frame in frames) {
    if (frame is! Map) continue;
    final timeMs = frame['timeMs'];
    final keypointsRaw = frame['keypoints'];
    if (timeMs is! num || keypointsRaw is! Map) continue;
    final keypoints = <String, _PosePoint>{};
    for (final entry in keypointsRaw.entries) {
      final key = entry.key;
      final value = entry.value;
      if (key is! String || value is! Map) continue;
      final typed = value.cast<String, dynamic>();
      final point = _extractPoint(typed);
      if (point != null) {
        final visibilityNode = typed['visibility'];
        final visibility =
            visibilityNode is num ? visibilityNode.toDouble() : 1.0;
        keypoints[key] = _PosePoint(offset: point, visibility: visibility);
      }
    }
    final tracked = frame['tracked'] == true;
    outFrames.add(
      _PoseFrame(
        timeMs: timeMs.toInt(),
        keypoints: keypoints,
        tracked: tracked,
      ),
    );
  }

  final outSkeleton = <List<String>>[];
  if (skeleton is List) {
    for (final edge in skeleton) {
      if (edge is List &&
          edge.length == 2 &&
          edge[0] is String &&
          edge[1] is String) {
        outSkeleton.add([edge[0] as String, edge[1] as String]);
      }
    }
  }

  outFrames.sort((a, b) => a.timeMs.compareTo(b.timeMs));
  return _PoseOverlay(
    frameWidth: w.toInt(),
    frameHeight: h.toInt(),
    sampleFps: sampleFps.toDouble(),
    frames: outFrames,
    skeleton: outSkeleton,
  );
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
    required this.onImport,
    required this.coachSoul,
    required this.onCoachSoulChanged,
    required this.showPoseOverlay,
    required this.onPoseOverlayChanged,
    required this.onPoseAvailabilityChanged,
    this.analysisProgress,
    this.compact = false,
    this.onVbtLive,
    this.onDebug,
    this.onAnalysisSummary,
    this.seekToMs,
    this.onSeekHandled,
  });

  final Api api;
  final String setId;
  final PickedVideo pickedVideo;
  final VoidCallback? onImport;
  final String coachSoul;
  final ValueChanged<String> onCoachSoulChanged;
  final bool showPoseOverlay;
  final ValueChanged<bool> onPoseOverlayChanged;
  final ValueChanged<bool> onPoseAvailabilityChanged;
  final _AnalysisProgress? analysisProgress;
  final bool compact;
  final ValueChanged<_VbtLive>? onVbtLive;
  final ValueChanged<_OverlayDebug>? onDebug;
  final ValueChanged<_AnalysisSummary?>? onAnalysisSummary;
  final int? seekToMs;
  final VoidCallback? onSeekHandled;

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
  String _lastAnalysisSig = '';

  Size? _serverFrameSize;
  int _overlayMaxGapMs = 180;

  Timer? _pollTimer;
  Timer? _playbackControlTimer;
  List<_VbtRep> _vbtReps = const [];
  _PoseOverlay? _poseOverlay;
  bool _showPlaybackControl = true;
  int? _lastHandledSeekMs;
  bool _isDraggingTimeline = false;

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

  @override
  void didUpdateWidget(covariant TrajectoryOverlayScreen oldWidget) {
    super.didUpdateWidget(oldWidget);
    final targetMs = widget.seekToMs;
    if (targetMs == null || targetMs == _lastHandledSeekMs) return;
    _lastHandledSeekMs = targetMs;
    unawaited(_seekToMs(targetMs));
  }

  void _emitDebug() {
    final report = _report;

    String? reportStatus;
    String? barbellError;
    String? screeningSummary;
    var screeningLines = const <String>[];
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
        final fusion = meta['analysisFusion'];
        if (fusion is Map) {
          final screeningMeta = _extractScreeningDebugFromFusion(
              Map<String, dynamic>.from(fusion));
          screeningSummary = screeningMeta.$1;
          screeningLines = screeningMeta.$2;
        }
      }
    }

    final overlayError = _err?.toString() ?? _extractOverlayError(report);
    final points = _frames.where((f) => f.point != null).length;
    final total = _frames.length;

    final sig =
        '${reportStatus ?? '-'}|${barbellError ?? '-'}|${overlayError ?? '-'}|$points|$total|$_nowMs|${screeningSummary ?? '-'}|${screeningLines.join(',')}';
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
        screeningSummary: screeningSummary,
        screeningLines: screeningLines,
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

    cb(
      _VbtLive(
        totalReps: _vbtReps.length,
        recentEntries: recentEntries,
        allEntries: [
          for (final rep in _vbtReps)
            _VbtHudEntry(
              repIndex: rep.repIndex,
              totalReps: _vbtReps.length,
              avgVelocityMps: rep.avgVelocityMps,
            ),
        ],
      ),
    );
  }

  void _emitAnalysisSummary() {
    final cb = widget.onAnalysisSummary;
    if (cb == null) return;
    final summary = _extractAnalysisSummary(_report);
    final sig = summary == null
        ? '-'
        : '${summary.liftType}|${summary.repCount}|${summary.avgRepVelocityMps}|'
            '${summary.barPathDriftCm}|${summary.velocityLossPct}|'
            '${summary.issues.map((e) => e.name).join(",")}';
    if (sig == _lastAnalysisSig) return;
    _lastAnalysisSig = sig;
    cb(summary);
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
      if (!_isDraggingTimeline) {
        _nowMs = value.position.inMilliseconds;
      }
      if (shouldShowControl) {
        _showPlaybackControl = true;
      }
    });
    if (shouldShowControl) {
      _playbackControlTimer?.cancel();
    }

    _emitVbt();
    _emitDebug();
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
      }

      final rep = await widget.api.getReport(widget.setId);
      final overlay = _extractOverlayStream(rep);
      final poseOverlay = _extractPoseOverlay(rep);
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
        _poseOverlay = poseOverlay;
        _serverFrameSize = serverSize;
        _overlayMaxGapMs = overlay?.maxGapMs ?? 180;
      });
      widget.onPoseAvailabilityChanged(poseOverlay?.frames.isNotEmpty ?? false);

      _emitVbt();
      _emitDebug();
      _emitAnalysisSummary();
      final status = rep['status'];
      if (status == 'pending') {
        final vc = _vc;
        if (vc != null && vc.value.isPlaying) {
          unawaited(vc.pause());
        }
        _revealPlaybackControl();
        _emitAnalysisSummary();

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
        _emitAnalysisSummary();
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
    } catch (e) {
      if (!mounted) return;
      setState(() => _err = e);
    }
  }

  Future<void> _seekToMs(int targetMs) async {
    final vc = _vc;
    if (vc == null) return;
    try {
      await vc.seekTo(Duration(milliseconds: targetMs));
      if (!mounted) return;
      setState(() {
        _nowMs = targetMs;
        _showPlaybackControl = true;
      });
      _emitVbt();
      _emitDebug();
    } catch (e) {
      if (!mounted) return;
      setState(() => _err = e);
    } finally {
      widget.onSeekHandled?.call();
    }
  }

  Future<void> _seekNormalized(double t) async {
    final vc = _vc;
    if (vc == null) return;
    final durationMs = vc.value.duration.inMilliseconds;
    if (durationMs <= 0) return;
    final targetMs = (durationMs * t.clamp(0.0, 1.0)).round();
    await _seekToMs(targetMs);
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
    final showInlineImport = !isAnalysisLoading &&
        (!vc.value.isPlaying || _isPlaybackCompleted(vc.value)) &&
        widget.onImport != null;

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
                  poseOverlay: _poseOverlay,
                  showPoseOverlay: widget.showPoseOverlay,
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
                          : Row(
                              mainAxisSize: MainAxisSize.min,
                              children: [
                                Material(
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
                                if (showInlineImport) ...[
                                  const SizedBox(width: 12),
                                  _InlineImportButton(onTap: widget.onImport),
                                ],
                              ],
                            ),
                    ),
                  ),
                ),
              ),
              if (widget.compact)
                Positioned(
                  left: 18,
                  right: 18,
                  bottom: 18,
                  child: _TimelineOverlay(
                    nowMs: _nowMs,
                    durationMs: vc.value.duration.inMilliseconds,
                    onChanged: (value) {
                      final durationMs = vc.value.duration.inMilliseconds;
                      if (durationMs <= 0) return;
                      setState(() {
                        _isDraggingTimeline = true;
                        _nowMs = (durationMs * value).round();
                        _showPlaybackControl = true;
                      });
                    },
                    onChangeEnd: (value) async {
                      setState(() => _isDraggingTimeline = false);
                      await _seekNormalized(value);
                    },
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

_AnalysisSummary? _extractAnalysisSummary(Map<String, dynamic>? report) {
  if (report == null) return null;
  final meta = report['meta'];
  if (meta is! Map) return null;
  final analysis = meta['analysis'];
  final videoClassification = meta['videoClassification'];
  final features = meta['features'];
  final phases = meta['phases'];
  final score = meta['score'];
  if (analysis is! Map || features is! Map) return null;

  final issues = <_AnalysisIssue>[];
  final topFindings = <_AnalysisIssue>[];
  final fusion = meta['analysisFusion'];
  final checklistStatusByCode = <String, String>{};
  final checklist = fusion is Map ? fusion['screeningChecklist'] : null;
  if (checklist is List) {
    for (final item in checklist) {
      if (item is! Map) continue;
      final code = item['code'];
      final status = item['finalAssessment'] ?? item['status'];
      if (code is String && status is String && code.trim().isNotEmpty) {
        checklistStatusByCode[code.trim()] = status.trim().toLowerCase();
      }
    }
  }
  final issuesRaw = analysis['issues'];
  if (issuesRaw is List) {
    for (final item in issuesRaw) {
      if (item is! Map) continue;
      final name = item['title'] is String ? item['title'] : item['name'];
      final code = item['name'] is String ? item['name'] as String : name;
      final severity = item['severity'];
      final confidence = item['confidence'];
      if (name is! String || severity is! String || confidence is! num)
        continue;
      final checklistStatus =
          code is String ? checklistStatusByCode[code] : null;
      if (checklistStatus != null && checklistStatus != 'present') {
        continue;
      }
      String timeLabel = '--:--';
      final tr = item['timeRangeMs'];
      if (tr is Map && tr['start'] is num && tr['end'] is num) {
        timeLabel =
            '${msToMmss((tr['start'] as num).toInt())}-${msToMmss((tr['end'] as num).toInt())}';
      }
      final visual = item['visualEvidence'];
      final kinematic = item['kinematicEvidence'];
      issues.add(
        _AnalysisIssue(
          code: code is String ? code : name,
          name: name,
          severity: severity,
          confidence: confidence.toDouble(),
          evidenceSource: item['evidenceSource'] is String
              ? item['evidenceSource'] as String
              : 'rule',
          timeLabel: timeLabel,
          startMs: tr is Map && tr['start'] is num
              ? (tr['start'] as num).toInt()
              : null,
          endMs:
              tr is Map && tr['end'] is num ? (tr['end'] as num).toInt() : null,
          visualEvidence:
              visual is List && visual.isNotEmpty ? '${visual.first}' : '',
          kinematicEvidence: kinematic is List && kinematic.isNotEmpty
              ? '${kinematic.first}'
              : '',
        ),
      );
    }
  }

  final top3 = report['top3'];
  if (top3 is List) {
    for (final item in top3) {
      if (item is! Map) continue;
      final name =
          item['labelDisplay'] is String ? item['labelDisplay'] : item['label'];
      final severity = item['severity'];
      final confidence = item['confidence'];
      final timeLabel = item['timeRangeMmss'];
      if (name is! String ||
          severity is! String ||
          confidence is! num ||
          timeLabel is! String) {
        continue;
      }
      topFindings.add(
        _AnalysisIssue(
          code: item['label'] is String ? item['label'] as String : name,
          name: name,
          severity: severity,
          confidence: confidence.toDouble(),
          evidenceSource: 'rule',
          timeLabel: timeLabel,
          startMs: null,
          endMs: null,
          visualEvidence: '',
          kinematicEvidence: '',
        ),
      );
    }
  }

  final drillsRaw = analysis['drills'];
  final drills = <String>[
    if (drillsRaw is List)
      for (final d in drillsRaw)
        if (d is String) d,
  ];
  final coachFeedback = analysis['coachFeedback'];
  final keepWatching = <String>[
    if (coachFeedback is Map && coachFeedback['keepWatching'] is List)
      for (final item in coachFeedback['keepWatching'] as List)
        if (item is String && item.trim().isNotEmpty) _watchLabel(item),
  ];
  if (keepWatching.isEmpty) {
    if (checklist is List) {
      for (final item in checklist) {
        if (item is! Map) continue;
        final status = item['finalAssessment'] ?? item['status'];
        if (status != 'possible') continue;
        final title = item['title'];
        if (title is String && title.trim().isNotEmpty) {
          keepWatching.add(_watchLabel(title));
        }
        if (keepWatching.length >= 3) break;
      }
    }
  }

  final repScores = <int, int>{};
  final repPoseMetrics = <_RepPoseMetrics>[];
  int? overallScore;
  String? overallGrade;
  int? bestRepIndex;
  int? weakestRepIndex;
  if (score is Map) {
    if (score['overall'] is num) {
      overallScore = (score['overall'] as num).toInt();
    }
    if (score['grade'] is String) {
      overallGrade = score['grade'] as String;
    }
    if (score['bestRepIndex'] is num) {
      bestRepIndex = (score['bestRepIndex'] as num).toInt();
    }
    if (score['weakestRepIndex'] is num) {
      weakestRepIndex = (score['weakestRepIndex'] as num).toInt();
    }
    final repsRaw = score['reps'];
    if (repsRaw is List) {
      for (final item in repsRaw) {
        if (item is! Map) continue;
        final repIndex = item['repIndex'];
        final repScore = item['score'];
        if (repIndex is num && repScore is num) {
          repScores[repIndex.toInt()] = repScore.toInt();
        }
      }
    }
  }

  final repSummariesRaw = features['repSummaries'];
  if (repSummariesRaw is List) {
    for (final item in repSummariesRaw) {
      if (item is! Map) continue;
      final repIndex = item['repIndex'];
      final timeRange = item['timeRangeMs'];
      if (repIndex is! num) continue;
      repPoseMetrics.add(
        _RepPoseMetrics(
          repIndex: repIndex.toInt(),
          startMs: timeRange is Map && timeRange['start'] is num
              ? (timeRange['start'] as num).toInt()
              : null,
          endMs: timeRange is Map && timeRange['end'] is num
              ? (timeRange['end'] as num).toInt()
              : null,
          hipKneeSyncScore: item['hipKneeSyncScore'] is num
              ? (item['hipKneeSyncScore'] as num).toDouble()
              : null,
          hipLeadMs: item['hipLeadMs'] is num
              ? (item['hipLeadMs'] as num).toInt()
              : null,
        ),
      );
    }
  }

  return _AnalysisSummary(
    liftType: analysis['liftType'] is String
        ? analysis['liftType'] as String
        : 'lift',
    recognizedLiftType:
        videoClassification is Map && videoClassification['liftType'] is String
            ? videoClassification['liftType'] as String
            : null,
    analysisSource:
        analysis['source'] is String ? analysis['source'] as String : 'rules',
    coachFocus: coachFeedback is Map && coachFeedback['focus'] is String
        ? coachFeedback['focus'] as String
        : '',
    coachWhy: coachFeedback is Map && coachFeedback['why'] is String
        ? coachFeedback['why'] as String
        : '',
    coachNextSet: coachFeedback is Map && coachFeedback['nextSet'] is String
        ? coachFeedback['nextSet'] as String
        : '',
    keepWatching: keepWatching,
    cue: analysis['cue'] is String ? analysis['cue'] as String : '',
    drills: drills,
    repCount:
        features['repCount'] is num ? (features['repCount'] as num).toInt() : 0,
    avgRepVelocityMps: features['avgRepVelocityMps'] is num
        ? (features['avgRepVelocityMps'] as num).toDouble()
        : null,
    barPathDriftCm: features['barPathDriftCm'] is num
        ? (features['barPathDriftCm'] as num).toDouble()
        : null,
    velocityLossPct: features['velocityLossPct'] is num
        ? (features['velocityLossPct'] as num).toDouble()
        : null,
    phaseCount: phases is List ? phases.length : 0,
    issues: issues,
    topFindings: topFindings,
    poseUsable: features['poseUsable'] == true,
    poseConfidence: _extractPoseConfidence(meta),
    posePrimarySide: features['posePrimarySide'] is String
        ? features['posePrimarySide'] as String
        : null,
    poseFrameCount: features['poseFrameCount'] is num
        ? (features['poseFrameCount'] as num).toInt()
        : 0,
    maxTorsoLeanDeg: features['maxTorsoLeanDeg'] is num
        ? (features['maxTorsoLeanDeg'] as num).toDouble()
        : null,
    avgTorsoLeanDeltaDeg: features['avgTorsoLeanDeltaDeg'] is num
        ? (features['avgTorsoLeanDeltaDeg'] as num).toDouble()
        : null,
    minKneeAngleDeg: features['minKneeAngleDeg'] is num
        ? (features['minKneeAngleDeg'] as num).toDouble()
        : null,
    overallScore: overallScore,
    overallGrade: overallGrade,
    bestRepIndex: bestRepIndex,
    weakestRepIndex: weakestRepIndex,
    repScores: repScores,
    repPoseMetrics: repPoseMetrics,
  );
}

double? _extractPoseConfidence(Map meta) {
  final pose = meta['pose'];
  if (pose is! Map) return null;
  final quality = pose['quality'];
  if (quality is! Map) return null;
  final confidence = quality['confidence'];
  return confidence is num ? confidence.toDouble() : null;
}

(String?, List<String>) _extractScreeningDebugFromFusion(
    Map<String, dynamic> fusion) {
  final summaryRaw = fusion['screeningSummary'];
  String? summary;
  if (summaryRaw is Map) {
    final total = summaryRaw['total'];
    final present = summaryRaw['present'];
    final possible = summaryRaw['possible'];
    final absent = summaryRaw['absent'];
    final notSupported = summaryRaw['notSupported'];
    summary =
        'present:${present ?? '-'} possible:${possible ?? '-'} absent:${absent ?? '-'} n/s:${notSupported ?? '-'} total:${total ?? '-'}';
  }

  final lines = <String>[];
  final raw = fusion['screeningChecklist'];
  if (raw is List) {
    for (final item in raw) {
      if (item is! Map) continue;
      final status = item['status'];
      final code = item['code'];
      final confidence = item['confidence'];
      if (status is! String || code is! String) continue;
      if (status != 'present' && status != 'possible') continue;
      final confText = confidence is num ? confidence.toStringAsFixed(2) : '-';
      lines.add('$status · $code · $confText');
      if (lines.length >= 8) break;
    }
  }

  return (summary, lines);
}

String _liftTypeLabel(String raw) {
  switch (raw) {
    case 'squat':
      return '深蹲';
    case 'bench':
      return '卧推';
    case 'deadlift':
      return '硬拉';
    case 'sumo_deadlift':
      return '相扑硬拉';
    default:
      return raw;
  }
}

const List<(String, String, String)> _coachSoulOptions = [
  ('balanced', '平衡型', '结论克制，解释完整，适合日常复盘'),
  ('direct', '直接型', '指出问题更干脆，纠错更明确'),
  ('analytical', '分析型', '更强调证据、阶段和动作逻辑'),
  ('competition', '比赛型', '更关注做组质量、稳定性和比赛表现'),
  ('plainspoken', '大白话', '更口语化，更像线下带动作时的提醒'),
];

String _coachSoulLabel(String raw) {
  for (final option in _coachSoulOptions) {
    if (option.$1 == raw) return option.$2;
  }
  return '平衡型';
}

String msToMmss(int ms) {
  final totalSeconds = ms < 0 ? 0 : ms ~/ 1000;
  final minutes = totalSeconds ~/ 60;
  final seconds = totalSeconds % 60;
  return '${minutes.toString().padLeft(2, '0')}:${seconds.toString().padLeft(2, '0')}';
}

String _watchLabel(String raw) {
  final text = raw.trim();
  if (text.isEmpty) return text;
  if (text.contains('继续观察') || text.contains('继续留意') || text.contains('留意')) {
    return text;
  }
  return '继续留意$text';
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
    required this.poseOverlay,
    required this.showPoseOverlay,
  });

  final List<_TrajectoryFrame> frames;
  final int nowMs;
  final Size sourceSize;
  final int maxGapMs;
  final _PoseOverlay? poseOverlay;
  final bool showPoseOverlay;

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

    if (showPoseOverlay) {
      _paintPose(canvas, size, toCanvas);
    }
  }

  void _paintPose(Canvas canvas, Size size, Offset Function(Offset) toCanvas) {
    final overlay = poseOverlay;
    if (overlay == null || overlay.frames.isEmpty) return;
    final poseFrame = _sampleNearestPoseFrame(overlay.frames, nowMs);
    if (poseFrame == null || poseFrame.keypoints.isEmpty) return;

    final bonePaint = Paint()
      ..color = const Color(0xFF7CFFDE)
      ..style = PaintingStyle.stroke
      ..strokeWidth = 3.0
      ..strokeCap = StrokeCap.round;
    final jointPaint = Paint()
      ..color = const Color(0xFFFF8A80)
      ..style = PaintingStyle.fill;

    for (final edge in overlay.skeleton) {
      final a = poseFrame.keypoints[edge[0]];
      final b = poseFrame.keypoints[edge[1]];
      if (a == null || b == null) continue;
      if (a.visibility < 0.45 || b.visibility < 0.45) continue;
      canvas.drawLine(toCanvas(a.offset), toCanvas(b.offset), bonePaint);
    }

    for (final point in poseFrame.keypoints.values) {
      if (point.visibility < 0.45) continue;
      canvas.drawCircle(toCanvas(point.offset), 4.0, jointPaint);
    }
  }

  @override
  bool shouldRepaint(covariant _TrajectoryPainter oldDelegate) {
    return oldDelegate.nowMs != nowMs ||
        oldDelegate.frames != frames ||
        oldDelegate.sourceSize != sourceSize ||
        oldDelegate.poseOverlay != poseOverlay ||
        oldDelegate.showPoseOverlay != showPoseOverlay;
  }
}

_PoseFrame? _sampleNearestPoseFrame(List<_PoseFrame> frames, int nowMs,
    {int maxGapMs = 220}) {
  if (frames.isEmpty) return null;
  _PoseFrame? best;
  var bestDelta = maxGapMs + 1;
  for (final frame in frames) {
    final delta = (frame.timeMs - nowMs).abs();
    if (delta < bestDelta) {
      best = frame;
      bestDelta = delta;
    }
    if (frame.timeMs > nowMs && delta > bestDelta) break;
  }
  return bestDelta <= maxGapMs ? best : null;
}
