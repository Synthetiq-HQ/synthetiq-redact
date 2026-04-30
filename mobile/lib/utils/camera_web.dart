// ignore: avoid_web_libraries_in_flutter
import 'dart:html' as html;
import 'dart:async';
import 'dart:typed_data';

/// Web implementation — uses a native browser file input with
/// capture="environment" which triggers the rear camera on iOS/Android.
Future<({Uint8List? bytes, String? name})> captureFromCamera() async {
  final completer = Completer<({Uint8List? bytes, String? name})>();

  final input = html.FileUploadInputElement()
    ..accept = 'image/*'
    ..setAttribute('capture', 'environment')
    ..style.display = 'none';

  html.document.body?.append(input);
  input.click();

  input.onChange.listen((event) async {
    final file = input.files?.isNotEmpty == true ? input.files!.first : null;
    input.remove();

    if (file == null) {
      completer.complete((bytes: null, name: null));
      return;
    }

    final reader = html.FileReader();
    reader.readAsArrayBuffer(file);

    reader.onLoad.listen((_) {
      final result = reader.result;
      Uint8List? bytes;
      if (result is List<int>) {
        bytes = Uint8List.fromList(result);
      } else if (result is ByteBuffer) {
        bytes = Uint8List.view(result);
      }
      completer.complete((bytes: bytes, name: file.name));
    });

    reader.onError.listen((_) {
      input.remove();
      completer.complete((bytes: null, name: null));
    });
  });

  // Handle cancel (user dismisses without picking)
  html.window.onFocus.first.then((_) {
    Future.delayed(const Duration(milliseconds: 500), () {
      if (!completer.isCompleted) {
        input.remove();
        completer.complete((bytes: null, name: null));
      }
    });
  });

  return completer.future;
}
