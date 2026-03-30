import 'dart:convert';

import 'package:http/http.dart' as http;

import 'platform_video_source.dart';

class Api {
  Api(this.baseUrl);

  final String baseUrl;

  Future<Map<String, dynamic>> uploadVideo(
      {required String videoId, required PickedVideo pickedVideo}) async {
    final uri = Uri.parse('$baseUrl/v1/videos/$videoId/upload');
    final req = http.MultipartRequest('POST', uri);

    final bytes = pickedVideo.bytes;
    final path = pickedVideo.path;

    if (bytes != null) {
      req.files.add(http.MultipartFile.fromBytes('file', bytes,
          filename: pickedVideo.fileName));
    } else if (path != null && path.isNotEmpty) {
      req.files.add(await http.MultipartFile.fromPath('file', path,
          filename: pickedVideo.fileName));
    } else {
      throw Exception('No upload source: missing bytes and path');
    }

    final streamed = await req.send();
    final res = await http.Response.fromStream(streamed);
    _ensureOk(res);
    return jsonDecode(res.body) as Map<String, dynamic>;
  }

  Future<String> createWorkout(String day) async {
    final res = await http.post(
      Uri.parse('$baseUrl/v1/workouts'),
      headers: {'content-type': 'application/json'},
      body: jsonEncode({'day': day}),
    );
    _ensureOk(res);
    return (jsonDecode(res.body) as Map<String, dynamic>)['workoutId']
        as String;
  }

  Future<String> createSet({
    required String workoutId,
    required String exercise,
    required double weightKg,
    required int repsDone,
    String? videoId,
  }) async {
    final res = await http.post(
      Uri.parse('$baseUrl/v1/workouts/$workoutId/sets'),
      headers: {'content-type': 'application/json'},
      body: jsonEncode({
        'exercise': exercise,
        'weightKg': weightKg,
        'repsDone': repsDone,
        'videoId': videoId,
      }),
    );
    _ensureOk(res);
    return (jsonDecode(res.body) as Map<String, dynamic>)['setId'] as String;
  }

  Future<Map<String, dynamic>> createVideoStub() async {
    final res = await http.post(Uri.parse('$baseUrl/v1/videos'));
    _ensureOk(res);
    return jsonDecode(res.body) as Map<String, dynamic>;
  }

  Future<Map<String, dynamic>> finalizeVideoStub({
    required String videoId,
    required String sha256,
    required int durationMs,
    required int fps,
    required int width,
    required int height,
  }) async {
    final res = await http.post(
      Uri.parse('$baseUrl/v1/videos/$videoId/finalize'),
      headers: {'content-type': 'application/json'},
      body: jsonEncode({
        'sha256': sha256,
        'durationMs': durationMs,
        'fps': fps,
        'width': width,
        'height': height,
      }),
    );
    _ensureOk(res);
    return jsonDecode(res.body) as Map<String, dynamic>;
  }

  Future<Map<String, dynamic>> createAnalysisJob({
    required String setId,
    required String videoSha256,
    String? coachSoul,
  }) async {
    final res = await http.post(
      Uri.parse('$baseUrl/v1/sets/$setId/analysis-jobs'),
      headers: {'content-type': 'application/json'},
      body: jsonEncode({
        'videoSha256': videoSha256,
        'pipelineVersion': 'pipe-v4',
        if (coachSoul != null && coachSoul.isNotEmpty) 'coachSoul': coachSoul,
      }),
    );
    _ensureOk(res);
    return jsonDecode(res.body) as Map<String, dynamic>;
  }

  Future<Map<String, dynamic>> getJob(String jobId) async {
    final res = await http.get(Uri.parse('$baseUrl/v1/analysis-jobs/$jobId'));
    _ensureOk(res);
    return jsonDecode(res.body) as Map<String, dynamic>;
  }

  Future<Map<String, dynamic>> getReport(String setId) async {
    final res = await http.get(Uri.parse('$baseUrl/v1/sets/$setId/report'));
    _ensureOk(res);
    return jsonDecode(res.body) as Map<String, dynamic>;
  }
}

void _ensureOk(http.Response res) {
  if (res.statusCode >= 200 && res.statusCode < 300) return;
  throw Exception('HTTP ${res.statusCode}: ${res.body}');
}
