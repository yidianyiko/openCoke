#!/usr/bin/env bash
set -euo pipefail

REMOTE_HOST="${REMOTE_HOST:-gcp-coke}"
REMOTE_ROOT="${REMOTE_ROOT:-/home/whoami/coke-clean}"
REMOTE_OLD_ROOT="${REMOTE_OLD_ROOT:-/home/whoami/coke}"
PROJECT_NAME="${PROJECT_NAME:-coke-clean}"
COKE_CLEAN_API_PORT="${COKE_CLEAN_API_PORT:-8000}"
COKE_CLEAN_WEB_PORT="${COKE_CLEAN_WEB_PORT:-4042}"
COKE_CLEAN_POSTGRES_PORT="${COKE_CLEAN_POSTGRES_PORT:-55432}"
COKE_CLEAN_REDIS_PORT="${COKE_CLEAN_REDIS_PORT:-56379}"

DRY_RUN=0
for arg in "$@"; do
  case "$arg" in
    --dry-run)
      DRY_RUN=1
      ;;
    -h|--help)
      cat <<USAGE
Usage: scripts/deploy-compose-to-gcp.sh [--dry-run]

Environment:
  REMOTE_HOST=${REMOTE_HOST}
  REMOTE_ROOT=${REMOTE_ROOT}
  REMOTE_OLD_ROOT=${REMOTE_OLD_ROOT}
  PROJECT_NAME=${PROJECT_NAME}
  COKE_CLEAN_API_PORT=${COKE_CLEAN_API_PORT}
  COKE_CLEAN_WEB_PORT=${COKE_CLEAN_WEB_PORT}
  COKE_CLEAN_POSTGRES_PORT=${COKE_CLEAN_POSTGRES_PORT}
  COKE_CLEAN_REDIS_PORT=${COKE_CLEAN_REDIS_PORT}
USAGE
      exit 0
      ;;
    *)
      echo "Unknown argument: $arg" >&2
      exit 2
      ;;
  esac
done

LOCAL_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
RSYNC_SOURCES=(
  "coke/"
  "web/"
  "migrations/"
  "docker-compose.prod.yml"
  "docker-compose.clean.yml"
  "Dockerfile"
  ".dockerignore"
  "requirements.txt"
  "alembic.ini"
  "deploy/"
  "scripts/"
)
RSYNC_EXCLUDES=(
  "--exclude=.git"
  "--exclude=.venv"
  "--exclude=.worktrees"
  "--exclude=.env"
  "--exclude=__pycache__"
  "--exclude=node_modules"
  "--exclude=.pnpm-store"
)

log() {
  printf '[deploy-clean] %s\n' "$*"
}

if [[ "$DRY_RUN" == "1" ]]; then
  log "dry run: would create ${REMOTE_HOST}:${REMOTE_ROOT}"
  log "dry run: would rsync clean stack sources"
  (
    cd "$LOCAL_ROOT"
    printf 'rsync -az --delete --relative --dry-run'
    printf ' %q' "${RSYNC_EXCLUDES[@]}"
    printf ' %q' "${RSYNC_SOURCES[@]}"
    printf ' %q\n' "${REMOTE_HOST}:${REMOTE_ROOT}/"
  )
  log "dry run: would write ${REMOTE_ROOT}/.env from existing clean env and ${REMOTE_OLD_ROOT}/.env without printing secrets"
  log "dry run: would run docker compose -p \"$PROJECT_NAME\" -f docker-compose.prod.yml -f docker-compose.clean.yml up -d --build"
  log "dry run: would run alembic upgrade head, alembic check, and curl -fsS \"http://127.0.0.1:${COKE_CLEAN_API_PORT}/healthz\""
  log "dry run: would curl -fsS \"http://127.0.0.1:${COKE_CLEAN_WEB_PORT}/auth/login\""
  exit 0
fi

log "creating clean remote root ${REMOTE_HOST}:${REMOTE_ROOT}"
ssh "$REMOTE_HOST" "mkdir -p '$REMOTE_ROOT'"

log "rsync clean stack sources"
(
  cd "$LOCAL_ROOT"
  rsync -az --delete --relative \
    "${RSYNC_EXCLUDES[@]}" \
    "${RSYNC_SOURCES[@]}" \
    "${REMOTE_HOST}:${REMOTE_ROOT}/"
)

log "writing clean runtime env on remote host"
ssh "$REMOTE_HOST" \
  "REMOTE_ROOT='$REMOTE_ROOT' REMOTE_OLD_ROOT='$REMOTE_OLD_ROOT' bash -se" <<'REMOTE_ENV'
set -euo pipefail

old_env="${REMOTE_OLD_ROOT}/.env"
clean_env="${REMOTE_ROOT}/.env"

if [[ ! -r "$old_env" && ! -r "$clean_env" ]]; then
  echo "No readable env source: $clean_env or $old_env" >&2
  exit 1
fi

read_env_from_file() {
  local file="$1"
  local key="$2"
  local line value
  if [[ ! -r "$file" ]]; then
    printf ''
    return
  fi
  line="$(grep -E "^${key}=" "$file" | tail -n 1 || true)"
  if [[ -z "$line" ]]; then
    printf ''
    return
  fi
  value="${line#*=}"
  value="${value%$'\r'}"
  if [[ "$value" == \"*\" && "$value" == *\" ]]; then
    value="${value:1:${#value}-2}"
  elif [[ "$value" == \'*\' && "$value" == *\' ]]; then
    value="${value:1:${#value}-2}"
  fi
  printf '%s' "$value"
}

read_env() {
  local key="$1"
  local value
  value="$(read_env_from_file "$clean_env" "$key")"
  if [[ -n "$value" ]]; then
    printf '%s' "$value"
    return
  fi
  read_env_from_file "$old_env" "$key"
}

rewrite_evolution_base() {
  local value="$1"
  value="${value//127.0.0.1/host.docker.internal}"
  value="${value//localhost/host.docker.internal}"
  printf '%s' "$value"
}

siliconflow_api_key="$(read_env SiliconFlow_API_KEY)"
evolution_base="$(read_env COKE_PROVIDER_EVOLUTION_BASE_URL)"
if [[ -z "$evolution_base" ]]; then
  evolution_base="$(read_env WHATSAPP_EVOLUTION_API_BASE)"
fi
evolution_base="$(rewrite_evolution_base "$evolution_base")"
evolution_api_key="$(read_env COKE_PROVIDER_EVOLUTION_API_KEY)"
if [[ -z "$evolution_api_key" ]]; then
  evolution_api_key="$(read_env WHATSAPP_EVOLUTION_API_KEY)"
fi
evolution_instance="$(read_env COKE_PROVIDER_EVOLUTION_INSTANCE)"
if [[ -z "$evolution_instance" ]]; then
  evolution_instance="$(read_env WHATSAPP_EVOLUTION_INSTANCE)"
fi
if [[ -z "$evolution_instance" ]]; then
  evolution_instance="coke"
fi
wechat_personal_endpoint="$(read_env COKE_PROVIDER_WECHAT_PERSONAL_ENDPOINT_URL)"
if [[ -z "$wechat_personal_endpoint" ]]; then
  wechat_personal_endpoint="http://host.docker.internal:8095/send"
fi
wechat_personal_api_key="$(read_env COKE_PROVIDER_WECHAT_PERSONAL_API_KEY)"

missing=()
[[ -n "$siliconflow_api_key" ]] || missing+=("SiliconFlow_API_KEY")
[[ -n "$evolution_base" ]] || missing+=("COKE_PROVIDER_EVOLUTION_BASE_URL")
[[ -n "$evolution_api_key" ]] || missing+=("COKE_PROVIDER_EVOLUTION_API_KEY")
if (( ${#missing[@]} > 0 )); then
  printf 'Missing required clean env keys: %s\n' "${missing[*]}" >&2
  exit 1
fi

umask 077
cat > "$clean_env" <<EOF
DATABASE_URL=postgresql+psycopg://coke:coke@postgres:5432/coke
REDIS_URL=redis://redis:6379/0
APP_ENV=production
AGNO_TELEMETRY=false
COKE_AGNO_CREATE_SCHEMA=1
SiliconFlow_API_KEY=${siliconflow_api_key}
COKE_PROVIDER_EVOLUTION_BASE_URL=${evolution_base}
COKE_PROVIDER_EVOLUTION_API_KEY=${evolution_api_key}
COKE_PROVIDER_EVOLUTION_INSTANCE=${evolution_instance}
COKE_PROVIDER_WECHAT_PERSONAL_ENDPOINT_URL=${wechat_personal_endpoint}
NEXT_PUBLIC_API_BASE_URL=https://coke.keep4oforever.com
NEXT_PUBLIC_COKE_WEB_URL=https://coke.keep4oforever.com
EOF
if [[ -n "$wechat_personal_api_key" ]]; then
  printf 'COKE_PROVIDER_WECHAT_PERSONAL_API_KEY=%s\n' "$wechat_personal_api_key" >> "$clean_env"
fi
chmod 600 "$clean_env"
echo "Clean env written to $clean_env"
REMOTE_ENV

log "starting clean compose project ${PROJECT_NAME}"
ssh "$REMOTE_HOST" \
  "REMOTE_ROOT='$REMOTE_ROOT' PROJECT_NAME='$PROJECT_NAME' COKE_CLEAN_API_PORT='$COKE_CLEAN_API_PORT' COKE_CLEAN_WEB_PORT='$COKE_CLEAN_WEB_PORT' COKE_CLEAN_POSTGRES_PORT='$COKE_CLEAN_POSTGRES_PORT' COKE_CLEAN_REDIS_PORT='$COKE_CLEAN_REDIS_PORT' bash -se" <<'REMOTE_DEPLOY'
set -euo pipefail

cd "$REMOTE_ROOT"
export COKE_CLEAN_API_PORT COKE_CLEAN_WEB_PORT COKE_CLEAN_POSTGRES_PORT COKE_CLEAN_REDIS_PORT
export COKE_API_PORT="$COKE_CLEAN_API_PORT"
export COKE_WEB_PORT="$COKE_CLEAN_WEB_PORT"

docker compose -p "$PROJECT_NAME" -f docker-compose.prod.yml -f docker-compose.clean.yml up -d --build
docker compose -p "$PROJECT_NAME" -f docker-compose.prod.yml -f docker-compose.clean.yml run --rm coke-migrate alembic upgrade head
docker compose -p "$PROJECT_NAME" -f docker-compose.prod.yml -f docker-compose.clean.yml run --rm coke-migrate alembic check

for _ in $(seq 1 60); do
  if curl -fsS "http://127.0.0.1:${COKE_CLEAN_API_PORT}/healthz" >/dev/null \
    && curl -fsS "http://127.0.0.1:${COKE_CLEAN_WEB_PORT}/auth/login" >/dev/null; then
    curl -fsS "http://127.0.0.1:${COKE_CLEAN_API_PORT}/healthz"
    printf '\n'
    exit 0
  fi
  sleep 2
done

docker compose -p "$PROJECT_NAME" -f docker-compose.prod.yml -f docker-compose.clean.yml ps
curl -fsS "http://127.0.0.1:${COKE_CLEAN_API_PORT}/healthz"
curl -fsS "http://127.0.0.1:${COKE_CLEAN_WEB_PORT}/auth/login"
REMOTE_DEPLOY

log "clean deploy health checks passed"
