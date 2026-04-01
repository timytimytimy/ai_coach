import 'package:flutter/material.dart';

import '../../api.dart';
import '../../auth.dart';

class ProfileScreen extends StatefulWidget {
  const ProfileScreen({
    super.key,
    required this.api,
    required this.auth,
  });

  final Api api;
  final AuthController auth;

  @override
  State<ProfileScreen> createState() => _ProfileScreenState();
}

class _ProfileScreenState extends State<ProfileScreen> {
  bool _busy = false;

  Future<void> _refreshMe() async {
    final me = await widget.api.getMe();
    await widget.auth.updateUser(
      user: Map<String, dynamic>.from(me['user'] as Map),
      quota: me['quota'] is Map
          ? Map<String, dynamic>.from(me['quota'] as Map)
          : null,
    );
  }

  Future<void> _changeDisplayName() async {
    final current = widget.auth.session;
    if (current == null) return;
    final controller = TextEditingController(text: current.displayName);
    final result = await showDialog<String>(
      context: context,
      builder: (context) => AlertDialog(
        title: const Text('修改用户名'),
        content: TextField(
          controller: controller,
          decoration: const InputDecoration(labelText: '显示名称'),
        ),
        actions: [
          TextButton(
              onPressed: () => Navigator.of(context).pop(),
              child: const Text('取消')),
          FilledButton(
            onPressed: () => Navigator.of(context).pop(controller.text.trim()),
            child: const Text('保存'),
          ),
        ],
      ),
    );
    if (result == null || result.isEmpty) return;
    setState(() => _busy = true);
    try {
      final updated = await widget.api.updateProfile(displayName: result);
      await widget.auth
          .updateUser(user: Map<String, dynamic>.from(updated['user'] as Map));
      await _refreshMe();
    } finally {
      if (mounted) setState(() => _busy = false);
    }
  }

  Future<void> _changePassword() async {
    final currentController = TextEditingController();
    final newController = TextEditingController();
    final result = await showDialog<bool>(
      context: context,
      builder: (context) => AlertDialog(
        title: const Text('修改密码'),
        content: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            TextField(
              controller: currentController,
              obscureText: true,
              decoration: const InputDecoration(labelText: '当前密码'),
            ),
            const SizedBox(height: 12),
            TextField(
              controller: newController,
              obscureText: true,
              decoration: const InputDecoration(labelText: '新密码'),
            ),
          ],
        ),
        actions: [
          TextButton(
              onPressed: () => Navigator.of(context).pop(false),
              child: const Text('取消')),
          FilledButton(
              onPressed: () => Navigator.of(context).pop(true),
              child: const Text('确认')),
        ],
      ),
    );
    if (result != true) return;
    setState(() => _busy = true);
    try {
      await widget.api.changePassword(
        currentPassword: currentController.text,
        newPassword: newController.text,
      );
      await widget.auth.clear();
    } finally {
      if (mounted) setState(() => _busy = false);
    }
  }

  Future<void> _logout() async {
    setState(() => _busy = true);
    try {
      await widget.api.logout();
    } catch (_) {
    } finally {
      await widget.auth.clear();
      if (mounted) setState(() => _busy = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    final session = widget.auth.session;
    final quota = session?.quota;
    final remaining = quota?['remaining'];
    return SafeArea(
      child: ListView(
        padding: const EdgeInsets.all(20),
        children: [
          Text(
            session?.displayName ?? '我的',
            style: Theme.of(context).textTheme.headlineSmall?.copyWith(
                  fontWeight: FontWeight.w800,
                ),
          ),
          const SizedBox(height: 8),
          Text(
            '@${session?.username ?? ''}',
            style: Theme.of(context).textTheme.bodyMedium?.copyWith(
                  color: Colors.white70,
                ),
          ),
          const SizedBox(height: 18),
          Card(
            child: Padding(
              padding: const EdgeInsets.all(16),
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  const Text('剩余额度'),
                  const SizedBox(height: 10),
                  Text('${remaining is num ? remaining.toInt() : '-'}'),
                ],
              ),
            ),
          ),
          const SizedBox(height: 12),
          FilledButton.tonal(
            onPressed: _busy ? null : _changeDisplayName,
            child: const Text('修改用户名'),
          ),
          const SizedBox(height: 10),
          FilledButton.tonal(
            onPressed: _busy ? null : _changePassword,
            child: const Text('修改密码'),
          ),
          const SizedBox(height: 10),
          OutlinedButton(
            onPressed: _busy ? null : _logout,
            child: Text(_busy ? '处理中…' : '退出登录'),
          ),
        ],
      ),
    );
  }
}
