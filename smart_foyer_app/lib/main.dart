import 'dart:async';
import 'package:flutter/foundation.dart';
import 'package:flutter/material.dart';
import 'screens/home_screen.dart';

/// Global navigator so any background callback / async error can still
/// reach the user with a SnackBar even if the widget that triggered the
/// work is gone.
final GlobalKey<NavigatorState> appNavigatorKey = GlobalKey<NavigatorState>();
final GlobalKey<ScaffoldMessengerState> appMessengerKey =
    GlobalKey<ScaffoldMessengerState>();

void main() {
  // ─── Global crash net ────────────────────────────────────────────
  // Any uncaught Flutter / async error is logged and surfaced as a snack
  // instead of taking down the app or producing a red error widget.
  FlutterError.onError = (FlutterErrorDetails details) {
    FlutterError.presentError(details);
    _reportError(details.exceptionAsString());
  };

  PlatformDispatcher.instance.onError = (Object error, StackTrace stack) {
    debugPrint('Uncaught async error: $error\n$stack');
    _reportError(error.toString());
    return true; // swallow so the engine doesn't kill the isolate
  };

  // In release builds, replace the red error widget with a friendly card
  // so a render error in one screen doesn't make the whole app unusable.
  ErrorWidget.builder = (FlutterErrorDetails details) {
    return _FriendlyErrorWidget(message: details.exceptionAsString());
  };

  runZonedGuarded(
    () => runApp(const SmartFoyerApp()),
    (error, stack) {
      debugPrint('Zone error: $error\n$stack');
      _reportError(error.toString());
    },
  );
}

void _reportError(String message) {
  final messenger = appMessengerKey.currentState;
  if (messenger == null) return;
  messenger.hideCurrentSnackBar();
  messenger.showSnackBar(
    SnackBar(
      content: Text(
        message.length > 240 ? '${message.substring(0, 240)}…' : message,
      ),
      backgroundColor: Colors.red.shade700,
      behavior: SnackBarBehavior.floating,
      duration: const Duration(seconds: 6),
    ),
  );
}

class SmartFoyerApp extends StatelessWidget {
  const SmartFoyerApp({super.key});

  @override
  Widget build(BuildContext context) {
    return MaterialApp(
      title: 'SmartFoyer',
      debugShowCheckedModeBanner: false,
      navigatorKey: appNavigatorKey,
      scaffoldMessengerKey: appMessengerKey,
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

/// Friendly replacement for the default red error widget. Shown when a
/// screen-level render error occurs (e.g. unexpected null in a builder).
/// Tapping "Retour" pops back to a working screen.
class _FriendlyErrorWidget extends StatelessWidget {
  final String message;
  const _FriendlyErrorWidget({required this.message});

  @override
  Widget build(BuildContext context) {
    return Material(
      color: const Color(0xFFFFF4F4),
      child: SafeArea(
        child: Padding(
          padding: const EdgeInsets.all(24),
          child: Column(
            mainAxisAlignment: MainAxisAlignment.center,
            children: [
              const Icon(Icons.error_outline, color: Colors.red, size: 64),
              const SizedBox(height: 16),
              const Text(
                'Cette page a rencontré un problème',
                style: TextStyle(
                    fontSize: 18, fontWeight: FontWeight.w700),
              ),
              const SizedBox(height: 8),
              Text(
                message.length > 400
                    ? '${message.substring(0, 400)}…'
                    : message,
                textAlign: TextAlign.center,
                style: const TextStyle(
                    fontSize: 12, color: Color(0xFF5C6470)),
              ),
              const SizedBox(height: 24),
              FilledButton(
                onPressed: () {
                  final nav = appNavigatorKey.currentState;
                  if (nav != null && nav.canPop()) {
                    nav.pop();
                  }
                },
                child: const Text('Retour'),
              ),
            ],
          ),
        ),
      ),
    );
  }
}
