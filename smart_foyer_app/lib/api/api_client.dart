import 'dart:convert';
import 'package:http/http.dart' as http;
import 'models.dart';

/// HTTP client for the SmartFoyer FastAPI backend.
class ApiClient {
  /// Backend base URL. When running Flutter Web on the same machine as the
  /// backend, localhost works directly.
  static const String baseUrl = 'http://127.0.0.1:8000';

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
}
