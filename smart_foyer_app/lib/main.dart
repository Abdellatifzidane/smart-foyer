import 'package:flutter/material.dart';
import 'screens/home_screen.dart';

void main() {
  runApp(const SmartFoyerApp());
}

class SmartFoyerApp extends StatelessWidget {
  const SmartFoyerApp({super.key});

  @override
  Widget build(BuildContext context) {
    return MaterialApp(
      title: 'SmartFoyer',
      debugShowCheckedModeBanner: false,
      theme: ThemeData(
        useMaterial3: true,
        colorScheme: ColorScheme.fromSeed(
          seedColor: const Color(0xFF1B8A6B),
          brightness: Brightness.light,
        ),
        scaffoldBackgroundColor: const Color(0xFFF6F7F9),
        appBarTheme: const AppBarTheme(
          centerTitle: true,
          elevation: 0,
          backgroundColor: Colors.transparent,
          foregroundColor: Color(0xFF1B8A6B),
          titleTextStyle: TextStyle(
            color: Color(0xFF1B8A6B),
            fontSize: 20,
            fontWeight: FontWeight.w700,
          ),
        ),
      ),
      home: const HomeScreen(),
    );
  }
}
