import 'dart:async';

import 'package:flutter/material.dart';

import '../../api.dart';

class ReportScreen extends StatefulWidget {
  const ReportScreen({super.key, required this.api, required this.setId});

  final Api api;
  final String setId;

  @override
  State<ReportScreen> createState() => _ReportScreenState();
}

class _ReportScreenState extends State<ReportScreen> {
  Object? _err;
  Map<String, dynamic>? _report;

  @override
  void initState() {
    super.initState();
    unawaited(_load());
  }

  Future<void> _load() async {
    try {
      final rep = await widget.api.getReport(widget.setId);
      if (!mounted) return;
      setState(() => _report = rep);
    } catch (e) {
      if (!mounted) return;
      setState(() => _err = e);
    }
  }

  @override
  Widget build(BuildContext context) {
    final report = _report;
    return Scaffold(
      appBar: AppBar(title: const Text('报告')),
      body: Padding(
        padding: const EdgeInsets.all(16),
        child: report == null
            ? _err == null
                ? const Center(child: CircularProgressIndicator())
                : Text('Error: $_err')
            : ListView(
                children: [
                  Text('Top3', style: Theme.of(context).textTheme.titleLarge),
                  const SizedBox(height: 8),
                  for (final f in (report['top3'] as List<dynamic>)) _FindingCard(f as Map<String, dynamic>),
                  const SizedBox(height: 16),
                  ExpansionTile(
                    title: const Text('全部问题清单'),
                    children: [
                      for (final f in (report['all'] as List<dynamic>))
                        ListTile(
                          dense: true,
                          title: Text('${(f as Map<String, dynamic>)['label']}'),
                          subtitle: Text('${f['timeRangeMmss']} · ${f['severity']}'),
                        ),
                    ],
                  ),
                ],
              ),
      ),
    );
  }
}

class _FindingCard extends StatelessWidget {
  const _FindingCard(this.f);

  final Map<String, dynamic> f;

  @override
  Widget build(BuildContext context) {
    final metrics = (f['metrics'] as Map<String, dynamic>? ?? const {});
    final metricsText = metrics.entries.map((e) => '${e.key}=${e.value}').join(' ');
    return Card(
      child: Padding(
        padding: const EdgeInsets.all(12),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Text('${f['label']}  (${f['severity']})', style: Theme.of(context).textTheme.titleMedium),
            const SizedBox(height: 6),
            Text('${f['timeRangeMmss']}  ${metricsText.isEmpty ? '' : metricsText}'),
          ],
        ),
      ),
    );
  }
}