import 'package:flutter/material.dart';
import '../api/api_client.dart';
import 'admin_screen.dart';
import 'analytics_screen.dart';
import 'chat_screen.dart';
import 'history_screen.dart';
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
    setState(() {
      _backendStatus = 'Vérification du backend...';
    });
    try {
      final stats = await ApiClient.catalogStats();
      final total = stats['total'] ?? 0;
      if (!mounted) return;
      setState(() {
        _backendOk = true;
        _backendStatus = 'Backend OK · $total produits indexés';
      });
    } catch (e) {
      if (!mounted) return;
      setState(() {
        _backendOk = false;
        _backendStatus = 'Backend injoignable — tape pour réessayer';
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
                  const SizedBox(height: 12),
                  OutlinedButton.icon(
                    onPressed: _backendOk
                        ? () => Navigator.of(context).push(
                              MaterialPageRoute(
                                builder: (_) => const HistoryScreen(),
                              ),
                            )
                        : null,
                    icon: const Icon(Icons.history_rounded),
                    label: const Padding(
                      padding: EdgeInsets.symmetric(
                          vertical: 12, horizontal: 8),
                      child: Text('Mes tickets',
                          style: TextStyle(fontSize: 15)),
                    ),
                    style: OutlinedButton.styleFrom(
                      minimumSize: const Size(double.infinity, 52),
                      shape: RoundedRectangleBorder(
                        borderRadius: BorderRadius.circular(16),
                      ),
                    ),
                  ),
                  const SizedBox(height: 12),
                  OutlinedButton.icon(
                    onPressed: _backendOk
                        ? () => Navigator.of(context).push(
                              MaterialPageRoute(
                                builder: (_) => const AnalyticsScreen(),
                              ),
                            )
                        : null,
                    icon: const Icon(Icons.insights_rounded),
                    label: const Padding(
                      padding: EdgeInsets.symmetric(
                          vertical: 12, horizontal: 8),
                      child: Text('Analytics',
                          style: TextStyle(fontSize: 15)),
                    ),
                    style: OutlinedButton.styleFrom(
                      minimumSize: const Size(double.infinity, 52),
                      shape: RoundedRectangleBorder(
                        borderRadius: BorderRadius.circular(16),
                      ),
                    ),
                  ),
                  const SizedBox(height: 12),
                  OutlinedButton.icon(
                    onPressed: _backendOk
                        ? () => Navigator.of(context).push(
                              MaterialPageRoute(
                                builder: (_) => const ChatScreen(),
                              ),
                            )
                        : null,
                    icon: const Icon(Icons.auto_awesome_rounded),
                    label: const Padding(
                      padding: EdgeInsets.symmetric(
                          vertical: 12, horizontal: 8),
                      child: Text('Conseiller IA',
                          style: TextStyle(fontSize: 15)),
                    ),
                    style: OutlinedButton.styleFrom(
                      minimumSize: const Size(double.infinity, 52),
                      shape: RoundedRectangleBorder(
                        borderRadius: BorderRadius.circular(16),
                      ),
                    ),
                  ),
                  const SizedBox(height: 12),
                  OutlinedButton.icon(
                    onPressed: _backendOk
                        ? () => Navigator.of(context).push(
                              MaterialPageRoute(
                                builder: (_) => const AdminScreen(),
                              ),
                            )
                        : null,
                    icon: const Icon(Icons.admin_panel_settings_rounded),
                    label: const Padding(
                      padding: EdgeInsets.symmetric(
                          vertical: 12, horizontal: 8),
                      child: Text('Administration',
                          style: TextStyle(fontSize: 15)),
                    ),
                    style: OutlinedButton.styleFrom(
                      minimumSize: const Size(double.infinity, 52),
                      shape: RoundedRectangleBorder(
                        borderRadius: BorderRadius.circular(16),
                      ),
                    ),
                  ),
                  const SizedBox(height: 24),
                  InkWell(
                    onTap: _backendOk ? null : _checkBackend,
                    borderRadius: BorderRadius.circular(8),
                    child: Padding(
                      padding: const EdgeInsets.symmetric(
                          horizontal: 8, vertical: 6),
                      child: Row(
                        mainAxisAlignment: MainAxisAlignment.center,
                        children: [
                          Icon(
                            _backendOk
                                ? Icons.check_circle_rounded
                                : Icons.error_rounded,
                            size: 16,
                            color: _backendOk
                                ? Colors.green
                                : Colors.redAccent,
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
                          if (!_backendOk) ...[
                            const SizedBox(width: 4),
                            const Icon(Icons.refresh_rounded,
                                size: 14, color: Colors.redAccent),
                          ],
                        ],
                      ),
                    ),
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
