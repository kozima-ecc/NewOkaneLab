import 'dart:convert';
import 'package:http/http.dart' as http;
import 'package:flutter_newokanelab/core/api_config.dart';
import 'package:flutter_newokanelab/models/investment_models.dart';

class ApiService {
  
  // 会社一覧を取得する
  Future<List<Company>> getCompanies() async {
    try {
      final response = await http.get(Uri.parse(ApiConfig.companiesEndpoint));

      if (response.statusCode == 200) {
        // 日本語が含まれる可能性があるため、UTF-8でデコード
        final List<dynamic> jsonResponse = json.decode(utf8.decode(response.bodyBytes));
        return jsonResponse.map((company) => Company.fromJson(company)).toList();
      } else {
        throw Exception('Failed to load companies: ${response.statusCode}');
      }
    } catch (e) {
      // 開発中などサーバーに繋がらない場合のエラーハンドリング
      print("Error fetching companies: $e");
      rethrow;
    }
  }

  // シミュレーションを実行する
  Future<SimulationResponse> simulate({
    required double initialInvestment,
    required double monthlyInvestment,
    required List<String> tickers,
    required String startDate,
    required String endDate,
  }) async {
    final Map<String, dynamic> requestBody = {
      "initial_investment": initialInvestment,
      "monthly_investment": monthlyInvestment,
      "tickers": tickers,
      "start_date": startDate,
      "end_date": endDate,
    };

    try {
      final response = await http.post(
        Uri.parse(ApiConfig.simulateEndpoint),
        headers: {"Content-Type": "application/json"},
        body: json.encode(requestBody),
      );

      if (response.statusCode == 200) {
        final Map<String, dynamic> jsonResponse = json.decode(utf8.decode(response.bodyBytes));
        return SimulationResponse.fromJson(jsonResponse);
      } else {
        throw Exception('Failed to run simulation: ${response.statusCode} ${response.body}');
      }
    } catch (e) {
      print("Error running simulation: $e");
      rethrow;
    }
  }
}
