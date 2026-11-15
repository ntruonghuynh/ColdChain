"""Deterministic file output.

* CSV: UTF-8, ``\\n`` line endings, fixed column order, rows in a fixed order.
* gzip: ``mtime=0`` and no file name in the header, so the same content gives the
  same bytes with the same zlib build.
* Two hashes per file: ``sha256`` of the stored bytes (integrity of what is on disk)
  and ``content_sha256`` of the uncompressed CSV (reproducibility; independent of the
  zlib build used to compress).
"""

import csv
import gzip
import hashlib
import io
import json
from collections.abc import Iterable, Sequence
from pathlib import Path
from typing import Any


def sha256_hex(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def csv_bytes(columns: Sequence[str], rows: Iterable[dict[str, Any]]) -> tuple[bytes, int]:
    buffer = io.StringIO()
    writer = csv.writer(buffer, lineterminator="\n")
    writer.writerow(columns)
    count = 0
    for row in rows:
        writer.writerow(["" if row[c] is None else row[c] for c in columns])
        count += 1
    return buffer.getvalue().encode("utf-8"), count


def gzip_bytes(data: bytes) -> bytes:
    out = io.BytesIO()
    with gzip.GzipFile(filename="", mode="wb", fileobj=out, compresslevel=9, mtime=0) as gz:
        gz.write(data)
    return out.getvalue()


def write_table(out_dir: Path, rel_path: str, columns: Sequence[str], rows: Iterable[dict[str, Any]],
                role: str, description: str) -> dict[str, Any]:
    content, count = csv_bytes(columns, rows)
    stored = gzip_bytes(content) if rel_path.endswith(".gz") else content
    target = out_dir / rel_path
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(stored)
    return {
        "path": rel_path,
        "role": role,
        "format": "csv+gzip" if rel_path.endswith(".gz") else "csv",
        "description": description,
        "columns": list(columns),
        "rows": count,
        "bytes": len(stored),
        "sha256": sha256_hex(stored),
        "content_sha256": sha256_hex(content),
    }


def json_bytes(document: Any) -> bytes:
    return (json.dumps(document, indent=2, sort_keys=True, ensure_ascii=False) + "\n").encode("utf-8")


def read_content(path: Path) -> bytes:
    data = path.read_bytes()
    return gzip.decompress(data) if path.name.endswith(".gz") else data


def read_csv_rows(path: Path) -> list[dict[str, str]]:
    text = read_content(path).decode("utf-8")
    return list(csv.DictReader(io.StringIO(text)))
