import 'dart:io';
import 'dart:math' as math;
import 'dart:typed_data';

import 'package:crypto/crypto.dart';
import 'package:file_picker/file_picker.dart';
import 'package:video_player/video_player.dart';

class PickedVideo {
  PickedVideo({
    required this.fileName,
    required this.path,
    required this.sha256,
    required this.durationMs,
    required this.width,
    required this.height,
    this.bytes,
    this.cleanupPath,
    this.objectUrl,
  });

  final String fileName;
  final String? path;
  final Uint8List? bytes;
  final String? objectUrl;
  final String? cleanupPath;

  final String sha256;
  final int durationMs;
  final int width;
  final int height;

  Future<VideoPlayerController> createController() async {
    final p = path;
    if (p == null || p.isEmpty) {
      throw StateError('missing file path');
    }
    final vc = VideoPlayerController.file(File(p));
    await vc.initialize();
    return vc;
  }

  Future<void> dispose() async {
    final p = cleanupPath;
    if (p != null && p.isNotEmpty) {
      try {
        final f = File(p);
        if (await f.exists()) {
          await f.delete();
        }
      } catch (_) {}
    }
  }
}

const int _maxUploadBytes = 20 * 1024 * 1024;

Future<String> _sha256File(String path) async {
  final digest = await sha256.bind(File(path).openRead()).first;
  return digest.toString();
}

Future<PickedVideo?> pickVideo() async {
  final picked = await FilePicker.platform.pickFiles(type: FileType.video);
  if (picked == null || picked.files.isEmpty) return null;

  final f0 = picked.files.single;
  final path = f0.path;
  if (path == null || path.isEmpty) return null;

  final f = File(path);
  if (!await f.exists()) return null;

  final sizeBytes = await f.length();
  final compressedPath =
      sizeBytes > _maxUploadBytes ? await _compressIfNeeded(path) : null;
  final finalPath = compressedPath ?? path;
  final finalFile = File(finalPath);

  final sha = await _sha256File(finalPath);

  final vc = VideoPlayerController.file(finalFile);
  await vc.initialize();
  final durationMs = vc.value.duration.inMilliseconds;
  final size = vc.value.size;
  await vc.dispose();

  final name = (f0.name.isNotEmpty) ? f0.name : path.split('/').last;

  return PickedVideo(
    fileName: name,
    path: finalPath,
    sha256: sha,
    durationMs: durationMs,
    width: size.width.round(),
    height: size.height.round(),
    cleanupPath: compressedPath,
  );
}

Future<String?> _compressIfNeeded(String inputPath) async {
  final inputFile = File(inputPath);
  if (!await inputFile.exists()) return null;
  if (await inputFile.length() <= _maxUploadBytes) return null;

  final probe = await Process.run('ffmpeg', ['-version']);
  if (probe.exitCode != 0) return null;

  final vc = VideoPlayerController.file(inputFile);
  await vc.initialize();
  final durationMs = math.max(1, vc.value.duration.inMilliseconds);
  await vc.dispose();

  final tempDir = await Directory.systemTemp.createTemp('ssc_video_');
  String? bestPath;
  int? bestSize;

  for (final factor in const [1.0, 0.82, 0.68]) {
    final totalBps =
        (((_maxUploadBytes * 8) / (durationMs / 1000.0)) * factor).floor();
    final audioBps = math.min(96 * 1000, math.max(48 * 1000, totalBps ~/ 6));
    final videoBps = math.max(180 * 1000, totalBps - audioBps);
    final outPath = '${tempDir.path}/compressed_${(factor * 100).round()}.mp4';

    final args = [
      '-y',
      '-i',
      inputPath,
      '-c:v',
      'libx264',
      '-preset',
      'veryfast',
      '-pix_fmt',
      'yuv420p',
      '-b:v',
      '${videoBps ~/ 1000}k',
      '-maxrate',
      '${videoBps ~/ 1000}k',
      '-bufsize',
      '${(videoBps * 2) ~/ 1000}k',
      '-c:a',
      'aac',
      '-b:a',
      '${audioBps ~/ 1000}k',
      '-movflags',
      '+faststart',
      outPath,
    ];

    final res = await Process.run('ffmpeg', args);
    final outFile = File(outPath);
    if (res.exitCode != 0 || !await outFile.exists()) {
      continue;
    }

    final outSize = await outFile.length();
    if (bestSize == null || outSize < bestSize) {
      bestSize = outSize;
      bestPath = outPath;
    }
    if (outSize <= _maxUploadBytes) {
      break;
    }
  }

  if (bestPath == null || bestSize == null) return null;
  if (bestSize >= await inputFile.length()) return null;
  return bestPath;
}
