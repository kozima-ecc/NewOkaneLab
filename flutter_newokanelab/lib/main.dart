

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
        primaryColor: kGreenColor,
        scaffoldBackgroundColor: kMainColor,
        cardColor: kCardColor,
        colorScheme: ColorScheme.fromSeed(
          seedColor: kGreenColor,
          brightness: Brightness.light,
          primary: kGreenColor,
          background: kMainColor,
          surface: kCardColor,
          onSurface: Colors.black,
        ),
        textTheme: const TextTheme(
          bodyMedium: TextStyle(color: Colors.black),
          headlineSmall: TextStyle(fontWeight: FontWeight.bold),
          titleLarge: TextStyle(fontWeight: FontWeight.bold, color: kGreenColor),
        ),
        inputDecorationTheme: InputDecorationTheme(
          border: OutlineInputBorder(
            borderRadius: BorderRadius.circular(8.0),
            borderSide: BorderSide(color: Colors.grey.shade400),
          ),
          focusedBorder: OutlineInputBorder(
            borderRadius: BorderRadius.circular(8.0),
            borderSide: const BorderSide(color: kGreenColor, width: 2),
          ),
          fillColor: kCardColor,
          filled: true,
        ),
        sliderTheme: SliderThemeData(
          activeTrackColor: kGreenColor,
          inactiveTrackColor: Colors.grey[300],
          thumbColor: kGreenColor,
          overlayColor: kGreenColor.withAlpha(100),
        ),
        elevatedButtonTheme: ElevatedButtonThemeData(
          style: ElevatedButton.styleFrom(
            backgroundColor: kGreenColor,
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
