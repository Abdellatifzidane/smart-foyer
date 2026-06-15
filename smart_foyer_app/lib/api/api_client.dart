import 'dart:async';
import 'dart:convert';
import 'package:http/http.dart' as http;
import 'auth_service.dart';
import 'models.dart';

/// Structured API error — never let raw `Exception` bubble up to the UI.
/// The UI catches `ApiException` and shows `message` in a SnackBar so the
/// app stays usable after any failure (network down, backend 500, timeout).
class ApiException implements Exception {
  final String message;
  final int? statusCode;
  final String? path;
  final bool isTimeout;
  final bool isNetwork;
  const ApiException(
    this.message, {
    this.statusCode,
    this.path,
    this.isTimeout = false,
    this.isNetwork = false,
  });

  @override
  String toString() => message;
}

/// HTTP client for the SmartFoyer FastAPI backend.
///
/// Every call is wrapped with a timeout and a structured `ApiException`
/// so callers can do `try { await ApiClient.scan(...) } on ApiException
/// catch (e) { showSnack(e.message); }` and the app keeps running.
class ApiClient {
  /// Backend base URL. Defaults to localhost which works for:
  ///   - Flutter Web on the same machine
  ///   - iOS Simulator (shares the host network)
  ///
  /// In production, set this via --dart-define=BACKEND_URL=https://...
  static const String baseUrl = String.fromEnvironment(
    'BACKEND_URL',
    defaultValue: 'http://127.0.0.1:8000',
  );

  // Generous defaults: OCR + NER + matching takes ~30s on CPU; quick
  // metadata endpoints get a much shorter timeout.
  static const Duration _scanTimeout = Duration(seconds: 180);
  static const Duration _quickTimeout = Duration(seconds: 15);
  static const Duration _mediumTimeout = Duration(seconds: 45);

  /// URL absolue d'un média (image ticket) avec le JWT en query param, car
  /// les balises <img>/Image.network ne peuvent pas porter d'en-tête.
  static String mediaUrl(String relative) {
    if (relative.isEmpty) return relative;
    final base = relative.startsWith('http') ? relative : '$baseUrl$relative';
    final token = AuthService.instance.token;
    if (token == null || token.isEmpty) return base;
    final sep = base.contains('?') ? '&' : '?';
    return '$base${sep}token=$token';
  }

  // ─── Auth header ─────────────────────────────────────────────────
  /// En-têtes communs incluant le JWT applicatif s'il existe. Toute requête
  /// passe par ici, donc le backend reçoit toujours l'identité du user.
  static Map<String, String> authHeaders([Map<String, String>? extra]) {
    final token = AuthService.instance.token;
    return {
      if (token != null && token.isNotEmpty) 'Authorization': 'Bearer $token',
      if (extra != null) ...extra,
    };
  }

  // ─── Common request wrapper ──────────────────────────────────────

  static Future<dynamic> _safeRequest(
    Future<http.Response> Function() send, {
    Duration timeout = _mediumTimeout,
    String? path,
  }) async {
    try {
      final resp = await send().timeout(timeout);
      // Session expirée / token invalide : on déconnecte proprement, l'AuthGate
      // renvoie alors vers l'écran de connexion.
      if (resp.statusCode == 401) {
        unawaited(AuthService.instance.logout());
        throw ApiException('Session expirée, reconnecte-toi.',
            statusCode: 401, path: path);
      }
      if (resp.statusCode < 200 || resp.statusCode >= 300) {
        // Try to surface the FastAPI `detail` / `message` field if present.
        String message =
            'Erreur ${resp.statusCode} (${path ?? "API"})';
        try {
          final body = jsonDecode(resp.body);
          if (body is Map) {
            message = (body['message'] ??
                    body['detail'] ??
                    body['error'] ??
                    message)
                .toString();
          }
        } catch (_) {
          if (resp.body.isNotEmpty && resp.body.length < 300) {
            message = '$message — ${resp.body}';
          }
        }
        throw ApiException(message,
            statusCode: resp.statusCode, path: path);
      }
      if (resp.body.isEmpty) return null;
      try {
        return jsonDecode(resp.body);
      } on FormatException catch (e) {
        throw ApiException(
          'Réponse JSON invalide du serveur : $e',
          path: path,
        );
      }
    } on TimeoutException {
      throw ApiException(
        'Le serveur ne répond pas (timeout). Vérifie que le backend est démarré.',
        isTimeout: true,
        path: path,
      );
    } on ApiException {
      rethrow;
    } catch (e) {
      throw ApiException(
        'Backend injoignable : $e',
        isNetwork: true,
        path: path,
      );
    }
  }

  /// Send a receipt image to the backend and parse the response.
  static Future<ScanResult> scan(List<int> imageBytes, String filename) async {
    final uri = Uri.parse('$baseUrl/scan');
    Future<http.Response> doSend() async {
      final request = http.MultipartRequest('POST', uri)
        ..headers.addAll(authHeaders())
        ..files.add(http.MultipartFile.fromBytes(
          'image',
          imageBytes,
          filename: filename,
        ));
      final streamed = await request.send();
      return http.Response.fromStream(streamed);
    }

    final decoded = await _safeRequest(
      doSend,
      timeout: _scanTimeout,
      path: '/scan',
    );
    if (decoded is! Map<String, dynamic>) {
      throw const ApiException('Réponse /scan inattendue (pas un objet JSON).');
    }
    return ScanResult.fromJson(decoded);
  }

  /// Quick health-check used by the home screen.
  static Future<Map<String, dynamic>> catalogStats() async {
    final decoded = await _safeRequest(
      () => http.get(Uri.parse('$baseUrl/catalog/stats'), headers: authHeaders()),
      timeout: _quickTimeout,
      path: '/catalog/stats',
    );
    return (decoded as Map?)?.cast<String, dynamic>() ?? const {};
  }

  /// List of past receipts (summaries, newest first).
  static Future<List<ReceiptSummary>> history() async {
    final decoded = await _safeRequest(
      () => http.get(Uri.parse('$baseUrl/history'), headers: authHeaders()),
      timeout: _quickTimeout,
      path: '/history',
    );
    final list = (decoded as List?) ?? const [];
    return list
        .whereType<Map>()
        .map((e) => ReceiptSummary.fromJson(e.cast<String, dynamic>()))
        .toList();
  }

  /// Delete one of the current user's receipts.
  static Future<void> deleteReceipt(String id) async {
    await _safeRequest(
      () => http.delete(Uri.parse('$baseUrl/history/$id'), headers: authHeaders()),
      timeout: _quickTimeout,
      path: '/history/$id',
    );
  }

  /// Aggregated stats across stored receipts.
  static Future<HistoryStats> historyStats() async {
    final decoded = await _safeRequest(
      () => http.get(Uri.parse('$baseUrl/history/stats'), headers: authHeaders()),
      timeout: _quickTimeout,
      path: '/history/stats',
    );
    return HistoryStats.fromJson(
      (decoded as Map?)?.cast<String, dynamic>() ?? const {},
    );
  }

  /// Full details of a stored receipt.
  static Future<ScanResult> historyDetail(String id) async {
    final decoded = await _safeRequest(
      () => http.get(Uri.parse('$baseUrl/history/$id'), headers: authHeaders()),
      timeout: _quickTimeout,
      path: '/history/$id',
    );
    return ScanResult.fromJson(
      (decoded as Map?)?.cast<String, dynamic>() ?? const {},
    );
  }

  /// Send a question to the RAG agent and get an answer.
  static Future<String> chat(
    String question,
    List<Map<String, String>> history,
  ) async {
    final decoded = await _safeRequest(
      () => http.post(
        Uri.parse('$baseUrl/chat'),
        headers: authHeaders({'Content-Type': 'application/json'}),
        body: jsonEncode({'question': question, 'history': history}),
      ),
      timeout: _mediumTimeout,
      path: '/chat',
    );
    final data = (decoded as Map?)?.cast<String, dynamic>() ?? const {};
    return (data['answer'] ?? '').toString();
  }

  // ─── Admin: catalog CRUD ───────────────────────────────────────────

  static Future<ProductPage> listProducts({
    int page = 1,
    int pageSize = 20,
    String q = '',
    String enseigne = '',
  }) async {
    final params = <String, String>{
      'page': page.toString(),
      'page_size': pageSize.toString(),
      if (q.isNotEmpty) 'q': q,
      if (enseigne.isNotEmpty) 'enseigne': enseigne,
    };
    final uri = Uri.parse('$baseUrl/catalog/products')
        .replace(queryParameters: params);
    final decoded = await _safeRequest(
      () => http.get(uri, headers: authHeaders()),
      timeout: _quickTimeout,
      path: '/catalog/products',
    );
    return ProductPage.fromJson(
      (decoded as Map?)?.cast<String, dynamic>() ?? const {},
    );
  }

  static Future<Product> createProduct(Product p) async {
    final decoded = await _safeRequest(
      () => http.post(
        Uri.parse('$baseUrl/catalog/products'),
        headers: authHeaders({'Content-Type': 'application/json'}),
        body: jsonEncode(p.toJsonInput()),
      ),
      timeout: _quickTimeout,
      path: '/catalog/products',
    );
    return Product.fromJson(
      (decoded as Map?)?.cast<String, dynamic>() ?? const {},
    );
  }

  static Future<Product> updateProduct(String id, Product p) async {
    final decoded = await _safeRequest(
      () => http.put(
        Uri.parse('$baseUrl/catalog/products/$id'),
        headers: authHeaders({'Content-Type': 'application/json'}),
        body: jsonEncode(p.toJsonInput()),
      ),
      timeout: _quickTimeout,
      path: '/catalog/products/$id',
    );
    return Product.fromJson(
      (decoded as Map?)?.cast<String, dynamic>() ?? const {},
    );
  }

  static Future<void> deleteProduct(String id) async {
    await _safeRequest(
      () => http.delete(Uri.parse('$baseUrl/catalog/products/$id'), headers: authHeaders()),
      timeout: _quickTimeout,
      path: '/catalog/products/$id',
    );
  }

  // ─── Admin: scraper jobs ───────────────────────────────────────────

  static Future<ScrapeJob> startScrape(String retailer, int maxProducts) async {
    final decoded = await _safeRequest(
      () => http.post(
        Uri.parse('$baseUrl/admin/scrape'),
        headers: authHeaders({'Content-Type': 'application/json'}),
        body: jsonEncode({'retailer': retailer, 'max_products': maxProducts}),
      ),
      timeout: _quickTimeout,
      path: '/admin/scrape',
    );
    return ScrapeJob.fromJson(
      (decoded as Map?)?.cast<String, dynamic>() ?? const {},
    );
  }

  static Future<ScrapeJob> scrapeStatus(String jobId) async {
    final uri = Uri.parse('$baseUrl/admin/scrape/status')
        .replace(queryParameters: {'job_id': jobId});
    final decoded = await _safeRequest(
      () => http.get(uri, headers: authHeaders()),
      timeout: _quickTimeout,
      path: '/admin/scrape/status',
    );
    return ScrapeJob.fromJson(
      (decoded as Map?)?.cast<String, dynamic>() ?? const {},
    );
  }
}
