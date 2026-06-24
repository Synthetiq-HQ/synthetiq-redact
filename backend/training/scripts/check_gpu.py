from __future__ import annotations

import json
import platform
import subprocess
import sys


def query_nvidia_smi() -> list[dict[str, str]]:
    command = [
        "nvidia-smi",
        "--query-gpu=name,memory.total,driver_version",
        "--format=csv,noheader,nounits",
    ]
    try:
        completed = subprocess.run(command, capture_output=True, text=True, check=True, timeout=20)
    except (FileNotFoundError, subprocess.CalledProcessError, subprocess.TimeoutExpired) as exc:
        return [{"available": "false", "error": str(exc)}]

    gpus = []
    for line in completed.stdout.splitlines():
        parts = [part.strip() for part in line.split(",")]
        if len(parts) >= 3:
            gpus.append(
                {
                    "available": "true",
                    "name": parts[0],
                    "vram_mb": parts[1],
                    "driver_version": parts[2],
                }
            )
    return gpus


def query_torch() -> dict:
    try:
        import torch
    except Exception as exc:
        return {
            "installed": False,
            "error": str(exc),
        }

    devices = []
    if torch.cuda.is_available():
        for index in range(torch.cuda.device_count()):
            props = torch.cuda.get_device_properties(index)
            devices.append(
                {
                    "index": index,
                    "name": props.name,
                    "vram_mb": round(props.total_memory / (1024 * 1024)),
                    "major": props.major,
                    "minor": props.minor,
                }
            )
    return {
        "installed": True,
        "version": torch.__version__,
        "cuda_available": torch.cuda.is_available(),
        "cuda_version": getattr(torch.version, "cuda", None),
        "device_count": len(devices),
        "devices": devices,
    }


def main() -> int:
    report = {
        "python": sys.version.split()[0],
        "platform": platform.platform(),
        "torch": query_torch(),
        "nvidia_smi": query_nvidia_smi(),
    }
    print(json.dumps(report, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
