import 'package:fl_chart/fl_chart.dart';
import 'package:flutter/material.dart';
import 'package:intl/intl.dart';
import '../models/investment_models.dart';

/// シミュレーション結果の表示セクション全体を構築するStatelessWidget
class ResultsSection extends StatelessWidget {
  final bool isLoading;
  final SimulationResult? simulationResult;
  final GlobalKey resultsKey;
  final double initialInvestment;
  final double averageMonthlyInvestment;
  final double? simulationYears;

  const ResultsSection({
    super.key,
    required this.isLoading,
    this.simulationResult,
    required this.resultsKey,
    required this.initialInvestment,
    required this.averageMonthlyInvestment,
    this.simulationYears,
  });

  @override
  Widget build(BuildContext context) {
    // 数値を通貨形式（円）にフォーマットするためのフォーマッター
    final formatter = NumberFormat.currency(locale: 'ja_JP', symbol: '¥');

    Widget content;

    if (isLoading) {
      // ローディング中の場合、インジケーターを表示
      content = const Center(
          child: Padding(
        padding: EdgeInsets.symmetric(vertical: 80.0),
        child: CircularProgressIndicator(),
      ));
    } else if (simulationResult == null) {
      // まだ結果がない場合、初期メッセージを表示
      content = Center(
        child: Padding(
          padding: const EdgeInsets.symmetric(vertical: 80.0),
          child: Column(
            mainAxisAlignment: MainAxisAlignment.center,
            children: [
              Icon(Icons.insights, size: 80, color: Colors.grey[700]),
              const SizedBox(height: 20),
              Text(
                'シミュレーションを実行して\n結果を表示します',
                textAlign: TextAlign.center,
                style: TextStyle(color: Colors.grey[600], fontSize: 16),
              ),
            ],
          ),
        ),
      );
    } else {
      // 結果がある場合、グラフとサマリーを表示
      final projectionData = simulationResult!.projectionData;
      final summaryData = simulationResult!.summaryData;
      final yearsForView = (simulationYears ?? 10).round().toDouble();
      final shown = projectionData.where((s) => s.x <= yearsForView).toList()
          ..sort((a, b) => a.x.compareTo(b.x));

      final fixedSummaryData = Map<String, double>.from(summaryData);

      if (shown.isNotEmpty) {
        final shownLastY = shown.last.y;

        // 表示年数の投資元本を再計算（初期投資 + 平均月額 * 12 * 年）
        final totalInvestedView =
        initialInvestment + averageMonthlyInvestment * 12 * yearsForView;

        fixedSummaryData["totalAmount"] = shownLastY;
        fixedSummaryData["totalInvested"] = totalInvestedView;

        fixedSummaryData["profit"] = shownLastY - totalInvestedView;
        fixedSummaryData["profitRate"] =
        totalInvestedView == 0 ? 0 : (fixedSummaryData["profit"]! / totalInvestedView) * 100;
      }
      // LayoutBuilderを使って、画面幅に応じたレイアウト切り替えを行う
      content = LayoutBuilder(
        builder: (context, constraints) {
          // 画面幅が800pxより大きい場合 (PCレイアウト)
          if (constraints.maxWidth > 800) {
            return Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                _buildChartCard(context, projectionData),
                const SizedBox(height: 16),
                Row(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Expanded(child: _buildInvestmentSummaryCard(context, fixedSummaryData, formatter)),
                    const SizedBox(width: 16),
                    Expanded(child: _buildExpectedResultsCard(context, fixedSummaryData, formatter)),
                  ],
                ),
              ],
            );
          } else { // 画面幅が800px以下の場合 (モバイルレイアウト)
            return Column(
              children: [
                _buildChartCard(context, projectionData),
                const SizedBox(height: 16),
                _buildSummaryCards(context, fixedSummaryData, formatter),
              ],
            );
          }
        },
      );
    }

    // 結果セクション全体のウィジェット
    return Column(
      key: resultsKey, // スクロール位置の特定に使用
      children: [
        Padding(
          padding: const EdgeInsets.only(top: 24, bottom: 8),
          child: Row(
            mainAxisAlignment: MainAxisAlignment.spaceBetween,
            children: [
              Text("シミュレーション結果", style: Theme.of(context).textTheme.headlineSmall),
            ],
          ),
        ),
        const SizedBox(height: 8),
        content,
      ],
    );
  }

  /// 資産成長グラフのカードを構築
  Widget _buildChartCard(BuildContext context, List<FlSpot> data) {
    final years = (simulationYears ?? 10).round().toDouble();

    
    final spots = data.where((s) => s.x <= years).toList()
      ..sort((a, b) => a.x.compareTo(b.x));

    // 右端まで線を伸ばす
    if (spots.isNotEmpty && spots.last.x < years) {
      spots.add(FlSpot(years, spots.last.y));
    }

    final double maxDataY = spots.isEmpty
        ? 0
        : spots.map((s) => s.y).reduce((a, b) => a > b ? a : b);

    final double paddedMaxY = maxDataY * 1.08;
    // 目盛り間隔を自動調整
    final double yInterval = _pickYInterval(paddedMaxY);
    // maxY を interval に合わせて切り上げ
    final double maxY = _ceilTo(paddedMaxY, yInterval);
    // minY は 0 固定
    const double minY = 0;
    
    return Card(
      child: Padding(
        padding: const EdgeInsets.fromLTRB(16, 16, 16, 12),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Text("${years.toInt()}年間の資産成長", style: Theme.of(context).textTheme.bodySmall),
            const SizedBox(height: 24),
            SizedBox(
              height: 500,
              child: LineChart(
                LineChartData(
                  minX: 0,
                  maxX: years,
                  minY: minY,
                  maxY: maxY,

                  gridData: FlGridData(show: false),
                  borderData: FlBorderData(show: false),

                  titlesData: FlTitlesData(
                    leftTitles: AxisTitles(
                      sideTitles: SideTitles(
                        showTitles: true,
                        reservedSize: 60,
                        interval: yInterval, 
                        getTitlesWidget: _leftTitleWidgets,
                      ),
                    ),
                    bottomTitles: AxisTitles(
                      sideTitles: SideTitles(
                        showTitles: true,
                        interval: 2,
                        reservedSize: 30,
                        getTitlesWidget: _bottomTitleWidgets,
                      ),
                    ),
                    topTitles: const AxisTitles(sideTitles: SideTitles(showTitles: false)),
                    rightTitles: const AxisTitles(sideTitles: SideTitles(showTitles: false)),
                  ),

                  lineBarsData: [
                    LineChartBarData(
                      spots: spots,
                      isCurved: true,
                      color: Theme.of(context).colorScheme.tertiary,
                      barWidth: 4,
                      isStrokeCapRound: true,
                      dotData: const FlDotData(show: false),
                      belowBarData: BarAreaData(
                        show: true,
                        color: Theme.of(context).colorScheme.tertiary.withOpacity(0.3),
                      ),
                    ),
                  ],
                  lineTouchData: LineTouchData(
                    touchTooltipData: LineTouchTooltipData(
                      getTooltipItems: (touchedBarSpots) {
                        return touchedBarSpots.map((barSpot) {
                          final year = barSpot.x.round(); // 
                          final amount = barSpot.y;
                          final formatter = NumberFormat.currency(locale: 'ja_JP', symbol: '¥');
                          return LineTooltipItem(
                            formatter.format(amount), 
                            TextStyle(color: Theme.of(context).colorScheme.onPrimary),
                          );
                        }).toList();
                      },
                    ),
                  ),               
                ),
              ),
            ),
          ],
        ),
      ),
    );
  }



double _pickYInterval(double maxY) {
  // 50万未満  10万刻み
  if (maxY < 500000) return 100000;

  // 50万以上 100万未満  50万刻み
  if (maxY < 1000000) return 500000;

  // 100万以上  100万刻み
  return 1000000;
}

double _ceilTo(double value, double step) {
  if (step == 0) return value;
  return (value / step).ceilToDouble() * step;
}

  /// グラフのX軸（下側）のラベルを構築
  Widget _bottomTitleWidgets(double value, TitleMeta meta) {
    const style = TextStyle(fontSize: 10);
    Widget text;
    return SideTitleWidget(meta: meta,space: 8.0,child: Text('${value.toInt()}年', style: style),
    );

  }

  /// グラフのY軸（左側）のラベルを構築
  Widget _leftTitleWidgets(double value, TitleMeta meta) {
    final style = TextStyle(fontSize: 10, color: Colors.grey[400]);

      if (value == 0) return const SizedBox.shrink();
      
      return Text('${(value / 10000).toInt()}万', style: style, textAlign: TextAlign.right);

      }

  /// サマリーカード群を構築（モバイルレイアウト用）
  Widget _buildSummaryCards(BuildContext context, Map<String, double> summaryData, NumberFormat formatter) {
    if (summaryData['totalInvested'] == null || summaryData['totalAmount'] == null || summaryData['profit'] == null || summaryData['profitRate'] == null) {
      return const SizedBox.shrink();
    }
    return Column(
      children: [
        _buildInvestmentSummaryCard(context, summaryData, formatter),
        const SizedBox(height: 16),
        _buildExpectedResultsCard(context, summaryData, formatter),
      ],
    );
  }

  /// 投資額サマリーカードを構築
  Widget _buildInvestmentSummaryCard(BuildContext context, Map<String, double> summary, NumberFormat formatter) {
    final years = (simulationYears ?? 10).round();
    return Card(
      child: Padding(
        padding: const EdgeInsets.all(16.0),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Text("投資額", style: Theme.of(context).textTheme.bodySmall),
            const SizedBox(height: 12),
            _buildSummaryRow(context, "初期投資", formatter.format(initialInvestment)),
            _buildSummaryRow(context, "月額投資 × ${years * 12}ヶ月", formatter.format(averageMonthlyInvestment * 12 * years)),
            const Divider(height: 24),
            _buildSummaryRow(context, "総投資額", formatter.format(summary['totalInvested']), isTotal: true),
          ],
        ),
      ),
    );
  }

  /// 予想成果カードを構築
  Widget _buildExpectedResultsCard(BuildContext context, Map<String, double> summary, NumberFormat formatter) {
    final years = (simulationYears ?? 10).round();
    return Card(
      child: Padding(
        padding: const EdgeInsets.all(16.0),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Text("予想成果（${years}年）", style: Theme.of(context).textTheme.bodySmall),
            const SizedBox(height: 12),
            Text("予想資産額", style: Theme.of(context).textTheme.bodySmall),
            Text(
              formatter.format(summary['totalAmount']),
              style: TextStyle(
                fontSize: 28,
                fontWeight: FontWeight.bold,
                color: Theme.of(context).colorScheme.tertiary,
              ),
            ),
            const Divider(height: 24),
            Text("利益", style: Theme.of(context).textTheme.bodySmall),
            Row(
              mainAxisAlignment: MainAxisAlignment.spaceBetween,
              children: [
                Text(formatter.format(summary['profit']), style: const TextStyle(fontWeight: FontWeight.bold, fontSize: 16)),
                Text('+${summary['profitRate']?.toStringAsFixed(1)}%', style: TextStyle(fontWeight: FontWeight.bold, fontSize: 16, color: Theme.of(context).colorScheme.tertiary)),
              ],
            )
          ],
        ),
      ),
    );
  }

  /// サマリーカード内の各行を構築
  Widget _buildSummaryRow(BuildContext context, String label, String value, {bool isTotal = false}) {
    final valueStyle = isTotal
        ? TextStyle(fontWeight: FontWeight.bold, color: Theme.of(context).colorScheme.tertiary, fontSize: 16)
        : const TextStyle(fontWeight: FontWeight.bold, fontSize: 16);
    return Padding(
      padding: const EdgeInsets.symmetric(vertical: 4.0),
      child: Row(
        mainAxisAlignment: MainAxisAlignment.spaceBetween,
        children: [
          Text(label, style: Theme.of(context).textTheme.bodySmall),
          Text(value, style: valueStyle),
        ],
      ),
    );
  }
}
