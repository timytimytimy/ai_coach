import 'dart:convert';

import 'package:http/http.dart' as http;

import 'platform_video_source.dart';

class Api {
  Api(
    this.baseUrl, {
    String? Function()? accessTokenProvider,
    Future<bool> Function()? onUnauthorized,
  })  : _accessTokenProvider = accessTokenProvider,
        _onUnauthorized = onUnauthorized;

  final String baseUrl;
  final String? Function()? _accessTokenProvider;
  final Future<bool> Function()? _onUnauthorized;

  Map<String, String> _headers({bool json = false}) {
    final headers = <String, String>{};
    final token = _accessTokenProvider?.call();
    if (token != null && token.isNotEmpty) {
      headers['authorization'] = 'Bearer $token';
    }
    if (json) {
      headers['content-type'] = 'application/json';
    }
    return headers;
  }

  Future<http.Response> _sendWithAuthRetry(
    Future<http.Response> Function() send,
  ) async {
    var res = await send();
    if (res.statusCode != 401 || _onUnauthorized == null) return res;
    final refreshed = await _onUnauthorized.call();
    if (!refreshed) return res;
    res = await send();
    return res;
  }

  Future<Map<String, dynamic>> uploadVideo(
      {required String videoId, required PickedVideo pickedVideo}) async {
    final uri = Uri.parse('$baseUrl/v1/videos/$videoId/upload');
    final req = http.MultipartRequest('POST', uri);
    req.headers.addAll(_headers());

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

    final res = await _sendWithAuthRetry(() async {
      final retryReq = http.MultipartRequest('POST', uri);
      retryReq.headers.addAll(_headers());
      if (bytes != null) {
        retryReq.files.add(http.MultipartFile.fromBytes('file', bytes,
            filename: pickedVideo.fileName));
      } else if (path != null && path.isNotEmpty) {
        retryReq.files.add(await http.MultipartFile.fromPath('file', path,
            filename: pickedVideo.fileName));
      }
      final streamed = await retryReq.send();
      return http.Response.fromStream(streamed);
    });
    _ensureOk(method: 'POST', uri: uri, res: res);
    return jsonDecode(res.body) as Map<String, dynamic>;
  }

  Future<String> createWorkout(String day) async {
    final uri = Uri.parse('$baseUrl/v1/workouts');
    final res = await _sendWithAuthRetry(() => http.post(
          uri,
          headers: _headers(json: true),
          body: jsonEncode({'day': day}),
        ));
    _ensureOk(method: 'POST', uri: uri, res: res);
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
    final uri = Uri.parse('$baseUrl/v1/workouts/$workoutId/sets');
    final res = await _sendWithAuthRetry(() => http.post(
          uri,
          headers: _headers(json: true),
          body: jsonEncode({
            'exercise': exercise,
            'weightKg': weightKg,
            'repsDone': repsDone,
            'videoId': videoId,
          }),
        ));
    _ensureOk(method: 'POST', uri: uri, res: res);
    return (jsonDecode(res.body) as Map<String, dynamic>)['setId'] as String;
  }

  Future<Map<String, dynamic>> createVideoStub() async {
    final uri = Uri.parse('$baseUrl/v1/videos');
    final res =
        await _sendWithAuthRetry(() => http.post(uri, headers: _headers()));
    _ensureOk(method: 'POST', uri: uri, res: res);
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
    final uri = Uri.parse('$baseUrl/v1/videos/$videoId/finalize');
    final res = await _sendWithAuthRetry(() => http.post(
          uri,
          headers: _headers(json: true),
          body: jsonEncode({
            'sha256': sha256,
            'durationMs': durationMs,
            'fps': fps,
            'width': width,
            'height': height,
          }),
        ));
    _ensureOk(method: 'POST', uri: uri, res: res);
    return jsonDecode(res.body) as Map<String, dynamic>;
  }

  Future<Map<String, dynamic>> createAnalysisJob({
    required String setId,
    required String videoSha256,
    String? coachSoul,
  }) async {
    final uri = Uri.parse('$baseUrl/v1/sets/$setId/analysis-jobs');
    final res = await _sendWithAuthRetry(() => http.post(
          uri,
          headers: _headers(json: true),
          body: jsonEncode({
            'videoSha256': videoSha256,
            'pipelineVersion': 'pipe-v4',
            if (coachSoul != null && coachSoul.isNotEmpty)
              'coachSoul': coachSoul,
          }),
        ));
    _ensureOk(method: 'POST', uri: uri, res: res);
    return jsonDecode(res.body) as Map<String, dynamic>;
  }

  Future<Map<String, dynamic>> getJob(String jobId) async {
    final uri = Uri.parse('$baseUrl/v1/analysis-jobs/$jobId');
    final res =
        await _sendWithAuthRetry(() => http.get(uri, headers: _headers()));
    _ensureOk(method: 'GET', uri: uri, res: res);
    return jsonDecode(res.body) as Map<String, dynamic>;
  }

  Future<Map<String, dynamic>> getReport(String setId) async {
    final uri = Uri.parse('$baseUrl/v1/sets/$setId/report');
    final res =
        await _sendWithAuthRetry(() => http.get(uri, headers: _headers()));
    _ensureOk(method: 'GET', uri: uri, res: res);
    return jsonDecode(res.body) as Map<String, dynamic>;
  }

  Future<Map<String, dynamic>> register({
    required String username,
    required String password,
    required String displayName,
  }) async {
    final uri = Uri.parse('$baseUrl/v1/auth/register');
    final res = await http.post(
      uri,
      headers: _headers(json: true),
      body: jsonEncode({
        'username': username,
        'password': password,
        'displayName': displayName,
      }),
    );
    _ensureOk(method: 'POST', uri: uri, res: res);
    return jsonDecode(res.body) as Map<String, dynamic>;
  }

  Future<Map<String, dynamic>> login({
    required String username,
    required String password,
  }) async {
    final uri = Uri.parse('$baseUrl/v1/auth/login');
    final res = await http.post(
      uri,
      headers: _headers(json: true),
      body: jsonEncode({
        'username': username,
        'password': password,
      }),
    );
    _ensureOk(method: 'POST', uri: uri, res: res);
    return jsonDecode(res.body) as Map<String, dynamic>;
  }

  Future<Map<String, dynamic>> refresh({required String refreshToken}) async {
    final uri = Uri.parse('$baseUrl/v1/auth/refresh');
    final res = await http.post(
      uri,
      headers: _headers(json: true),
      body: jsonEncode({'refreshToken': refreshToken}),
    );
    _ensureOk(method: 'POST', uri: uri, res: res);
    return jsonDecode(res.body) as Map<String, dynamic>;
  }

  Future<void> logout() async {
    final uri = Uri.parse('$baseUrl/v1/auth/logout');
    final res =
        await _sendWithAuthRetry(() => http.post(uri, headers: _headers()));
    _ensureOk(method: 'POST', uri: uri, res: res);
  }

  Future<Map<String, dynamic>> getMe() async {
    final uri = Uri.parse('$baseUrl/v1/me');
    final res =
        await _sendWithAuthRetry(() => http.get(uri, headers: _headers()));
    _ensureOk(method: 'GET', uri: uri, res: res);
    return jsonDecode(res.body) as Map<String, dynamic>;
  }

  Future<Map<String, dynamic>> updateProfile({
    required String displayName,
  }) async {
    final uri = Uri.parse('$baseUrl/v1/me/profile');
    final res = await _sendWithAuthRetry(() => http.patch(
          uri,
          headers: _headers(json: true),
          body: jsonEncode({'displayName': displayName}),
        ));
    _ensureOk(method: 'PATCH', uri: uri, res: res);
    return jsonDecode(res.body) as Map<String, dynamic>;
  }

  Future<void> changePassword({
    required String currentPassword,
    required String newPassword,
  }) async {
    final uri = Uri.parse('$baseUrl/v1/me/change-password');
    final res = await _sendWithAuthRetry(() => http.post(
          uri,
          headers: _headers(json: true),
          body: jsonEncode({
            'currentPassword': currentPassword,
            'newPassword': newPassword,
          }),
        ));
    _ensureOk(method: 'POST', uri: uri, res: res);
  }
}

void _ensureOk({
  required String method,
  required Uri uri,
  required http.Response res,
}) {
  if (res.statusCode >= 200 && res.statusCode < 300) return;
  throw Exception('$method $uri -> HTTP ${res.statusCode}: ${res.body}');
}
