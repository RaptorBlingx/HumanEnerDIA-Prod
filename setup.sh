#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$ROOT_DIR"

REQUESTED_SERVER_IP="${SERVER_IP:-}"
REQUESTED_OVOS_BRIDGE_HOST="${OVOS_BRIDGE_HOST:-}"
REQUESTED_OVOS_BRIDGE_PORT="${OVOS_BRIDGE_PORT:-}"
SERVER_IP=""
SERVER_IP_EXPLICIT=false
NO_BUILD=false
NO_START=false

usage() {
  cat <<'EOF'
Usage: ./setup.sh [--server-ip HOST_OR_IP] [--ovos-bridge-host HOST] [--ovos-bridge-port PORT] [--no-build] [--no-start]

Creates a local .env from .env.example when needed, fills first-run placeholder
secrets with generated values, validates Docker Compose, then builds and starts
the stack. Existing non-placeholder .env values are preserved.

Examples:
  ./setup.sh
  ./setup.sh --server-ip 192.168.1.50
  ./setup.sh --server-ip 192.168.1.50 --ovos-bridge-host host.docker.internal --ovos-bridge-port 5000
  SERVER_IP=energy-demo.local ./setup.sh
EOF
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --server-ip)
      REQUESTED_SERVER_IP="${2:?--server-ip requires a value}"
      SERVER_IP_EXPLICIT=true
      shift 2
      ;;
    --no-build)
      NO_BUILD=true
      shift
      ;;
    --ovos-bridge-host)
      REQUESTED_OVOS_BRIDGE_HOST="${2:?--ovos-bridge-host requires a value}"
      shift 2
      ;;
    --ovos-bridge-port)
      REQUESTED_OVOS_BRIDGE_PORT="${2:?--ovos-bridge-port requires a value}"
      shift 2
      ;;
    --no-start)
      NO_START=true
      shift
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      if [[ "$1" != -* && "$SERVER_IP_EXPLICIT" == "false" && -z "$REQUESTED_SERVER_IP" ]]; then
        REQUESTED_SERVER_IP="$1"
        SERVER_IP_EXPLICIT=true
        shift
      else
        echo "Unknown argument: $1" >&2
        usage >&2
        exit 1
      fi
      ;;
  esac
done

require_command() {
  local command_name="$1"
  local install_hint="$2"
  if ! command -v "$command_name" >/dev/null 2>&1; then
    echo "$command_name is required. $install_hint" >&2
    exit 1
  fi
}

random_hex() {
  local bytes="$1"
  if command -v openssl >/dev/null 2>&1; then
    openssl rand -hex "$bytes"
  else
    od -An -N "$bytes" -tx1 /dev/urandom | tr -d ' \n'
  fi
}

set_env_value() {
  local key="$1"
  local value="$2"
  local escaped
  escaped="$(printf '%s' "$value" | sed -e 's/[\/&]/\\&/g')"

  if grep -qE "^${key}=" .env; then
    sed -i "s|^${key}=.*|${key}=${escaped}|" .env
  else
    printf '%s=%s\n' "$key" "$value" >> .env
  fi
}

get_env_value() {
  local key="$1"
  grep -E "^${key}=" .env | tail -n 1 | cut -d= -f2- || true
}

get_env_or_default() {
  local key="$1"
  local default="$2"
  local current
  current="$(get_env_value "$key")"
  printf '%s\n' "${current:-$default}"
}

compose_env_escape() {
  printf '%s' "$1" | sed 's/\$/$$/g'
}

value_needs_generation() {
  local key="$1"
  local current
  current="$(get_env_value "$key")"
  [[ -z "$current" || "$current" == *"<CHANGE_ME"* ]]
}

ensure_secret() {
  local key="$1"
  local bytes="${2:-24}"
  if value_needs_generation "$key"; then
    set_env_value "$key" "$(random_hex "$bytes")"
  fi
}

generate_node_red_hash() {
  local password="$1"

  if python3 -c 'import bcrypt' >/dev/null 2>&1; then
    python3 - "$password" <<'PY'
import bcrypt
import sys

password = sys.argv[1].encode("utf-8")
print(bcrypt.hashpw(password, bcrypt.gensalt(rounds=12)).decode("utf-8"))
PY
    return
  fi

  if docker info >/dev/null 2>&1; then
    docker run --rm \
      -e NODE_RED_PLAIN_PASSWORD="$password" \
      --entrypoint sh \
      nodered/node-red:3.1.0 \
      -c 'printf "%s\n" "$NODE_RED_PLAIN_PASSWORD" | node-red admin hash-pw' \
      | awk '/Password:|^\$2[aby]\$/ { print $NF }' \
      | tail -n 1
    return
  fi

  echo "Unable to generate Node-RED bcrypt hash. Start Docker or install python3-bcrypt." >&2
  exit 1
}

prepare_env() {
  local env_created=false
  if [[ ! -f .env ]]; then
    if [[ ! -f .env.example ]]; then
      echo ".env is missing and .env.example was not found." >&2
      exit 1
    fi
    cp .env.example .env
    env_created=true
    echo "Created .env from .env.example"
  fi

  local current_server_ip
  current_server_ip="$(get_env_value SERVER_IP)"
  if [[ -n "$REQUESTED_SERVER_IP" ]]; then
    SERVER_IP="$REQUESTED_SERVER_IP"
    set_env_value SERVER_IP "$SERVER_IP"
  elif [[ -n "$current_server_ip" && "$current_server_ip" != *"<CHANGE_ME"* ]]; then
    SERVER_IP="$current_server_ip"
  else
    SERVER_IP="localhost"
    set_env_value SERVER_IP "$SERVER_IP"
  fi

  ensure_secret POSTGRES_PASSWORD 24
  ensure_secret GRAFANA_ADMIN_PASSWORD 20
  ensure_secret NODE_RED_CREDENTIAL_SECRET 24
  ensure_secret REDIS_PASSWORD 24
  ensure_secret MQTT_PASSWORD 24
  ensure_secret JWT_SECRET 32
  ensure_secret API_KEY 32

  if value_needs_generation NODE_RED_PASSWORD_HASH; then
    local node_red_password
    node_red_password="$(get_env_value NODE_RED_ADMIN_PASSWORD)"
    if [[ -z "$node_red_password" || "$node_red_password" == *"<CHANGE_ME"* ]]; then
      node_red_password="nr-$(random_hex 12)"
      set_env_value NODE_RED_ADMIN_PASSWORD "$node_red_password"
    fi
    set_env_value NODE_RED_PASSWORD_HASH "$(compose_env_escape "$(generate_node_red_hash "$node_red_password")")"
  elif [[ "$(get_env_value NODE_RED_PASSWORD_HASH)" == \$2* ]]; then
    set_env_value NODE_RED_PASSWORD_HASH "$(compose_env_escape "$(get_env_value NODE_RED_PASSWORD_HASH)")"
  fi

  local nginx_port
  nginx_port="$(get_env_value NGINX_HTTP_PORT)"
  nginx_port="${nginx_port:-8080}"

  local frontend_url
  frontend_url="$(get_env_value FRONTEND_URL)"
  if [[ -z "$frontend_url" || "$frontend_url" == "https://your-humanerdia-domain.example" || "$frontend_url" == *"<CHANGE_ME"* ]]; then
    set_env_value FRONTEND_URL "http://${SERVER_IP}:${nginx_port}"
  fi

  local grafana_root_url
  grafana_root_url="$(get_env_value GRAFANA_ROOT_URL)"
  if [[ "$env_created" == "true" || -z "$grafana_root_url" || "$grafana_root_url" == *'${SERVER_IP}'* || "$grafana_root_url" == *"<CHANGE_ME"* || "$SERVER_IP_EXPLICIT" == "true" ]]; then
    set_env_value GRAFANA_ROOT_URL "http://${SERVER_IP}:${nginx_port}/grafana"
  fi

  if [[ -n "$REQUESTED_OVOS_BRIDGE_HOST" ]]; then
    set_env_value OVOS_BRIDGE_HOST "$REQUESTED_OVOS_BRIDGE_HOST"
  fi

  if [[ -n "$REQUESTED_OVOS_BRIDGE_PORT" ]]; then
    set_env_value OVOS_BRIDGE_PORT "$REQUESTED_OVOS_BRIDGE_PORT"
  fi
}

compose_files=(-f docker-compose.yml)
if [[ -f docker-compose.ovos.yml ]]; then
  compose_files+=(-f docker-compose.ovos.yml)
  HAS_OVOS_OVERLAY=true
else
  HAS_OVOS_OVERLAY=false
fi

require_command docker "Install Docker Engine 20.10+ and Docker Compose v2."
docker compose version >/dev/null

prepare_env

if [[ "$HAS_OVOS_OVERLAY" == "true" ]]; then
  set_env_value OVOS_BRIDGE_HOST "ovos"
fi

if grep -Eq '^[[:space:]]*[^#].*<CHANGE_ME' .env; then
  echo "Placeholder values are still present in .env. Update them or rerun setup." >&2
  exit 1
fi

docker compose "${compose_files[@]}" config >/dev/null

if [[ "$NO_BUILD" != "true" ]]; then
  docker compose "${compose_files[@]}" build
fi

if [[ "$NO_START" != "true" ]]; then
  if docker compose up --help 2>/dev/null | grep -q -- '--wait'; then
    docker compose "${compose_files[@]}" up -d --wait --wait-timeout 420
  else
    docker compose "${compose_files[@]}" up -d
  fi
fi

if [[ "$NO_START" == "true" ]]; then
  STATUS_LABEL="Prepared"
else
  STATUS_LABEL="Started"
fi

cat <<EOF
${STATUS_LABEL} stack with compose files: ${compose_files[*]}

Access:
  Portal:      http://${SERVER_IP}:$(get_env_or_default NGINX_HTTP_PORT 8080)
  Grafana:     http://${SERVER_IP}:$(get_env_or_default NGINX_HTTP_PORT 8080)/grafana
  Analytics:   http://${SERVER_IP}:$(get_env_or_default ANALYTICS_PORT 8001)/api/v1/health

OVOS integration:
  API URL for separate OVOS package:
    http://${SERVER_IP}:$(get_env_or_default ANALYTICS_PORT 8001)/api/v1
  EnMS voice proxy target:
    http://$(get_env_or_default OVOS_BRIDGE_HOST host.docker.internal):$(get_env_or_default OVOS_BRIDGE_PORT 5000)

Generated first-run credentials are stored in .env. For production, rotate the
generated values, set DNS/TLS, and keep .env out of version control.
EOF
