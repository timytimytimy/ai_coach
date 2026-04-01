import 'package:flutter/material.dart';

import '../../api.dart';
import '../../auth.dart';

class AuthScreen extends StatefulWidget {
  const AuthScreen({
    super.key,
    required this.api,
    required this.auth,
  });

  final Api api;
  final AuthController auth;

  @override
  State<AuthScreen> createState() => _AuthScreenState();
}

class _AuthScreenState extends State<AuthScreen> {
  final _username = TextEditingController();
  final _displayName = TextEditingController();
  final _password = TextEditingController();
  bool _registerMode = false;
  bool _submitting = false;
  String? _error;

  @override
  void dispose() {
    _username.dispose();
    _displayName.dispose();
    _password.dispose();
    super.dispose();
  }

  Future<void> _submit() async {
    setState(() {
      _submitting = true;
      _error = null;
    });
    try {
      final result = _registerMode
          ? await widget.api.register(
              username: _username.text.trim(),
              password: _password.text,
              displayName: _displayName.text.trim().isEmpty
                  ? _username.text.trim()
                  : _displayName.text.trim(),
            )
          : await widget.api.login(
              username: _username.text.trim(),
              password: _password.text,
            );
      final session = Map<String, dynamic>.from(result['session'] as Map);
      final user = Map<String, dynamic>.from(result['user'] as Map);
      await widget.auth.setSession(
        accessToken: session['accessToken'] as String,
        refreshToken: session['refreshToken'] as String,
        user: user,
      );
      final me = await widget.api.getMe();
      await widget.auth.updateUser(
        user: Map<String, dynamic>.from(me['user'] as Map),
        quota: me['quota'] is Map
            ? Map<String, dynamic>.from(me['quota'] as Map)
            : null,
      );
    } catch (e) {
      setState(() => _error = e.toString());
    } finally {
      if (mounted) {
        setState(() => _submitting = false);
      }
    }
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      backgroundColor: const Color(0xFF0B0D10),
      body: SafeArea(
        child: Center(
          child: ConstrainedBox(
            constraints: const BoxConstraints(maxWidth: 420),
            child: Padding(
              padding: const EdgeInsets.all(24),
              child: Column(
                mainAxisAlignment: MainAxisAlignment.center,
                crossAxisAlignment: CrossAxisAlignment.stretch,
                children: [
                  Text(
                    'Smart Strength Coach',
                    textAlign: TextAlign.center,
                    style: Theme.of(context).textTheme.headlineMedium?.copyWith(
                          fontWeight: FontWeight.w800,
                        ),
                  ),
                  const SizedBox(height: 12),
                  Text(
                    _registerMode ? '注册后才能上传和分析视频' : '登录后继续使用训练分析',
                    textAlign: TextAlign.center,
                    style: Theme.of(context).textTheme.bodyMedium?.copyWith(
                          color: Colors.white70,
                        ),
                  ),
                  const SizedBox(height: 28),
                  TextField(
                    controller: _username,
                    decoration: const InputDecoration(
                      labelText: '用户名',
                      border: OutlineInputBorder(),
                    ),
                  ),
                  if (_registerMode) ...[
                    const SizedBox(height: 14),
                    TextField(
                      controller: _displayName,
                      decoration: const InputDecoration(
                        labelText: '显示名称',
                        border: OutlineInputBorder(),
                      ),
                    ),
                  ],
                  const SizedBox(height: 14),
                  TextField(
                    controller: _password,
                    obscureText: true,
                    decoration: const InputDecoration(
                      labelText: '密码',
                      border: OutlineInputBorder(),
                    ),
                  ),
                  if (_error != null) ...[
                    const SizedBox(height: 12),
                    Text(
                      _error!,
                      style: Theme.of(context).textTheme.bodySmall?.copyWith(
                            color: const Color(0xFFFF8F8F),
                          ),
                    ),
                  ],
                  const SizedBox(height: 18),
                  FilledButton(
                    onPressed: _submitting ? null : _submit,
                    child: Text(_submitting
                        ? '处理中…'
                        : (_registerMode ? '注册并登录' : '登录')),
                  ),
                  const SizedBox(height: 10),
                  TextButton(
                    onPressed: _submitting
                        ? null
                        : () {
                            setState(() {
                              _registerMode = !_registerMode;
                              _error = null;
                            });
                          },
                    child: Text(_registerMode ? '已有账号，去登录' : '没有账号，去注册'),
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
