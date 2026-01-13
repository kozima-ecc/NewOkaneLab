import 'package:flutter_newokanelab/models/investment_models.dart';
import 'package:flutter_newokanelab/services/api_service.dart';

class SimulationService {
  static final ApiService _apiService = ApiService();

  /// シミュレーションを実行し、結果を返す
  static Future<SimulationResult> calculate({
    required double initialInvestment,
    required double averageMonthlyInvestment,
    required String selectedFundId,
    required List<Fund> funds,
    required int simulationYears,
  }) async {
    
    // 1. ファンドIDに基づいて投資銘柄(Tickers)を決定する
    List<String> tickers;
    switch (selectedFundId) {
      case 'nikkei225':
        // 日経平均株価連動
        tickers = ["^N225"];
        break;
      case 'japan_core':
        // 国内主力大型株 (トヨタ, ソニーG, 三菱UFJ)
        tickers = ["7203.T", "6758.T", "8306.T"];
        break;
      case 'us_tech':
        // 米国テック大手 (Apple, Microsoft, Google)
        tickers = ["AAPL", "MSFT", "GOOGL"];
        break;
      case 'semi_growth':
        // 半導体・グロース (東京エレクトロン, キーエンス, NVIDIA)
        tickers = ["8035.T", "6861.T", "NVDA"];
        break;
      case 'high_dividend':
        // 高配当・バリュー (三菱商事, 武田薬品, NTT)
        tickers = ["8058.T", "4502.T", "9432.T"];
        break;
      default:
        // デフォルト
        tickers = ["^N225"];
    }

    // 2. シミュレーション期間の設定
    // バックエンドのデータが 2015-01-01 からあるため、そこを開始点とします。
    // 終了日は開始日から simulationYears 後、またはデータの終わり(2024年末)まで
    const startYear = 2015;
    final endYear = startYear + simulationYears;
    
    // データが存在する範囲にクリップする（バックエンドのデータが2024年までと仮定）
    final effectiveEndYear = endYear > 2024 ? 2024 : endYear;

    final startDate = "$startYear-01-01";
    final endDate = "$effectiveEndYear-12-31";

    try {
      // 3. API呼び出し
      final response = await _apiService.simulate(
        initialInvestment: initialInvestment,
        monthlyInvestment: averageMonthlyInvestment,
        tickers: tickers,
        startDate: startDate,
        endDate: endDate,
      );

      // 4. 結果の変換
      return SimulationResult.fromResponse(response);

    } catch (e) {
      print("Simulation failed: $e");
      // エラー時は空の結果などを返すか、再スローしてUI側でハンドリングさせます
      // ここでは簡易的にエラーを再スローします
      rethrow;
    }
  }
}
