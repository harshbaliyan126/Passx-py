import os
import shutil
import tempfile
from pathlib import Path


def atomic_write(path, data):
    """Write data to path so that a crash leaves either the old or the new file."""
    path = Path(path)
    fd, tmp = tempfile.mkstemp(dir=path.parent, prefix='.' + path.name + '.')
    try:
        with os.fdopen(fd, 'wb') as f:
            f.write(data)
            f.flush()
            os.fsync(f.fileno())
        if path.exists():
            shutil.copy2(path, path.with_name(path.name + '.bak'))
        os.replace(tmp, path)
    except BaseException:
        if os.path.exists(tmp):
            os.remove(tmp)
        raise
