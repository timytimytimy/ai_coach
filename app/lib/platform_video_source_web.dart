import 'dart:async';
import 'dart:typed_data';
import 'dart:html' as html;

import 'package:crypto/crypto.dart';
import 'package:file_picker/file_picker.dart';
import 'package:video_player/video_player.dart';

String _mimeFromName(String name) {
  final lower = name.toLowerCase();
  if (lower.endsWith('.webm')) return 'video/webm';
  if (lower.endsWith('.mov')) return 'video/quicktime';
  if (lower.endsWith('.m4v')) return 'video/x-m4v';
  return 'video/mp4';
}

class PickedVideo {
  PickedVideo({
    required this.fileName,
    required this.bytes,
    required this.objectUrl,
    required this.sha256,
    required this.durationMs,
    required this.width,
    required this.height,
    this.path,
  });

  final String fileName;
  final String? path;
  final Uint8List? bytes;
  final String? objectUrl;

  final String sha256;
  final int durationMs;
  final int width;
  final int height;

  Future<VideoPlayerController> createController() async {
    final u = objectUrl;
    if (u == null || u.isEmpty) {
      throw StateError('missing objectUrl');
    }
    final vc = VideoPlayerController.networkUrl(Uri.parse(u));
    await vc.initialize();
    return vc;
  }

  Future<void> dispose() async {
    final u = objectUrl;
    if (u != null && u.isNotEmpty) {
      html.Url.revokeObjectUrl(u);
    }
  }
}

const int _maxUploadBytes = 20 * 1024 * 1024;
const _mediaRecorderStopEvent = html.EventStreamProvider<html.Event>('stop');
const _mediaRecorderDataEvent =
    html.EventStreamProvider<html.BlobEvent>('dataavailable');

Future<PickedVideo?> pickVideo() async {
  final picked =
      await FilePicker.platform.pickFiles(type: FileType.video, withData: true);
  if (picked == null || picked.files.isEmpty) return null;

  final f0 = picked.files.single;
  final rawBytes = f0.bytes;
  final bytes = rawBytes == null || rawBytes.length <= _maxUploadBytes
      ? rawBytes
      : await _compressBytesIfNeeded(rawBytes, f0.name);
  if (bytes == null || bytes.isEmpty) return null;

  final sha = sha256.convert(bytes).toString();

  final outName = _outputName(f0.name, compressed: !identical(bytes, rawBytes));
  final blob = html.Blob([bytes], _mimeFromName(outName));
  final objectUrl = html.Url.createObjectUrlFromBlob(blob);

  final vc = VideoPlayerController.networkUrl(Uri.parse(objectUrl));
  await vc.initialize();
  final durationMs = vc.value.duration.inMilliseconds;
  final size = vc.value.size;
  await vc.dispose();

  return PickedVideo(
    fileName: outName,
    bytes: bytes,
    objectUrl: objectUrl,
    sha256: sha,
    durationMs: durationMs,
    width: size.width.round(),
    height: size.height.round(),
  );
}

String _outputName(String original, {required bool compressed}) {
  if (!compressed) {
    return original.isNotEmpty ? original : 'upload.mp4';
  }
  final dot = original.lastIndexOf('.');
  final stem = dot > 0
      ? original.substring(0, dot)
      : (original.isNotEmpty ? original : 'upload');
  return '$stem.webm';
}

String _preferredRecorderMime() {
  const candidates = [
    'video/webm;codecs=vp9,opus',
    'video/webm;codecs=vp8,opus',
    'video/webm',
  ];
  for (final mime in candidates) {
    if (html.MediaRecorder.isTypeSupported(mime)) {
      return mime;
    }
  }
  return 'video/webm';
}

Future<Uint8List?> _compressBytesIfNeeded(
    Uint8List input, String originalName) async {
  if (input.lengthInBytes <= _maxUploadBytes) return input;

  final inputBlob = html.Blob([input], _mimeFromName(originalName));
  final inputUrl = html.Url.createObjectUrlFromBlob(inputBlob);
  final video = html.VideoElement()
    ..src = inputUrl
    ..muted = true
    ..preload = 'auto';

  try {
    await video.onLoadedMetadata.first;
    final durationSec =
        video.duration.isFinite && video.duration > 0 ? video.duration : 0.0;
    if (durationSec <= 0) return input;

    Uint8List? bestBytes;
    final mime = _preferredRecorderMime();
    for (final factor in const [1.0, 0.82, 0.68]) {
      final targetBps = (((_maxUploadBytes * 0.94) * 8) / durationSec * factor)
          .floor()
          .clamp(220000, 3500000);
      final stream = video.captureStream();
      final chunks = <html.Blob>[];
      final recorder = html.MediaRecorder(
        stream,
        {
          'mimeType': mime,
          'videoBitsPerSecond': targetBps,
          'audioBitsPerSecond': 96000,
        },
      );

      final stopFuture = _mediaRecorderStopEvent.forTarget(recorder).first;
      _mediaRecorderDataEvent.forTarget(recorder).listen((event) {
        final data = event.data;
        if (data != null && data.size > 0) {
          chunks.add(data);
        }
      });

      video.currentTime = 0;
      recorder.start(250);
      await video.play();
      await video.onEnded.first;
      recorder.stop();
      await stopFuture;
      for (final track in stream.getTracks()) {
        track.stop();
      }

      final encoded = await _blobToBytes(html.Blob(chunks, mime));
      if (encoded == null || encoded.isEmpty) {
        continue;
      }
      if (bestBytes == null ||
          encoded.lengthInBytes < bestBytes.lengthInBytes) {
        bestBytes = encoded;
      }
      if (encoded.lengthInBytes <= _maxUploadBytes) {
        return encoded;
      }
    }

    if (bestBytes != null && bestBytes.lengthInBytes < input.lengthInBytes) {
      return bestBytes;
    }
    return input;
  } finally {
    video.pause();
    html.Url.revokeObjectUrl(inputUrl);
  }
}

Future<Uint8List?> _blobToBytes(html.Blob blob) async {
  final reader = html.FileReader();
  final completer = Completer<Uint8List?>();
  reader.onLoadEnd.first.then((_) {
    final result = reader.result;
    if (result is ByteBuffer) {
      completer.complete(Uint8List.view(result));
      return;
    }
    completer.complete(null);
  });
  reader.readAsArrayBuffer(blob);
  return completer.future;
}
