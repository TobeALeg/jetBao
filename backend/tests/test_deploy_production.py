from __future__ import annotations

import os
import sqlite3
import subprocess
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
DEPLOY_SCRIPT = REPO_ROOT / "scripts" / "deploy-production.sh"
SHA = "3" * 40


def _write_executable(path: Path, content: str) -> None:
    path.write_text(content, encoding="utf-8")
    path.chmod(0o755)


def _prepare_fake_host(
    tmp_path: Path,
    *,
    pull_failures: int,
) -> tuple[Path, dict[str, str]]:
    app_dir = tmp_path / "jetbao"
    app_subdir = app_dir / "app"
    data_dir = app_dir / "data"
    app_subdir.mkdir(parents=True)
    data_dir.mkdir()
    (app_dir / ".env").write_text("SECRET_KEY=test\n", encoding="utf-8")
    (app_subdir / "compose.production.yml").write_text(
        "name: jetbao\nservices: {}\n",
        encoding="utf-8",
    )
    (app_subdir / "compose.production.yml.candidate").write_text(
        "name: jetbao\nservices: {candidate: {}}\n",
        encoding="utf-8",
    )
    (app_subdir / "sso.env").write_text("AUTH_MODE=legacy\n", encoding="utf-8")
    (app_subdir / "sso.env.candidate").write_text(
        "AUTH_MODE=hybrid\n",
        encoding="utf-8",
    )
    with sqlite3.connect(data_dir / "jetbao.sqlite3") as database:
        database.execute("CREATE TABLE marker (value TEXT NOT NULL)")
        database.execute("INSERT INTO marker VALUES ('before-deploy')")

    fake_bin = tmp_path / "bin"
    fake_bin.mkdir()
    docker_log = tmp_path / "docker.log"
    pull_count = tmp_path / "pull-count"
    lock_file = tmp_path / "deploy.lock"
    lock_file.touch()

    _write_executable(
        fake_bin / "docker",
        """#!/usr/bin/env bash
set -eu
echo "$*" >> "${DOCKER_LOG}"
if [[ "${1:-}" == "info" ]]; then
  exit 0
fi
if [[ "${1:-}" == "container" && "${2:-}" == "inspect" ]]; then
  container="${*: -1}"
  if [[ " $* " != *" --format "* ]]; then
    if [[ "${container}" == "jetbao-backend-1" && -n "${CURRENT_BACKEND_IMAGE:-}" ]]; then
      exit 0
    fi
    if [[ "${container}" == "jetbao-frontend-1" && -n "${CURRENT_FRONTEND_IMAGE:-}" ]]; then
      exit 0
    fi
  fi
  if [[ " $* " == *" .Config.Image "* ]]; then
    if [[ "${container}" == "jetbao-backend-1" && -n "${CURRENT_BACKEND_IMAGE:-}" ]]; then
      echo "${CURRENT_BACKEND_IMAGE}"
      exit 0
    fi
    if [[ "${container}" == "jetbao-frontend-1" && -n "${CURRENT_FRONTEND_IMAGE:-}" ]]; then
      echo "${CURRENT_FRONTEND_IMAGE}"
      exit 0
    fi
  fi
  exit 1
fi
if [[ "${1:-}" == "compose" ]]; then
  for arg in "$@"; do
    if [[ "${arg}" == *"/.release.env.candidate."* ]]; then
      cat "${arg}" >> "${DOCKER_LOG}"
    fi
  done
  if [[ " $* " == *" pull "* ]]; then
    count=0
    [[ -f "${PULL_COUNT}" ]] && count="$(cat "${PULL_COUNT}")"
    count=$((count + 1))
    echo "${count}" > "${PULL_COUNT}"
    if ((count <= PULL_FAILURES)); then
      exit 1
    fi
  fi
  exit 0
fi
exit 0
""",
    )
    _write_executable(fake_bin / "flock", "#!/usr/bin/env bash\nexit 0\n")
    _write_executable(
        fake_bin / "curl",
        """#!/usr/bin/env bash
if [[ -n "${CURL_FAIL_PATTERN:-}" && " $* " == *"${CURL_FAIL_PATTERN}"* ]]; then
  exit 1
fi
exit 0
""",
    )
    _write_executable(fake_bin / "sleep", "#!/usr/bin/env bash\nexit 0\n")
    _write_executable(
        fake_bin / "mv",
        """#!/usr/bin/env bash
target="${*: -1}"
if [[ -n "${MV_FAIL_TARGET:-}" && "${target}" == *"${MV_FAIL_TARGET}" &&
      ! -f "${MV_FAILURE_MARKER}" ]]; then
  touch "${MV_FAILURE_MARKER}"
  exit 1
fi
exec /bin/mv "$@"
""",
    )

    env = os.environ.copy()
    env.update(
        {
            "APP_DIR": str(app_dir),
            "BACKUP_DIR": str(app_dir / "backups" / "sqlite"),
            "DEPLOY_LOCK_FILE": str(lock_file),
            "DOCKER_LOG": str(docker_log),
            "IMAGE_PREFIX": "ghcr.io/example/jetbao",
            "IMAGE_TAG": SHA,
            "PATH": f"{fake_bin}:{env['PATH']}",
            "PULL_ATTEMPTS": "2",
            "PULL_FAILURES": str(pull_failures),
            "PULL_COUNT": str(pull_count),
            "PULL_RETRY_DELAY": "0",
            "PUBLIC_BASE_URL": "https://jetbao.example.test",
            "MV_FAILURE_MARKER": str(tmp_path / "mv-failed"),
        }
    )
    return app_dir, env


def _run_deploy(env: dict[str, str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["bash", str(DEPLOY_SCRIPT)],
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )


def test_success_retries_pull_backs_up_database_and_promotes_release(
    tmp_path: Path,
) -> None:
    app_dir, env = _prepare_fake_host(tmp_path, pull_failures=1)
    original_release = "IMAGE_PREFIX=ghcr.io/example/jetbao\nIMAGE_TAG=old-sha\n"
    (app_dir / "app" / "release.env").write_text(original_release, encoding="utf-8")

    result = _run_deploy(env)

    assert result.returncode == 0, result.stderr
    assert (app_dir / "app" / "release.env").read_text(encoding="utf-8") == (
        f"IMAGE_PREFIX=ghcr.io/example/jetbao\nIMAGE_TAG={SHA}\n"
    )
    assert (app_dir / "app" / "release.env.previous").read_text(
        encoding="utf-8"
    ) == original_release
    assert "candidate" in (
        app_dir / "app" / "compose.production.yml"
    ).read_text(encoding="utf-8")
    assert (app_dir / "app" / "sso.env").read_text(encoding="utf-8") == (
        "AUTH_MODE=hybrid\n"
    )
    backups = list((app_dir / "backups" / "sqlite").glob("jetbao-*.sqlite3"))
    assert len(backups) == 1
    with sqlite3.connect(backups[0]) as database:
        assert database.execute("PRAGMA integrity_check").fetchone() == ("ok",)
        assert database.execute("SELECT value FROM marker").fetchone() == (
            "before-deploy",
        )
    assert Path(env["PULL_COUNT"]).read_text().strip() == "2"


def test_failed_pull_keeps_release_and_does_not_create_backup(tmp_path: Path) -> None:
    app_dir, env = _prepare_fake_host(tmp_path, pull_failures=2)
    original_release = "IMAGE_PREFIX=ghcr.io/example/jetbao\nIMAGE_TAG=old-sha\n"
    (app_dir / "app" / "release.env").write_text(original_release, encoding="utf-8")

    result = _run_deploy(env)

    assert result.returncode != 0
    assert (app_dir / "app" / "release.env").read_text(
        encoding="utf-8"
    ) == original_release
    assert not (app_dir / "backups").exists()
    docker_log = Path(env["DOCKER_LOG"]).read_text(encoding="utf-8")
    assert " up -d" not in docker_log


def test_failed_health_rolls_back_app_but_never_restores_database(
    tmp_path: Path,
) -> None:
    app_dir, env = _prepare_fake_host(tmp_path, pull_failures=0)
    original_release = "IMAGE_PREFIX=ghcr.io/example/jetbao\nIMAGE_TAG=old-sha\n"
    (app_dir / "app" / "release.env").write_text(original_release, encoding="utf-8")
    env["CURL_FAIL_PATTERN"] = "https://jetbao.example.test/api/health"

    result = _run_deploy(env)

    assert result.returncode != 0
    assert "restoring the last successful application release" in result.stderr
    assert (app_dir / "app" / "release.env").read_text(
        encoding="utf-8"
    ) == original_release
    with sqlite3.connect(app_dir / "data" / "jetbao.sqlite3") as database:
        assert database.execute("SELECT value FROM marker").fetchone() == (
            "before-deploy",
        )
    assert len(list((app_dir / "backups" / "sqlite").glob("jetbao-*.sqlite3"))) == 1
    docker_log = Path(env["DOCKER_LOG"]).read_text(encoding="utf-8")
    assert "up -d --remove-orphans --wait --wait-timeout 180" in docker_log
    assert (
        "up -d --remove-orphans --force-recreate --wait --wait-timeout 180"
        in docker_log
    )


def test_first_contract_deploy_uses_running_release_as_baseline(
    tmp_path: Path,
) -> None:
    app_dir, env = _prepare_fake_host(tmp_path, pull_failures=0)
    env.update(
        {
            "CURRENT_BACKEND_IMAGE": "ghcr.io/example/jetbao-backend:old-sha",
            "CURRENT_FRONTEND_IMAGE": "ghcr.io/example/jetbao-frontend:old-sha",
        }
    )

    result = _run_deploy(env)

    assert result.returncode == 0, result.stderr
    assert "Initialized release baseline from running containers: old-sha" in result.stdout
    assert (app_dir / "app" / "release.env.previous").read_text(
        encoding="utf-8"
    ) == "IMAGE_PREFIX=ghcr.io/example/jetbao\nIMAGE_TAG=old-sha\n"


def test_existing_mismatched_images_block_deploy_without_baseline(
    tmp_path: Path,
) -> None:
    app_dir, env = _prepare_fake_host(tmp_path, pull_failures=0)
    env.update(
        {
            "CURRENT_BACKEND_IMAGE": "ghcr.io/example/jetbao-backend:backend-sha",
            "CURRENT_FRONTEND_IMAGE": "ghcr.io/example/jetbao-frontend:frontend-sha",
        }
    )

    result = _run_deploy(env)

    assert result.returncode != 0
    assert "backend and frontend image tags differ" in result.stderr
    assert not (app_dir / "app" / "release.env").exists()
    assert " pull" not in Path(env["DOCKER_LOG"]).read_text(encoding="utf-8")


def test_backup_failure_blocks_application_switch(tmp_path: Path) -> None:
    app_dir, env = _prepare_fake_host(tmp_path, pull_failures=0)
    original_release = "IMAGE_PREFIX=ghcr.io/example/jetbao\nIMAGE_TAG=old-sha\n"
    (app_dir / "app" / "release.env").write_text(original_release, encoding="utf-8")
    (app_dir / "data" / "jetbao.sqlite3").write_bytes(b"not a sqlite database")

    result = _run_deploy(env)

    assert result.returncode != 0
    docker_log = Path(env["DOCKER_LOG"]).read_text(encoding="utf-8")
    assert " up -d" not in docker_log
    assert (app_dir / "app" / "release.env").read_text(
        encoding="utf-8"
    ) == original_release


def test_missing_bootstrapped_lock_blocks_deploy(tmp_path: Path) -> None:
    app_dir, env = _prepare_fake_host(tmp_path, pull_failures=0)
    (app_dir / "app" / "release.env").write_text(
        "IMAGE_PREFIX=ghcr.io/example/jetbao\nIMAGE_TAG=old-sha\n",
        encoding="utf-8",
    )
    Path(env["DEPLOY_LOCK_FILE"]).unlink()

    result = _run_deploy(env)

    assert result.returncode != 0
    assert "Missing host deployment lock" in result.stderr
    assert " pull " not in f" {Path(env['DOCKER_LOG']).read_text()} "


def test_promotion_failure_restores_complete_previous_contract(
    tmp_path: Path,
) -> None:
    app_dir, env = _prepare_fake_host(tmp_path, pull_failures=0)
    app_subdir = app_dir / "app"
    original_release = "IMAGE_PREFIX=ghcr.io/example/jetbao\nIMAGE_TAG=old-sha\n"
    original_compose = (app_subdir / "compose.production.yml").read_text()
    original_sso = (app_subdir / "sso.env").read_text()
    (app_subdir / "release.env").write_text(original_release, encoding="utf-8")
    previous_files = {
        "compose.production.yml.previous": "previous-compose\n",
        "sso.env.previous": "previous-sso\n",
        "release.env.previous": "previous-release\n",
    }
    for name, content in previous_files.items():
        (app_subdir / name).write_text(content, encoding="utf-8")
    env["MV_FAIL_TARGET"] = "sso.env"

    result = _run_deploy(env)

    assert result.returncode != 0
    assert (app_subdir / "compose.production.yml").read_text() == original_compose
    assert (app_subdir / "sso.env").read_text() == original_sso
    assert (app_subdir / "release.env").read_text() == original_release
    for name, content in previous_files.items():
        assert (app_subdir / name).read_text() == content
