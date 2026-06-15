import 'package:flutter/material.dart';
import '../api/api_client.dart';
import '../api/models.dart';
import 'results_screen.dart';

class HistoryScreen extends StatefulWidget {
  const HistoryScreen({super.key});

  @override
  State<HistoryScreen> createState() => _HistoryScreenState();
}

class _HistoryScreenState extends State<HistoryScreen> {
  late Future<_HistoryData> _future;

  @override
  void initState() {
    super.initState();
    _future = _load();
  }

  Future<_HistoryData> _load() async {
    final stats = await ApiClient.historyStats();
    final receipts = await ApiClient.history();
    return _HistoryData(stats: stats, receipts: receipts);
  }

  Future<void> _refresh() async {
    final data = await _load();
    if (!mounted) return;
    setState(() => _future = Future.value(data));
  }

  Future<void> _deleteReceipt(ReceiptSummary r) async {
    final confirmed = await showDialog<bool>(
      context: context,
      builder: (ctx) => AlertDialog(
        title: const Text('Supprimer ce ticket ?'),
        content: Text(
          'Le ticket ${r.enseigne.isEmpty ? '' : '${r.enseigne} '}'
          '(${r.total.toStringAsFixed(2)} €) sera définitivement supprimé.',
        ),
        actions: [
          TextButton(
            onPressed: () => Navigator.of(ctx).pop(false),
            child: const Text('Annuler'),
          ),
          FilledButton(
            style: FilledButton.styleFrom(backgroundColor: Colors.red.shade700),
            onPressed: () => Navigator.of(ctx).pop(true),
            child: const Text('Supprimer'),
          ),
        ],
      ),
    );
    if (confirmed != true) return;
    try {
      await ApiClient.deleteReceipt(r.id);
      if (!mounted) return;
      ScaffoldMessenger.of(context).showSnackBar(
        const SnackBar(content: Text('Ticket supprimé')),
      );
      await _refresh();
    } on ApiException catch (e) {
      if (!mounted) return;
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(content: Text(e.message), backgroundColor: Colors.red.shade700),
      );
    } catch (e) {
      if (!mounted) return;
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(content: Text('Erreur : $e')),
      );
    }
  }

  Future<void> _openReceipt(String id) async {
    showDialog(
      context: context,
      barrierDismissible: false,
      builder: (_) => const Center(child: CircularProgressIndicator()),
    );
    try {
      final scan = await ApiClient.historyDetail(id);
      if (!mounted) return;
      Navigator.of(context).pop();
      Navigator.of(context).push(
        MaterialPageRoute(builder: (_) => ResultsScreen(result: scan)),
      );
    } on ApiException catch (e) {
      if (!mounted) return;
      Navigator.of(context).pop();
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(
          content: Text(e.message),
          backgroundColor: Colors.red.shade700,
        ),
      );
    } catch (e) {
      if (!mounted) return;
      Navigator.of(context).pop();
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(content: Text('Erreur : $e')),
      );
    }
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(title: const Text('Mes tickets')),
      body: SafeArea(
        child: Center(
          child: ConstrainedBox(
            constraints: const BoxConstraints(maxWidth: 600),
            child: RefreshIndicator(
              onRefresh: _refresh,
              child: FutureBuilder<_HistoryData>(
                future: _future,
                builder: (context, snapshot) {
                  if (snapshot.connectionState != ConnectionState.done) {
                    return const Center(child: CircularProgressIndicator());
                  }
                  if (snapshot.hasError) {
                    return ListView(
                      padding: const EdgeInsets.all(24),
                      children: [
                        Text('Erreur : ${snapshot.error}',
                            style: const TextStyle(color: Colors.red)),
                      ],
                    );
                  }
                  final data = snapshot.data!;
                  if (data.receipts.isEmpty) {
                    return ListView(
                      padding: const EdgeInsets.all(24),
                      children: const [
                        SizedBox(height: 80),
                        Icon(Icons.receipt_long_outlined,
                            size: 64, color: Color(0xFF8A93A1)),
                        SizedBox(height: 12),
                        Text(
                          'Aucun ticket scanné pour le moment.',
                          textAlign: TextAlign.center,
                          style: TextStyle(color: Color(0xFF5C6470)),
                        ),
                      ],
                    );
                  }
                  return ListView(
                    padding: const EdgeInsets.fromLTRB(20, 12, 20, 24),
                    children: [
                      _StatsCard(stats: data.stats),
                      const SizedBox(height: 16),
                      const Padding(
                        padding: EdgeInsets.fromLTRB(4, 8, 4, 8),
                        child: Text('Historique',
                            style: TextStyle(
                                fontSize: 16, fontWeight: FontWeight.w700)),
                      ),
                      ...data.receipts.map(
                        (r) => _ReceiptTile(
                          receipt: r,
                          onTap: () => _openReceipt(r.id),
                          onDelete: () => _deleteReceipt(r),
                        ),
                      ),
                    ],
                  );
                },
              ),
            ),
          ),
        ),
      ),
    );
  }
}

class _HistoryData {
  final HistoryStats stats;
  final List<ReceiptSummary> receipts;
  _HistoryData({required this.stats, required this.receipts});
}

class _StatsCard extends StatelessWidget {
  final HistoryStats stats;
  const _StatsCard({required this.stats});

  @override
  Widget build(BuildContext context) {
    final topEnseignes = stats.byEnseigne.entries.toList()
      ..sort((a, b) => b.value.compareTo(a.value));

    return Container(
      padding: const EdgeInsets.all(20),
      decoration: BoxDecoration(
        color: Colors.white,
        borderRadius: BorderRadius.circular(20),
        border: Border.all(color: const Color(0xFFE3E6EB)),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            mainAxisAlignment: MainAxisAlignment.spaceBetween,
            children: [
              Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  const Text('Total dépensé',
                      style: TextStyle(
                          fontSize: 13, color: Color(0xFF5C6470))),
                  const SizedBox(height: 2),
                  Text(
                    '${stats.totalSpent.toStringAsFixed(2)} €',
                    style: const TextStyle(
                        fontSize: 26,
                        fontWeight: FontWeight.w800,
                        color: Color(0xFF1B8A6B)),
                  ),
                ],
              ),
              Column(
                crossAxisAlignment: CrossAxisAlignment.end,
                children: [
                  const Text('Tickets',
                      style: TextStyle(
                          fontSize: 13, color: Color(0xFF5C6470))),
                  const SizedBox(height: 2),
                  Text(
                    '${stats.nReceipts}',
                    style: const TextStyle(
                        fontSize: 22, fontWeight: FontWeight.w800),
                  ),
                ],
              ),
            ],
          ),
          if (topEnseignes.isNotEmpty) ...[
            const Divider(height: 24),
            const Text('Dépenses par enseigne',
                style: TextStyle(fontSize: 13, color: Color(0xFF5C6470))),
            const SizedBox(height: 8),
            ...topEnseignes.take(5).map(
                  (e) => Padding(
                    padding: const EdgeInsets.symmetric(vertical: 3),
                    child: Row(
                      children: [
                        Expanded(child: Text(e.key.isEmpty ? 'Inconnu' : e.key)),
                        Text('${e.value.toStringAsFixed(2)} €',
                            style: const TextStyle(
                                fontWeight: FontWeight.w600)),
                      ],
                    ),
                  ),
                ),
          ],
        ],
      ),
    );
  }
}

class _ReceiptTile extends StatelessWidget {
  final ReceiptSummary receipt;
  final VoidCallback onTap;
  final VoidCallback onDelete;
  const _ReceiptTile({
    required this.receipt,
    required this.onTap,
    required this.onDelete,
  });

  String _formatDate(String iso) {
    if (iso.isEmpty) return '';
    // expects ISO like 2026-05-23T10:30:00...
    final m = RegExp(r'^(\d{4})-(\d{2})-(\d{2})').firstMatch(iso);
    if (m == null) return iso;
    return '${m[3]}/${m[2]}/${m[1]}';
  }

  @override
  Widget build(BuildContext context) {
    final label = receipt.enseigne.isEmpty ? '—' : receipt.enseigne;
    final date = receipt.date.isNotEmpty
        ? receipt.date
        : _formatDate(receipt.scannedAt);

    final hasImage = receipt.imageUrl.isNotEmpty;
    final imageFull = hasImage ? ApiClient.mediaUrl(receipt.imageUrl) : null;

    return Card(
      margin: const EdgeInsets.symmetric(vertical: 4),
      elevation: 0,
      shape: RoundedRectangleBorder(
        borderRadius: BorderRadius.circular(14),
        side: const BorderSide(color: Color(0xFFE3E6EB)),
      ),
      child: ListTile(
        contentPadding:
            const EdgeInsets.symmetric(horizontal: 12, vertical: 6),
        leading: imageFull != null
            ? ClipRRect(
                borderRadius: BorderRadius.circular(8),
                child: Image.network(
                  imageFull,
                  width: 44,
                  height: 56,
                  fit: BoxFit.cover,
                  errorBuilder: (_, __, ___) => const CircleAvatar(
                    backgroundColor: Color(0xFFE7F6EF),
                    child: Icon(Icons.store_rounded,
                        color: Color(0xFF1B8A6B)),
                  ),
                ),
              )
            : const CircleAvatar(
                backgroundColor: Color(0xFFE7F6EF),
                child:
                    Icon(Icons.store_rounded, color: Color(0xFF1B8A6B)),
              ),
        title: Text(label,
            style: const TextStyle(fontWeight: FontWeight.w700)),
        subtitle: Text(
          '$date · ${receipt.nItems} produits',
          style: const TextStyle(fontSize: 12, color: Color(0xFF5C6470)),
        ),
        trailing: Row(
          mainAxisSize: MainAxisSize.min,
          children: [
            Text(
              '${receipt.total.toStringAsFixed(2)} €',
              style: const TextStyle(
                  fontSize: 15,
                  fontWeight: FontWeight.w800,
                  color: Color(0xFF1B8A6B)),
            ),
            PopupMenuButton<String>(
              icon: const Icon(Icons.more_vert, color: Color(0xFF8A93A1)),
              tooltip: 'Options',
              onSelected: (v) {
                if (v == 'delete') onDelete();
              },
              itemBuilder: (_) => const [
                PopupMenuItem<String>(
                  value: 'delete',
                  child: Row(children: [
                    Icon(Icons.delete_outline, size: 18, color: Colors.red),
                    SizedBox(width: 8),
                    Text('Supprimer'),
                  ]),
                ),
              ],
            ),
          ],
        ),
        onTap: onTap,
      ),
    );
  }
}
