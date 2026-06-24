"""Compatibility entrypoint for Synthetiq Redact.

The default backend is now the V2 council workflow app. Keep this file small so
existing commands such as `uvicorn main:app` do not accidentally run the old
prototype path.
"""

from main_v2 import app
