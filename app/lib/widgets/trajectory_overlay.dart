class TrajectoryOverlayScreen extends StatefulWidget {
  const TrajectoryOverlayScreen({super.key, required this.api, required this.setId, required this.pickedVideo});

  final Api api;
  final String setId;
  final PickedVideo pickedVideo;

  @override
  State<TrajectoryOverlayScreen> createState() => _TrajectoryOverlayScreenState();
}

class _TrajectoryOverlayScreenState extends State<TrajectoryOverlayScreen> {
  Object? _err;
  Map<String, dynamic>? _report;
  List<_TrajectoryFrame> _frames = const [];
  VideoPlayerController? _vc;

  int _nowMs = 0;
  int _lastTickMs = 0;

  Size? _serverFrameSize;
  int _rotationQuarterTurns = 0;

  Timer? _pollTimer;
  List<_VbtRep> _vbtReps = const [];

  @override
  void initState() {
    super.initState();
    unawaited(_load());
  }

  @override
  void dispose() {
    _pollTimer?.cancel();
    _vc?.removeListener(_onVideoTick);
    _vc?.dispose();
    unawaited(widget.pickedVideo.dispose());
    super.dispose();
  }

  void _onVideoTick() {
    final vc = _vc;
    if (vc == null) return;
    if (!mounted) return;

    final now = DateTime.now().millisecondsSinceEpoch;
    if (now - _lastTickMs < 33) return;
    _lastTickMs = now;

    setState(() {
      _nowMs = vc.value.position.inMilliseconds;
    });
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
        });
      }

      final rep = await widget.api.getReport(widget.setId);
      final frames = _extractTrajectoryFrames(rep);
      final serverSize = _extractBarbellFrameSize(rep);
      final vbtReps = _extractVbtReps(rep);

      final vc = _vc;
      final displaySize = vc?.value.size;
      int rot = 0;
      if (serverSize != null && displaySize != null && displaySize.width > 0 && displaySize.height > 0) {
        final sw = serverSize.frameWidth.toDouble();
        final sh = serverSize.frameHeight.toDouble();
        final dw = displaySize.width;
        final dh = displaySize.height;

        final same = (sw - dw).abs() / dw < 0.12 && (sh - dh).abs() / dh < 0.12;
        final swapped = (sw - dh).abs() / dh < 0.12 && (sh - dw).abs() / dw < 0.12;

        if (!same && swapped) {
          rot = 1;
        }
      }

      if (!mounted) return;

      setState(() {
        _err = null;
        _report = rep;
        _frames = frames;
        _vbtReps = vbtReps;
        _serverFrameSize = serverSize == null ? null : Size(serverSize.frameWidth.toDouble(), serverSize.frameHeight.toDouble());
        _rotationQuarterTurns = rot;
      });

      final status = rep['status'];
      if (status == 'pending') {
        final vc = _vc;
        if (vc != null && vc.value.isPlaying) {
          unawaited(vc.pause());
        }

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
        }
      }
    } catch (e) {
      if (!mounted) return;
      setState(() => _err = e);
    }
  }

  Future<void> _toggle() async {
    final vc = _vc;
    if (vc == null) return;
    try {
      if (vc.value.isPlaying) {
        await vc.pause();
      } else {
        await vc.play();
      }
      if (!mounted) return;
      setState(() {});
    } catch (e) {
      if (!mounted) return;
      setState(() => _err = e);
    }
  }

  @override
  Widget build(BuildContext context) {
    final vc = _vc;
    final report = _report;

    String? barbellError;
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

    return Padding(
      padding: const EdgeInsets.all(8),
      child: vc == null
          ? _err == null
              ? const Center(child: CircularProgressIndicator())
              : Text('Error: $_err')
          : Column(
              crossAxisAlignment: CrossAxisAlignment.stretch,
              children: [
                Expanded(
                  child: Center(
                    child: AspectRatio(
                      aspectRatio: vc.value.aspectRatio,
                      child: Stack(
                        fit: StackFit.expand,
                        children: [
                          VideoPlayer(vc),
                          CustomPaint(
                            painter: _TrajectoryPainter(
                              frames: _frames,
                              nowMs: _nowMs,
                              sourceSize: _serverFrameSize ??
                                  ((vc.value.size.width > 0 && vc.value.size.height > 0)
                                      ? vc.value.size
                                      : Size(widget.pickedVideo.width.toDouble(), widget.pickedVideo.height.toDouble())),
                              rotationQuarterTurns: _rotationQuarterTurns,
                              vbtReps: _vbtReps,
                            ),
                          ),
                        ],
                      ),
                    ),
                  ),
                ),
                const SizedBox(height: 8),
                Text('reportStatus: ${report == null ? '-' : report['status'] ?? '-'}'),
                if (barbellError != null) Text('barbellError: $barbellError'),
                if (_err != null) Text('overlayError: $_err'),
                const SizedBox(height: 12),
                Row(
                  children: [
                    FilledButton.tonal(
                      onPressed: _toggle,
                      child: Text(vc.value.isPlaying ? '暂停' : '播放'),
                    ),
                    const SizedBox(width: 12),
                    Text('${(_nowMs / 1000).toStringAsFixed(2)}s'),
                    const Spacer(),
                    Text('points: ${_frames.where((f) => f.point != null).length}/${_frames.length}'),
                  ],
                ),
                const SizedBox(height: 8),
                const Text('绿色轨迹来自服务端返回的 barbell trajectory（按时间同步）。'),
              ],
            ),
    );
  }
}

const _trajectoryOverlayFileSentinel = 0;