import 'package:flutter/material.dart';

class AnalysisScreen extends StatelessWidget {
  const AnalysisScreen({super.key});

  @override
  Widget build(BuildContext context) {
    return SafeArea(
      child: Center(child: Text('分析', style: Theme.of(context).textTheme.headlineSmall)),
    );
  }
}