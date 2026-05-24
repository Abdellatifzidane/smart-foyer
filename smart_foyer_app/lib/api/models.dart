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
  final String id;
  final String scannedAt;
  final Receipt receipt;
  final List<ItemComparison> comparisons;
  final double totalSavings;
  final double ocrConfidence;
  final String imageUrl; // relative URL (e.g. /history/{id}/image)
  final bool pipelineOk;
  final List<String> pipelineErrors;

  ScanResult({
    required this.id,
    required this.scannedAt,
    required this.receipt,
    required this.comparisons,
    required this.totalSavings,
    required this.ocrConfidence,
    this.imageUrl = '',
    this.pipelineOk = true,
    this.pipelineErrors = const [],
  });

  factory ScanResult.fromJson(Map<String, dynamic> j) {
    final receiptJson = (j['receipt'] as Map?)?.cast<String, dynamic>();
    final pipeline = (j['pipeline'] as Map?)?.cast<String, dynamic>();
    return ScanResult(
      id: j['id']?.toString() ?? '',
      scannedAt: j['scanned_at']?.toString() ?? '',
      receipt: receiptJson != null
          ? Receipt.fromJson(receiptJson)
          : Receipt(enseigne: '', total: 0, date: '', items: const []),
      comparisons: ((j['comparisons'] as List?) ?? const [])
          .whereType<Map>()
          .map((e) => ItemComparison.fromJson(e.cast<String, dynamic>()))
          .toList(),
      totalSavings: _toDouble(j['total_savings']),
      ocrConfidence: _toDouble(j['ocr']?['avg_confidence']),
      imageUrl: j['image_url']?.toString() ?? '',
      pipelineOk: pipeline == null ? true : (pipeline['ok'] as bool? ?? true),
      pipelineErrors: ((pipeline?['errors'] as List?) ?? const [])
          .map((e) => e.toString())
          .toList(),
    );
  }
}


class ReceiptSummary {
  final String id;
  final String scannedAt;
  final String enseigne;
  final String date;
  final double total;
  final int nItems;
  final double totalSavings;
  final String imageUrl;

  ReceiptSummary({
    required this.id,
    required this.scannedAt,
    required this.enseigne,
    required this.date,
    required this.total,
    required this.nItems,
    required this.totalSavings,
    this.imageUrl = '',
  });

  factory ReceiptSummary.fromJson(Map<String, dynamic> j) => ReceiptSummary(
        id: j['id'] ?? '',
        scannedAt: j['scanned_at'] ?? '',
        enseigne: j['enseigne'] ?? '',
        date: j['date'] ?? '',
        total: _toDouble(j['total']),
        nItems: (j['n_items'] as num?)?.toInt() ?? 0,
        totalSavings: _toDouble(j['total_savings']),
        imageUrl: j['image_url']?.toString() ?? '',
      );
}


class HistoryStats {
  final int nReceipts;
  final double totalSpent;
  final double totalSavings;
  final Map<String, double> byEnseigne;
  final Map<String, double> byMonth;
  final Map<String, double> byWeek;
  final Map<String, double> byCategory;

  HistoryStats({
    required this.nReceipts,
    required this.totalSpent,
    required this.totalSavings,
    required this.byEnseigne,
    required this.byMonth,
    this.byWeek = const {},
    this.byCategory = const {},
  });

  factory HistoryStats.fromJson(Map<String, dynamic> j) => HistoryStats(
        nReceipts: (j['n_receipts'] as num?)?.toInt() ?? 0,
        totalSpent: _toDouble(j['total_spent']),
        totalSavings: _toDouble(j['total_savings']),
        byEnseigne: ((j['by_enseigne'] as Map?) ?? {})
            .map((k, v) => MapEntry(k.toString(), _toDouble(v))),
        byMonth: ((j['by_month'] as Map?) ?? {})
            .map((k, v) => MapEntry(k.toString(), _toDouble(v))),
        byWeek: ((j['by_week'] as Map?) ?? {})
            .map((k, v) => MapEntry(k.toString(), _toDouble(v))),
        byCategory: ((j['by_category'] as Map?) ?? {})
            .map((k, v) => MapEntry(k.toString(), _toDouble(v))),
      );
}

double _toDouble(dynamic v) {
  if (v == null) return 0.0;
  if (v is num) return v.toDouble();
  return double.tryParse(v.toString()) ?? 0.0;
}


// ─── Admin: catalog product ─────────────────────────────────────────

class Product {
  final String id;
  final String name;
  final double price;
  final String currency;
  final String unitPrice;
  final String brand;
  final String imageUrl;
  final String productUrl;
  final String enseigne;
  final String category;
  final String sku;

  Product({
    this.id = '',
    required this.name,
    this.price = 0.0,
    this.currency = 'EUR',
    this.unitPrice = '',
    this.brand = '',
    this.imageUrl = '',
    this.productUrl = '',
    this.enseigne = '',
    this.category = '',
    this.sku = '',
  });

  factory Product.fromJson(Map<String, dynamic> j) => Product(
        id: j['id']?.toString() ?? '',
        name: j['name'] ?? '',
        price: _toDouble(j['price']),
        currency: j['currency'] ?? 'EUR',
        unitPrice: j['unit_price'] ?? '',
        brand: j['brand'] ?? '',
        imageUrl: j['image_url'] ?? '',
        productUrl: j['product_url'] ?? '',
        enseigne: j['enseigne'] ?? '',
        category: j['category'] ?? '',
        sku: j['sku']?.toString() ?? '',
      );

  Map<String, dynamic> toJsonInput() => {
        'name': name,
        'price': price,
        'currency': currency,
        'unit_price': unitPrice,
        'brand': brand,
        'image_url': imageUrl,
        'product_url': productUrl,
        'enseigne': enseigne,
        'category': category,
        'sku': sku,
      };
}


class ProductPage {
  final List<Product> items;
  final int total;
  final int page;
  final int pageSize;

  ProductPage({
    required this.items,
    required this.total,
    required this.page,
    required this.pageSize,
  });

  factory ProductPage.fromJson(Map<String, dynamic> j) => ProductPage(
        items: ((j['items'] as List?) ?? [])
            .map((e) => Product.fromJson(e as Map<String, dynamic>))
            .toList(),
        total: (j['total'] as num?)?.toInt() ?? 0,
        page: (j['page'] as num?)?.toInt() ?? 1,
        pageSize: (j['page_size'] as num?)?.toInt() ?? 20,
      );
}


class ScrapeJob {
  final String jobId;
  final String retailer;
  final int maxProducts;
  final int scraped;
  final String state; // "running", "done", "error"
  final String? error;

  ScrapeJob({
    required this.jobId,
    required this.retailer,
    required this.maxProducts,
    required this.scraped,
    required this.state,
    this.error,
  });

  bool get isRunning => state == 'running';
  bool get isDone => state == 'done';
  bool get isError => state == 'error';

  factory ScrapeJob.fromJson(Map<String, dynamic> j) => ScrapeJob(
        jobId: j['job_id']?.toString() ?? '',
        retailer: j['retailer'] ?? '',
        maxProducts: (j['max_products'] as num?)?.toInt() ?? 0,
        scraped: (j['scraped'] as num?)?.toInt() ?? 0,
        state: j['state'] ?? 'unknown',
        error: j['error']?.toString(),
      );
}
