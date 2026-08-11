from __future__ import annotations

import importlib.util
from datetime import UTC, datetime, timedelta
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT_PATH = REPO_ROOT / "scripts" / "prune_docker_images.py"


def _load_module():
    spec = importlib.util.spec_from_file_location("prune_docker_images", SCRIPT_PATH)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_select_candidates_preserves_active_release_recent_and_rollback_images() -> None:
    module = _load_module()
    now = datetime(2026, 8, 11, tzinfo=UTC)
    old = now - timedelta(days=10)
    recent = now - timedelta(hours=2)
    image = module.ImageRecord
    images = [
        image("repo/api", "active", "sha256:active", old),
        image("repo/api", "rollback", "sha256:rollback", old),
        image("repo/api", "recent", "sha256:recent", recent),
        image("repo/api", "newest", "sha256:newest", old + timedelta(days=3)),
        image("repo/api", "previous", "sha256:previous", old + timedelta(days=2)),
        image("repo/api", "stale", "sha256:stale", old),
        image("<none>", "<none>", "sha256:dangling", old),
    ]

    candidates = module.select_candidates(
        images,
        active_image_ids={"sha256:active"},
        protected_tags={"rollback"},
        keep_per_repository=2,
        minimum_age=timedelta(hours=24),
        now=now,
    )

    assert {candidate.image_id for candidate in candidates} == {
        "sha256:stale",
        "sha256:dangling",
        "sha256:previous",
    }


def test_select_candidates_keeps_all_tags_when_one_tag_protects_shared_image() -> None:
    module = _load_module()
    now = datetime(2026, 8, 11, tzinfo=UTC)
    created = now - timedelta(days=10)
    images = [
        module.ImageRecord("repo/api", "stale", "sha256:shared", created),
        module.ImageRecord("repo/api", "rollback", "sha256:shared", created),
    ]

    candidates = module.select_candidates(
        images,
        active_image_ids=set(),
        protected_tags={"rollback"},
        keep_per_repository=0,
        minimum_age=timedelta(hours=24),
        now=now,
    )

    assert candidates == []


def test_load_protected_release_tags_supports_multi_service_tag_names(
    tmp_path: Path,
) -> None:
    module = _load_module()
    release_file = tmp_path / "mentihub-geo" / "release.env.previous"
    release_file.parent.mkdir()
    release_file.write_text(
        "MONITOR_API_IMAGE_TAG=monitor-api-sha\n"
        "CONSOLE_WEB_IMAGE_TAG=console-web-sha\n"
        "IMAGE_TAG=single-service-sha\n"
        "IMAGE_PREFIX=ghcr.io/example/app\n",
        encoding="utf-8",
    )

    protected_tags = module.load_protected_release_tags(tmp_path)

    assert protected_tags == {
        "monitor-api-sha",
        "console-web-sha",
        "single-service-sha",
    }
