from __future__ import annotations

import re
import time
from dataclasses import dataclass
from io import BytesIO
from pathlib import Path
from secrets import token_hex
from typing import Iterator


EXPORT_FILE_TTL_SECONDS = 60 * 60
EXPORT_ID_PATTERN = re.compile(r"^[a-f0-9]{32}$")
RANGE_PATTERN = re.compile(r"^bytes=(\d+)-(\d*)$")


@dataclass(frozen=True)
class PreparedExportFile:
    export_id: str
    path: Path
    size: int


class ExportFileStore:
    def __init__(self, directory: Path) -> None:
        self.directory = directory

    def save(self, output: BytesIO) -> PreparedExportFile:
        self._ensure_directory()
        self.cleanup_expired()
        export_id = token_hex(16)
        path = self.directory / f"{export_id}.zip"
        path.write_bytes(output.getbuffer())
        path.chmod(0o600)
        return PreparedExportFile(export_id=export_id, path=path, size=path.stat().st_size)

    def resolve(self, export_id: str) -> Path | None:
        if not EXPORT_ID_PATTERN.fullmatch(export_id):
            return None
        path = self.directory / f"{export_id}.zip"
        if not path.is_file():
            return None
        if path.stat().st_mtime < time.time() - EXPORT_FILE_TTL_SECONDS:
            path.unlink(missing_ok=True)
            return None
        return path

    def delete(self, export_id: str) -> None:
        path = self.resolve(export_id)
        if path is not None:
            path.unlink(missing_ok=True)

    def cleanup_expired(self) -> None:
        if not self.directory.exists():
            return
        expires_before = time.time() - EXPORT_FILE_TTL_SECONDS
        for path in self.directory.glob("*.zip"):
            if EXPORT_ID_PATTERN.fullmatch(path.stem) and path.stat().st_mtime < expires_before:
                path.unlink(missing_ok=True)

    def _ensure_directory(self) -> None:
        self.directory.mkdir(mode=0o700, parents=True, exist_ok=True)
        self.directory.chmod(0o700)


def parse_byte_range(range_header: str | None, file_size: int) -> tuple[int, int] | None:
    if range_header is None:
        return None
    match = RANGE_PATTERN.fullmatch(range_header.strip())
    if match is None:
        raise ValueError("不支持的下载范围")
    start = int(match.group(1))
    end = int(match.group(2)) if match.group(2) else file_size - 1
    if start >= file_size or end < start:
        raise ValueError("下载范围超出文件大小")
    return start, min(end, file_size - 1)


def iterate_file_range(path: Path, start: int, end: int, chunk_size: int = 256 * 1024) -> Iterator[bytes]:
    remaining = end - start + 1
    with path.open("rb") as file:
        file.seek(start)
        while remaining:
            chunk = file.read(min(chunk_size, remaining))
            if not chunk:
                break
            remaining -= len(chunk)
            yield chunk
