import 'package:flutter/material.dart';
import '../api/api_client.dart';
import '../api/auth_service.dart';

/// Écran de connexion / création de compte.
///
/// Deux chemins : email + mot de passe (toujours dispo) et « Continuer avec
/// Google » (affiché seulement si le client ID Google est fourni au build).
/// En cas de succès, AuthService notifie l'AuthGate qui bascule sur l'app.
class LoginScreen extends StatefulWidget {
  const LoginScreen({super.key});

  @override
  State<LoginScreen> createState() => _LoginScreenState();
}

class _LoginScreenState extends State<LoginScreen> {
  final _formKey = GlobalKey<FormState>();
  final _email = TextEditingController();
  final _password = TextEditingController();
  final _name = TextEditingController();

  bool _isRegister = false;
  bool _loading = false;

  @override
  void dispose() {
    _email.dispose();
    _password.dispose();
    _name.dispose();
    super.dispose();
  }

  void _snack(String message, {bool error = true}) {
    if (!mounted) return;
    ScaffoldMessenger.of(context).showSnackBar(SnackBar(
      content: Text(message),
      backgroundColor: error ? Colors.red.shade700 : Colors.green.shade700,
      behavior: SnackBarBehavior.floating,
    ));
  }

  Future<void> _submitEmail() async {
    if (!_formKey.currentState!.validate()) return;
    setState(() => _loading = true);
    try {
      final auth = AuthService.instance;
      if (_isRegister) {
        await auth.register(
            _email.text.trim(), _password.text, _name.text.trim());
      } else {
        await auth.login(_email.text.trim(), _password.text);
      }
      // L'AuthGate prend le relais automatiquement.
    } on ApiException catch (e) {
      _snack(e.message);
    } catch (e) {
      _snack('Erreur : $e');
    } finally {
      if (mounted) setState(() => _loading = false);
    }
  }

  Future<void> _google() async {
    setState(() => _loading = true);
    try {
      await AuthService.instance.signInWithGoogle();
    } on ApiException catch (e) {
      _snack(e.message);
    } catch (e) {
      _snack('Connexion Google impossible : $e');
    } finally {
      if (mounted) setState(() => _loading = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    final googleEnabled = AuthService.instance.googleEnabled;
    return Scaffold(
      body: SafeArea(
        child: Center(
          child: SingleChildScrollView(
            child: ConstrainedBox(
              constraints: const BoxConstraints(maxWidth: 420),
              child: Padding(
                padding: const EdgeInsets.symmetric(horizontal: 24, vertical: 32),
                child: Form(
                  key: _formKey,
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.stretch,
                    children: [
                      const Icon(Icons.receipt_long_rounded,
                          size: 72, color: Color(0xFF1B8A6B)),
                      const SizedBox(height: 16),
                      const Text('SmartFoyer',
                          textAlign: TextAlign.center,
                          style: TextStyle(fontSize: 28, fontWeight: FontWeight.w800)),
                      const SizedBox(height: 4),
                      Text(
                        _isRegister
                            ? 'Crée ton compte pour suivre tes courses'
                            : 'Connecte-toi pour retrouver tes tickets',
                        textAlign: TextAlign.center,
                        style: const TextStyle(fontSize: 14, color: Color(0xFF5C6470)),
                      ),
                      const SizedBox(height: 28),

                      if (_isRegister) ...[
                        TextFormField(
                          controller: _name,
                          textInputAction: TextInputAction.next,
                          decoration: const InputDecoration(
                            labelText: 'Nom (optionnel)',
                            prefixIcon: Icon(Icons.person_outline),
                            border: OutlineInputBorder(),
                          ),
                        ),
                        const SizedBox(height: 12),
                      ],

                      TextFormField(
                        controller: _email,
                        keyboardType: TextInputType.emailAddress,
                        textInputAction: TextInputAction.next,
                        decoration: const InputDecoration(
                          labelText: 'Email',
                          prefixIcon: Icon(Icons.mail_outline),
                          border: OutlineInputBorder(),
                        ),
                        validator: (v) {
                          final t = (v ?? '').trim();
                          if (t.isEmpty || !t.contains('@')) {
                            return 'Email invalide';
                          }
                          return null;
                        },
                      ),
                      const SizedBox(height: 12),
                      TextFormField(
                        controller: _password,
                        obscureText: true,
                        textInputAction: TextInputAction.done,
                        onFieldSubmitted: (_) => _loading ? null : _submitEmail(),
                        decoration: const InputDecoration(
                          labelText: 'Mot de passe',
                          prefixIcon: Icon(Icons.lock_outline),
                          border: OutlineInputBorder(),
                        ),
                        validator: (v) {
                          if ((v ?? '').length < 6) {
                            return '6 caractères minimum';
                          }
                          return null;
                        },
                      ),
                      const SizedBox(height: 20),

                      FilledButton(
                        onPressed: _loading ? null : _submitEmail,
                        style: FilledButton.styleFrom(
                          minimumSize: const Size(double.infinity, 52),
                        ),
                        child: _loading
                            ? const SizedBox(
                                height: 22, width: 22,
                                child: CircularProgressIndicator(strokeWidth: 2, color: Colors.white))
                            : Text(_isRegister ? 'Créer mon compte' : 'Se connecter'),
                      ),
                      const SizedBox(height: 12),
                      TextButton(
                        onPressed: _loading
                            ? null
                            : () => setState(() => _isRegister = !_isRegister),
                        child: Text(_isRegister
                            ? 'J\'ai déjà un compte — Se connecter'
                            : 'Pas de compte ? Créer un compte'),
                      ),

                      if (googleEnabled) ...[
                        const SizedBox(height: 8),
                        Row(children: const [
                          Expanded(child: Divider()),
                          Padding(
                            padding: EdgeInsets.symmetric(horizontal: 8),
                            child: Text('ou', style: TextStyle(color: Color(0xFF5C6470))),
                          ),
                          Expanded(child: Divider()),
                        ]),
                        const SizedBox(height: 8),
                        OutlinedButton.icon(
                          onPressed: _loading ? null : _google,
                          icon: const Icon(Icons.account_circle, color: Color(0xFF4285F4)),
                          label: const Text('Continuer avec Google'),
                          style: OutlinedButton.styleFrom(
                            minimumSize: const Size(double.infinity, 52),
                          ),
                        ),
                      ],
                    ],
                  ),
                ),
              ),
            ),
          ),
        ),
      ),
    );
  }
}
