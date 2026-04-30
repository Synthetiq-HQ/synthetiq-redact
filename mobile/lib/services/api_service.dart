import 'dart:async';
import 'dart:convert';
import 'package:http/http.dart' as http;
import '../config.dart';
import '../models/document.dart';

class ApiService {
  static final ApiService _i = ApiService._();
  factory ApiService() => _i;
  ApiService._();

  final _client = http.Client();

  // ── Documents ────────────────────────────────────────────────────────────

  Future<List<Document>> listDocuments() async {
    final res = await _client.get(Uri.parse('$kApiBase/documents'));
    _check(res);
    final data = jsonDecode(res.body) as List<dynamic>;
    return data.map((e) => Document.fromJson(e as Map<String, dynamic>)).toList();
  }

  Future<Document> getDocument(int docId) async {
    final res = await _client.get(Uri.parse('$kApiBase/document/$docId'));
    _check(res);
    return Document.fromJson(jsonDecode(res.body) as Map<String, dynamic>);
  }

  Future<Map<String, dynamic>> getProgress(int docId) async {
    final res = await _client.get(Uri.parse('$kApiBase/progress/$docId'));
    if (res.statusCode == 200) {
      // SSE returns text/event-stream; parse last data: line
      final lines = res.body.split('\n');
      for (final line in lines.reversed) {
        if (line.startsWith('data:')) {
          final jsonStr = line.substring(5).trim();
          if (jsonStr.isNotEmpty) {
            return jsonDecode(jsonStr) as Map<String, dynamic>;
          }
        }
      }
    }
    return {'status': 'processing', 'message': 'Processing...', 'percent': 50};
  }

  // ── Upload ────────────────────────────────────────────────────────────────

  Future<int> uploadDocument({
    required String filename,
    required List<int> fileBytes,
    required String mimeType,
    bool translate = false,
    String selectedCategory = '',
  }) async {
    final uri = Uri.parse('$kApiBase/upload');
    final req = http.MultipartRequest('POST', uri)
      ..files.add(http.MultipartFile.fromBytes(
        'file',
        fileBytes,
        filename: filename,
      ))
      ..fields['translate'] = translate ? '1' : '0'
      ..fields['selected_category'] = selectedCategory;

    final streamed = await _client.send(req);
    final res = await http.Response.fromStream(streamed);
    _check(res);
    final body = jsonDecode(res.body) as Map<String, dynamic>;
    return body['document_id'] as int;
  }

  // ── Actions ───────────────────────────────────────────────────────────────

  Future<void> approveDocument(int docId) async {
    final res = await _client.post(Uri.parse('$kApiBase/document/$docId/approve'));
    _check(res);
  }

  Future<void> flagForReview(int docId) async {
    final res = await _client.post(Uri.parse('$kApiBase/document/$docId/review'));
    _check(res);
  }

  // ── URLs (for Image.network) ──────────────────────────────────────────────

  String imageUrl(int docId, {bool redacted = true}) =>
      '$kApiBase/document/$docId/image?type=${redacted ? 'redacted' : 'original'}';

  String exportUrl(int docId) => '$kApiBase/document/$docId/export';

  // ── Helpers ───────────────────────────────────────────────────────────────

  void _check(http.Response res) {
    if (res.statusCode >= 400) {
      String msg = 'Request failed (${res.statusCode})';
      try {
        final body = jsonDecode(res.body) as Map<String, dynamic>;
        msg = body['detail']?.toString() ?? msg;
      } catch (_) {}
      throw ApiException(msg, res.statusCode);
    }
  }
}

class ApiException implements Exception {
  final String message;
  final int statusCode;
  ApiException(this.message, this.statusCode);
  @override
  String toString() => message;
}
