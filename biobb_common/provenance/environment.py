"""Module containing the function to describe the machine where a building block is executed."""
import os
import platform
import shutil
import subprocess
from functools import lru_cache
from pathlib import Path
from typing import Any, Optional


@lru_cache(maxsize=None)
def execution_environment() -> dict[str, Any]:
    """Return a description of the machine running the building blocks.
    Hostname and username are never included. Keys with unknown values are omitted."""
    uname = platform.uname()
    environment = {
        "operating_system": f"{uname.system} {uname.release}",
        "architecture": uname.machine,
        "cpu_model": _cpu_model(),
        "cpu_count": os.cpu_count(),
        "memory_bytes": _memory_bytes(),
        "python_version": platform.python_version(),
        **_nvidia_gpus(),
        "cuda_visible_devices": os.environ.get("CUDA_VISIBLE_DEVICES"),
        "conda_environment": os.environ.get("CONDA_DEFAULT_ENV"),
        "slurm_job_id": os.environ.get("SLURM_JOB_ID"),
        "slurm_cluster_name": os.environ.get("SLURM_CLUSTER_NAME"),
    }
    return {key: value for key, value in environment.items() if value}


def _cpu_model() -> Optional[str]:
    cpuinfo = Path("/proc/cpuinfo")
    if cpuinfo.exists():
        for line in cpuinfo.read_text().splitlines():
            if line.startswith("model name"):
                return line.split(":", 1)[1].strip()
    return platform.processor() or None


def _memory_bytes() -> Optional[int]:
    try:
        return os.sysconf("SC_PAGE_SIZE") * os.sysconf("SC_PHYS_PAGES")
    except (ValueError, OSError, AttributeError):
        return None


def _nvidia_gpus() -> dict[str, Any]:
    """Return the model, count, memory and driver version of the NVIDIA GPUs reported by nvidia-smi."""
    nvidia_smi = shutil.which("nvidia-smi")
    if not nvidia_smi:
        return {}
    try:
        output = subprocess.run([nvidia_smi, "--query-gpu=name,memory.total,driver_version", "--format=csv,noheader,nounits"],
                                capture_output=True, text=True, timeout=30, check=True).stdout
    except (OSError, subprocess.SubprocessError):
        return {}
    gpus = [[value.strip() for value in line.split(",")] for line in output.strip().splitlines() if line.count(",") == 2]
    if not gpus:
        return {}
    return {
        "gpu_model": ", ".join(dict.fromkeys(name for name, _, _ in gpus)),
        "gpu_count": len(gpus),
        "gpu_memory_bytes": int(gpus[0][1]) * 1024 * 1024 if gpus[0][1].isdigit() else None,
        "gpu_driver_version": gpus[0][2],
    }
