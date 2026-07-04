#!/usr/bin/env bash

set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
VENV_PYTHON="${ROOT_DIR}/.venv/bin/python"
UVICORN_BIN="${ROOT_DIR}/.venv/bin/uvicorn"
API_HOST="${API_HOST:-127.0.0.1}"
API_PORT="${API_PORT:-9118}"
DASHBOARD_HOST="${DASHBOARD_HOST:-127.0.0.1}"
DASHBOARD_PORT="${DASHBOARD_PORT:-9119}"
LOG_DIR="${ROOT_DIR}/.run"
HEALTH_TIMEOUT_SECONDS="${HEALTH_TIMEOUT_SECONDS:-20}"
RELOAD_DELAY_SECONDS="${RELOAD_DELAY_SECONDS:-0.5}"

mkdir -p "${LOG_DIR}"

if [[ ! -x "${VENV_PYTHON}" ]]; then
  echo "Missing virtualenv python: ${VENV_PYTHON}" >&2
  echo "Run: python3 -m venv .venv && ./.venv/bin/pip install -e \".[dev]\"" >&2
  exit 1
fi

if [[ ! -x "${UVICORN_BIN}" ]]; then
  echo "Missing uvicorn binary: ${UVICORN_BIN}" >&2
  echo "Run: ./.venv/bin/pip install -e \".[dev]\"" >&2
  exit 1
fi

if [[ ! -d "${ROOT_DIR}/dashboard/node_modules" ]]; then
  echo "Missing dashboard dependencies: ${ROOT_DIR}/dashboard/node_modules" >&2
  echo "Run: cd dashboard && npm install && npm run build" >&2
  exit 1
fi

if [[ ! -f "${ROOT_DIR}/src/dashboard/static/index.html" ]] && [[ "${DEV_UI:-}" != "1" ]]; then
  echo "Missing built dashboard assets under src/dashboard/static" >&2
  echo "Run: cd dashboard && npm run build" >&2
  echo "Or set DEV_UI=1 to use Vite dev server with hot reload." >&2
  exit 1
fi

pids=()
service_names=()

port_is_listening() {
  local port="$1"
  if command -v lsof >/dev/null 2>&1; then
    lsof -nP -iTCP:"${port}" -sTCP:LISTEN >/dev/null 2>&1
    return $?
  fi
  (echo >/dev/tcp/127.0.0.1/"${port}") >/dev/null 2>&1
}

describe_port_listener() {
  local port="$1"
  if command -v lsof >/dev/null 2>&1; then
    lsof -nP -iTCP:"${port}" -sTCP:LISTEN 2>/dev/null || true
  else
    echo "  (install lsof to see which process owns port ${port})"
  fi
}

ensure_ports_available() {
  local conflicts=0

  if port_is_listening "${API_PORT}"; then
    echo "Port ${API_PORT} (API) is already in use:" >&2
    describe_port_listener "${API_PORT}" >&2
    conflicts=1
  fi

  if port_is_listening "${DASHBOARD_PORT}"; then
    echo "Port ${DASHBOARD_PORT} (dashboard) is already in use:" >&2
    describe_port_listener "${DASHBOARD_PORT}" >&2
    conflicts=1
  fi

  if [[ ${conflicts} -ne 0 ]]; then
    echo "Stop the process above or set API_PORT/DASHBOARD_PORT to free ports." >&2
    exit 1
  fi
}

verify_started_processes() {
  sleep 1
  local failed=0

  for i in "${!pids[@]}"; do
    if ! kill -0 "${pids[$i]}" 2>/dev/null; then
      echo "Service ${service_names[$i]} exited during startup (pid=${pids[$i]})." >&2
      echo "Check log: ${LOG_DIR}/${service_names[$i]}.log" >&2
      failed=1
    fi
  done

  if [[ ${failed} -ne 0 ]]; then
    exit 1
  fi
}

cleanup() {
  local exit_code=$?
  trap - EXIT INT TERM
  if [[ ${#pids[@]} -gt 0 ]]; then
    echo
    echo "Stopping Emperor services..."
    for pid in "${pids[@]}"; do
      if kill -0 "${pid}" 2>/dev/null; then
        kill "${pid}" 2>/dev/null || true
      fi
    done
    wait "${pids[@]}" 2>/dev/null || true
  fi
  exit "${exit_code}"
}

trap cleanup EXIT INT TERM

start_service() {
  local name="$1"
  shift
  local log_file="${LOG_DIR}/${name}.log"
  echo "Starting ${name}..."
  (
    cd "${ROOT_DIR}"
    exec "$@" >>"${log_file}" 2>&1
  ) &
  local pid=$!
  pids+=("${pid}")
  service_names+=("${name}")
  echo "  pid=${pid} log=${log_file}"
}

check_health() {
  local name="$1"
  local url="$2"
  local log_file="$3"
  local deadline=$((SECONDS + HEALTH_TIMEOUT_SECONDS))

  echo "Checking ${name} health: ${url}"
  while (( SECONDS < deadline )); do
    if curl -fsS "${url}" >/dev/null 2>&1; then
      echo "  ${name}: OK"
      return 0
    fi
    sleep 1
  done

  echo "  ${name}: FAILED"
  echo "  Check log: ${log_file}"
  return 1
}

ensure_ports_available

start_service "api" \
  "${UVICORN_BIN}" api.server:create_dev_api_app \
  --factory \
  --host "${API_HOST}" \
  --port "${API_PORT}" \
  --reload \
  --reload-delay "${RELOAD_DELAY_SECONDS}" \
  --reload-dir "${ROOT_DIR}/src"

start_service "dashboard" \
  "${UVICORN_BIN}" dashboard.server:create_dev_dashboard_app \
  --factory \
  --host "${DASHBOARD_HOST}" \
  --port "${DASHBOARD_PORT}" \
  --reload \
  --reload-delay "${RELOAD_DELAY_SECONDS}" \
  --reload-dir "${ROOT_DIR}/src"

if [[ -n "${TELEGRAM_BOT_TOKEN:-}" ]]; then
  start_service "gateway-telegram" \
    "${VENV_PYTHON}" -m cli.main gateway start --telegram
else
  echo "Skipping Telegram gateway: TELEGRAM_BOT_TOKEN is not set."
fi

verify_started_processes

echo
echo "Emperor services are running."
echo "  Dashboard: http://${DASHBOARD_HOST}:${DASHBOARD_PORT}"
echo "  API:       http://${API_HOST}:${API_PORT}"
resolved_home="${EMPEROR_HOME:-${HOME}/.emperor}"
echo "  EMPEROR_HOME=${resolved_home} (sessions: ${resolved_home}/profiles/<profile>/state.db)"
echo "  Mode:      dev / reload"
echo "Press Ctrl+C to stop all services."

health_failed=0
check_health "API" "http://${API_HOST}:${API_PORT}/health" "${LOG_DIR}/api.log" || health_failed=1
check_health "Dashboard" "http://${DASHBOARD_HOST}:${DASHBOARD_PORT}/health" "${LOG_DIR}/dashboard.log" || health_failed=1

if [[ ${health_failed} -ne 0 ]]; then
  echo
  echo "One or more services failed health checks."
  exit 1
fi

if [[ "${DEV_UI:-}" == "1" ]]; then
  DASHBOARD_DEV_PORT="${DASHBOARD_DEV_PORT:-5173}"
  echo
  echo "Starting Vite dev UI on http://${DASHBOARD_HOST}:${DASHBOARD_DEV_PORT} (proxy -> ${DASHBOARD_PORT})"
  start_service "dashboard-vite" \
    bash -lc "cd '${ROOT_DIR}/dashboard' && exec pnpm exec vite --host '${DASHBOARD_HOST}' --port '${DASHBOARD_DEV_PORT}'"
  echo "  Open http://${DASHBOARD_HOST}:${DASHBOARD_DEV_PORT}/ for hot reload."
fi

while true; do
  for i in "${!pids[@]}"; do
    if ! kill -0 "${pids[$i]}" 2>/dev/null; then
      echo "Service ${service_names[$i]} stopped unexpectedly (pid=${pids[$i]})." >&2
      echo "Check log: ${LOG_DIR}/${service_names[$i]}.log" >&2
      wait "${pids[$i]}" 2>/dev/null || true
      exit 1
    fi
  done
  sleep 1
done
