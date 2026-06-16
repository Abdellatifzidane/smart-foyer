import 'package:flutter/material.dart';
import '../api/api_client.dart';
import '../api/models.dart';
import '../widgets/feedback_buttons.dart';

class ResultsScreen extends StatelessWidget {
  final ScanResult result;
  const ResultsScreen({super.key, required this.result});

  @override
  Widget build(BuildContext context) {
    final receipt = result.receipt;

    // Récap panier "au meilleur prix" : pour chaque produit, on prend le prix
    // payé, ou l'alternative moins chère si elle existe. On ne compte JAMAIS un
    // produit plus cher que ce qui a été payé.
    double bestBasket = 0.0;
    int matchedItems = 0;
    for (int i = 0; i < receipt.items.length; i++) {
      final paid = receipt.items[i].price;
      final cmp = i < result.comparisons.length ? result.comparisons[i] : null;
      if (cmp != null && cmp.cheaperAlternatives.isNotEmpty) {
        bestBasket += cmp.cheaperAlternatives.first.price;
        matchedItems++;
      } else {
        bestBasket += paid;
      }
    }
    final altTotal = bestBasket;
    final scannedHasPrices = receipt.total > 0;

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
                if (!result.pipelineOk && result.pipelineErrors.isNotEmpty)
                  _PipelineErrorBanner(errors: result.pipelineErrors),
                if (!result.pipelineOk && result.pipelineErrors.isNotEmpty)
                  const SizedBox(height: 12),
                if (result.imageUrl.isNotEmpty)
                  _ReceiptPhotoCard(imageUrl: result.imageUrl),
                if (result.imageUrl.isNotEmpty) const SizedBox(height: 12),
                _ReceiptHeaderCard(
                    receipt: receipt, ocrConfidence: result.ocrConfidence),
                Align(
                  alignment: Alignment.centerRight,
                  child: FeedbackButtons(
                    target: 'ocr',
                    label: 'Texte bien lu ?',
                    receiptId: result.id,
                  ),
                ),
                const SizedBox(height: 16),
                if (result.totalSavings > 0)
                  _SavingsBanner(
                    amount: result.totalSavings,
                    scannedTotal: scannedHasPrices ? receipt.total : 0,
                    altTotal: altTotal,
                    matchedItems: matchedItems,
                    totalItems: receipt.items.length,
                  ),
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
                if (receipt.items.isNotEmpty) ...[
                  const SizedBox(height: 8),
                  Align(
                    alignment: Alignment.centerRight,
                    child: FeedbackButtons(
                      target: 'matching',
                      label: 'Correspondances correctes ?',
                      receiptId: result.id,
                    ),
                  ),
                ],
              ],
            ),
          ),
        ),
      ),
    );
  }
}

class _ReceiptPhotoCard extends StatelessWidget {
  final String imageUrl;
  const _ReceiptPhotoCard({required this.imageUrl});

  String get _fullUrl => ApiClient.mediaUrl(imageUrl);

  @override
  Widget build(BuildContext context) {
    return Container(
      decoration: BoxDecoration(
        color: Colors.white,
        borderRadius: BorderRadius.circular(20),
        border: Border.all(color: const Color(0xFFE3E6EB)),
      ),
      clipBehavior: Clip.antiAlias,
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          GestureDetector(
            onTap: () => _openFullScreen(context),
            child: ConstrainedBox(
              constraints: const BoxConstraints(maxHeight: 320),
              child: Image.network(
                _fullUrl,
                fit: BoxFit.contain,
                errorBuilder: (_, __, ___) => Container(
                  height: 120,
                  alignment: Alignment.center,
                  child: const Text(
                    'Image indisponible',
                    style: TextStyle(color: Color(0xFF8A93A1)),
                  ),
                ),
              ),
            ),
          ),
          Padding(
            padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 8),
            child: Row(
              children: [
                const Icon(Icons.image_outlined,
                    size: 16, color: Color(0xFF5C6470)),
                const SizedBox(width: 6),
                const Expanded(
                  child: Text(
                    'Photo originale du ticket',
                    style:
                        TextStyle(fontSize: 12, color: Color(0xFF5C6470)),
                  ),
                ),
                TextButton(
                  onPressed: () => _openFullScreen(context),
                  child: const Text('Plein écran'),
                ),
              ],
            ),
          ),
        ],
      ),
    );
  }

  void _openFullScreen(BuildContext context) {
    Navigator.of(context).push(
      MaterialPageRoute(
        builder: (_) => _FullScreenImage(url: _fullUrl),
      ),
    );
  }
}

class _FullScreenImage extends StatelessWidget {
  final String url;
  const _FullScreenImage({required this.url});

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      backgroundColor: Colors.black,
      appBar: AppBar(
        backgroundColor: Colors.black,
        iconTheme: const IconThemeData(color: Colors.white),
      ),
      body: Center(
        child: InteractiveViewer(
          maxScale: 5,
          child: Image.network(url, fit: BoxFit.contain),
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
  final double scannedTotal;
  final double altTotal;
  final int matchedItems;
  final int totalItems;
  const _SavingsBanner({
    required this.amount,
    required this.scannedTotal,
    required this.altTotal,
    required this.matchedItems,
    required this.totalItems,
  });

  @override
  Widget build(BuildContext context) {
    final hasComparison =
        matchedItems > 0 && altTotal > 0 && scannedTotal > 0;
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 14),
      decoration: BoxDecoration(
        color: const Color(0xFFE7F6EF),
        borderRadius: BorderRadius.circular(16),
        border: Border.all(color: const Color(0xFFB6E0CB)),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            children: [
              const Icon(Icons.savings_rounded, color: Color(0xFF1B8A6B)),
              const SizedBox(width: 10),
              Expanded(
                child: Text(
                  'Économies possibles : ${amount.toStringAsFixed(2)} €',
                  style: const TextStyle(
                      fontWeight: FontWeight.w700,
                      color: Color(0xFF0E5C45),
                      fontSize: 15),
                ),
              ),
            ],
          ),
          if (hasComparison) ...[
            const SizedBox(height: 8),
            Text(
              'Le même panier ailleurs : ~${altTotal.toStringAsFixed(2)} €  '
              '(payé : ${scannedTotal.toStringAsFixed(2)} €)',
              style: const TextStyle(fontSize: 12, color: Color(0xFF0E5C45)),
            ),
            const SizedBox(height: 2),
            Text(
              '$matchedItems / $totalItems produits comparés',
              style: const TextStyle(fontSize: 11, color: Color(0xFF3A4250)),
            ),
          ],
        ],
      ),
    );
  }
}

class _PipelineErrorBanner extends StatelessWidget {
  final List<String> errors;
  const _PipelineErrorBanner({required this.errors});

  @override
  Widget build(BuildContext context) {
    return Container(
      padding: const EdgeInsets.all(14),
      decoration: BoxDecoration(
        color: const Color(0xFFFFF4E5),
        borderRadius: BorderRadius.circular(14),
        border: Border.all(color: const Color(0xFFE8C893)),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            children: const [
              Icon(Icons.warning_amber_rounded, color: Color(0xFFB3640F)),
              SizedBox(width: 8),
              Expanded(
                child: Text(
                  'Analyse partielle',
                  style: TextStyle(
                      fontWeight: FontWeight.w700,
                      color: Color(0xFF7A3F00)),
                ),
              ),
            ],
          ),
          const SizedBox(height: 6),
          ...errors.map(
            (e) => Padding(
              padding: const EdgeInsets.only(top: 2),
              child: Text(
                '• $e',
                style: const TextStyle(
                    fontSize: 12, color: Color(0xFF7A3F00)),
              ),
            ),
          ),
          const SizedBox(height: 4),
          const Text(
            'Le ticket a été sauvegardé tel quel. Tu peux réessayer ou continuer.',
            style: TextStyle(fontSize: 11, color: Color(0xFF7A3F00)),
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
          // Produit reconnu (info de transparence) — SANS prix concurrent, pour
          // ne jamais afficher un produit plus cher que ce qui a été payé.
          if (hasMatch) ...[
            const SizedBox(height: 6),
            Text(
              'Produit reconnu : ${comparison!.bestMatchName}'
              ' · pertinence ${(comparison!.bestMatchScore * 100).toStringAsFixed(0)}%',
              style: const TextStyle(fontSize: 11, color: Color(0xFF8A93A1)),
              maxLines: 2,
              overflow: TextOverflow.ellipsis,
            ),
          ],
          if (cheapers.isNotEmpty) ...[
            const Divider(height: 18),
            Row(
              children: [
                const Icon(Icons.savings_rounded,
                    size: 14, color: Color(0xFF1B8A6B)),
                const SizedBox(width: 4),
                Text(
                  'Moins cher ailleurs · tu peux économiser '
                  '${comparison!.savings.toStringAsFixed(2)} €',
                  style: const TextStyle(
                      fontSize: 12,
                      fontWeight: FontWeight.w700,
                      color: Color(0xFF0E5C45)),
                ),
              ],
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
          // Produit reconnu mais rien de moins cher ailleurs → bon prix.
          if (hasMatch && cheapers.isEmpty && item.price > 0) ...[
            const SizedBox(height: 6),
            Row(
              children: const [
                Icon(Icons.check_circle_rounded,
                    size: 14, color: Color(0xFF1B8A6B)),
                SizedBox(width: 4),
                Text(
                  'Bon prix : rien de moins cher trouvé ailleurs',
                  style: TextStyle(
                      fontSize: 12,
                      fontWeight: FontWeight.w600,
                      color: Color(0xFF0E5C45)),
                ),
              ],
            ),
          ],
        ],
      ),
    );
  }
}
