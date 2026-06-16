import 'dart:async';
import 'package:flutter/material.dart';
import '../api/api_client.dart';
import '../api/models.dart';

class AdminScreen extends StatefulWidget {
  const AdminScreen({super.key});

  @override
  State<AdminScreen> createState() => _AdminScreenState();
}

class _AdminScreenState extends State<AdminScreen>
    with SingleTickerProviderStateMixin {
  late final TabController _tabController;

  @override
  void initState() {
    super.initState();
    _tabController = TabController(length: 3, vsync: this);
  }

  @override
  void dispose() {
    _tabController.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(
        title: const Text('Administration'),
        bottom: TabBar(
          controller: _tabController,
          tabs: const [
            Tab(icon: Icon(Icons.inventory_2_outlined), text: 'Catalogue'),
            Tab(icon: Icon(Icons.cloud_download_outlined), text: 'Scraping'),
            Tab(icon: Icon(Icons.thumbs_up_down_outlined), text: 'Feedback'),
          ],
        ),
      ),
      body: TabBarView(
        controller: _tabController,
        children: const [
          _CatalogTab(),
          _ScrapingTab(),
          _FeedbackTab(),
        ],
      ),
    );
  }
}

// ─── Catalogue tab ──────────────────────────────────────────────────────

class _CatalogTab extends StatefulWidget {
  const _CatalogTab();

  @override
  State<_CatalogTab> createState() => _CatalogTabState();
}

class _CatalogTabState extends State<_CatalogTab> {
  final _searchCtrl = TextEditingController();
  Timer? _debounce;

  int _page = 1;
  final int _pageSize = 20;
  String _q = '';
  String _enseigne = '';

  ProductPage? _data;
  bool _loading = false;
  String? _error;

  List<String> _enseigneOptions = [];

  @override
  void initState() {
    super.initState();
    _loadEnseignes();
    _fetch();
  }

  @override
  void dispose() {
    _debounce?.cancel();
    _searchCtrl.dispose();
    super.dispose();
  }

  Future<void> _loadEnseignes() async {
    try {
      final stats = await ApiClient.catalogStats();
      final m = (stats['by_enseigne'] as Map?) ?? {};
      setState(() {
        _enseigneOptions = m.keys.map((k) => k.toString()).toList()..sort();
      });
    } catch (_) {
      // silent — filter just won't be populated
    }
  }

  Future<void> _fetch() async {
    setState(() {
      _loading = true;
      _error = null;
    });
    try {
      final page = await ApiClient.listProducts(
        page: _page,
        pageSize: _pageSize,
        q: _q,
        enseigne: _enseigne,
      );
      setState(() {
        _data = page;
        _loading = false;
      });
    } catch (e) {
      setState(() {
        _error = e.toString();
        _loading = false;
      });
    }
  }

  void _onSearchChanged(String v) {
    _debounce?.cancel();
    _debounce = Timer(const Duration(milliseconds: 300), () {
      setState(() {
        _q = v;
        _page = 1;
      });
      _fetch();
    });
  }

  Future<void> _openAddDialog() async {
    final created = await showDialog<Product>(
      context: context,
      builder: (_) => const _ProductFormDialog(),
    );
    if (created == null) return;
    try {
      await ApiClient.createProduct(created);
      if (!mounted) return;
      ScaffoldMessenger.of(context).showSnackBar(
        const SnackBar(content: Text('Produit ajouté')),
      );
      _loadEnseignes();
      _fetch();
    } catch (e) {
      if (!mounted) return;
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(content: Text('Erreur : $e')),
      );
    }
  }

  Future<void> _openEditDialog(Product p) async {
    final edited = await showDialog<Product>(
      context: context,
      builder: (_) => _ProductFormDialog(initial: p),
    );
    if (edited == null) return;
    try {
      await ApiClient.updateProduct(p.id, edited);
      if (!mounted) return;
      ScaffoldMessenger.of(context).showSnackBar(
        const SnackBar(content: Text('Produit mis à jour')),
      );
      _fetch();
    } catch (e) {
      if (!mounted) return;
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(content: Text('Erreur : $e')),
      );
    }
  }

  Future<void> _confirmDelete(Product p) async {
    final ok = await showDialog<bool>(
      context: context,
      builder: (_) => AlertDialog(
        title: const Text('Supprimer ce produit ?'),
        content: Text('« ${p.name} » sera retiré du catalogue.'),
        actions: [
          TextButton(
              onPressed: () => Navigator.pop(context, false),
              child: const Text('Annuler')),
          FilledButton(
              onPressed: () => Navigator.pop(context, true),
              child: const Text('Supprimer')),
        ],
      ),
    );
    if (ok != true) return;
    try {
      await ApiClient.deleteProduct(p.id);
      if (!mounted) return;
      ScaffoldMessenger.of(context).showSnackBar(
        const SnackBar(content: Text('Produit supprimé')),
      );
      _fetch();
    } catch (e) {
      if (!mounted) return;
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(content: Text('Erreur : $e')),
      );
    }
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      body: Column(
        children: [
          Padding(
            padding: const EdgeInsets.all(12),
            child: Column(
              children: [
                TextField(
                  controller: _searchCtrl,
                  onChanged: _onSearchChanged,
                  decoration: InputDecoration(
                    hintText: 'Rechercher un produit…',
                    prefixIcon: const Icon(Icons.search),
                    border: OutlineInputBorder(
                      borderRadius: BorderRadius.circular(12),
                    ),
                    isDense: true,
                  ),
                ),
                const SizedBox(height: 8),
                Row(
                  children: [
                    const Text('Enseigne : ',
                        style: TextStyle(color: Color(0xFF5C6470))),
                    Expanded(
                      child: DropdownButton<String>(
                        isExpanded: true,
                        value: _enseigne.isEmpty ? null : _enseigne,
                        hint: const Text('Toutes'),
                        items: [
                          const DropdownMenuItem(
                              value: '', child: Text('Toutes')),
                          ..._enseigneOptions.map(
                            (e) =>
                                DropdownMenuItem(value: e, child: Text(e)),
                          ),
                        ],
                        onChanged: (v) {
                          setState(() {
                            _enseigne = v ?? '';
                            _page = 1;
                          });
                          _fetch();
                        },
                      ),
                    ),
                  ],
                ),
              ],
            ),
          ),
          Expanded(child: _buildList()),
          if (_data != null && _data!.total > _pageSize) _buildPagination(),
        ],
      ),
      floatingActionButton: FloatingActionButton.extended(
        onPressed: _openAddDialog,
        icon: const Icon(Icons.add),
        label: const Text('Ajouter'),
      ),
    );
  }

  Widget _buildList() {
    if (_loading && _data == null) {
      return const Center(child: CircularProgressIndicator());
    }
    if (_error != null) {
      return Center(
        child: Padding(
          padding: const EdgeInsets.all(24),
          child: Text('Erreur : $_error',
              style: const TextStyle(color: Colors.redAccent)),
        ),
      );
    }
    final items = _data?.items ?? [];
    if (items.isEmpty) {
      return const Center(
        child: Padding(
          padding: EdgeInsets.all(24),
          child: Text(
            'Aucun produit. Ajoutez-en un manuellement ou lancez un scraper.',
            style: TextStyle(color: Color(0xFF5C6470)),
            textAlign: TextAlign.center,
          ),
        ),
      );
    }
    return ListView.separated(
      padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 4),
      itemCount: items.length,
      separatorBuilder: (_, _) => const SizedBox(height: 6),
      itemBuilder: (_, i) => _ProductTile(
        product: items[i],
        onEdit: () => _openEditDialog(items[i]),
        onDelete: () => _confirmDelete(items[i]),
      ),
    );
  }

  Widget _buildPagination() {
    final total = _data!.total;
    final maxPage = (total / _pageSize).ceil();
    return SafeArea(
      top: false,
      child: Padding(
        padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 8),
        child: Row(
          mainAxisAlignment: MainAxisAlignment.spaceBetween,
          children: [
            IconButton(
              onPressed: _page > 1
                  ? () {
                      setState(() => _page -= 1);
                      _fetch();
                    }
                  : null,
              icon: const Icon(Icons.chevron_left),
            ),
            Text('Page $_page / $maxPage  ·  $total produits',
                style: const TextStyle(color: Color(0xFF5C6470))),
            IconButton(
              onPressed: _page < maxPage
                  ? () {
                      setState(() => _page += 1);
                      _fetch();
                    }
                  : null,
              icon: const Icon(Icons.chevron_right),
            ),
          ],
        ),
      ),
    );
  }
}


class _ProductTile extends StatelessWidget {
  final Product product;
  final VoidCallback onEdit;
  final VoidCallback onDelete;

  const _ProductTile({
    required this.product,
    required this.onEdit,
    required this.onDelete,
  });

  @override
  Widget build(BuildContext context) {
    return Container(
      decoration: BoxDecoration(
        color: Colors.white,
        borderRadius: BorderRadius.circular(14),
        border: Border.all(color: const Color(0xFFE3E6EB)),
      ),
      padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 10),
      child: Row(
        children: [
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              mainAxisSize: MainAxisSize.min,
              children: [
                Text(
                  product.name,
                  style: const TextStyle(fontWeight: FontWeight.w700),
                  maxLines: 2,
                  overflow: TextOverflow.ellipsis,
                ),
                const SizedBox(height: 4),
                Row(
                  children: [
                    if (product.enseigne.isNotEmpty) ...[
                      Container(
                        padding: const EdgeInsets.symmetric(
                            horizontal: 8, vertical: 2),
                        decoration: BoxDecoration(
                          color: const Color(0xFF1B8A6B).withValues(alpha: 0.1),
                          borderRadius: BorderRadius.circular(8),
                        ),
                        child: Text(
                          product.enseigne,
                          style: const TextStyle(
                              fontSize: 11,
                              color: Color(0xFF1B8A6B),
                              fontWeight: FontWeight.w600),
                        ),
                      ),
                      const SizedBox(width: 6),
                    ],
                    Text(
                      '${product.price.toStringAsFixed(2)} €',
                      style: const TextStyle(
                          color: Color(0xFF5C6470),
                          fontWeight: FontWeight.w600),
                    ),
                    if (product.brand.isNotEmpty) ...[
                      const SizedBox(width: 8),
                      Flexible(
                        child: Text(
                          '· ${product.brand}',
                          style: const TextStyle(
                              fontSize: 12, color: Color(0xFF5C6470)),
                          overflow: TextOverflow.ellipsis,
                        ),
                      ),
                    ],
                  ],
                ),
              ],
            ),
          ),
          IconButton(
              onPressed: onEdit,
              icon: const Icon(Icons.edit_outlined, size: 20)),
          IconButton(
              onPressed: onDelete,
              icon: const Icon(Icons.delete_outline,
                  size: 20, color: Colors.redAccent)),
        ],
      ),
    );
  }
}


// ─── Add/Edit dialog ────────────────────────────────────────────────────

class _ProductFormDialog extends StatefulWidget {
  final Product? initial;
  const _ProductFormDialog({this.initial});

  @override
  State<_ProductFormDialog> createState() => _ProductFormDialogState();
}

class _ProductFormDialogState extends State<_ProductFormDialog> {
  late final TextEditingController _name;
  late final TextEditingController _price;
  late final TextEditingController _enseigne;
  late final TextEditingController _brand;
  late final TextEditingController _category;

  @override
  void initState() {
    super.initState();
    final p = widget.initial;
    _name = TextEditingController(text: p?.name ?? '');
    _price = TextEditingController(
        text: p == null ? '' : p.price.toStringAsFixed(2));
    _enseigne = TextEditingController(text: p?.enseigne ?? '');
    _brand = TextEditingController(text: p?.brand ?? '');
    _category = TextEditingController(text: p?.category ?? '');
  }

  @override
  void dispose() {
    _name.dispose();
    _price.dispose();
    _enseigne.dispose();
    _brand.dispose();
    _category.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final isEdit = widget.initial != null;
    return AlertDialog(
      title: Text(isEdit ? 'Modifier le produit' : 'Nouveau produit'),
      content: SingleChildScrollView(
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            TextField(
              controller: _name,
              decoration: const InputDecoration(labelText: 'Nom *'),
              autofocus: true,
            ),
            TextField(
              controller: _price,
              decoration: const InputDecoration(labelText: 'Prix (€)'),
              keyboardType:
                  const TextInputType.numberWithOptions(decimal: true),
            ),
            TextField(
              controller: _enseigne,
              decoration: const InputDecoration(
                  labelText: 'Enseigne (ex: Lidl, Monoprix)'),
            ),
            TextField(
              controller: _brand,
              decoration: const InputDecoration(labelText: 'Marque'),
            ),
            TextField(
              controller: _category,
              decoration: const InputDecoration(labelText: 'Catégorie'),
            ),
          ],
        ),
      ),
      actions: [
        TextButton(
          onPressed: () => Navigator.pop(context),
          child: const Text('Annuler'),
        ),
        FilledButton(
          onPressed: () {
            final name = _name.text.trim();
            if (name.isEmpty) {
              ScaffoldMessenger.of(context).showSnackBar(
                const SnackBar(content: Text('Le nom est requis')),
              );
              return;
            }
            final price =
                double.tryParse(_price.text.replaceAll(',', '.').trim()) ?? 0.0;
            final p = Product(
              id: widget.initial?.id ?? '',
              name: name,
              price: price,
              enseigne: _enseigne.text.trim(),
              brand: _brand.text.trim(),
              category: _category.text.trim(),
              sku: widget.initial?.sku ?? '',
              productUrl: widget.initial?.productUrl ?? '',
              imageUrl: widget.initial?.imageUrl ?? '',
              unitPrice: widget.initial?.unitPrice ?? '',
            );
            Navigator.pop(context, p);
          },
          child: Text(isEdit ? 'Enregistrer' : 'Ajouter'),
        ),
      ],
    );
  }
}


// ─── Scraping tab ───────────────────────────────────────────────────────

class _ScrapingTab extends StatefulWidget {
  const _ScrapingTab();

  @override
  State<_ScrapingTab> createState() => _ScrapingTabState();
}

class _ScrapingTabState extends State<_ScrapingTab> {
  // Active jobs keyed by retailer
  final Map<String, ScrapeJob> _jobs = {};
  final Map<String, TextEditingController> _maxCtrls = {
    'lidl': TextEditingController(text: '50'),
    'monoprix': TextEditingController(text: '50'),
  };
  Timer? _poll;

  @override
  void dispose() {
    _poll?.cancel();
    for (final c in _maxCtrls.values) {
      c.dispose();
    }
    super.dispose();
  }

  Future<void> _launch(String retailer) async {
    final max =
        int.tryParse(_maxCtrls[retailer]?.text.trim() ?? '') ?? 0;
    if (max <= 0) {
      ScaffoldMessenger.of(context).showSnackBar(
        const SnackBar(content: Text('Indique un nombre max de produits')),
      );
      return;
    }
    try {
      final job = await ApiClient.startScrape(retailer, max);
      setState(() => _jobs[retailer] = job);
      _startPolling();
    } catch (e) {
      if (!mounted) return;
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(content: Text('Erreur : $e')),
      );
    }
  }

  void _startPolling() {
    _poll?.cancel();
    _poll = Timer.periodic(const Duration(seconds: 2), (_) => _refresh());
  }

  Future<void> _refresh() async {
    final runningIds = _jobs.entries
        .where((e) => e.value.isRunning)
        .map((e) => MapEntry(e.key, e.value.jobId))
        .toList();
    if (runningIds.isEmpty) {
      _poll?.cancel();
      return;
    }
    for (final entry in runningIds) {
      try {
        final updated = await ApiClient.scrapeStatus(entry.value);
        if (!mounted) return;
        setState(() => _jobs[entry.key] = updated);
      } catch (_) {
        // ignore transient errors
      }
    }
  }

  @override
  Widget build(BuildContext context) {
    return ListView(
      padding: const EdgeInsets.all(16),
      children: [
        const Text(
          'Lancer un scraper pour peupler le catalogue. Les produits sont ajoutés à l\'index FAISS au fur et à mesure.',
          style: TextStyle(color: Color(0xFF5C6470)),
        ),
        const SizedBox(height: 16),
        _retailerCard('monoprix', 'Monoprix', Icons.shopping_basket_rounded),
        const SizedBox(height: 12),
        _retailerCard('lidl', 'Lidl', Icons.local_grocery_store_rounded),
      ],
    );
  }

  Widget _retailerCard(String key, String label, IconData icon) {
    final job = _jobs[key];
    final running = job?.isRunning == true;
    return Container(
      padding: const EdgeInsets.all(16),
      decoration: BoxDecoration(
        color: Colors.white,
        borderRadius: BorderRadius.circular(16),
        border: Border.all(color: const Color(0xFFE3E6EB)),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            children: [
              Icon(icon, color: const Color(0xFF1B8A6B)),
              const SizedBox(width: 8),
              Text(label,
                  style: const TextStyle(
                      fontSize: 18, fontWeight: FontWeight.w700)),
            ],
          ),
          const SizedBox(height: 12),
          Row(
            children: [
              SizedBox(
                width: 110,
                child: TextField(
                  controller: _maxCtrls[key],
                  enabled: !running,
                  keyboardType: TextInputType.number,
                  decoration: const InputDecoration(
                    labelText: 'Max produits',
                    isDense: true,
                  ),
                ),
              ),
              const SizedBox(width: 12),
              Expanded(
                child: FilledButton.icon(
                  onPressed: running ? null : () => _launch(key),
                  icon: const Icon(Icons.download_rounded),
                  label: Text(running ? 'En cours…' : 'Lancer'),
                ),
              ),
            ],
          ),
          if (job != null) ...[
            const SizedBox(height: 14),
            if (running) ...[
              LinearProgressIndicator(
                value: job.maxProducts > 0
                    ? (job.scraped / job.maxProducts).clamp(0.0, 1.0)
                    : null,
              ),
              const SizedBox(height: 6),
              Text('${job.scraped} / ${job.maxProducts} produits scrapés',
                  style: const TextStyle(
                      fontSize: 12, color: Color(0xFF5C6470))),
            ] else if (job.isDone) ...[
              Row(children: [
                const Icon(Icons.check_circle_rounded,
                    color: Color(0xFF1B8A6B), size: 18),
                const SizedBox(width: 6),
                Text('${job.scraped} produits ajoutés au catalogue',
                    style: const TextStyle(
                        color: Color(0xFF1B8A6B),
                        fontWeight: FontWeight.w600)),
              ])
            ] else if (job.isError) ...[
              Row(children: [
                const Icon(Icons.error_outline,
                    color: Colors.redAccent, size: 18),
                const SizedBox(width: 6),
                Flexible(
                  child: Text(job.error ?? 'Erreur inconnue',
                      style: const TextStyle(color: Colors.redAccent)),
                ),
              ])
            ],
          ],
        ],
      ),
    );
  }
}

// ─── Feedback tab (stats 👍/👎 : OCR, matching, agent) ──────────────────

class _FeedbackTab extends StatefulWidget {
  const _FeedbackTab();

  @override
  State<_FeedbackTab> createState() => _FeedbackTabState();
}

class _FeedbackTabState extends State<_FeedbackTab> {
  Map<String, dynamic>? _data;
  bool _loading = false;
  String? _error;

  static const Map<String, String> _labels = {
    'ocr': 'OCR (lecture du ticket)',
    'matching': 'Matching (correspondances prix)',
    'agent': 'Agent IA (qualité des réponses)',
  };

  @override
  void initState() {
    super.initState();
    _fetch();
  }

  Future<void> _fetch() async {
    setState(() {
      _loading = true;
      _error = null;
    });
    try {
      final data = await ApiClient.feedbackStats();
      if (mounted) setState(() => _data = data);
    } on ApiException catch (e) {
      if (mounted) setState(() => _error = e.message);
    } catch (e) {
      if (mounted) setState(() => _error = '$e');
    } finally {
      if (mounted) setState(() => _loading = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    if (_loading && _data == null) {
      return const Center(child: CircularProgressIndicator());
    }
    if (_error != null) {
      return _ErrorRetry(message: _error!, onRetry: _fetch);
    }
    final byTarget =
        (_data?['by_target'] as Map?)?.cast<String, dynamic>() ?? const {};
    final comments =
        (_data?['recent_comments'] as List?) ?? const [];

    return RefreshIndicator(
      onRefresh: _fetch,
      child: ListView(
        padding: const EdgeInsets.all(16),
        children: [
          for (final entry in _labels.entries)
            _FeedbackCard(
              title: entry.value,
              stats: (byTarget[entry.key] as Map?)?.cast<String, dynamic>() ??
                  const {},
            ),
          const SizedBox(height: 12),
          const Text('Derniers commentaires',
              style: TextStyle(fontSize: 16, fontWeight: FontWeight.w700)),
          const SizedBox(height: 8),
          if (comments.isEmpty)
            const Padding(
              padding: EdgeInsets.all(16),
              child: Text('Aucun commentaire pour le moment.',
                  style: TextStyle(color: Color(0xFF5C6470))),
            ),
          ...comments.whereType<Map>().map((c) {
            final m = c.cast<String, dynamic>();
            final isDown = (m['rating'] ?? '') == 'down';
            return Card(
              child: ListTile(
                leading: Icon(
                  isDown ? Icons.thumb_down : Icons.thumb_up,
                  color: isDown ? Colors.redAccent : Colors.green,
                ),
                title: Text((m['comment'] ?? '').toString()),
                subtitle: Text(
                    '${_labels[m['target']] ?? m['target']} · ${(m['created_at'] ?? '').toString().split('T').first}'),
              ),
            );
          }),
        ],
      ),
    );
  }
}

class _FeedbackCard extends StatelessWidget {
  final String title;
  final Map<String, dynamic> stats;
  const _FeedbackCard({required this.title, required this.stats});

  @override
  Widget build(BuildContext context) {
    final up = (stats['up'] ?? 0) as int;
    final down = (stats['down'] ?? 0) as int;
    final total = (stats['total'] ?? 0) as int;
    final pct = stats['satisfaction_pct'];
    final ratio = total > 0 ? up / total : 0.0;

    return Card(
      margin: const EdgeInsets.only(bottom: 12),
      child: Padding(
        padding: const EdgeInsets.all(16),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Text(title,
                style: const TextStyle(
                    fontSize: 15, fontWeight: FontWeight.w700)),
            const SizedBox(height: 10),
            ClipRRect(
              borderRadius: BorderRadius.circular(6),
              child: LinearProgressIndicator(
                value: ratio,
                minHeight: 10,
                backgroundColor: const Color(0xFFFFE0E0),
                valueColor:
                    const AlwaysStoppedAnimation<Color>(Color(0xFF1B8A6B)),
              ),
            ),
            const SizedBox(height: 10),
            Row(
              children: [
                const Icon(Icons.thumb_up, size: 16, color: Colors.green),
                const SizedBox(width: 4),
                Text('$up'),
                const SizedBox(width: 16),
                const Icon(Icons.thumb_down, size: 16, color: Colors.redAccent),
                const SizedBox(width: 4),
                Text('$down'),
                const Spacer(),
                Text(
                  pct == null ? 'Pas encore noté' : '$pct % satisfaction',
                  style: const TextStyle(
                      fontWeight: FontWeight.w600, color: Color(0xFF5C6470)),
                ),
              ],
            ),
          ],
        ),
      ),
    );
  }
}

class _ErrorRetry extends StatelessWidget {
  final String message;
  final VoidCallback onRetry;
  const _ErrorRetry({required this.message, required this.onRetry});

  @override
  Widget build(BuildContext context) {
    return Center(
      child: Padding(
        padding: const EdgeInsets.all(24),
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            const Icon(Icons.error_outline, size: 40, color: Color(0xFF5C6470)),
            const SizedBox(height: 12),
            Text(message, textAlign: TextAlign.center),
            const SizedBox(height: 12),
            FilledButton(onPressed: onRetry, child: const Text('Réessayer')),
          ],
        ),
      ),
    );
  }
}
