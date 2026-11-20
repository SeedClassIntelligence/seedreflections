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


def remove_temp(temp):
    """Delete a TemporaryDirectory after a test. Windows will not delete a file another handle still has open, and a handle
    can outlive the code that opened it until the garbage collector runs, so collect first and allow a short, bounded wait.
    A file that is still locked after that raises with its name: a real leak is reported, never hidden."""
    import gc
    import time
    for attempt in range(10):
        gc.collect()
        try:
            temp.cleanup()
            return
        except PermissionError:
            if attempt == 9:
                raise
            time.sleep(0.3)
