import 'package:flutter/material.dart';
import 'core/constants.dart';
import 'screens/home_screen.dart'; // Import the new home screen

/// アプリケーションのエントリーポイント（開始点）
void main() {
  // InvestmentSimulatorApp ウィジェットをアプリケーションのルートとして実行
  runApp(const InvestmentSimulatorApp());
}

/// アプリケーション全体のテーマと基本的な設定を定義するルートウィジェット
class InvestmentSimulatorApp extends StatelessWidget {
  // constコンストラクタ
  const InvestmentSimulatorApp({super.key});

  @override
  Widget build(BuildContext context) {
    // MaterialAppウィジェットは、アプリケーションの基本的な構造やナビゲーションを提供
    return MaterialApp(
      // アプリケーションのタイトル
      title: '投資シミュレーター',
      // アプリケーション全体のテーマ設定
      theme: ThemeData(
        brightness: Brightness.light,
        primaryColor: Colors.green,
        scaffoldBackgroundColor: Colors.green,
        cardColor: Colors.green,
        colorScheme: ColorScheme.fromSeed(
          seedColor: Colors.green,
          brightness: Brightness.light,
          primary: Colors.green,
          background: Colors.green,
          surface: Colors.green,
          onSurface: Colors.black,
        ),
        textTheme: const TextTheme(
          bodyMedium: TextStyle(color: Colors.black),
          headlineSmall: TextStyle(fontWeight: FontWeight.bold),
          titleLarge: TextStyle(fontWeight: FontWeight.bold, color: Colors.green),
        ),
        inputDecorationTheme: InputDecorationTheme(
          border: OutlineInputBorder(
            borderRadius: BorderRadius.circular(8.0),
            borderSide: BorderSide(color: Colors.grey.shade400),
          ),
          focusedBorder: OutlineInputBorder(
            borderRadius: BorderRadius.circular(8.0),
            borderSide: const BorderSide(color: Colors.green, width: 2),
          ),
          fillColor: Colors.green,
          filled: true,
        ),
        sliderTheme: SliderThemeData(
          activeTrackColor: Colors.green,
          inactiveTrackColor: Colors.grey[300],
          thumbColor: Colors.green,
          overlayColor: Colors.green.withAlpha(100),
        ),
        elevatedButtonTheme: ElevatedButtonThemeData(
          style: ElevatedButton.styleFrom(
            backgroundColor: Colors.green,
            foregroundColor: Colors.white,
            padding: const EdgeInsets.symmetric(vertical: 16),
            shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(8)),
            textStyle: const TextStyle(fontSize: 16, fontWeight: FontWeight.bold),
          ),
        ),
      ),
      // アプリケーションのホームページ
      home: const HomePage(),
    );
  }
}
