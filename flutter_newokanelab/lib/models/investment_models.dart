import 'package:fl_chart/fl_chart.dart';

// --- データモデルクラス ---

/// 投資ファンドのデータを保持するクラス
class Fund {
  final String id;          // ファンドの一意なID
  final String label;       // ファンドの表示名
  final double annualReturn; // 年間リターン（利率）

  const Fund({required this.id, required this.label, required this.annualReturn});
}

/// ライフイベントのデータを保持するクラス
class LifeEvent {
  final String id;    // イベントの一意なID
  final String label; // イベントの表示名

  const LifeEvent({required this.id, required this.label});
}

/// シミュレーション結果のデータを保持するクラス
class SimulationResult {
  final List<FlSpot> projectionData; // グラフ描画用のデータ
  final Map<String, double> summaryData; // サマリー表示用のデータ

  SimulationResult({required this.projectionData, required this.summaryData});
}
