import 'dart:typed_data';

export 'camera_stub.dart'
    if (dart.library.html) 'camera_web.dart';

typedef CameraResult = ({Uint8List? bytes, String? name});
