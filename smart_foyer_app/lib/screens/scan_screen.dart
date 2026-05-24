import 'dart:typed_data';

import 'package:file_picker/file_picker.dart';
import 'package:flutter/foundation.dart' show kIsWeb;
import 'package:flutter/material.dart';
import 'package:image_picker/image_picker.dart';

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

  final ImagePicker _picker = ImagePicker();

  /// On mobile we prefer image_picker (native camera + gallery); on web we
  /// fall back to file_picker (image_picker on web only opens a file dialog).
  Future<void> _pickFromCamera() async {
    try {
      final picked = await _picker.pickImage(
        source: ImageSource.camera,
        imageQuality: 85,
        maxWidth: 2000,
      );
      if (picked == null) return;
      final bytes = await picked.readAsBytes();
      setState(() {
        _imageBytes = bytes;
        _filename = picked.name;
        _errorMessage = null;
      });
    } catch (e) {
      setState(() => _errorMessage = 'Caméra : $e');
    }
  }

  Future<void> _pickFromGallery() async {
    try {
      if (kIsWeb) {
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
      } else {
        final picked = await _picker.pickImage(
          source: ImageSource.gallery,
          imageQuality: 85,
          maxWidth: 2000,
        );
        if (picked == null) return;
        final bytes = await picked.readAsBytes();
        setState(() {
          _imageBytes = bytes;
          _filename = picked.name;
          _errorMessage = null;
        });
      }
    } catch (e) {
      setState(() => _errorMessage = 'Galerie : $e');
    }
  }

  Future<void> _showPickerSheet() async {
    // On the web there's no camera picker, just open the file dialog directly.
    if (kIsWeb) {
      await _pickFromGallery();
      return;
    }
    await showModalBottomSheet<void>(
      context: context,
      showDragHandle: true,
      builder: (ctx) => SafeArea(
        child: Wrap(
          children: [
            ListTile(
              leading: const Icon(Icons.photo_camera_rounded),
              title: const Text('Prendre une photo'),
              onTap: () {
                Navigator.of(ctx).pop();
                _pickFromCamera();
              },
            ),
            ListTile(
              leading: const Icon(Icons.photo_library_rounded),
              title: const Text('Choisir dans la galerie'),
              onTap: () {
                Navigator.of(ctx).pop();
                _pickFromGallery();
              },
            ),
          ],
        ),
      ),
    );
  }

  Future<void> _submit() async {
    if (_imageBytes == null) return;
    setState(() {
      _loading = true;
      _errorMessage = null;
    });

    try {
      final scan =
          await ApiClient.scan(_imageBytes!, _filename ?? 'ticket.jpg');
      if (!mounted) return;
      // Even on partial failures (pipeline.ok == false), navigate to the
      // results screen — it knows how to render a degraded response and
      // show the user what went wrong. This way the app never feels stuck.
      Navigator.of(context).pushReplacement(
        MaterialPageRoute(builder: (_) => ResultsScreen(result: scan)),
      );
    } on ApiException catch (e) {
      if (!mounted) return;
      setState(() {
        _errorMessage = e.message;
        _loading = false;
      });
    } catch (e) {
      if (!mounted) return;
      setState(() {
        _errorMessage = 'Erreur inattendue : $e';
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
                      imageBytes: _imageBytes, onTap: _showPickerSheet),
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
                  if (!kIsWeb)
                    Row(
                      children: [
                        Expanded(
                          child: OutlinedButton.icon(
                            onPressed: _loading ? null : _pickFromCamera,
                            icon: const Icon(Icons.photo_camera_rounded),
                            label: const Text('Photo'),
                            style: OutlinedButton.styleFrom(
                              minimumSize: const Size.fromHeight(52),
                              shape: RoundedRectangleBorder(
                                borderRadius: BorderRadius.circular(14),
                              ),
                            ),
                          ),
                        ),
                        const SizedBox(width: 10),
                        Expanded(
                          child: OutlinedButton.icon(
                            onPressed: _loading ? null : _pickFromGallery,
                            icon: const Icon(Icons.photo_library_outlined),
                            label: const Text('Galerie'),
                            style: OutlinedButton.styleFrom(
                              minimumSize: const Size.fromHeight(52),
                              shape: RoundedRectangleBorder(
                                borderRadius: BorderRadius.circular(14),
                              ),
                            ),
                          ),
                        ),
                      ],
                    )
                  else
                    OutlinedButton.icon(
                      onPressed: _loading ? null : _pickFromGallery,
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
                    onPressed:
                        (_imageBytes != null && !_loading) ? _submit : null,
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
                        style:
                            TextStyle(color: Color(0xFF5C6470), fontSize: 12),
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
                    Icon(Icons.add_a_photo_outlined,
                        size: 64, color: Color(0xFF1B8A6B)),
                    SizedBox(height: 12),
                    Text(
                      'Touchez pour prendre\nune photo ou choisir une image',
                      textAlign: TextAlign.center,
                      style:
                          TextStyle(fontSize: 14, color: Color(0xFF5C6470)),
                    ),
                  ],
                ),
              )
            : Image.memory(imageBytes!, fit: BoxFit.contain),
      ),
    );
  }
}
