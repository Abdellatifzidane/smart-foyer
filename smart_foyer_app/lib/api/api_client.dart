import 'dart:convert';
import 'package:http/http.dart' as http;
import 'models.dart';

/// HTTP client for the SmartFoyer FastAPI backend.
class ApiClient {
  /// Backend base URL. Defaults to localhost which works for:
  ///   - Flutter Web on the same machine
  ///   - iOS Simulator (shares the host network)
  ///
  /// On a PHYSICAL iPhone, override with your Mac's LAN IP:
  ///   flutter run --dart-define=BACKEND_URL=http://192.168.1.42:8000
  ///
  /// In production, set this to your deployed backend URL (HTTPS).
  static const String baseUrl = String.fromEnvironment(
    'BACKEND_URL',
    defaultValue: 'http://127.0.0.1:8000',
  );

  /// Send a receipt image to the backend and parse the response.
  ///
  /// `imageBytes` is the raw file contents; `filename` is used to set the
  /// multipart content disposition (and Content-Type via the extension).
  static Future<ScanResult> scan(List<int> imageBytes, String filename) async {
    final uri = Uri.parse('$baseUrl/scan');
    final request = http.MultipartRequest('POST', uri)
      ..files.add(http.MultipartFile.fromBytes(
        'image',
        imageBytes,
        filename: filename,
      ));

    final streamed = await request.send();
    final response = await http.Response.fromStream(streamed);

    if (response.statusCode != 200) {
      throw Exception(
          'Backend error ${response.statusCode}: ${response.body}');
    }

    final decoded = jsonDecode(response.body) as Map<String, dynamic>;
    return ScanResult.fromJson(decoded);
  }

  /// Quick health-check used by the home screen.
  static Future<Map<String, dynamic>> catalogStats() async {
    final resp = await http.get(Uri.parse('$baseUrl/catalog/stats'));
    if (resp.statusCode != 200) {
      throw Exception('Backend unreachable');
    }
    return jsonDecode(resp.body) as Map<String, dynamic>;
  }

  /// List of past receipts (summaries, newest first).
  static Future<List<ReceiptSummary>> history() async {
    final resp = await http.get(Uri.parse('$baseUrl/history'));
    if (resp.statusCode != 200) {
      throw Exception('Backend error ${resp.statusCode}');
    }
    final list = jsonDecode(resp.body) as List;
    return list
        .map((e) => ReceiptSummary.fromJson(e as Map<String, dynamic>))
        .toList();
  }

  /// Aggregated stats across stored receipts.
  static Future<HistoryStats> historyStats() async {
    final resp = await http.get(Uri.parse('$baseUrl/history/stats'));
    if (resp.statusCode != 200) {
      throw Exception('Backend error ${resp.statusCode}');
    }
    return HistoryStats.fromJson(jsonDecode(resp.body) as Map<String, dynamic>);
  }

  /// Full details of a stored receipt.
  static Future<ScanResult> historyDetail(String id) async {
    final resp = await http.get(Uri.parse('$baseUrl/history/$id'));
    if (resp.statusCode != 200) {
      throw Exception('Backend error ${resp.statusCode}');
    }
    return ScanResult.fromJson(jsonDecode(resp.body) as Map<String, dynamic>);
  }

  /// Send a question to the RAG agent and get an answer.
  /// `history` carries prior turns so the agent has conversation context.
  static Future<String> chat(
    String question,
    List<Map<String, String>> history,
  ) async {
    final resp = await http.post(
      Uri.parse('$baseUrl/chat'),
      headers: {'Content-Type': 'application/json'},
      body: jsonEncode({'question': question, 'history': history}),
    );
    if (resp.statusCode != 200) {
      throw Exception('Backend error ${resp.statusCode}: ${resp.body}');
    }
    final data = jsonDecode(resp.body) as Map<String, dynamic>;
    return (data['answer'] ?? '').toString();
  }
}
