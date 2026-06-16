import 'package:flutter/material.dart';
import '../api/api_client.dart';

/// Boutons 👍/👎 réutilisables pour évaluer un composant (OCR, matching, agent).
///
/// - 👍 envoie immédiatement un feedback positif.
/// - 👎 ouvre un petit champ de commentaire optionnel ("qu'est-ce qui n'allait
///   pas ?") puis envoie le feedback négatif.
///
/// Le widget gère son propre état (évité une fois noté) et ne casse jamais
/// l'UI : une erreur réseau affiche juste un SnackBar.
class FeedbackButtons extends StatefulWidget {
  /// 'ocr' | 'matching' | 'agent'.
  final String target;

  /// Libellé affiché à gauche des pouces (ex. "OCR correct ?").
  final String label;

  /// Références transmises au backend selon la cible.
  final String receiptId;
  final String question;
  final String answer;

  const FeedbackButtons({
    super.key,
    required this.target,
    required this.label,
    this.receiptId = '',
    this.question = '',
    this.answer = '',
  });

  @override
  State<FeedbackButtons> createState() => _FeedbackButtonsState();
}

class _FeedbackButtonsState extends State<FeedbackButtons> {
  String? _submitted; // 'up' | 'down' une fois noté
  bool _sending = false;

  void _snack(String msg) {
    if (!mounted) return;
    ScaffoldMessenger.of(context)
        .showSnackBar(SnackBar(content: Text(msg)));
  }

  Future<void> _send(String rating, {String comment = ''}) async {
    setState(() => _sending = true);
    try {
      await ApiClient.sendFeedback(
        target: widget.target,
        rating: rating,
        receiptId: widget.receiptId,
        question: widget.question,
        answer: widget.answer,
        comment: comment,
      );
      if (mounted) setState(() => _submitted = rating);
      _snack('Merci pour ton retour !');
    } on ApiException catch (e) {
      _snack(e.message);
    } catch (e) {
      _snack('Impossible d\'envoyer le feedback : $e');
    } finally {
      if (mounted) setState(() => _sending = false);
    }
  }

  Future<void> _onThumbDown() async {
    final controller = TextEditingController();
    final comment = await showDialog<String>(
      context: context,
      builder: (ctx) => AlertDialog(
        title: const Text('Qu\'est-ce qui n\'allait pas ?'),
        content: TextField(
          controller: controller,
          autofocus: true,
          maxLines: 3,
          decoration: const InputDecoration(
            hintText: 'Optionnel — décris le problème',
            border: OutlineInputBorder(),
          ),
        ),
        actions: [
          TextButton(
            onPressed: () => Navigator.pop(ctx, null),
            child: const Text('Annuler'),
          ),
          FilledButton(
            onPressed: () => Navigator.pop(ctx, controller.text.trim()),
            child: const Text('Envoyer'),
          ),
        ],
      ),
    );
    // null = dialog annulé ; chaîne (même vide) = envoi confirmé.
    if (comment != null) {
      await _send('down', comment: comment);
    }
  }

  @override
  Widget build(BuildContext context) {
    final done = _submitted != null;
    final upActive = _submitted == 'up';
    final downActive = _submitted == 'down';

    return Row(
      mainAxisSize: MainAxisSize.min,
      children: [
        Text(
          done ? 'Merci !' : widget.label,
          style: TextStyle(
            fontSize: 13,
            color: Theme.of(context).colorScheme.onSurfaceVariant,
          ),
        ),
        const SizedBox(width: 4),
        IconButton(
          tooltip: 'Bien',
          visualDensity: VisualDensity.compact,
          onPressed: (done || _sending) ? null : () => _send('up'),
          icon: Icon(
            upActive ? Icons.thumb_up : Icons.thumb_up_outlined,
            size: 20,
            color: upActive ? Colors.green : null,
          ),
        ),
        IconButton(
          tooltip: 'Pas bien',
          visualDensity: VisualDensity.compact,
          onPressed: (done || _sending) ? null : _onThumbDown,
          icon: Icon(
            downActive ? Icons.thumb_down : Icons.thumb_down_outlined,
            size: 20,
            color: downActive ? Colors.redAccent : null,
          ),
        ),
      ],
    );
  }
}
