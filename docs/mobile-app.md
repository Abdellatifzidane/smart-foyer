# SmartFoyer — Documentation de l'app mobile (iOS)

Ce document décrit le passage de l'app **Flutter Web** à une **vraie app mobile iOS**, ce qui a été modifié, comment la lancer (sur simulateur ou iPhone réel), et comment la version web continue à fonctionner en parallèle sans bricolage.

---

## 1. Vue d'ensemble

L'app SmartFoyer existait déjà en version **Flutter Web** (testable dans le navigateur). On y a ajouté la **cible iOS** sans casser le web : la même base de code Dart compile maintenant pour les deux plateformes.

```
                ┌─────────────────────────────────┐
                │      Code Dart partagé           │
                │  (lib/main.dart + screens/ + api/)│
                └────────┬───────────────────┬────┘
                         │                   │
              compilé pour                compilé pour
                         │                   │
                ┌────────▼─────────┐ ┌──────▼──────────┐
                │  iOS (simulateur │ │  Web (navigateur│
                │    ou iPhone)    │ │   Safari/Chrome)│
                └──────────────────┘ └─────────────────┘
```

**Aucune duplication de code** : un seul ensemble de fichiers Dart, qui choisit le bon comportement à l'exécution selon la plateforme.

---

## 2. Plateformes supportées

| Cible | Statut | Comment lancer |
|---|---|---|
| **iOS Simulator** | ✅ Fonctionnel | `flutter run -d <id-simulateur>` |
| **iPhone physique** | ✅ Code prêt, nécessite un Apple ID + signature | `flutter run -d <id-iphone> --dart-define=BACKEND_URL=http://<ip-mac>:8000` |
| **Flutter Web (Safari, Firefox, etc.)** | ✅ Fonctionne toujours | `flutter run -d web-server --web-hostname=127.0.0.1 --web-port=5173` |
| **Android** | ❌ Pas encore activé | Voir section "Pour aller plus loin" |

---

## 3. Ce qui a été fait techniquement

### 3.1 Ajout de la plateforme iOS

Le projet Flutter avait été créé avec `--platforms=web` uniquement. On a ajouté iOS :

```bash
cd smart_foyer_app
flutter create --platforms=ios .
```

Cela crée le dossier [`ios/`](../smart_foyer_app/ios/) avec tout le projet Xcode généré (`Runner.xcodeproj`, `Runner/`, `Podfile`, …).

### 3.2 Nouveau package : `image_picker`

Pour avoir un vrai accès **caméra + galerie native** sur mobile, on a ajouté le package officiel Flutter `image_picker`.

Pourquoi pas garder `file_picker` ? Il fonctionne, mais sur mobile il ouvre uniquement le navigateur de fichiers — pas la caméra. Avec `image_picker` on a **caméra + galerie** comme dans les vraies apps iOS.

| Plateforme | Sélecteur utilisé | Pourquoi |
|---|---|---|
| iOS / Android | `image_picker` (camera + gallery) | Accès natif à la caméra |
| Web | `file_picker` (fallback) | Sur web, image_picker n'ouvre qu'un simple `<input type=file>` ; file_picker est plus stable |

### 3.3 Adaptation du code de scan

Dans [`scan_screen.dart`](../smart_foyer_app/lib/screens/scan_screen.dart), on détecte la plateforme à l'exécution avec `kIsWeb` :

```dart
if (kIsWeb) {
  // Web → file_picker
  final result = await FilePicker.platform.pickFiles(...);
} else {
  // Mobile → image_picker (camera ou galerie)
  final picked = await _picker.pickImage(source: ImageSource.camera, ...);
}
```

L'**UI s'adapte aussi** :
- Sur mobile : 2 boutons côte à côte **Photo** / **Galerie** + bottom sheet natif au clic sur la zone d'image
- Sur web : 1 seul bouton **Choisir une image**

### 3.4 Permissions iOS (Info.plist)

iOS demande des descriptions explicites des permissions avant d'autoriser l'accès caméra/photos. Ajout dans [`ios/Runner/Info.plist`](../smart_foyer_app/ios/Runner/Info.plist) :

```xml
<key>NSCameraUsageDescription</key>
<string>SmartFoyer a besoin de la caméra pour scanner vos tickets de caisse.</string>

<key>NSPhotoLibraryUsageDescription</key>
<string>SmartFoyer a besoin d'accéder à vos photos pour analyser un ticket de caisse existant.</string>

<key>NSPhotoLibraryAddUsageDescription</key>
<string>SmartFoyer peut enregistrer la photo de votre ticket dans votre galerie.</string>
```

Et aussi (temporairement, pour le dev en local) :

```xml
<key>NSAppTransportSecurity</key>
<dict>
    <key>NSAllowsArbitraryLoads</key>
    <true/>
</dict>
```

⚠️ `NSAllowsArbitraryLoads` autorise les appels HTTP non-HTTPS — nécessaire en dev pour atteindre le backend local en `http://127.0.0.1:8000`. **À enlever quand le backend sera déployé en HTTPS.**

### 3.5 URL backend configurable

Sur le simulateur iOS, `127.0.0.1` fonctionne (partage du réseau du Mac). Mais sur un **iPhone physique**, il faut l'IP locale du Mac. Solution : URL injectable au build via `--dart-define`.

Dans [`lib/api/api_client.dart`](../smart_foyer_app/lib/api/api_client.dart) :

```dart
static const String baseUrl = String.fromEnvironment(
  'BACKEND_URL',
  defaultValue: 'http://127.0.0.1:8000',
);
```

| Contexte | Commande |
|---|---|
| Web ou simulateur iOS | `flutter run -d ...` (défaut localhost) |
| iPhone physique | `flutter run -d <id> --dart-define=BACKEND_URL=http://192.168.1.42:8000` |
| Prod (futur) | `flutter build ios --dart-define=BACKEND_URL=https://api.smartfoyer.fr` |

---

## 4. Fichiers concernés

### Modifiés

| Fichier | Changement |
|---|---|
| [`smart_foyer_app/pubspec.yaml`](../smart_foyer_app/pubspec.yaml) | Ajout `image_picker: ^1.1.2` |
| [`smart_foyer_app/lib/api/api_client.dart`](../smart_foyer_app/lib/api/api_client.dart) | `baseUrl` configurable via `--dart-define=BACKEND_URL=...` |
| [`smart_foyer_app/lib/screens/scan_screen.dart`](../smart_foyer_app/lib/screens/scan_screen.dart) | Réécrit : caméra + galerie sur mobile, file_picker sur web |
| [`smart_foyer_app/ios/Runner/Info.plist`](../smart_foyer_app/ios/Runner/Info.plist) | Permissions caméra/photos + ATS dev |

### Ajoutés

Tout le dossier [`smart_foyer_app/ios/`](../smart_foyer_app/ios/) — projet Xcode généré par `flutter create --platforms=ios`. Notamment :
- `Runner.xcodeproj/` — le projet Xcode
- `Runner/AppDelegate.swift` — point d'entrée natif
- `Runner/Info.plist` — config + permissions
- `Podfile` — généré au premier `flutter run`

### Inchangés (fonctionnent sur web ET iOS)

- `lib/main.dart`
- `lib/api/models.dart`
- `lib/screens/home_screen.dart`
- `lib/screens/history_screen.dart`
- `lib/screens/chat_screen.dart`
- `lib/screens/results_screen.dart`

---

## 5. Comment lancer l'app

### 5.1 Préparation commune (à faire une seule fois)

**Backend Python**
```bash
cd /Users/issomeli/smart-foyer
source .venv/bin/activate
uvicorn backend.main:app --host 127.0.0.1 --port 8000
```
Laisse ce terminal ouvert.

**Ollama**
```bash
ollama serve
```
Laisse ce terminal ouvert.

### 5.2 Lancer sur iOS Simulator

```bash
cd /Users/issomeli/smart-foyer/smart_foyer_app

# Démarre le simulateur (apparait dans une fenêtre Mac)
open -a Simulator

# Lance l'app
flutter run -d "iPhone 17 Test"
```

Si tu as plusieurs simulateurs disponibles, liste-les avec :
```bash
flutter devices
```
et utilise l'identifiant exact :
```bash
flutter run -d <id-du-simulateur>
```

**Premier lancement** : `flutter run` exécute `pod install` (~10 s) puis `Xcode build` (~90 s la première fois, instantané ensuite). Le hot reload (touche `r`) marche après le premier build.

### 5.3 Lancer sur iPhone physique (via USB)

**Prérequis :**
- Câble USB
- Un Apple ID (gratuit) configuré dans Xcode (`Xcode > Settings > Accounts > +`)
- "Trust this computer" sur l'iPhone à la première connexion
- "Developer Mode" activé sur l'iPhone (`Settings > Privacy & Security > Developer Mode`)

**Étape 1 — Trouver l'IP locale du Mac**
```bash
ipconfig getifaddr en0
# ex: 192.168.1.42
```

**Étape 2 — Relancer le backend en écoutant sur le réseau** (pas seulement localhost) :
```bash
uvicorn backend.main:app --host 0.0.0.0 --port 8000
```

**Étape 3 — Identifier l'iPhone**
```bash
flutter devices
# cherche la ligne avec "ios" qui n'est PAS "simulator"
```

**Étape 4 — Lancer l'app avec l'IP du Mac comme backend**
```bash
cd /Users/issomeli/smart-foyer/smart_foyer_app
flutter run -d <id-iphone> --dart-define=BACKEND_URL=http://192.168.1.42:8000
```

L'iPhone et le Mac doivent être sur le **même réseau Wi-Fi**.

### 5.4 Lancer la version Web (toujours disponible)

```bash
cd /Users/issomeli/smart-foyer/smart_foyer_app
flutter run -d web-server --web-hostname=127.0.0.1 --web-port=5173
```

Puis ouvrir `http://127.0.0.1:5173` dans Safari, Firefox, Chrome…

**La version web n'a pas été cassée par les changements iOS** :
- Le code détecte la plateforme via `kIsWeb` et utilise `file_picker` sur le web
- Les permissions iOS ne s'appliquent qu'au build iOS
- L'`Info.plist` ne s'applique qu'au build iOS

---

## 6. Différences UX entre Web et iOS

| Fonctionnalité | Web | iOS |
|---|---|---|
| Bouton de sélection d'image | "Choisir une image" → ouvre le file picker | 2 boutons "Photo" + "Galerie" OU bottom sheet natif |
| Accès caméra | Limité (juste le file picker du navigateur) | Caméra native, vraie expérience photo |
| Backend URL par défaut | `127.0.0.1:8000` | `127.0.0.1:8000` (override possible) |
| Performance | Idem | Légèrement meilleure (rendu Skia natif) |
| Permissions à demander | Aucune | Caméra + Photos au premier usage |

---

## 7. Prérequis par cible

### Pour iOS Simulator

| Outil | Comment installer |
|---|---|
| Xcode (~10 Go) | App Store |
| Configuration Xcode | `sudo xcode-select -s /Applications/Xcode.app/Contents/Developer` + `sudo xcodebuild -runFirstLaunch` + `sudo xcodebuild -license accept` |
| CocoaPods | `brew install cocoapods` |
| Runtime iOS Simulator (~8 Go) | `xcodebuild -downloadPlatform iOS` |
| Au moins un simulateur | `xcrun simctl create "iPhone 17 Test" com.apple.CoreSimulator.SimDeviceType.iPhone-17 com.apple.CoreSimulator.SimRuntime.iOS-26-5` |

Vérification : `flutter doctor` doit afficher ✓ sur Xcode.

### Pour iPhone physique

Tout ce qui précède + :
- Câble USB
- Apple ID dans Xcode Settings → Accounts
- Developer Mode activé sur l'iPhone

### Pour le Web

Aucun prérequis supplémentaire — Flutter Web tourne directement avec Flutter SDK.

---

## 8. Configuration en production (futur)

Quand le backend sera déployé sur GCP (HTTPS), il faudra :

**1. Supprimer `NSAllowsArbitraryLoads`** dans `Info.plist` (sécurité)

**2. Builder l'app avec l'URL de prod**
```bash
flutter build ios --release \
  --dart-define=BACKEND_URL=https://api.smartfoyer.fr
```

**3. Distribuer via TestFlight** (test) ou App Store (public).

---

## 9. Pour aller plus loin

### Ajouter Android

```bash
cd smart_foyer_app
flutter create --platforms=android .
```

Permissions à ajouter dans `android/app/src/main/AndroidManifest.xml` :
```xml
<uses-permission android:name="android.permission.CAMERA"/>
<uses-permission android:name="android.permission.INTERNET"/>
```

L'écran de scan fonctionnera **sans modification de code** : `image_picker` supporte déjà Android.

Pour tester : `Android Studio` installé + un émulateur Android, puis `flutter run -d <id-emulateur>`.

### Améliorations envisageables

- **Stocker une mini-image** du ticket scanné côté backend pour pouvoir la ré-afficher dans l'historique
- **Mode hors-ligne** : cache local des derniers tickets
- **Notifications push** quand un produit récurrent baisse ailleurs
- **Authentification Firebase** pour synchroniser les tickets entre Web et iOS pour un même utilisateur

---

## 10. Récapitulatif visuel

```
✅ Plateforme iOS activée
✅ Package image_picker installé
✅ Caméra + Galerie natives accessibles
✅ Permissions iOS configurées
✅ URL backend configurable (simulateur vs device physique)
✅ Version Web préservée (file_picker en fallback)
✅ Code 100% partagé entre Web et iOS
```

**État actuel** : l'app tourne sur **iOS Simulator** (iPhone 17 testé) ET sur **Flutter Web**, avec exactement les mêmes fonctionnalités (scan, historique, chat IA).
