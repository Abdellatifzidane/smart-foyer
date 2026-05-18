import 'dart:typed_data';
import 'package:file_picker/file_picker.dart';
import 'package:flutter/material.dart';
import '../api/api_client.dart';
import 'results_screen.dart';

class ScanScreen extends StatefulWidget {
  const ScanScreen({super.key});

  @override
  State<ScanScreen> createState() => _ScanScreenState();
}

class _ScanScreenState extends State<ScanScreen> {
  Uint8List? _imageBytes;
  String? _filename;
  bool _loading = false;
  String? _errorMessage;

  Future<void> _pickImage() async {
    final result = await FilePicker.platform.pickFiles(
      type: FileType.image,
      withData: true,
    );
    if (result == null || result.files.isEmpty) return;

    final file = result.files.first;
    setState(() {
      _imageBytes = file.bytes;
      _filename = file.name;
      _errorMessage = null;
    });
  }

  Future<void> _submit() async {
    if (_imageBytes == null) return;

    setState(() {
      _loading = true;
      _errorMessage = null;
    });

    try {
      final scan = await ApiClient.scan(_imageBytes!, _filename ?? 'ticket.jpg');
      if (!mounted) return;
      Navigator.of(context).pushReplacement(
        MaterialPageRoute(
          builder: (_) => ResultsScreen(result: scan),
        ),
      );
    } catch (e) {
      setState(() {
        _errorMessage = e.toString();
        _loading = false;
      });
    }
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(title: const Text('Nouveau ticket')),
      body: SafeArea(
        child: Center(
          child: ConstrainedBox(
            constraints: const BoxConstraints(maxWidth: 480),
            child: Padding(
              padding: const EdgeInsets.symmetric(horizontal: 24),
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.stretch,
                children: [
                  const SizedBox(height: 16),
                  _PreviewArea(
                    imageBytes: _imageBytes,
                    onTap: _pickImage,
                  ),
                  const SizedBox(height: 16),
                  if (_filename != null)
                    Text(
                      _filename!,
                      style: const TextStyle(
                          fontSize: 13, color: Color(0xFF5C6470)),
                      textAlign: TextAlign.center,
                    ),
                  const SizedBox(height: 24),
                  if (_errorMessage != null)
                    Container(
                      padding: const EdgeInsets.all(12),
                      decoration: BoxDecoration(
                        color: Colors.red.shade50,
                        borderRadius: BorderRadius.circular(12),
                      ),
                      child: Text(
                        _errorMessage!,
                        style: TextStyle(color: Colors.red.shade700),
                      ),
                    ),
                  if (_errorMessage != null) const SizedBox(height: 16),
                  OutlinedButton.icon(
                    onPressed: _loading ? null : _pickImage,
                    icon: const Icon(Icons.image_outlined),
                    label: Text(_imageBytes == null
                        ? 'Choisir une image'
                        : 'Changer d\'image'),
                    style: OutlinedButton.styleFrom(
                      minimumSize: const Size.fromHeight(52),
                      shape: RoundedRectangleBorder(
                        borderRadius: BorderRadius.circular(14),
                      ),
                    ),
                  ),
                  const SizedBox(height: 12),
                  FilledButton(
                    onPressed: (_imageBytes != null && !_loading)
                        ? _submit
                        : null,
                    style: FilledButton.styleFrom(
                      minimumSize: const Size.fromHeight(56),
                      shape: RoundedRectangleBorder(
                        borderRadius: BorderRadius.circular(16),
                      ),
                    ),
                    child: _loading
                        ? const SizedBox(
                            height: 22,
                            width: 22,
                            child: CircularProgressIndicator(
                              strokeWidth: 2.5,
                              color: Colors.white,
                            ),
                          )
                        : const Text('Analyser le ticket',
                            style: TextStyle(fontSize: 16)),
                  ),
                  if (_loading)
                    const Padding(
                      padding: EdgeInsets.only(top: 16),
                      child: Text(
                        'OCR + extraction + comparaison...\nCette étape prend 20-40s.',
                        textAlign: TextAlign.center,
                        style: TextStyle(
                            color: Color(0xFF5C6470), fontSize: 12),
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

class _PreviewArea extends StatelessWidget {
  final Uint8List? imageBytes;
  final VoidCallback onTap;

  const _PreviewArea({required this.imageBytes, required this.onTap});

  @override
  Widget build(BuildContext context) {
    return GestureDetector(
      onTap: onTap,
      child: Container(
        height: 320,
        decoration: BoxDecoration(
          color: Colors.white,
          borderRadius: BorderRadius.circular(20),
          border: Border.all(color: const Color(0xFFE3E6EB), width: 1.5),
        ),
        clipBehavior: Clip.antiAlias,
        child: imageBytes == null
            ? const Center(
                child: Column(
                  mainAxisSize: MainAxisSize.min,
                  children: [
                    Icon(Icons.add_photo_alternate_outlined,
                        size: 64, color: Color(0xFF1B8A6B)),
                    SizedBox(height: 12),
                    Text(
                      'Cliquez pour choisir\nune photo de ticket',
                      textAlign: TextAlign.center,
                      style: TextStyle(
                          fontSize: 14, color: Color(0xFF5C6470)),
                    ),
                  ],
                ),
              )
            : Image.memory(imageBytes!, fit: BoxFit.contain),
      ),
    );
  }
}
