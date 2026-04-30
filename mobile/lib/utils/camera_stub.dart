import 'dart:typed_data';

/// Stub for non-web platforms — never called directly on native
Future<({Uint8List? bytes, String? name})> captureFromCamera() async =>
    (bytes: null, name: null);
