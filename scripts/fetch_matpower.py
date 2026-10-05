"""Download the official pinned MATPOWER release; never vendor it into git."""

import argparse
import hashlib
import io
import json
import urllib.request
import zipfile
from pathlib import Path

URL = "https://github.com/MATPOWER/matpower/releases/download/8.1/matpower8.1.zip"
SHA256 = "7f13b1441669a64e312d14a60e564cd91977ff1676ff77d25538e94ff313dd56"


def fetch(destination: Path) -> Path:
    """Verify archive and extracted file hashes, using an empty destination."""
    destination.mkdir(parents=True, exist_ok=False)
    with urllib.request.urlopen(URL, timeout=120) as response:
        data = response.read()
    if hashlib.sha256(data).hexdigest() != SHA256:
        raise ValueError("MATPOWER archive checksum mismatch")
    files = {}
    with zipfile.ZipFile(io.BytesIO(data)) as archive:
        for info in archive.infolist():
            target = destination / info.filename
            if not target.resolve().is_relative_to(destination.resolve()):
                raise ValueError("Unsafe archive member")
            if info.is_dir():
                target.mkdir(parents=True, exist_ok=True)
            else:
                target.parent.mkdir(parents=True, exist_ok=True)
                content = archive.read(info)
                target.write_bytes(content)
                files[info.filename] = hashlib.sha256(content).hexdigest()
    (destination / "provenance.json").write_text(
        json.dumps({"url": URL, "archive_sha256": SHA256, "files": files}, indent=2)
    )
    return destination / "matpower8.1"


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--destination", type=Path, required=True)
    print(fetch(parser.parse_args().destination).resolve())
