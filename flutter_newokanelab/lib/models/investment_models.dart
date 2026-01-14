import 'package:fl_chart/fl_chart.dart';

// --- UI用モデル ---

/// 投資ファンドのデータ（UIでの選択肢）
class Fund {
  final String id;          // ファンドID
  final String label;       // 表示名
  final double annualReturn; // (バックエンド利用時は参考値、またはロジック側で使用)

  const Fund({required this.id, required this.label, required this.annualReturn});
}

/// ライフイベントのデータ（UIでの選択肢）
class LifeEvent {
  final String id;
  final String label;

  const LifeEvent({required this.id, required this.label});
}

// --- API連携用データモデル ---

/// 企業情報 (/api/companies レスポンス用)
class Company {
  final String tickerCode;
  final String companyName;

  Company({required this.tickerCode, required this.companyName});

  factory Company.fromJson(Map<String, dynamic> json) {
    return Company(
      tickerCode: json['ticker_code'] as String,
      companyName: json['company_name'] as String,
    );
  }
}

/// シミュレーションAPIのレスポンス全体
class SimulationResponse {
  final List<GraphData> graphData;
  final List<SimulationEvent> events;
  final SimulationSummary summary;

  SimulationResponse({
    required this.graphData,
    required this.events,
    required this.summary,
  });

  factory SimulationResponse.fromJson(Map<String, dynamic> json) {
    return SimulationResponse(
      graphData: (json['graph_data'] as List)
          .map((e) => GraphData.fromJson(e))
          .toList(),
      events: (json['events'] as List)
          .map((e) => SimulationEvent.fromJson(e))
          .toList(),
      summary: SimulationSummary.fromJson(json['summary']),
    );
  }

  /// グラフ描画用に fl_chart の FlSpot リストに変換するヘルパーメソッド
  /// X軸: シミュレーション開始からの経過年数 (0, 1, 2...) ※簡易的な変換
  /// 日付ベースでX軸を描画する場合は別途調整が必要ですが、
  /// 現在のUIロジックに合わせて「年単位」または「インデックス」でマッピングします。
  List<FlSpot> toFlSpots() {
    // データが多すぎる場合は間引くなどの処理が必要かもしれませんが、
    // ここでは単純に最初の日付からの経過年数（概算）をX軸にします。
    if (graphData.isEmpty) return [];

    final startDate = DateTime.parse(graphData.first.date);
    return graphData.map((data) {
      final currentDate = DateTime.parse(data.date);
      final diffDays = currentDate.difference(startDate).inDays;
      final years = diffDays / 365.25; // 年換算
      return FlSpot(years, data.totalAssets.toDouble());
    }).toList();
  }
}

/// 日次の資産データ
class GraphData {
  final String date;
  final num totalAssets;
  final num investedAmount;

  GraphData({
    required this.date,
    required this.totalAssets,
    required this.investedAmount,
  });

  factory GraphData.fromJson(Map<String, dynamic> json) {
    return GraphData(
      date: json['date'] as String,
      totalAssets: json['total_assets'] as num,
      investedAmount: json['invested_amount'] as num,
    );
  }
}

/// イベント（ニュース）データ
class SimulationEvent {
  final String date;
  final String ticker;
  final String title;
  final String description;
  final num sentiment;

  SimulationEvent({
    required this.date,
    required this.ticker,
    required this.title,
    required this.description,
    required this.sentiment,
  });

  factory SimulationEvent.fromJson(Map<String, dynamic> json) {
    return SimulationEvent(
      date: json['date'] as String,
      ticker: json['ticker'] as String,
      title: json['title'] as String,
      description: json['description'] as String,
      sentiment: json['sentiment'] as num,
    );
  }
}

/// サマリーデータ
class SimulationSummary {
  final num finalAssets;
  final num totalInvested;
  final num returnRate;

  SimulationSummary({
    required this.finalAssets,
    required this.totalInvested,
    required this.returnRate,
  });

  factory SimulationSummary.fromJson(Map<String, dynamic> json) {
    return SimulationSummary(
      finalAssets: json['final_assets'] as num,
      totalInvested: json['total_invested'] as num,
      returnRate: json['return_rate'] as num,
    );
  }
}

// --- アプリ内で使用する統合結果オブジェクト (ResultsSectionへ渡すもの) ---
class SimulationResult {
  final List<FlSpot> projectionData;
  final Map<String, double> summaryData;
  final List<SimulationEvent> events; // イベント表示用に追加

  SimulationResult({
    required this.projectionData,
    required this.summaryData,
    this.events = const [],
  });

  /// APIレスポンスからUI用Resultを作成するファクトリ
  factory SimulationResult.fromResponse(SimulationResponse response) {
    final spots = response.toFlSpots();
    final profit = response.summary.finalAssets - response.summary.totalInvested;
    
    return SimulationResult(
      projectionData: spots,
      summaryData: {
        "totalAmount": response.summary.finalAssets.toDouble(),
        "totalInvested": response.summary.totalInvested.toDouble(),
        "profit": profit.toDouble(),
        "profitRate": response.summary.returnRate.toDouble(),
      },
      events: response.events,
    );
  }
}
