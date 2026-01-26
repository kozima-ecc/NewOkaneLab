import 'package:flutter/material.dart';
import 'package:intl/intl.dart';

import '../models/investment_models.dart';

/// ユーザー入力を受け付けるフォームセクション全体を構築するStatelessWidget
class InputSection extends StatelessWidget {
  // --- 現在の入力値 ---
  final double initialInvestment;
  final double? simulationYears;
  final bool isMonthlyMode;
  final double fixedMonthlyInvestment;
  final List<double> monthlyInvestments;
  final String selectedFundId;
  final Set<String> selectedEventIds;

  // --- データ ---
  final List<Fund> funds;
  final List<LifeEvent> events;
  final List<String> months;
  final double averageMonthlyInvestment;

  // --- コールバック関数 ---
  final ValueChanged<double> onInitialInvestmentChanged;
  final ValueChanged<double> onSimulationYearsChanged;
  final ValueChanged<bool> onMonthlyModeChanged;
  final ValueChanged<double> onFixedMonthlyInvestmentChanged;
  final void Function(int, double) onMonthlyInvestmentChanged;
  final ValueChanged<String?> onFundIdChanged;
  final void Function(String, bool?) onEventIdToggled;
  final VoidCallback onSimulatePressed;

  const InputSection({
    super.key,
    required this.initialInvestment,
    this.simulationYears,
    required this.isMonthlyMode,
    required this.fixedMonthlyInvestment,
    required this.monthlyInvestments,
    required this.selectedFundId,
    required this.selectedEventIds,
    required this.funds,
    required this.events,
    required this.months,
    required this.averageMonthlyInvestment,
    required this.onInitialInvestmentChanged,
    required this.onSimulationYearsChanged,
    required this.onMonthlyModeChanged,
    required this.onFixedMonthlyInvestmentChanged,
    required this.onMonthlyInvestmentChanged,
    required this.onFundIdChanged,
    required this.onEventIdToggled,
    required this.onSimulatePressed,
  });

  @override
  Widget build(BuildContext context) {
    return Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        Row(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Expanded(
              child: Column(
                children: [
                  _buildInitialInvestmentCard(context),
                  const SizedBox(height: 16),
                  _buildYearsSelectorCard(context),
                ],
              ),
            ),
            const SizedBox(width: 16),
            Expanded(child: _buildFundSelectorCard(context)),
          ],
        ),
        const SizedBox(height: 16),
        _buildMonthlyInvestmentCard(context),
        const SizedBox(height: 16),
        //_buildEventsCard(context), // ライフイベントカードは一旦非表示
        const SizedBox(height: 24),
        ElevatedButton(
          onPressed: onSimulatePressed,
          child: const Text('シミュレーションを実行'),
        ),
      ],
    );
  }

  /// 初期投資金額設定カード
  Widget _buildInitialInvestmentCard(BuildContext context) {
    final formatter = NumberFormat.currency(locale: 'ja_JP', symbol: '¥');
    return Card(
      child: Padding(
        padding: const EdgeInsets.all(16.0),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Row(
              mainAxisAlignment: MainAxisAlignment.spaceBetween,
              children: [
                Text("初期投資金額", style: Theme.of(context).textTheme.bodySmall),
                InkWell(
                  onTap: () {
                    _showNumberInputDialog(
                      context: context,
                      title: '初期投資金額',
                      initialValue: initialInvestment.toStringAsFixed(0),
                      onSave: (value) {
                        final newValue = double.tryParse(value);
                        if (newValue != null) {
                          final clampedValue = newValue.clamp(10000.0, 1000000.0);
                          onInitialInvestmentChanged(clampedValue);
                        }
                      },
                    );
                  },
                  child: Text(
                    formatter.format(initialInvestment),
                    style: TextStyle(
                      fontWeight: FontWeight.bold,
                      fontSize: 18,
                      color: Theme.of(context).colorScheme.tertiary,
                    ),
                  ),
                ),
              ],
            ),
            const SizedBox(height: 8),
            Slider(
              value: initialInvestment,
              min: 10000,
              max: 1000000,
              divisions: 99,
              onChanged: onInitialInvestmentChanged,
            ),
            Row(
              mainAxisAlignment: MainAxisAlignment.spaceBetween,
              children: [
                Text("¥10,000", style: Theme.of(context).textTheme.bodySmall),
                Text("¥1,000,000", style: Theme.of(context).textTheme.bodySmall),
              ],
            ),
          ],
        ),
      ),
    );
  }

  /// シミュレーション年数設定カード
  Widget _buildYearsSelectorCard(BuildContext context) {
    const double maxYears = 10;
    return Card(
      child: Padding(
        padding: const EdgeInsets.all(16.0),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Row(
              mainAxisAlignment: MainAxisAlignment.spaceBetween,
              children: [
                Text("シミュレーション年数", style: Theme.of(context).textTheme.bodySmall),
                InkWell(
                  onTap: () {
                    _showNumberInputDialog(
                      context: context,
                      title: 'シミュレーション年数',
                      initialValue: (simulationYears ?? 10).round().toString(),
                      onSave: (value) {
                        final newValue = double.tryParse(value);
                        if (newValue != null) {
                          final clampedValue = newValue.clamp(1.0, 10.0);
                          onSimulationYearsChanged(clampedValue);
                        }
                      },
                    );
                  },
                  child: Text(
                    '${(simulationYears ?? 10).round()} 年',
                    style: TextStyle(
                      fontWeight: FontWeight.bold,
                      fontSize: 18,
                      color: Theme.of(context).colorScheme.tertiary,
                    ),
                  ),
                ),
              ],
            ),
            const SizedBox(height: 8),
            Slider(
              value: (simulationYears ?? maxYears).clamp(1.0, maxYears),
              min: 1,
              max: maxYears,
              divisions: (maxYears - 1).toInt(), // 1年刻み
              onChanged: onSimulationYearsChanged,
            ),
            Row(
              mainAxisAlignment: MainAxisAlignment.spaceBetween,
              children: [
                Text("1年", style: Theme.of(context).textTheme.bodySmall),
                Text("10年", style: Theme.of(context).textTheme.bodySmall),
              ],
            ),
          ],
        ),
      ),
    );
  }

  /// ファンド選択カード
  Widget _buildFundSelectorCard(BuildContext context) {
    final selectedFund = funds.firstWhere((f) => f.id == selectedFundId);
    return Card(
      child: Padding(
        padding: const EdgeInsets.all(16.0),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            const Text("ファンドを選択", style: TextStyle(fontWeight: FontWeight.bold)),
            const SizedBox(height: 16),
            DropdownButtonFormField<String>(
              value: selectedFundId,
              items: funds.map((fund) {
                return DropdownMenuItem(
                  value: fund.id,
                  child: Text('${fund.label} (リターン: ${(fund.annualReturn * 100).toStringAsFixed(1)}%)'),
                );
              }).toList(),
              onChanged: onFundIdChanged,
              decoration: const InputDecoration(
                contentPadding: EdgeInsets.symmetric(horizontal: 12, vertical: 12),
              ),
            ),
            const SizedBox(height: 16),
            Container(
              padding: const EdgeInsets.all(12),
              decoration: BoxDecoration(
                color: Theme.of(context).scaffoldBackgroundColor,
                borderRadius: BorderRadius.circular(8),
              ),
              child: Row(
                children: [
                  const Text("選択中のファンド: "),
                  Text(selectedFund.label, style: TextStyle(fontWeight: FontWeight.bold, color: Theme.of(context).colorScheme.tertiary)),
                ],
              ),
            ),
          ],
        ),
      ),
    );
  }

  /// 月額投資設定カード
  Widget _buildMonthlyInvestmentCard(BuildContext context) {
    final formatter = NumberFormat.currency(locale: 'ja_JP', symbol: '¥');
    return Card(
      child: Padding(
        padding: const EdgeInsets.all(16.0),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Row(
              mainAxisAlignment: MainAxisAlignment.spaceBetween,
              children: [
                const Text("月ごとの投資金額設定", style: TextStyle(fontWeight: FontWeight.bold)),
                Row(
                  children: [
                    Text("定額", style: TextStyle(color: !isMonthlyMode ? Theme.of(context).colorScheme.tertiary : Colors.grey)),
                    Switch(
                      value: isMonthlyMode,
                      onChanged: onMonthlyModeChanged,
                      activeColor: Theme.of(context).colorScheme.tertiary,
                    ),
                    Text("月ごと", style: TextStyle(color: isMonthlyMode ? Theme.of(context).colorScheme.tertiary : Colors.grey)),
                  ],
                ),
              ],
            ),
            const SizedBox(height: 16),
            !isMonthlyMode
                ? _buildFixedInvestmentInput(context)
                : _buildMonthlyInvestmentInputs(context),
            Padding(
              padding: const EdgeInsets.only(top: 12.0),
              child: Text(
                isMonthlyMode
                    ? '平均月額: ${formatter.format(averageMonthlyInvestment)}'
                    : '年間投資額: ${formatter.format(fixedMonthlyInvestment * 12)}',
                style: Theme.of(context).textTheme.bodySmall,
              ),
            ),
          ],
        ),
      ),
    );
  }

  /// 定額投資入力フィールド
  Widget _buildFixedInvestmentInput(BuildContext context) {
    return TextFormField(
      initialValue: fixedMonthlyInvestment.toStringAsFixed(0),
      decoration: const InputDecoration(
        labelText: '月額投資金額',
        prefixText: '¥ ',
      ),
      keyboardType: TextInputType.number,
      onChanged: (value) => onFixedMonthlyInvestmentChanged(double.tryParse(value) ?? fixedMonthlyInvestment),
    );
  }

  /// 月ごと投資入力フィールド
  Widget _buildMonthlyInvestmentInputs(BuildContext context) {
    return GridView.builder(
      shrinkWrap: true,
      physics: const NeverScrollableScrollPhysics(),
      gridDelegate: const SliverGridDelegateWithFixedCrossAxisCount(
        crossAxisCount: 4,
        childAspectRatio: 3.0,
        crossAxisSpacing: 10,
        mainAxisSpacing: 5,
      ),
      itemCount: 12,
      itemBuilder: (context, index) {
        return Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Text(months[index], style: Theme.of(context).textTheme.bodySmall),
            Expanded(
              child: TextFormField(
                initialValue: monthlyInvestments[index].toStringAsFixed(0),
                keyboardType: TextInputType.number,
                decoration: const InputDecoration(
                  prefixText: '¥ ',
                  contentPadding: EdgeInsets.symmetric(horizontal: 8),
                ),
                onChanged: (value) => onMonthlyInvestmentChanged(index, double.tryParse(value) ?? monthlyInvestments[index]),
              ),
            ),
          ],
        );
      },
    );
  }

  /// ライフイベント選択カード
  Widget _buildEventsCard(BuildContext context) {
    return Card(
      child: Padding(
        padding: const EdgeInsets.all(16.0),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            const Text("重要なイベント", style: TextStyle(fontWeight: FontWeight.bold)),
            const SizedBox(height: 8),
            GridView.builder(
              shrinkWrap: true,
              physics: const NeverScrollableScrollPhysics(),
              gridDelegate: const SliverGridDelegateWithFixedCrossAxisCount(
                crossAxisCount: 4,
                childAspectRatio: 3,
                crossAxisSpacing: 10,
                mainAxisSpacing: 10,
              ),
              itemCount: events.length,
              itemBuilder: (context, index) {
                final event = events[index];
                return CheckboxListTile(
                  title: Text(event.label, style: Theme.of(context).textTheme.bodySmall),
                  value: selectedEventIds.contains(event.id),
                  onChanged: (value) => onEventIdToggled(event.id, value),
                  controlAffinity: ListTileControlAffinity.leading,
                  activeColor: Theme.of(context).colorScheme.tertiary,
                  contentPadding: EdgeInsets.zero,
                );
              },
            ),
          ],
        ),
      ),
    );
  }

  // Helper method to show a dialog for number input
  Future<void> _showNumberInputDialog({
    required BuildContext context,
    required String title,
    required String initialValue,
    required void Function(String) onSave,
  }) async {
    final controller = TextEditingController(text: initialValue);
    return showDialog<void>(
      context: context,
      builder: (BuildContext context) {
        return AlertDialog(
          title: Text(title),
          content: TextField(
            controller: controller,
            keyboardType: const TextInputType.numberWithOptions(decimal: true),
            autofocus: true,
            decoration: const InputDecoration(
              hintText: '数値を入力してください',
            ),
          ),
          actions: <Widget>[
            TextButton(
              child: const Text('キャンセル'),
              onPressed: () {
                Navigator.of(context).pop();
              },
            ),
            TextButton(
              child: const Text('保存'),
              onPressed: () {
                onSave(controller.text);
                Navigator.of(context).pop();
              },
            ),
          ],
        );
      },
    );
  }
}
