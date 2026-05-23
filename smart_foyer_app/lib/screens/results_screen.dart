import 'package:flutter/material.dart';
import '../api/models.dart';

class ResultsScreen extends StatelessWidget {
  final ScanResult result;
  const ResultsScreen({super.key, required this.result});

  @override
  Widget build(BuildContext context) {
    final receipt = result.receipt;

    return Scaffold(
      appBar: AppBar(
        title: const Text('Ticket analysé'),
        leading: IconButton(
          icon: const Icon(Icons.close),
          onPressed: () =>
              Navigator.of(context).popUntil((r) => r.isFirst),
        ),
      ),
      body: SafeArea(
        child: Center(
          child: ConstrainedBox(
            constraints: const BoxConstraints(maxWidth: 600),
            child: ListView(
              padding: const EdgeInsets.fromLTRB(20, 8, 20, 24),
              children: [
                _ReceiptHeaderCard(receipt: receipt, ocrConfidence: result.ocrConfidence),
                const SizedBox(height: 16),
                if (result.totalSavings > 0) _SavingsBanner(amount: result.totalSavings),
                const SizedBox(height: 8),
                const Padding(
                  padding: EdgeInsets.fromLTRB(4, 12, 4, 8),
                  child: Text('Produits scannés',
                      style: TextStyle(
                          fontSize: 16, fontWeight: FontWeight.w700)),
                ),
                if (receipt.items.isEmpty)
                  const Padding(
                    padding: EdgeInsets.all(24),
                    child: Text(
                      'Aucun produit détecté.',
                      textAlign: TextAlign.center,
                      style: TextStyle(color: Color(0xFF5C6470)),
                    ),
                  ),
                ...List.generate(receipt.items.length, (i) {
                  final item = receipt.items[i];
                  final cmp = i < result.comparisons.length
                      ? result.comparisons[i]
                      : null;
                  return _ItemCard(item: item, comparison: cmp);
                }),
              ],
            ),
          ),
        ),
      ),
    );
  }
}

class _ReceiptHeaderCard extends StatelessWidget {
  final Receipt receipt;
  final double ocrConfidence;

  const _ReceiptHeaderCard({required this.receipt, required this.ocrConfidence});

  @override
  Widget build(BuildContext context) {
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
            children: [
              const Icon(Icons.store_rounded,
                  color: Color(0xFF1B8A6B), size: 22),
              const SizedBox(width: 8),
              Expanded(
                child: Text(
                  receipt.enseigne.isNotEmpty ? receipt.enseigne : '— enseigne inconnue —',
                  style: const TextStyle(
                      fontSize: 18, fontWeight: FontWeight.w700),
                ),
              ),
            ],
          ),
          const SizedBox(height: 4),
          if (receipt.date.isNotEmpty)
            Text(
              receipt.date,
              style: const TextStyle(color: Color(0xFF5C6470), fontSize: 13),
            ),
          const Divider(height: 24),
          Row(
            mainAxisAlignment: MainAxisAlignment.spaceBetween,
            children: [
              const Text('Total',
                  style: TextStyle(fontSize: 15, fontWeight: FontWeight.w600)),
              Text(
                '${receipt.total.toStringAsFixed(2)} €',
                style: const TextStyle(
                    fontSize: 22,
                    fontWeight: FontWeight.w800,
                    color: Color(0xFF1B8A6B)),
              ),
            ],
          ),
          const SizedBox(height: 8),
          Text(
            'OCR : ${(ocrConfidence * 100).toStringAsFixed(0)}% confiance · ${receipt.items.length} produits détectés',
            style: const TextStyle(fontSize: 12, color: Color(0xFF5C6470)),
          ),
        ],
      ),
    );
  }
}

class _SavingsBanner extends StatelessWidget {
  final double amount;
  const _SavingsBanner({required this.amount});

  @override
  Widget build(BuildContext context) {
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 14),
      decoration: BoxDecoration(
        color: const Color(0xFFE7F6EF),
        borderRadius: BorderRadius.circular(16),
        border: Border.all(color: const Color(0xFFB6E0CB)),
      ),
      child: Row(
        children: [
          const Icon(Icons.savings_rounded, color: Color(0xFF1B8A6B)),
          const SizedBox(width: 10),
          Expanded(
            child: Text(
              'Économies possibles : ${amount.toStringAsFixed(2)} €',
              style: const TextStyle(
                  fontWeight: FontWeight.w700, color: Color(0xFF0E5C45)),
            ),
          ),
        ],
      ),
    );
  }
}

class _ItemCard extends StatelessWidget {
  final LineItem item;
  final ItemComparison? comparison;

  const _ItemCard({required this.item, this.comparison});

  @override
  Widget build(BuildContext context) {
    final hasMatch =
        comparison != null && comparison!.bestMatchName.isNotEmpty;
    final cheapers = comparison?.cheaperAlternatives ?? const [];

    return Container(
      margin: const EdgeInsets.symmetric(vertical: 6),
      padding: const EdgeInsets.all(14),
      decoration: BoxDecoration(
        color: Colors.white,
        borderRadius: BorderRadius.circular(16),
        border: Border.all(color: const Color(0xFFE3E6EB)),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Expanded(
                child: Text(
                  item.name.isEmpty ? '(produit sans nom)' : item.name,
                  style: const TextStyle(
                      fontSize: 15, fontWeight: FontWeight.w600),
                ),
              ),
              const SizedBox(width: 8),
              Text(
                '${item.price.toStringAsFixed(2)} €',
                style: const TextStyle(
                    fontSize: 15, fontWeight: FontWeight.w700),
              ),
            ],
          ),
          if (item.quantity != 1.0)
            Padding(
              padding: const EdgeInsets.only(top: 2),
              child: Text(
                'Quantité : ${item.quantity.toStringAsFixed(0)}',
                style: const TextStyle(
                    fontSize: 12, color: Color(0xFF5C6470)),
              ),
            ),
          if (!hasMatch)
            const Padding(
              padding: EdgeInsets.only(top: 6),
              child: Text(
                'Aucune correspondance trouvée dans le catalogue.',
                style: TextStyle(fontSize: 12, color: Color(0xFF8A93A1)),
              ),
            ),
          if (hasMatch) ...[
            const Divider(height: 18),
            Row(
              children: [
                const Icon(Icons.compare_arrows_rounded,
                    size: 14, color: Color(0xFF1B8A6B)),
                const SizedBox(width: 4),
                Expanded(
                  child: Text(
                    'Match : ${comparison!.bestMatchEnseigne} · ${comparison!.bestMatchName}',
                    style: const TextStyle(
                        fontSize: 12,
                        fontWeight: FontWeight.w600,
                        color: Color(0xFF0E5C45)),
                    maxLines: 2,
                    overflow: TextOverflow.ellipsis,
                  ),
                ),
                const SizedBox(width: 6),
                Text(
                  '${comparison!.bestMatchPrice.toStringAsFixed(2)} €',
                  style: const TextStyle(
                      fontSize: 12, fontWeight: FontWeight.w700),
                ),
              ],
            ),
          ],
          if (cheapers.isNotEmpty) ...[
            const SizedBox(height: 8),
            const Text(
              'Moins cher ailleurs :',
              style: TextStyle(
                  fontSize: 12,
                  fontWeight: FontWeight.w700,
                  color: Color(0xFF0E5C45)),
            ),
            const SizedBox(height: 6),
            ...cheapers.take(3).map((alt) => Padding(
                  padding: const EdgeInsets.only(bottom: 4),
                  child: Row(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      const Icon(Icons.arrow_downward_rounded,
                          size: 14, color: Color(0xFF1B8A6B)),
                      const SizedBox(width: 4),
                      Expanded(
                        child: Text(
                          '${alt.enseigne} · ${alt.name}',
                          style: const TextStyle(
                              fontSize: 12, color: Color(0xFF3A4250)),
                          maxLines: 2,
                          overflow: TextOverflow.ellipsis,
                        ),
                      ),
                      const SizedBox(width: 6),
                      Text(
                        '${alt.price.toStringAsFixed(2)} €',
                        style: const TextStyle(
                            fontSize: 12, fontWeight: FontWeight.w700),
                      ),
                    ],
                  ),
                )),
          ],
        ],
      ),
    );
  }
}
