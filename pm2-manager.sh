#!/bin/bash

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

ECOSYSTEM_CONFIG="ecosystem.config.json"
SERVICE_NAME="coke-agent"

show_help() {
    cat <<'EOF'
Coke Project PM2 管理脚本

用法:
  ./pm2-manager.sh <command> [service-name]

支持命令:
  start
  stop
  restart
  status
  logs
  delete
  save
  list

当前仅管理服务:
  coke-agent
EOF
}

service_arg="${2:-$SERVICE_NAME}"

case "${1:-help}" in
    start)
        if [[ -z "${2:-}" ]]; then
            pm2 start "$ECOSYSTEM_CONFIG"
            pm2 save
        else
            pm2 start "$service_arg"
        fi
        pm2 status
        ;;
    stop)
        if [[ -z "${2:-}" ]]; then
            pm2 stop all
        else
            pm2 stop "$service_arg"
        fi
        pm2 status
        ;;
    restart)
        if [[ -z "${2:-}" ]]; then
            pm2 restart all
        else
            pm2 restart "$service_arg"
        fi
        pm2 status
        ;;
    status)
        pm2 status
        ;;
    logs)
        if [[ -z "${2:-}" ]]; then
            pm2 logs --lines 100
        else
            pm2 logs "$service_arg" --lines 100
        fi
        ;;
    delete)
        if [[ -z "${2:-}" ]]; then
            pm2 delete all
        else
            pm2 delete "$service_arg"
        fi
        pm2 save --force
        ;;
    save)
        pm2 save
        ;;
    list)
        pm2 list
        ;;
    help|--help|-h)
        show_help
        ;;
    *)
        show_help
        exit 1
        ;;
esac
