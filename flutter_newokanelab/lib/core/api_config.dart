import 'dart:io';
import 'package:flutter/foundation.dart';

class ApiConfig {
  // Androidエミュレータからは '10.0.2.2'、iOSシミュレータやWebからは 'localhost' または '127.0.0.1'
  // 実機の場合はPCのローカルIPアドレスを指定する必要があります
  static String get baseUrl {
    if (kReleaseMode) {
      // 本番環境のURL（今回は未使用）
      return 'http://your-production-server.com';
    }
    
    // Androidエミュレータの場合
    if (!kIsWeb && Platform.isAndroid) {
      return 'http://10.0.2.2:8080'; 
    }
    
    // iOSシミュレータ、Web、デスクトップの場合
    return 'http://127.0.0.1:8080';
  }
  
  // エンドポイント
  static String get healthEndpoint => '$baseUrl/api/health';
  static String get companiesEndpoint => '$baseUrl/api/companies';
  static String get simulateEndpoint => '$baseUrl/api/simulate';
}