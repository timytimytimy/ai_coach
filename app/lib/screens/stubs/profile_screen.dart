import 'package:flutter/material.dart';

class ProfileScreen extends StatelessWidget {
  const ProfileScreen({super.key});

  @override
  Widget build(BuildContext context) {
    return SafeArea(
      child: Center(child: Text('我的', style: Theme.of(context).textTheme.headlineSmall)),
    );
  }
}