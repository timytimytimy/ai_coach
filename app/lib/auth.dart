import 'dart:convert';

import 'package:flutter/foundation.dart';
import 'package:shared_preferences/shared_preferences.dart';

class AuthSnapshot {
  const AuthSnapshot({
    required this.accessToken,
    required this.refreshToken,
    required this.user,
    required this.quota,
  });

  final String accessToken;
  final String refreshToken;
  final Map<String, dynamic> user;
  final Map<String, dynamic>? quota;

  String get displayName =>
      (user['displayName'] as String?) ?? (user['username'] as String?) ?? '用户';

  String get username => (user['username'] as String?) ?? '';

  Map<String, dynamic> toJson() => {
        'accessToken': accessToken,
        'refreshToken': refreshToken,
        'user': user,
        'quota': quota,
      };

  static AuthSnapshot? fromJson(Map<String, dynamic>? json) {
    if (json == null) return null;
    final accessToken = json['accessToken'];
    final refreshToken = json['refreshToken'];
    final user = json['user'];
    if (accessToken is! String || refreshToken is! String || user is! Map) {
      return null;
    }
    return AuthSnapshot(
      accessToken: accessToken,
      refreshToken: refreshToken,
      user: Map<String, dynamic>.from(user),
      quota: json['quota'] is Map
          ? Map<String, dynamic>.from(json['quota'] as Map)
          : null,
    );
  }
}

class AuthController extends ChangeNotifier {
  AuthController();

  static const _storageKey = 'ssc_auth_session_v1';

  bool _initialized = false;
  AuthSnapshot? _session;

  bool get initialized => _initialized;
  bool get isLoggedIn => _session != null;
  AuthSnapshot? get session => _session;
  String? get accessToken => _session?.accessToken;
  String? get refreshToken => _session?.refreshToken;

  Future<void> init() async {
    final prefs = await SharedPreferences.getInstance();
    final raw = prefs.getString(_storageKey);
    if (raw != null && raw.isNotEmpty) {
      try {
        _session = AuthSnapshot.fromJson(
          jsonDecode(raw) as Map<String, dynamic>,
        );
      } catch (_) {
        _session = null;
      }
    }
    _initialized = true;
    notifyListeners();
  }

  Future<void> setSession({
    required String accessToken,
    required String refreshToken,
    required Map<String, dynamic> user,
    Map<String, dynamic>? quota,
  }) async {
    _session = AuthSnapshot(
      accessToken: accessToken,
      refreshToken: refreshToken,
      user: Map<String, dynamic>.from(user),
      quota: quota == null ? null : Map<String, dynamic>.from(quota),
    );
    await _persist();
    notifyListeners();
  }

  Future<void> updateUser({
    Map<String, dynamic>? user,
    Map<String, dynamic>? quota,
  }) async {
    final current = _session;
    if (current == null) return;
    _session = AuthSnapshot(
      accessToken: current.accessToken,
      refreshToken: current.refreshToken,
      user: user == null ? current.user : Map<String, dynamic>.from(user),
      quota: quota ?? current.quota,
    );
    await _persist();
    notifyListeners();
  }

  Future<void> updateTokens({
    required String accessToken,
    required String refreshToken,
  }) async {
    final current = _session;
    if (current == null) return;
    _session = AuthSnapshot(
      accessToken: accessToken,
      refreshToken: refreshToken,
      user: current.user,
      quota: current.quota,
    );
    await _persist();
    notifyListeners();
  }

  Future<void> clear() async {
    _session = null;
    final prefs = await SharedPreferences.getInstance();
    await prefs.remove(_storageKey);
    notifyListeners();
  }

  Future<void> _persist() async {
    final prefs = await SharedPreferences.getInstance();
    final session = _session;
    if (session == null) {
      await prefs.remove(_storageKey);
      return;
    }
    await prefs.setString(_storageKey, jsonEncode(session.toJson()));
  }
}
