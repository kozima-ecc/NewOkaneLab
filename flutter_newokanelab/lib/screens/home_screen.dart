import 'package:flutter/material.dart';

import '../models/investment_models.dart';
import '../services/simulation_service.dart';
import '../widgets/input_section.dart';
import '../widgets/results_section.dart';

class HomePage extends StatefulWidget {
  const HomePage({super.key});

  @override
  State<HomePage> createState() => _HomePageState();
}

class _HomePageState extends State<HomePage> {
  final _scrollController = ScrollController();
  final _resultsKey = GlobalKey();

  // --- State Variables ---
  double _initialInvestment = 300000;
  double _simulationYears = 20;
  bool _isMonthlyMode = false;
  double _fixedMonthlyInvestment = 20000;
  late List<double> _monthlyInvestments;
  String _selectedFundId = "balanced";
  final Set<String> _selectedEventIds = {};
  
  bool _isLoading = false;
  SimulationResult? _simulationResult;

  // --- Static Data ---
  final List<Fund> _funds = const [
    Fund(id: "aggressive", label: "アグレッシブファンド", annualReturn: 0.08),
    Fund(id: "balanced", label: "バランスファンド", annualReturn: 0.06),
    Fund(id: "conservative", label: "コンサバティブファンド", annualReturn: 0.04),
    Fund(id: "growth", label: "グロースファンド", annualReturn: 0.09),
    Fund(id: "income", label: "インカムファンド", annualReturn: 0.05),
  ];
  final List<LifeEvent> _events = const [
    LifeEvent(id: "retirement", label: "バブル崩壊"),
    LifeEvent(id: "education", label: "コロナショック"),
    LifeEvent(id: "housing", label: "トランプショック"),
  ];
  final List<String> _months = const [
    "1月", "2月", "3月", "4月", "5月", "6月", "7月", "8月", "9月", "10月", "11月", "12月"
  ];

  @override
  void initState() {
    super.initState();
    _monthlyInvestments = List.filled(12, 20000);
  }

  @override
  void dispose() {
    _scrollController.dispose();
    super.dispose();
  }

  double get _averageMonthlyInvestment {
    if (!_isMonthlyMode) {
      return _fixedMonthlyInvestment;
    }
    return _monthlyInvestments.reduce((a, b) => a + b) / 12;
  }

  void _runSimulation() async {
    setState(() {
      _isLoading = true;
      _simulationResult = null;
    });

    final result = await SimulationService.calculate(
      initialInvestment: _initialInvestment,
      averageMonthlyInvestment: _averageMonthlyInvestment,
      selectedFundId: _selectedFundId,
      funds: _funds,
      simulationYears: _simulationYears.round(),
    );

    setState(() {
      _simulationResult = result;
      _isLoading = false;
    });

    WidgetsBinding.instance.addPostFrameCallback((_) {
      final context = _resultsKey.currentContext;
      if (context != null) {
        Scrollable.ensureVisible(context,
            duration: const Duration(milliseconds: 500),
            curve: Curves.easeInOut);
      }
    });
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(
        title: const Text('投資シミュレーター'),
        backgroundColor: Theme.of(context).cardColor,
        elevation: 1,
        bottom: PreferredSize(
          preferredSize: const Size.fromHeight(20.0),
          child: Padding(
            padding: const EdgeInsets.only(left: 16.0, bottom: 8.0),
            child: Align(
              alignment: Alignment.centerLeft,
              child: Text(
                '将来の資産形成をシミュレーションします',
                style: Theme.of(context).textTheme.bodySmall,
              ),
            ),
          ),
        ),
      ),
      body: SingleChildScrollView(
        controller: _scrollController,
        child: Padding(
          padding: const EdgeInsets.all(16.0),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.stretch,
            children: [
              InputSection(
                initialInvestment: _initialInvestment,
                onInitialInvestmentChanged: (value) => setState(() => _initialInvestment = value),
                simulationYears: _simulationYears ?? 20,
                onSimulationYearsChanged: (value) => setState(() => _simulationYears = value),
                isMonthlyMode: _isMonthlyMode,
                onMonthlyModeChanged: (value) => setState(() => _isMonthlyMode = value),
                fixedMonthlyInvestment: _fixedMonthlyInvestment,
                onFixedMonthlyInvestmentChanged: (value) => setState(() => _fixedMonthlyInvestment = value),
                monthlyInvestments: _monthlyInvestments,
                onMonthlyInvestmentChanged: (index, value) => setState(() => _monthlyInvestments[index] = value),
                selectedFundId: _selectedFundId,
                onFundIdChanged: (value) {
                  if (value != null) {
                    setState(() => _selectedFundId = value);
                  }
                },
                selectedEventIds: _selectedEventIds,
                onEventIdToggled: (id, value) {
                  setState(() {
                    if (value == true) {
                      _selectedEventIds.add(id);
                    } else {
                      _selectedEventIds.remove(id);
                    }
                  });
                },
                funds: _funds,
                events: _events,
                months: _months,
                averageMonthlyInvestment: _averageMonthlyInvestment,
                onSimulatePressed: _runSimulation,
              ),
              const SizedBox(height: 16),
              ResultsSection(
                isLoading: _isLoading,
                simulationResult: _simulationResult,
                resultsKey: _resultsKey,
                initialInvestment: _initialInvestment,
                averageMonthlyInvestment: _averageMonthlyInvestment,
                simulationYears: _simulationYears ?? 20,
              ),
            ],
          ),
        ),
      ),
    );
  }
}
