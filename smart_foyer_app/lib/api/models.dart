// Dart models mirroring the backend JSON shape.
//
// To add a new field:
//   1. Add it to the Python model (ner/models.py) - it appears in JSON automatically.
//   2. Add the field + parsing here.
//   3. Display it in the screens/widgets.

class LineItem {
  final String name;
  final double price;
  final double quantity;

  LineItem({required this.name, required this.price, required this.quantity});

  factory LineItem.fromJson(Map<String, dynamic> j) => LineItem(
        name: j['name'] ?? '',
        price: _toDouble(j['price']),
        quantity: _toDouble(j['quantity']),
      );
}

class Receipt {
  final String enseigne;
  final double total;
  final String date;
  final List<LineItem> items;

  Receipt({
    required this.enseigne,
    required this.total,
    required this.date,
    required this.items,
  });

  factory Receipt.fromJson(Map<String, dynamic> j) => Receipt(
        enseigne: j['enseigne'] ?? '',
        total: _toDouble(j['total']),
        date: j['date'] ?? '',
        items: ((j['items'] as List?) ?? [])
            .map((e) => LineItem.fromJson(e as Map<String, dynamic>))
            .toList(),
      );
}

class CheaperAlternative {
  final String name;
  final String enseigne;
  final double price;
  final double score;
  final double savings;

  CheaperAlternative({
    required this.name,
    required this.enseigne,
    required this.price,
    required this.score,
    required this.savings,
  });

  factory CheaperAlternative.fromJson(Map<String, dynamic> j) =>
      CheaperAlternative(
        name: j['name'] ?? '',
        enseigne: j['enseigne'] ?? '',
        price: _toDouble(j['price']),
        score: _toDouble(j['score']),
        savings: _toDouble(j['savings']),
      );
}

class ItemComparison {
  final String scannedName;
  final double scannedPrice;
  final String bestMatchName;
  final String bestMatchEnseigne;
  final double bestMatchPrice;
  final double bestMatchScore;
  final List<CheaperAlternative> cheaperAlternatives;
  final double savings;

  ItemComparison({
    required this.scannedName,
    required this.scannedPrice,
    required this.bestMatchName,
    required this.bestMatchEnseigne,
    required this.bestMatchPrice,
    required this.bestMatchScore,
    required this.cheaperAlternatives,
    required this.savings,
  });

  factory ItemComparison.fromJson(Map<String, dynamic> j) => ItemComparison(
        scannedName: j['scanned_name'] ?? '',
        scannedPrice: _toDouble(j['scanned_price']),
        bestMatchName: j['best_match_name'] ?? '',
        bestMatchEnseigne: j['best_match_enseigne'] ?? '',
        bestMatchPrice: _toDouble(j['best_match_price']),
        bestMatchScore: _toDouble(j['best_match_score']),
        cheaperAlternatives: ((j['cheaper_alternatives'] as List?) ?? [])
            .map((e) => CheaperAlternative.fromJson(e as Map<String, dynamic>))
            .toList(),
        savings: _toDouble(j['savings']),
      );
}

class ScanResult {
  final Receipt receipt;
  final List<ItemComparison> comparisons;
  final double totalSavings;
  final double ocrConfidence;

  ScanResult({
    required this.receipt,
    required this.comparisons,
    required this.totalSavings,
    required this.ocrConfidence,
  });

  factory ScanResult.fromJson(Map<String, dynamic> j) => ScanResult(
        receipt: Receipt.fromJson(j['receipt'] as Map<String, dynamic>),
        comparisons: ((j['comparisons'] as List?) ?? [])
            .map((e) => ItemComparison.fromJson(e as Map<String, dynamic>))
            .toList(),
        totalSavings: _toDouble(j['total_savings']),
        ocrConfidence: _toDouble(j['ocr']?['avg_confidence']),
      );
}

double _toDouble(dynamic v) {
  if (v == null) return 0.0;
  if (v is num) return v.toDouble();
  return double.tryParse(v.toString()) ?? 0.0;
}
