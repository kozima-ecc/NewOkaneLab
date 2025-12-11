import 'dart:convert';
import 'package:http/http.dart' as http;
import 'package:flutter_newokanelab/models/investment_models.dart';

class ApiService {
  final String _baseUrl = "http://127.0.0.1:5000"; // Pythonサーバーのアドレス

  // 会社一覧を取得する
  Future<List<Company>> getCompanies() async {
    final response = await http.get(Uri.parse('$_baseUrl/companies'));

    if (response.statusCode == 200) {
      // 日本語が含まれる可能性があるため、UTF-8でデコード
      final List<dynamic> jsonResponse = json.decode(utf8.decode(response.bodyBytes));
      return jsonResponse.map((company) => Company.fromJson(company)).toList();
    } else {
      throw Exception('Failed to load companies');
    }
  }
}
