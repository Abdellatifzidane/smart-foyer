import 'package:flutter/material.dart';
import '../api/api_client.dart';
import '../widgets/feedback_buttons.dart';

class ChatScreen extends StatefulWidget {
  const ChatScreen({super.key});

  @override
  State<ChatScreen> createState() => _ChatScreenState();
}

class _ChatMessage {
  final String role; // 'user' or 'assistant'
  final String content;
  _ChatMessage(this.role, this.content);
}

class _ChatScreenState extends State<ChatScreen> {
  final TextEditingController _controller = TextEditingController();
  final ScrollController _scroll = ScrollController();
  final List<_ChatMessage> _messages = [];
  bool _loading = false;

  static const List<String> _suggestions = [
    'Combien j\'ai dépensé ce mois-ci ?',
    'Quelle est mon enseigne la plus chère ?',
    'Quel ticket coûte le plus cher ?',
    'Où je dépense le plus ?',
    'Combien j\'aurais pu économiser ?',
  ];

  @override
  void dispose() {
    _controller.dispose();
    _scroll.dispose();
    super.dispose();
  }

  Future<void> _send(String text) async {
    final question = text.trim();
    if (question.isEmpty || _loading) return;

    setState(() {
      _messages.add(_ChatMessage('user', question));
      _loading = true;
    });
    _controller.clear();
    _scrollToBottom();

    try {
      // Pass prior turns (excluding the just-added question) for context
      final history = _messages
          .sublist(0, _messages.length - 1)
          .map((m) => {'role': m.role, 'content': m.content})
          .toList();
      final answer = await ApiClient.chat(question, history);
      if (!mounted) return;
      setState(() {
        _messages.add(_ChatMessage('assistant', answer));
        _loading = false;
      });
    } catch (e) {
      if (!mounted) return;
      setState(() {
        _messages.add(_ChatMessage(
            'assistant', 'Désolé, une erreur est survenue : $e'));
        _loading = false;
      });
    }
    _scrollToBottom();
  }

  void _scrollToBottom() {
    WidgetsBinding.instance.addPostFrameCallback((_) {
      if (_scroll.hasClients) {
        _scroll.animateTo(
          _scroll.position.maxScrollExtent,
          duration: const Duration(milliseconds: 250),
          curve: Curves.easeOut,
        );
      }
    });
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(title: const Text('Conseiller IA')),
      body: SafeArea(
        child: Center(
          child: ConstrainedBox(
            constraints: const BoxConstraints(maxWidth: 700),
            child: Column(
              children: [
                Expanded(
                  child: _messages.isEmpty
                      ? _EmptyState(onPickSuggestion: _send)
                      : ListView.builder(
                          controller: _scroll,
                          padding: const EdgeInsets.fromLTRB(16, 12, 16, 12),
                          itemCount: _messages.length + (_loading ? 1 : 0),
                          itemBuilder: (context, i) {
                            if (i == _messages.length && _loading) {
                              return const _TypingBubble();
                            }
                            final m = _messages[i];
                            if (m.role == 'user') {
                              return _Bubble(isUser: true, text: m.content);
                            }
                            // Réponse de l'agent : bulle + feedback 👍/👎.
                            final question =
                                i > 0 ? _messages[i - 1].content : '';
                            return Column(
                              crossAxisAlignment: CrossAxisAlignment.start,
                              children: [
                                _Bubble(isUser: false, text: m.content),
                                Padding(
                                  padding:
                                      const EdgeInsets.only(left: 4, bottom: 8),
                                  child: FeedbackButtons(
                                    key: ValueKey('agentfb_$i'),
                                    target: 'agent',
                                    label: 'Réponse utile ?',
                                    question: question,
                                    answer: m.content,
                                  ),
                                ),
                              ],
                            );
                          },
                        ),
                ),
                const Divider(height: 1),
                Padding(
                  padding: const EdgeInsets.fromLTRB(12, 10, 12, 12),
                  child: Row(
                    crossAxisAlignment: CrossAxisAlignment.end,
                    children: [
                      Expanded(
                        child: TextField(
                          controller: _controller,
                          minLines: 1,
                          maxLines: 4,
                          textInputAction: TextInputAction.send,
                          onSubmitted: _loading ? null : _send,
                          decoration: InputDecoration(
                            hintText: 'Pose une question...',
                            filled: true,
                            fillColor: const Color(0xFFF1F3F6),
                            contentPadding: const EdgeInsets.symmetric(
                                horizontal: 16, vertical: 12),
                            border: OutlineInputBorder(
                              borderRadius: BorderRadius.circular(24),
                              borderSide: BorderSide.none,
                            ),
                          ),
                        ),
                      ),
                      const SizedBox(width: 8),
                      FloatingActionButton.small(
                        elevation: 0,
                        onPressed: _loading
                            ? null
                            : () => _send(_controller.text),
                        child: const Icon(Icons.send_rounded),
                      ),
                    ],
                  ),
                ),
              ],
            ),
          ),
        ),
      ),
    );
  }
}

class _EmptyState extends StatelessWidget {
  final ValueChanged<String> onPickSuggestion;
  const _EmptyState({required this.onPickSuggestion});

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: const EdgeInsets.symmetric(horizontal: 24, vertical: 32),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          const SizedBox(height: 12),
          Row(
            children: const [
              CircleAvatar(
                backgroundColor: Color(0xFFE7F6EF),
                radius: 22,
                child: Icon(Icons.auto_awesome_rounded,
                    color: Color(0xFF1B8A6B)),
              ),
              SizedBox(width: 12),
              Expanded(
                child: Text(
                  'Pose-moi une question sur tes courses :',
                  style: TextStyle(
                      fontSize: 16, fontWeight: FontWeight.w600),
                ),
              ),
            ],
          ),
          const SizedBox(height: 16),
          ..._ChatScreenState._suggestions.map(
            (q) => Padding(
              padding: const EdgeInsets.only(bottom: 8),
              child: InkWell(
                onTap: () => onPickSuggestion(q),
                borderRadius: BorderRadius.circular(12),
                child: Container(
                  padding: const EdgeInsets.symmetric(
                      horizontal: 14, vertical: 12),
                  decoration: BoxDecoration(
                    color: Colors.white,
                    border:
                        Border.all(color: const Color(0xFFE3E6EB)),
                    borderRadius: BorderRadius.circular(12),
                  ),
                  child: Row(
                    children: [
                      const Icon(Icons.bolt_rounded,
                          size: 18, color: Color(0xFF1B8A6B)),
                      const SizedBox(width: 8),
                      Expanded(
                        child: Text(q,
                            style: const TextStyle(fontSize: 14)),
                      ),
                    ],
                  ),
                ),
              ),
            ),
          ),
        ],
      ),
    );
  }
}

class _Bubble extends StatelessWidget {
  final bool isUser;
  final String text;
  const _Bubble({required this.isUser, required this.text});

  @override
  Widget build(BuildContext context) {
    return Align(
      alignment: isUser ? Alignment.centerRight : Alignment.centerLeft,
      child: Container(
        margin: const EdgeInsets.symmetric(vertical: 4),
        padding:
            const EdgeInsets.symmetric(horizontal: 14, vertical: 10),
        constraints: BoxConstraints(
            maxWidth: MediaQuery.of(context).size.width * 0.78),
        decoration: BoxDecoration(
          color: isUser ? const Color(0xFF1B8A6B) : Colors.white,
          borderRadius: BorderRadius.only(
            topLeft: const Radius.circular(16),
            topRight: const Radius.circular(16),
            bottomLeft: Radius.circular(isUser ? 16 : 4),
            bottomRight: Radius.circular(isUser ? 4 : 16),
          ),
          border: isUser
              ? null
              : Border.all(color: const Color(0xFFE3E6EB)),
        ),
        child: Text(
          text,
          style: TextStyle(
            color: isUser ? Colors.white : const Color(0xFF1A1F26),
            fontSize: 14,
            height: 1.4,
          ),
        ),
      ),
    );
  }
}

class _TypingBubble extends StatelessWidget {
  const _TypingBubble();

  @override
  Widget build(BuildContext context) {
    return Align(
      alignment: Alignment.centerLeft,
      child: Container(
        margin: const EdgeInsets.symmetric(vertical: 4),
        padding: const EdgeInsets.all(14),
        decoration: BoxDecoration(
          color: Colors.white,
          borderRadius: BorderRadius.circular(16),
          border: Border.all(color: const Color(0xFFE3E6EB)),
        ),
        child: Row(
          mainAxisSize: MainAxisSize.min,
          children: const [
            SizedBox(
                width: 14,
                height: 14,
                child: CircularProgressIndicator(strokeWidth: 2)),
            SizedBox(width: 8),
            Text('Réflexion...',
                style: TextStyle(
                    color: Color(0xFF5C6470), fontSize: 13)),
          ],
        ),
      ),
    );
  }
}
