# Dataset Text Prompt Pack

This folder is for generating fake council-style document images with ChatGPT or
another image generator.

Use only synthetic documents from this folder. Do not upload real council
records, real resident data, or private case files.

Recommended workflow:

1. Open one file from `documents/`.
2. Copy that full document block into ChatGPT image generation.
3. Ask it to generate the 10 images described in that file.
4. Download the 10 images into a folder named after the document id, for example
   `generated_images/DOC-001/`.
5. Keep the prompt text and answer key with the images.
6. Reject any image where the visible text is too distorted, missing fields, or
   has invented real-looking extra personal data.

Important: image models can misspell or alter text. For OCR training, use an
image only if the visible text matches the answer key closely enough to be
useful. Treat mismatched images as visual augmentation examples, not trusted OCR
ground truth.

Files:

- `documents/` has 75 separate paste-ready prompt files.
- `answer_keys/` has 75 matching JSON answer keys.
- `document_index.json` and `document_index.jsonl` map document ids to files.
- `SUMMARY.json` records the current batch size.
