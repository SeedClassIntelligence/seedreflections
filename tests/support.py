import functools
import subprocess
import unittest


@functools.lru_cache(maxsize=1)
def bash_works():
    """True only when `bash` really runs. On Windows `bash` can be a launcher for WSL with no distribution installed."""
    try:
        return subprocess.run(["bash", "-c", "exit 0"], capture_output=True, timeout=20).returncode == 0
    except (OSError, subprocess.SubprocessError):
        return False


needs_bash = unittest.skipUnless(bash_works(), "a working bash is not available here (the deploy scripts target Linux)")
