"""Test TrOCR on EasyOCR-detected regions."""

from PIL import Image
import warnings
warnings.filterwarnings('ignore')
import easyocr
from transformers import TrOCRProcessor, VisionEncoderDecoderModel

print('Loading models...')
reader = easyocr.Reader(['en'], gpu=False)
processor = TrOCRProcessor.from_pretrained('microsoft/trocr-base-handwritten')
model = VisionEncoderDecoderModel.from_pretrained('microsoft/trocr-base-handwritten')

img_path = 'evaluation/datasets/iam_forms/iam_handwritten_0000.png'
img = Image.open(img_path).convert('RGB')
print(f'Image size: {img.size}')

print('EasyOCR detection...')
result = reader.readtext(img_path)
print(f'Found {len(result)} regions')

print('Running TrOCR on top 10 regions...')
for i, r in enumerate(result[:10]):
    bbox = r[0]
    xs = [p[0] for p in bbox]
    ys = [p[1] for p in bbox]
    x1, y1, x2, y2 = int(min(xs)), int(min(ys)), int(max(xs)), int(max(ys))
    x1, y1 = max(0, x1), max(0, y1)
    crop = img.crop((x1, y1, x2, y2))
    if crop.width < 10 or crop.height < 10:
        continue
    pixel_values = processor(images=crop, return_tensors='pt').pixel_values
    generated_ids = model.generate(pixel_values, max_new_tokens=50)
    text = processor.batch_decode(generated_ids, skip_special_tokens=True)[0]
    print(f'  Region {i}: EasyOCR="{r[1]}" TrOCR="{text}"')

print('Done')
