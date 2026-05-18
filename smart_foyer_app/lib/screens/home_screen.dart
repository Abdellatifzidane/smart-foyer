import 'package:flutter/material.dart';
import '../api/api_client.dart';
import 'scan_screen.dart';

class HomeScreen extends StatefulWidget {
  const HomeScreen({super.key});

  @override
  State<HomeScreen> createState() => _HomeScreenState();
}

class _HomeScreenState extends State<HomeScreen> {
  String _backendStatus = 'Vérification du backend...';
  bool _backendOk = false;

  @override
  void initState() {
    super.initState();
    _checkBackend();
  }

  Future<void> _checkBackend() async {
    try {
      final stats = await ApiClient.catalogStats();
      final total = stats['total'] ?? 0;
      setState(() {
        _backendOk = true;
        _backendStatus = 'Backend OK · $total produits indexés';
      });
    } catch (_) {
      setState(() {
        _backendOk = false;
        _backendStatus = 'Backend injoignable (http://127.0.0.1:8000)';
      });
    }
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(title: const Text('SmartFoyer')),
      body: SafeArea(
        child: Center(
          child: ConstrainedBox(
            constraints: const BoxConstraints(maxWidth: 480),
            child: Padding(
              padding: const EdgeInsets.symmetric(horizontal: 24),
              child: Column(
                mainAxisAlignment: MainAxisAlignment.center,
                children: [
                  const Icon(Icons.receipt_long_rounded,
                      size: 96, color: Color(0xFF1B8A6B)),
                  const SizedBox(height: 24),
                  const Text(
                    'Scanne ton ticket',
                    style: TextStyle(
                        fontSize: 28, fontWeight: FontWeight.w800),
                    textAlign: TextAlign.center,
                  ),
                  const SizedBox(height: 8),
                  const Text(
                    'Comparez les prix entre enseignes et économisez sur vos courses.',
                    style:
                        TextStyle(fontSize: 15, color: Color(0xFF5C6470)),
                    textAlign: TextAlign.center,
                  ),
                  const SizedBox(height: 32),
                  FilledButton.icon(
                    onPressed: _backendOk
                        ? () => Navigator.of(context).push(
                              MaterialPageRoute(
                                builder: (_) => const ScanScreen(),
                              ),
                            )
                        : null,
                    icon: const Icon(Icons.camera_alt_rounded),
                    label: const Padding(
                      padding: EdgeInsets.symmetric(
                          vertical: 14, horizontal: 8),
                      child: Text('Scanner un ticket',
                          style: TextStyle(fontSize: 16)),
                    ),
                    style: FilledButton.styleFrom(
                      minimumSize: const Size(double.infinity, 56),
                      shape: RoundedRectangleBorder(
                        borderRadius: BorderRadius.circular(16),
                      ),
                    ),
                  ),
                  const SizedBox(height: 24),
                  Row(
                    mainAxisAlignment: MainAxisAlignment.center,
                    children: [
                      Icon(
                        _backendOk
                            ? Icons.check_circle_rounded
                            : Icons.error_rounded,
                        size: 16,
                        color:
                            _backendOk ? Colors.green : Colors.redAccent,
                      ),
                      const SizedBox(width: 6),
                      Flexible(
                        child: Text(
                          _backendStatus,
                          style: const TextStyle(
                              fontSize: 12, color: Color(0xFF5C6470)),
                          textAlign: TextAlign.center,
                        ),
                      ),
                    ],
                  ),
                ],
              ),
            ),
          ),
        ),
      ),
    );
  }
}
