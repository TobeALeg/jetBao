#!/usr/bin/env bash

set -Eeuo pipefail

APP_DIR="${APP_DIR:-/opt/jetbao}"
APP_SUBDIR="${APP_DIR}/app"
APP_ENV_FILE="${APP_DIR}/.env"
COMPOSE_FILE="${APP_SUBDIR}/compose.production.yml"
SSO_ENV_FILE="${APP_SUBDIR}/sso.env"
RELEASE_FILE="${APP_SUBDIR}/release.env"
PREVIOUS_COMPOSE_FILE="${APP_SUBDIR}/compose.production.yml.previous"
PREVIOUS_SSO_ENV_FILE="${APP_SUBDIR}/sso.env.previous"
PREVIOUS_RELEASE_FILE="${APP_SUBDIR}/release.env.previous"
CANDIDATE_COMPOSE_FILE="${CANDIDATE_COMPOSE_FILE:-${APP_SUBDIR}/compose.production.yml.candidate}"
CANDIDATE_SSO_ENV_FILE="${CANDIDATE_SSO_ENV_FILE:-${APP_SUBDIR}/sso.env.candidate}"
DEPLOY_LOCK_FILE="${DEPLOY_LOCK_FILE:-/var/lock/mentti-docker-deploy.lock}"
BACKUP_DIR="${BACKUP_DIR:-${APP_DIR}/backups/sqlite}"
BACKUP_RETENTION_COUNT="${BACKUP_RETENTION_COUNT:-20}"
PUBLIC_BASE_URL="${PUBLIC_BASE_URL:-https://jetbao.mentti.work}"
PULL_ATTEMPTS="${PULL_ATTEMPTS:-2}"
PULL_RETRY_DELAY="${PULL_RETRY_DELAY:-15}"
MIN_AVAILABLE_BYTES="${MIN_AVAILABLE_BYTES:-4294967296}"
MIN_AVAILABLE_PERCENT="${MIN_AVAILABLE_PERCENT:-10}"
IMAGE_PRUNER="${IMAGE_PRUNER:-${APP_DIR}/scripts/prune_docker_images.py}"

: "${IMAGE_PREFIX:?IMAGE_PREFIX is required}"
: "${IMAGE_TAG:?IMAGE_TAG is required}"
if [[ ! "${IMAGE_TAG}" =~ ^[0-9a-f]{40}$ ]]; then
  echo "IMAGE_TAG must be a lowercase 40-character commit SHA" >&2
  exit 1
fi

for required_file in \
  "${APP_ENV_FILE}" \
  "${CANDIDATE_COMPOSE_FILE}" \
  "${CANDIDATE_SSO_ENV_FILE}"; do
  if [[ ! -f "${required_file}" ]]; then
    echo "Missing deployment file: ${required_file}" >&2
    exit 1
  fi
done

for command_name in docker flock curl python3; do
  command -v "${command_name}" >/dev/null
done
docker info >/dev/null

# The lock is bootstrapped once as root:docker 0664. Deployments only acquire it.
if [[ ! -e "${DEPLOY_LOCK_FILE}" ]]; then
  echo "Missing host deployment lock: ${DEPLOY_LOCK_FILE}" >&2
  exit 1
fi
exec 9<>"${DEPLOY_LOCK_FILE}"
echo "Waiting for host deployment lock: ${DEPLOY_LOCK_FILE}"
flock -w 1800 9
echo "Host deployment lock acquired"

check_disk_capacity() {
  local available_kb
  local used_percent
  local available_bytes
  local available_percent

  read -r available_kb used_percent < <(
    df -Pk "${APP_DIR}" | awk 'NR == 2 { gsub(/%/, "", $5); print $4, $5 }'
  )
  if [[ ! "${available_kb}" =~ ^[0-9]+$ || ! "${used_percent}" =~ ^[0-9]+$ ]]; then
    echo "Cannot determine disk capacity for ${APP_DIR}" >&2
    return 1
  fi
  available_bytes=$((available_kb * 1024))
  available_percent=$((100 - used_percent))
  echo "Disk preflight: available=${available_bytes} bytes (${available_percent}%)"
  if ((available_bytes < MIN_AVAILABLE_BYTES || available_percent < MIN_AVAILABLE_PERCENT)); then
    echo "Insufficient disk space: require at least ${MIN_AVAILABLE_BYTES} bytes and ${MIN_AVAILABLE_PERCENT}% available" >&2
    df -h "${APP_DIR}" >&2 || true
    docker system df >&2 || true
    return 1
  fi
}

check_disk_capacity

initialize_release_baseline() {
  [[ -s "${RELEASE_FILE}" ]] && return 0

  local backend_image
  local frontend_image
  local backend_prefix="${IMAGE_PREFIX}-backend:"
  local frontend_prefix="${IMAGE_PREFIX}-frontend:"
  local backend_tag
  local frontend_tag
  local baseline_release
  local backend_exists=0
  local frontend_exists=0

  docker container inspect jetbao-backend-1 >/dev/null 2>&1 && backend_exists=1
  docker container inspect jetbao-frontend-1 >/dev/null 2>&1 && frontend_exists=1

  if ((backend_exists == 0 && frontend_exists == 0)); then
    echo "No running release found; continuing as a new installation"
    return 0
  fi
  if ((backend_exists != 1 || frontend_exists != 1)); then
    echo "Cannot establish rollback baseline: both production containers must exist" >&2
    return 1
  fi

  backend_image="$(
    docker container inspect --format '{{ .Config.Image }}' jetbao-backend-1
  )" || {
    echo "Cannot inspect the current backend image for rollback" >&2
    return 1
  }
  frontend_image="$(
    docker container inspect --format '{{ .Config.Image }}' jetbao-frontend-1
  )" || {
    echo "Cannot inspect the current frontend image for rollback" >&2
    return 1
  }

  if [[ "${backend_image}" != "${backend_prefix}"* || "${frontend_image}" != "${frontend_prefix}"* ]]; then
    echo "Cannot establish rollback baseline from unexpected image names" >&2
    return 1
  fi
  backend_tag="${backend_image#"${backend_prefix}"}"
  frontend_tag="${frontend_image#"${frontend_prefix}"}"
  if [[ -z "${backend_tag}" || "${backend_tag}" != "${frontend_tag}" ]]; then
    echo "Cannot establish rollback baseline: backend and frontend image tags differ" >&2
    return 1
  fi

  baseline_release="$(mktemp "${APP_SUBDIR}/.release.env.baseline.XXXXXX")"
  printf 'IMAGE_PREFIX=%s\nIMAGE_TAG=%s\n' "${IMAGE_PREFIX}" "${backend_tag}" >"${baseline_release}"
  chmod 600 "${baseline_release}"
  mv -f "${baseline_release}" "${RELEASE_FILE}"
  echo "Initialized release baseline from running containers: ${backend_tag}"
}

initialize_release_baseline

candidate_release="$(mktemp "${APP_SUBDIR}/.release.env.candidate.XXXXXX")"
deployment_started=0

compose_release() {
  local manifest="$1"
  local sso_env="$2"
  local release_env="$3"
  shift 3

  local args=(
    compose
    -f "${manifest}"
    --env-file "${APP_ENV_FILE}"
  )
  if [[ -s "${sso_env}" ]]; then
    args+=(--env-file "${sso_env}")
  fi
  args+=(--env-file "${release_env}")
  docker "${args[@]}" "$@"
}

cleanup() {
  local status=$?
  trap - EXIT

  rm -f \
    "${candidate_release}" \
    "${CANDIDATE_COMPOSE_FILE}" \
    "${CANDIDATE_SSO_ENV_FILE}"

  if ((status != 0 && deployment_started == 1)) && \
    [[ -s "${COMPOSE_FILE}" && -s "${RELEASE_FILE}" ]]; then
    echo "Deployment failed; restoring the last successful application release" >&2
    compose_release \
      "${COMPOSE_FILE}" \
      "${SSO_ENV_FILE}" \
      "${RELEASE_FILE}" \
      up -d --remove-orphans --force-recreate --wait --wait-timeout 180 || true
  elif ((status != 0 && deployment_started == 1)); then
    echo "Deployment failed and no previous application release is available" >&2
  fi

  exit "${status}"
}
trap cleanup EXIT

printf 'IMAGE_PREFIX=%s\nIMAGE_TAG=%s\n' "${IMAGE_PREFIX}" "${IMAGE_TAG}" >"${candidate_release}"
chmod 600 "${candidate_release}"

pull_images() {
  local attempt
  for ((attempt = 1; attempt <= PULL_ATTEMPTS; attempt += 1)); do
    echo "Pulling release ${IMAGE_TAG} (attempt ${attempt}/${PULL_ATTEMPTS})"
    if compose_release \
      "${CANDIDATE_COMPOSE_FILE}" \
      "${CANDIDATE_SSO_ENV_FILE}" \
      "${candidate_release}" \
      pull; then
      return 0
    fi
    if ((attempt < PULL_ATTEMPTS)); then
      echo "Image pull failed; retrying in ${PULL_RETRY_DELAY}s" >&2
      sleep "${PULL_RETRY_DELAY}"
    fi
  done
  return 1
}

backup_database() {
  local source_database="${APP_DIR}/data/jetbao.sqlite3"
  if [[ ! -f "${source_database}" ]]; then
    echo "No SQLite database found; skipping backup for a new installation"
    return 0
  fi

  mkdir -p "${BACKUP_DIR}"
  python3 - "${source_database}" "${BACKUP_DIR}" "${IMAGE_TAG}" "${BACKUP_RETENTION_COUNT}" <<'PY'
from __future__ import annotations

import datetime
import sqlite3
import sys
from pathlib import Path

source = Path(sys.argv[1])
backup_dir = Path(sys.argv[2])
image_tag = sys.argv[3]
retention_count = int(sys.argv[4])
if retention_count < 1:
    raise SystemExit("BACKUP_RETENTION_COUNT must be at least 1")

timestamp = datetime.datetime.now(datetime.UTC).strftime("%Y%m%dT%H%M%SZ")
target = backup_dir / f"jetbao-{timestamp}-{image_tag}.sqlite3"
temporary = target.with_suffix(".sqlite3.tmp")

try:
    with sqlite3.connect(f"file:{source}?mode=ro", uri=True) as source_db:
        with sqlite3.connect(temporary) as backup_db:
            source_db.backup(backup_db)
    with sqlite3.connect(f"file:{temporary}?mode=ro", uri=True) as backup_db:
        result = backup_db.execute("PRAGMA integrity_check").fetchone()
    if not result or result[0] != "ok":
        raise RuntimeError(f"backup integrity check failed: {result}")
    temporary.chmod(0o600)
    temporary.replace(target)
finally:
    temporary.unlink(missing_ok=True)

backups = sorted(
    backup_dir.glob("jetbao-*.sqlite3"),
    key=lambda path: path.stat().st_mtime,
    reverse=True,
)
for stale_backup in backups[retention_count:]:
    stale_backup.unlink()

print(f"Created consistent SQLite backup: {target}")
PY
}

wait_for_url() {
  local label="$1"
  local url="$2"
  local attempt
  for attempt in {1..20}; do
    if curl --silent --show-error --fail --max-time 10 --output /dev/null "${url}"; then
      echo "${label} is ready: ${url}"
      return 0
    fi
    sleep 3
  done
  echo "${label} did not become ready: ${url}" >&2
  return 1
}

pull_images
backup_database

deployment_started=1
compose_release \
  "${CANDIDATE_COMPOSE_FILE}" \
  "${CANDIDATE_SSO_ENV_FILE}" \
  "${candidate_release}" \
  up -d --remove-orphans --wait --wait-timeout 180

wait_for_url "Local API" "http://127.0.0.1:18000/api/health"
wait_for_url "Local Web" "http://127.0.0.1:18080/"
wait_for_url "Public API" "${PUBLIC_BASE_URL}/api/health"
wait_for_url "Public Web" "${PUBLIC_BASE_URL}/"

promote_candidate_contract() {
  local promotion_dir
  local had_compose=0
  local had_sso=0
  local had_release=0
  local had_previous_compose=0
  local had_previous_sso=0
  local had_previous_release=0

  promotion_dir="$(mktemp -d "${APP_SUBDIR}/.promotion.XXXXXX")"
  if [[ -f "${COMPOSE_FILE}" ]]; then
    cp -f "${COMPOSE_FILE}" "${promotion_dir}/compose.old"
    had_compose=1
  fi
  if [[ -f "${SSO_ENV_FILE}" ]]; then
    cp -f "${SSO_ENV_FILE}" "${promotion_dir}/sso.old"
    had_sso=1
  fi
  if [[ -f "${RELEASE_FILE}" ]]; then
    cp -f "${RELEASE_FILE}" "${promotion_dir}/release.old"
    had_release=1
  fi
  if [[ -f "${PREVIOUS_COMPOSE_FILE}" ]]; then
    cp -f "${PREVIOUS_COMPOSE_FILE}" "${promotion_dir}/compose.previous"
    had_previous_compose=1
  fi
  if [[ -f "${PREVIOUS_SSO_ENV_FILE}" ]]; then
    cp -f "${PREVIOUS_SSO_ENV_FILE}" "${promotion_dir}/sso.previous"
    had_previous_sso=1
  fi
  if [[ -f "${PREVIOUS_RELEASE_FILE}" ]]; then
    cp -f "${PREVIOUS_RELEASE_FILE}" "${promotion_dir}/release.previous"
    had_previous_release=1
  fi
  cp -f "${CANDIDATE_COMPOSE_FILE}" "${promotion_dir}/compose.next"
  cp -f "${CANDIDATE_SSO_ENV_FILE}" "${promotion_dir}/sso.next"
  cp -f "${candidate_release}" "${promotion_dir}/release.next"
  chmod 600 \
    "${promotion_dir}/sso.next" \
    "${promotion_dir}/release.next"

  restore_contract() {
    if ((had_compose == 1)); then
      cp -f "${promotion_dir}/compose.old" "${COMPOSE_FILE}"
    else
      rm -f "${COMPOSE_FILE}"
    fi
    if ((had_sso == 1)); then
      cp -f "${promotion_dir}/sso.old" "${SSO_ENV_FILE}"
      chmod 600 "${SSO_ENV_FILE}"
    else
      rm -f "${SSO_ENV_FILE}"
    fi
    if ((had_release == 1)); then
      cp -f "${promotion_dir}/release.old" "${RELEASE_FILE}"
      chmod 600 "${RELEASE_FILE}"
    else
      rm -f "${RELEASE_FILE}"
    fi
    if ((had_previous_compose == 1)); then
      cp -f "${promotion_dir}/compose.previous" "${PREVIOUS_COMPOSE_FILE}"
    else
      rm -f "${PREVIOUS_COMPOSE_FILE}"
    fi
    if ((had_previous_sso == 1)); then
      cp -f "${promotion_dir}/sso.previous" "${PREVIOUS_SSO_ENV_FILE}"
      chmod 600 "${PREVIOUS_SSO_ENV_FILE}"
    else
      rm -f "${PREVIOUS_SSO_ENV_FILE}"
    fi
    if ((had_previous_release == 1)); then
      cp -f "${promotion_dir}/release.previous" "${PREVIOUS_RELEASE_FILE}"
      chmod 600 "${PREVIOUS_RELEASE_FILE}"
    else
      rm -f "${PREVIOUS_RELEASE_FILE}"
    fi
  }

  write_previous_contract() {
    if ((had_compose == 1)); then
      cp -f "${promotion_dir}/compose.old" "${PREVIOUS_COMPOSE_FILE}" || return 1
    fi
    if ((had_sso == 1)); then
      cp -f "${promotion_dir}/sso.old" "${PREVIOUS_SSO_ENV_FILE}" || return 1
      chmod 600 "${PREVIOUS_SSO_ENV_FILE}" || return 1
    fi
    if ((had_release == 1)); then
      cp -f "${promotion_dir}/release.old" "${PREVIOUS_RELEASE_FILE}" || return 1
      chmod 600 "${PREVIOUS_RELEASE_FILE}" || return 1
    fi
  }

  if ! write_previous_contract; then
    restore_contract
    rm -rf "${promotion_dir}"
    return 1
  fi

  if ! mv -f "${promotion_dir}/compose.next" "${COMPOSE_FILE}"; then
    restore_contract
    rm -rf "${promotion_dir}"
    return 1
  fi
  if ! mv -f "${promotion_dir}/sso.next" "${SSO_ENV_FILE}"; then
    restore_contract
    rm -rf "${promotion_dir}"
    return 1
  fi
  if ! mv -f "${promotion_dir}/release.next" "${RELEASE_FILE}"; then
    restore_contract
    rm -rf "${promotion_dir}"
    return 1
  fi

  rm -rf "${promotion_dir}"
}

promote_candidate_contract

deployment_started=0

if [[ -f "${IMAGE_PRUNER}" ]]; then
  if ! python3 "${IMAGE_PRUNER}" \
    --apply \
    --repository-prefix "${IMAGE_PREFIX}-" \
    --release-root "${APP_DIR}" \
    --keep-per-repository 2 \
    --minimum-age-hours 24; then
    echo "Warning: release succeeded but stale JetBao image cleanup failed" >&2
  fi
fi

echo "Release ${IMAGE_TAG} deployed successfully"
