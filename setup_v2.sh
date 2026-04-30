#!/bin/bash
# setup.sh - Setup script for Synthetiq Redact v2.0

echo "=== Synthetiq Redact v2.0 Setup ==="
cd backend

# Create virtual environment
python3 -m venv venv
source venv/bin/activate

# Upgrade pip
pip install --upgrade pip

# Install new dependencies
echo "Installing dependencies..."
pip install paddlepaddle paddleocr transformers torch torchvision torchaudio
pip install onnxruntime tokenizers sentencepiece
pip install timm einops pyyaml
pip install bcrypt pyjwt

# Keep existing requirements
echo "Installing existing requirements..."
pip install -r requirements.txt

# Download spaCy model
python -m spacy download en_core_web_sm

echo "=== Setup complete ==="
echo "Run: source backend/venv/bin/activate && cd backend && uvicorn main:app --host 127.0.0.1 --port 8000"