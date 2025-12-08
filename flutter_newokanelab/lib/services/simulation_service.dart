import 'package:fl_chart/fl_chart.dart';
import '../models/investment_models.dart';

class SimulationService {
  /// シミュレーションを実行し、結果を返す
  static Future<SimulationResult> calculate({
    required double initialInvestment,
    required double averageMonthlyInvestment,
    required String selectedFundId,
    required List<Fund> funds,
    required int simulationYears,
  }) async {
    // 実際のアプリではここでAPI通信を行う。
    // この例では、2秒待つことで非同期処理を模倣。
    await Future.delayed(const Duration(seconds: 2));

    // 選択されたファンドの情報を取得
    final fund = funds.firstWhere((f) => f.id == selectedFundId);
    final returnRate = fund.annualReturn;
    
    // グラフ描画用のデータを生成
    double projectionTotal = initialInvestment;
    final List<FlSpot> projectionData = [];
    for (int year = 0; year <= simulationYears; year++) {
      projectionData.add(FlSpot(year.toDouble(), projectionTotal.roundToDouble()));
      projectionTotal = projectionTotal * (1 + returnRate) + averageMonthlyInvestment * 12;
    }

    // サマリー表示用のデータを生成
    double summaryTotal = initialInvestment;
    for (int i = 1; i <= simulationYears; i++) {
        summaryTotal = summaryTotal * (1 + returnRate) + averageMonthlyInvestment * 12;
    }
    final totalInvested = initialInvestment + averageMonthlyInvestment * 12 * simulationYears;
    final profit = summaryTotal - totalInvested;
    final profitRate = (profit / totalInvested) * 100;
    
    // 計算結果をMapにまとめる
    final summaryData = {
        "totalAmount": summaryTotal,
        "totalInvested": totalInvested,
        "profit": profit,
        "profitRate": profitRate,
    };

    // SimulationResultオブジェクトとして返す
    return SimulationResult(projectionData: projectionData, summaryData: summaryData);
  }
}
