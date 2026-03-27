import 'package:flutter/material.dart';

class PlanScreen extends StatelessWidget {
  const PlanScreen({super.key});

  @override
  Widget build(BuildContext context) {
    return SafeArea(
      child: Center(child: Text('计划', style: Theme.of(context).textTheme.headlineSmall)),
    );
  }
}