import 'dart:convert';
import 'package:flutter/foundation.dart';
import 'package:google_sign_in/google_sign_in.dart';
import 'package:http/http.dart' as http;
import 'package:shared_preferences/shared_preferences.dart';

import 'api_client.dart';

/// Service d'authentification : conserve le JWT applicatif (émis par le
/// backend) et l'identité de l'utilisateur connecté.
///
/// Toutes les requêtes d'`ApiClient` lisent le token via [token] et l'envoient
/// dans l'en-tête `Authorization: Bearer ...`. L'état (`isLoggedIn`) est exposé
/// par un [ValueNotifier] auquel l'`AuthGate` se réabonne pour afficher soit
/// l'écran de connexion, soit l'application.
class AuthService {
  AuthService._();
  static final AuthService instance = AuthService._();

  static const _kToken = 'sf_token';
  static const _kUser = 'sf_user';

  /// Client ID Google (Web). Fourni au build via --dart-define, sinon vide
  /// (le bouton Google est alors masqué et seul email/mot de passe reste).
  static const String googleClientId = String.fromEnvironment(
    'GOOGLE_CLIENT_ID',
    defaultValue: '',
  );

  String? _token;
  Map<String, dynamic>? _user;

  /// Notifie l'UI à chaque changement d'état de connexion.
  final ValueNotifier<bool> authState = ValueNotifier<bool>(false);

  String? get token => _token;
  Map<String, dynamic>? get user => _user;
  bool get isLoggedIn => _token != null && _token!.isNotEmpty;
  bool get googleEnabled => googleClientId.isNotEmpty;

  /// Restaure une session depuis le stockage local au démarrage.
  Future<void> bootstrap() async {
    final prefs = await SharedPreferences.getInstance();
    _token = prefs.getString(_kToken);
    final raw = prefs.getString(_kUser);
    if (raw != null) {
      try {
        _user = (jsonDecode(raw) as Map).cast<String, dynamic>();
      } catch (_) {
        _user = null;
      }
    }
    authState.value = isLoggedIn;
  }

  Future<void> _persist(String token, Map<String, dynamic> user) async {
    _token = token;
    _user = user;
    final prefs = await SharedPreferences.getInstance();
    await prefs.setString(_kToken, token);
    await prefs.setString(_kUser, jsonEncode(user));
    authState.value = true;
  }

  /// Efface la session (déconnexion). Appelée aussi sur 401.
  Future<void> logout() async {
    _token = null;
    _user = null;
    final prefs = await SharedPreferences.getInstance();
    await prefs.remove(_kToken);
    await prefs.remove(_kUser);
    try {
      await GoogleSignIn().signOut();
    } catch (_) {}
    authState.value = false;
  }

  // ─── Email / mot de passe ────────────────────────────────────────
  Future<void> register(String email, String password, String name) async {
    final data = await _postAuth('/auth/register', {
      'email': email,
      'password': password,
      'name': name,
    });
    await _persist(data['access_token'], _userOf(data));
  }

  Future<void> login(String email, String password) async {
    final data = await _postAuth('/auth/login', {
      'email': email,
      'password': password,
    });
    await _persist(data['access_token'], _userOf(data));
  }

  // ─── Google Sign-In ──────────────────────────────────────────────
  Future<void> signInWithGoogle() async {
    if (!googleEnabled) {
      throw const ApiException('Connexion Google non configurée (client ID manquant).');
    }
    final google = GoogleSignIn(
      clientId: googleClientId,
      scopes: const ['email', 'profile'],
    );
    final account = await google.signIn();
    if (account == null) {
      throw const ApiException('Connexion Google annulée.');
    }
    final gauth = await account.authentication;
    final idToken = gauth.idToken;
    final accessToken = gauth.accessToken;
    // Sur le web, signIn() renvoie un access token (pas d'ID token) ; sur mobile
    // c'est l'inverse. On envoie ce qu'on a, le backend gère les deux.
    if ((idToken == null || idToken.isEmpty) &&
        (accessToken == null || accessToken.isEmpty)) {
      throw const ApiException('Google n\'a renvoyé aucun jeton.');
    }
    final data = await _postAuth('/auth/google', {
      if (idToken != null && idToken.isNotEmpty) 'id_token': idToken,
      if (accessToken != null && accessToken.isNotEmpty) 'access_token': accessToken,
    });
    await _persist(data['access_token'], _userOf(data));
  }

  Map<String, dynamic> _userOf(Map<String, dynamic> data) =>
      (data['user'] as Map?)?.cast<String, dynamic>() ?? const {};

  /// POST vers une route d'auth, sans token (on n'en a pas encore).
  Future<Map<String, dynamic>> _postAuth(
      String path, Map<String, dynamic> body) async {
    http.Response resp;
    try {
      resp = await http
          .post(
            Uri.parse('${ApiClient.baseUrl}$path'),
            headers: {'Content-Type': 'application/json'},
            body: jsonEncode(body),
          )
          .timeout(const Duration(seconds: 20));
    } catch (e) {
      throw ApiException('Backend injoignable : $e', isNetwork: true, path: path);
    }
    if (resp.statusCode < 200 || resp.statusCode >= 300) {
      String message = 'Erreur ${resp.statusCode}';
      try {
        final b = jsonDecode(resp.body);
        if (b is Map) {
          message = (b['detail'] ?? b['message'] ?? b['error'] ?? message).toString();
        }
      } catch (_) {}
      throw ApiException(message, statusCode: resp.statusCode, path: path);
    }
    return (jsonDecode(resp.body) as Map).cast<String, dynamic>();
  }
}
