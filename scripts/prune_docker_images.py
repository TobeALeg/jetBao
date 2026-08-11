#!/usr/bin/env python3
"""Safely retain rollback-capable Docker images and remove only stale ones."""

from __future__ import annotations

import argparse
import json
import subprocess
from collections import defaultdict
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import NamedTuple, Sequence


class ImageRecord(NamedTuple):
    repository: str
    tag: str
    image_id: str
    created_at: datetime


def _run_docker(arguments: Sequence[str]) -> str:
    result = subprocess.run(
        ["docker", *arguments],
        check=True,
        capture_output=True,
        text=True,
    )
    return result.stdout


def _split_repo_tag(repo_tag: str) -> tuple[str, str]:
    repository, separator, tag = repo_tag.rpartition(":")
    if not separator or "/" in tag:
        return repo_tag, "<none>"
    return repository, tag


def load_images(repository_prefix: str | None = None) -> list[ImageRecord]:
    image_ids = {
        line.strip()
        for line in _run_docker(["image", "ls", "-q", "--no-trunc"]).splitlines()
        if line.strip()
    }
    if not image_ids:
        return []

    inspected = json.loads(_run_docker(["image", "inspect", *sorted(image_ids)]))
    images: list[ImageRecord] = []
    for item in inspected:
        created_at = datetime.fromisoformat(item["Created"].replace("Z", "+00:00"))
        tags = item.get("RepoTags") or ["<none>:<none>"]
        for repo_tag in tags:
            repository, tag = _split_repo_tag(repo_tag)
            if repository_prefix and not repository.startswith(repository_prefix):
                continue
            images.append(
                ImageRecord(repository, tag, item["Id"], created_at.astimezone(UTC))
            )
    return images


def load_active_image_ids() -> set[str]:
    container_ids = [
        line.strip()
        for line in _run_docker(["ps", "-aq"]).splitlines()
        if line.strip()
    ]
    if not container_ids:
        return set()
    return {
        line.strip()
        for line in _run_docker(
            ["inspect", "--format", "{{.Image}}", *container_ids]
        ).splitlines()
        if line.strip()
    }


def load_protected_release_tags(release_root: Path) -> set[str]:
    tags: set[str] = set()
    for release_file in release_root.rglob("release.env*"):
        try:
            lines = release_file.read_text(encoding="utf-8").splitlines()
        except (OSError, UnicodeError):
            continue
        for line in lines:
            key, separator, value = line.partition("=")
            if separator and (key == "IMAGE_TAG" or key.endswith("_IMAGE_TAG")):
                tag = value.strip()
                if tag:
                    tags.add(tag)
    return tags


def select_candidates(
    images: Sequence[ImageRecord],
    *,
    active_image_ids: set[str],
    protected_tags: set[str],
    keep_per_repository: int,
    minimum_age: timedelta,
    now: datetime,
) -> list[ImageRecord]:
    keep_ids = set(active_image_ids)
    records_by_repository: dict[str, list[ImageRecord]] = defaultdict(list)
    records_by_id: dict[str, list[ImageRecord]] = defaultdict(list)

    for image in images:
        records_by_id[image.image_id].append(image)
        if image.repository != "<none>":
            records_by_repository[image.repository].append(image)
        if image.tag in protected_tags or now - image.created_at < minimum_age:
            keep_ids.add(image.image_id)

    for records in records_by_repository.values():
        newest_ids: list[str] = []
        for record in sorted(records, key=lambda item: item.created_at, reverse=True):
            if record.image_id not in newest_ids:
                newest_ids.append(record.image_id)
            if len(newest_ids) >= keep_per_repository:
                break
        keep_ids.update(newest_ids)

    candidates = [
        records[0]
        for image_id, records in records_by_id.items()
        if image_id not in keep_ids
    ]
    return sorted(candidates, key=lambda item: item.created_at)


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Keep active, release-referenced, recent, and rollback images; "
            "preview stale candidates unless --apply is provided."
        )
    )
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--repository-prefix")
    parser.add_argument("--release-root", type=Path, default=Path("/opt"))
    parser.add_argument("--keep-per-repository", type=int, default=2)
    parser.add_argument("--minimum-age-hours", type=int, default=24)
    return parser.parse_args()


def main() -> int:
    args = _parse_args()
    if args.keep_per_repository < 1:
        raise SystemExit("--keep-per-repository must be at least 1")
    if args.minimum_age_hours < 1:
        raise SystemExit("--minimum-age-hours must be at least 1")

    images = load_images(args.repository_prefix)
    candidates = select_candidates(
        images,
        active_image_ids=load_active_image_ids(),
        protected_tags=load_protected_release_tags(args.release_root),
        keep_per_repository=args.keep_per_repository,
        minimum_age=timedelta(hours=args.minimum_age_hours),
        now=datetime.now(UTC),
    )

    mode = "APPLY" if args.apply else "DRY-RUN"
    print(f"Docker image retention mode={mode} candidates={len(candidates)}")
    for candidate in candidates:
        print(
            f"candidate {candidate.repository}:{candidate.tag} "
            f"{candidate.image_id} created={candidate.created_at.isoformat()}"
        )

    if not args.apply:
        return 0

    for candidate in candidates:
        if candidate.image_id in load_active_image_ids():
            print(f"skip newly active image {candidate.image_id}")
            continue
        _run_docker(["image", "rm", candidate.image_id])
        print(f"removed {candidate.image_id}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
