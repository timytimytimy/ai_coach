import 'dart:async';
import 'dart:typed_data';
import 'dart:html' as html;
import 'package:flutter/foundation.dart';

import 'package:crypto/crypto.dart';
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

void _logWeb(String message) {
  debugPrint('[ssc-web] $message');
  html.window.console.log('[ssc-web] $message');
}

Future<PickedVideo?> pickVideo() async {
  try {
    _logWeb('pickVideo start');
    final selectedFile = await _pickVideoFile();
    if (selectedFile == null) {
      _logWeb('pickVideo no file selected');
      return null;
    }
    _logWeb(
      'pickVideo selected name=${selectedFile.name} size=${selectedFile.size} type=${selectedFile.type}',
    );

    final rawBytes = await _fileToBytes(selectedFile);
    _logWeb('pickVideo rawBytes=${rawBytes?.length ?? 0}');
    final bytes = rawBytes == null || rawBytes.length <= _maxUploadBytes
        ? rawBytes
        : await _compressBytesIfNeeded(rawBytes, selectedFile.name);
    _logWeb('pickVideo finalBytes=${bytes?.length ?? 0}');
    if (bytes == null || bytes.isEmpty) {
      _logWeb('pickVideo bytes missing after read/compress');
      return null;
    }

    final sha = sha256.convert(bytes).toString();

    final outName = _outputName(
      selectedFile.name,
      compressed: !identical(bytes, rawBytes),
    );
    final blob = html.Blob([bytes], _mimeFromName(outName));
    final objectUrl = html.Url.createObjectUrlFromBlob(blob);

    _logWeb('pickVideo initializing video metadata objectUrl');
    final vc = VideoPlayerController.networkUrl(Uri.parse(objectUrl));
    await vc.initialize();
    final durationMs = vc.value.duration.inMilliseconds;
    final size = vc.value.size;
    await vc.dispose();
    _logWeb('pickVideo initialized durationMs=$durationMs size=${size.width}x${size.height}');

    return PickedVideo(
      fileName: outName,
      bytes: bytes,
      objectUrl: objectUrl,
      sha256: sha,
      durationMs: durationMs,
      width: size.width.round(),
      height: size.height.round(),
    );
  } catch (e) {
    _logWeb('pickVideo error=$e');
    rethrow;
  }
}

Future<html.File?> _pickVideoFile() async {
  _logWeb('open native file input');
  final input = html.FileUploadInputElement()
    ..accept = 'video/*,.mp4,.mov,.m4v,.webm'
    ..multiple = false;
  input.style
    ..position = 'fixed'
    ..left = '-1000px'
    ..top = '0'
    ..width = '1px'
    ..height = '1px'
    ..opacity = '0'
    ..pointerEvents = 'none';
  html.document.body?.append(input);
  final completer = Completer<html.File?>();

  void finish(html.File? file) {
    input.remove();
    if (!completer.isCompleted) {
      completer.complete(file);
    }
  }

  void handleSelection(String source) {
    _logWeb('$source fired');
    final files = input.files;
    if (files == null || files.isEmpty) {
      _logWeb('$source with no files');
      finish(null);
      return;
    }
    _logWeb('$source received first file=${files.first.name}');
    finish(files.first);
  }

  input.onInput.first.then((_) {
    handleSelection('file input input');
  }).catchError((_) {
    _logWeb('file input onInput error');
    finish(null);
  });

  input.onChange.first.then((_) {
    handleSelection('file input change');
  }).catchError((_) {
    _logWeb('file input onChange error');
    finish(null);
  });

  input.click();
  return completer.future;
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
  _logWeb('compress start originalBytes=${input.lengthInBytes} name=$originalName');

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
      late final html.MediaStream stream;
      try {
        final dynamic videoDyn = video;
        stream = videoDyn.captureStream() as html.MediaStream;
      } catch (e) {
        _logWeb('compress captureStream unsupported, fallback to original bytes error=$e');
        return input;
      }
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
        _logWeb('compress factor=$factor produced empty bytes');
        continue;
      }
      _logWeb('compress factor=$factor produced bytes=${encoded.lengthInBytes}');
      if (bestBytes == null ||
          encoded.lengthInBytes < bestBytes.lengthInBytes) {
        bestBytes = encoded;
      }
      if (encoded.lengthInBytes <= _maxUploadBytes) {
        return encoded;
      }
    }

    if (bestBytes != null && bestBytes.lengthInBytes < input.lengthInBytes) {
      _logWeb('compress using bestBytes=${bestBytes.lengthInBytes}');
      return bestBytes;
    }
    _logWeb('compress fallback to original bytes');
    return input;
  } finally {
    video.pause();
    html.Url.revokeObjectUrl(inputUrl);
  }
}

Future<Uint8List?> _blobToBytes(html.Blob blob) async {
  _logWeb('blobToBytes start size=${blob.size}');
  final reader = html.FileReader();
  final completer = Completer<Uint8List?>();
  reader.onLoadEnd.first.then((_) {
    final result = reader.result;
    _logWeb('blobToBytes resultType=${result.runtimeType}');
    if (result is ByteBuffer) {
      _logWeb('blobToBytes success');
      completer.complete(Uint8List.view(result));
      return;
    }
    if (result is Uint8List) {
      _logWeb('blobToBytes success from Uint8List');
      completer.complete(result);
      return;
    }
    if (result is List<int>) {
      _logWeb('blobToBytes success from List<int>');
      completer.complete(Uint8List.fromList(result));
      return;
    }
    if (result is TypedData) {
      _logWeb('blobToBytes success from TypedData');
      completer.complete(result.buffer.asUint8List());
      return;
    }
    _logWeb('blobToBytes unsupported resultType=${result.runtimeType}');
    completer.complete(null);
  });
  reader.readAsArrayBuffer(blob);
  return completer.future;
}

Future<Uint8List?> _fileToBytes(html.File file) async {
  return _blobToBytes(file);
}
