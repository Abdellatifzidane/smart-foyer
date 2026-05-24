import 'package:flutter/material.dart';
import '../api/api_client.dart';
import '../api/models.dart';

/// Analytics screen: aggregate spending by week, month, category and enseigne.
///
/// Charts are drawn with CustomPaint (no extra dependency) so the app stays
/// lightweight. Three tabs:
///   - Période  : bar chart by week, then month
///   - Catégorie: horizontal bars by category
///   - Enseigne : horizontal bars + pie of share by enseigne
class AnalyticsScreen extends StatefulWidget {
  const AnalyticsScreen({super.key});

  @override
  State<AnalyticsScreen> createState() => _AnalyticsScreenState();
}

class _AnalyticsScreenState extends State<AnalyticsScreen> {
  late Future<HistoryStats> _future;

  @override
  void initState() {
    super.initState();
    _future = ApiClient.historyStats();
  }

  Future<void> _refresh() async {
    final stats = await ApiClient.historyStats();
    if (!mounted) return;
    setState(() => _future = Future.value(stats));
  }

  @override
  Widget build(BuildContext context) {
    return DefaultTabController(
      length: 3,
      child: Scaffold(
        appBar: AppBar(
          title: const Text('Analytics'),
          bottom: const TabBar(
            tabs: [
              Tab(icon: Icon(Icons.calendar_view_week_rounded), text: 'Période'),
              Tab(icon: Icon(Icons.category_rounded), text: 'Catégorie'),
              Tab(icon: Icon(Icons.store_rounded), text: 'Enseigne'),
            ],
          ),
        ),
        body: SafeArea(
          child: FutureBuilder<HistoryStats>(
            future: _future,
            builder: (context, snap) {
              if (snap.connectionState != ConnectionState.done) {
                return const Center(child: CircularProgressIndicator());
              }
              if (snap.hasError) {
                return Center(
                  child: Padding(
                    padding: const EdgeInsets.all(24),
                    child: Text('Erreur : ${snap.error}',
                        style: const TextStyle(color: Colors.red)),
                  ),
                );
              }
              final stats = snap.data!;
              if (stats.nReceipts == 0) {
                return const Center(
                  child: Padding(
                    padding: EdgeInsets.all(32),
                    child: Text(
                      'Aucun ticket scanné pour le moment.\n'
                      'Scannez un ticket pour commencer à analyser vos dépenses.',
                      textAlign: TextAlign.center,
                      style: TextStyle(color: Color(0xFF5C6470)),
                    ),
                  ),
                );
              }
              return RefreshIndicator(
                onRefresh: _refresh,
                child: TabBarView(
                  children: [
                    _PeriodTab(stats: stats),
                    _CategoryTab(stats: stats),
                    _EnseigneTab(stats: stats),
                  ],
                ),
              );
            },
          ),
        ),
      ),
    );
  }
}

class _SummaryHeader extends StatelessWidget {
  final HistoryStats stats;
  const _SummaryHeader({required this.stats});

  @override
  Widget build(BuildContext context) {
    return Container(
      margin: const EdgeInsets.fromLTRB(20, 16, 20, 8),
      padding: const EdgeInsets.all(18),
      decoration: BoxDecoration(
        color: const Color(0xFFE7F6EF),
        borderRadius: BorderRadius.circular(20),
        border: Border.all(color: const Color(0xFFB6E0CB)),
      ),
      child: Row(
        children: [
          _SummaryMetric(
            label: 'Dépensé',
            value: '${stats.totalSpent.toStringAsFixed(2)} €',
          ),
          const SizedBox(width: 16),
          _SummaryMetric(
            label: 'Économies',
            value: '${stats.totalSavings.toStringAsFixed(2)} €',
          ),
          const SizedBox(width: 16),
          _SummaryMetric(
            label: 'Tickets',
            value: '${stats.nReceipts}',
          ),
        ],
      ),
    );
  }
}

class _SummaryMetric extends StatelessWidget {
  final String label;
  final String value;
  const _SummaryMetric({required this.label, required this.value});

  @override
  Widget build(BuildContext context) {
    return Expanded(
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text(label,
              style: const TextStyle(fontSize: 11, color: Color(0xFF0E5C45))),
          const SizedBox(height: 2),
          Text(value,
              style: const TextStyle(
                  fontSize: 17,
                  fontWeight: FontWeight.w800,
                  color: Color(0xFF0E5C45))),
        ],
      ),
    );
  }
}

// ─── Period tab (weekly + monthly bar charts) ─────────────────────────

class _PeriodTab extends StatelessWidget {
  final HistoryStats stats;
  const _PeriodTab({required this.stats});

  @override
  Widget build(BuildContext context) {
    final weekly = stats.byWeek;
    final monthly = stats.byMonth;
    return ListView(
      padding: const EdgeInsets.only(bottom: 24),
      children: [
        _SummaryHeader(stats: stats),
        const _SectionTitle(title: 'Dépenses par semaine'),
        Padding(
          padding: const EdgeInsets.symmetric(horizontal: 20),
          child: weekly.isEmpty
              ? const _EmptyChart(message: 'Pas assez de données.')
              : _BarChart(
                  data: weekly.entries
                      .map((e) => BarPoint(label: _shortWeek(e.key), value: e.value))
                      .toList(),
                ),
        ),
        const SizedBox(height: 24),
        const _SectionTitle(title: 'Dépenses par mois'),
        Padding(
          padding: const EdgeInsets.symmetric(horizontal: 20),
          child: monthly.isEmpty
              ? const _EmptyChart(message: 'Pas assez de données.')
              : _BarChart(
                  data: monthly.entries
                      .map((e) => BarPoint(label: _shortMonth(e.key), value: e.value))
                      .toList(),
                ),
        ),
      ],
    );
  }

  String _shortWeek(String iso) {
    // "2026-W21" → "S21"
    final m = RegExp(r'W(\d+)').firstMatch(iso);
    return m == null ? iso : 'S${m[1]}';
  }

  String _shortMonth(String iso) {
    // "2026-05" → "05/26"
    final m = RegExp(r'^(\d{4})-(\d{2})').firstMatch(iso);
    return m == null ? iso : '${m[2]}/${m[1]!.substring(2)}';
  }
}

// ─── Category tab (horizontal bars) ───────────────────────────────────

class _CategoryTab extends StatelessWidget {
  final HistoryStats stats;
  const _CategoryTab({required this.stats});

  @override
  Widget build(BuildContext context) {
    final entries = stats.byCategory.entries.toList()
      ..sort((a, b) => b.value.compareTo(a.value));
    return ListView(
      padding: const EdgeInsets.only(bottom: 24),
      children: [
        _SummaryHeader(stats: stats),
        const _SectionTitle(title: 'Dépenses par catégorie'),
        if (entries.isEmpty)
          const Padding(
            padding: EdgeInsets.all(24),
            child: _EmptyChart(
                message:
                    'Aucune catégorie détectée.\nScannez plus de tickets pour enrichir le graphique.'),
          ),
        ...entries.map((e) => _HBar(
              label: e.key,
              value: e.value,
              maxValue: entries.first.value,
            )),
      ],
    );
  }
}

// ─── Enseigne tab ─────────────────────────────────────────────────────

class _EnseigneTab extends StatelessWidget {
  final HistoryStats stats;
  const _EnseigneTab({required this.stats});

  @override
  Widget build(BuildContext context) {
    final entries = stats.byEnseigne.entries.toList()
      ..sort((a, b) => b.value.compareTo(a.value));
    return ListView(
      padding: const EdgeInsets.only(bottom: 24),
      children: [
        _SummaryHeader(stats: stats),
        const _SectionTitle(title: 'Répartition par enseigne'),
        if (entries.isNotEmpty)
          Padding(
            padding: const EdgeInsets.symmetric(horizontal: 20, vertical: 8),
            child: SizedBox(
              height: 200,
              child: CustomPaint(
                painter: _PiePainter(
                  values: entries.map((e) => e.value).toList(),
                  labels: entries.map((e) => e.key).toList(),
                ),
                child: const SizedBox.expand(),
              ),
            ),
          ),
        if (entries.isEmpty)
          const Padding(
            padding: EdgeInsets.all(24),
            child: _EmptyChart(message: 'Aucune dépense enregistrée.'),
          ),
        ...entries.map((e) => _HBar(
              label: e.key.isEmpty ? 'Inconnu' : e.key,
              value: e.value,
              maxValue: entries.first.value,
            )),
      ],
    );
  }
}

// ─── Generic widgets ──────────────────────────────────────────────────

class _SectionTitle extends StatelessWidget {
  final String title;
  const _SectionTitle({required this.title});

  @override
  Widget build(BuildContext context) => Padding(
        padding: const EdgeInsets.fromLTRB(24, 20, 24, 8),
        child: Text(title,
            style: const TextStyle(fontSize: 16, fontWeight: FontWeight.w700)),
      );
}

class _EmptyChart extends StatelessWidget {
  final String message;
  const _EmptyChart({required this.message});

  @override
  Widget build(BuildContext context) => Container(
        margin: const EdgeInsets.symmetric(horizontal: 20, vertical: 8),
        padding: const EdgeInsets.all(20),
        decoration: BoxDecoration(
          color: const Color(0xFFF2F4F7),
          borderRadius: BorderRadius.circular(14),
        ),
        child: Center(
          child: Text(message,
              textAlign: TextAlign.center,
              style: const TextStyle(color: Color(0xFF5C6470))),
        ),
      );
}

class _HBar extends StatelessWidget {
  final String label;
  final double value;
  final double maxValue;
  const _HBar({
    required this.label,
    required this.value,
    required this.maxValue,
  });

  @override
  Widget build(BuildContext context) {
    final fraction = maxValue <= 0 ? 0.0 : (value / maxValue).clamp(0.0, 1.0);
    return Padding(
      padding: const EdgeInsets.fromLTRB(24, 8, 24, 0),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            mainAxisAlignment: MainAxisAlignment.spaceBetween,
            children: [
              Expanded(
                child: Text(label,
                    style: const TextStyle(fontSize: 13)),
              ),
              Text('${value.toStringAsFixed(2)} €',
                  style: const TextStyle(
                      fontSize: 13, fontWeight: FontWeight.w700)),
            ],
          ),
          const SizedBox(height: 4),
          ClipRRect(
            borderRadius: BorderRadius.circular(8),
            child: LinearProgressIndicator(
              value: fraction,
              minHeight: 8,
              backgroundColor: const Color(0xFFE3E6EB),
              valueColor: const AlwaysStoppedAnimation(Color(0xFF1B8A6B)),
            ),
          ),
        ],
      ),
    );
  }
}

class BarPoint {
  final String label;
  final double value;
  const BarPoint({required this.label, required this.value});
}

class _BarChart extends StatelessWidget {
  final List<BarPoint> data;
  const _BarChart({required this.data});

  @override
  Widget build(BuildContext context) {
    return SizedBox(
      height: 220,
      child: CustomPaint(
        painter: _BarChartPainter(data: data),
        child: const SizedBox.expand(),
      ),
    );
  }
}

class _BarChartPainter extends CustomPainter {
  final List<BarPoint> data;
  _BarChartPainter({required this.data});

  @override
  void paint(Canvas canvas, Size size) {
    if (data.isEmpty) return;
    final maxV = data.map((d) => d.value).reduce((a, b) => a > b ? a : b);
    if (maxV <= 0) return;

    const leftPad = 36.0;
    const rightPad = 8.0;
    const topPad = 12.0;
    const bottomPad = 28.0;
    final chartW = size.width - leftPad - rightPad;
    final chartH = size.height - topPad - bottomPad;
    final barGap = 6.0;
    final barW =
        ((chartW - barGap * (data.length - 1)) / data.length).clamp(4.0, 60.0);

    final axisPaint = Paint()
      ..color = const Color(0xFFE3E6EB)
      ..strokeWidth = 1;
    // Horizontal gridlines (4 levels)
    final textStyle = const TextStyle(fontSize: 9, color: Color(0xFF8A93A1));
    for (int i = 0; i <= 4; i++) {
      final y = topPad + chartH * (1 - i / 4);
      canvas.drawLine(
          Offset(leftPad, y), Offset(size.width - rightPad, y), axisPaint);
      final value = maxV * i / 4;
      final tp = TextPainter(
        text: TextSpan(text: value.toStringAsFixed(0), style: textStyle),
        textDirection: TextDirection.ltr,
      )..layout();
      tp.paint(canvas, Offset(leftPad - tp.width - 4, y - tp.height / 2));
    }

    final barPaint = Paint()..color = const Color(0xFF1B8A6B);

    for (int i = 0; i < data.length; i++) {
      final d = data[i];
      final h = chartH * (d.value / maxV);
      final x = leftPad + i * (barW + barGap);
      final rect = Rect.fromLTWH(x, topPad + (chartH - h), barW, h);
      canvas.drawRRect(
        RRect.fromRectAndRadius(rect, const Radius.circular(4)),
        barPaint,
      );

      // X-axis label
      final tp = TextPainter(
        text: TextSpan(text: d.label, style: textStyle),
        textDirection: TextDirection.ltr,
      )..layout(maxWidth: barW + barGap);
      tp.paint(
        canvas,
        Offset(x + (barW - tp.width) / 2, topPad + chartH + 6),
      );
    }
  }

  @override
  bool shouldRepaint(covariant _BarChartPainter old) =>
      old.data.length != data.length ||
      !_listsEqual(old.data, data);

  bool _listsEqual(List<BarPoint> a, List<BarPoint> b) {
    if (a.length != b.length) return false;
    for (int i = 0; i < a.length; i++) {
      if (a[i].label != b[i].label || a[i].value != b[i].value) return false;
    }
    return true;
  }
}

class _PiePainter extends CustomPainter {
  final List<double> values;
  final List<String> labels;
  _PiePainter({required this.values, required this.labels});

  static const _palette = [
    Color(0xFF1B8A6B),
    Color(0xFF2BB48E),
    Color(0xFF6FD4B1),
    Color(0xFFE0AC4F),
    Color(0xFFD06A4F),
    Color(0xFF6E7AE0),
    Color(0xFF8A93A1),
  ];

  @override
  void paint(Canvas canvas, Size size) {
    if (values.isEmpty) return;
    final total = values.fold<double>(0, (a, b) => a + b);
    if (total <= 0) return;

    final radius = (size.shortestSide / 2) - 8;
    final center = Offset(size.width / 2, size.height / 2);
    final rect = Rect.fromCircle(center: center, radius: radius);

    double start = -90 * 3.14159 / 180;
    for (int i = 0; i < values.length; i++) {
      final sweep = (values[i] / total) * 2 * 3.14159;
      final paint = Paint()..color = _palette[i % _palette.length];
      canvas.drawArc(rect, start, sweep, true, paint);
      start += sweep;
    }

    // Inner white circle for donut effect
    canvas.drawCircle(center, radius * 0.55, Paint()..color = Colors.white);
    // Total label
    final tp = TextPainter(
      text: TextSpan(
        text: '${total.toStringAsFixed(0)} €',
        style: const TextStyle(
            fontSize: 16,
            fontWeight: FontWeight.w800,
            color: Color(0xFF0E5C45)),
      ),
      textDirection: TextDirection.ltr,
    )..layout();
    tp.paint(canvas, center - Offset(tp.width / 2, tp.height / 2));
  }

  @override
  bool shouldRepaint(covariant _PiePainter old) =>
      old.values.length != values.length ||
      old.values.any((v) => !values.contains(v));
}
