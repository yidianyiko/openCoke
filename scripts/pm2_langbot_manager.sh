#!/bin/bash
# LangBot PM2 管理脚本

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
ECOSYSTEM_CONFIG="$PROJECT_ROOT/ecosystem.langbot.config.json"

case "$1" in
  start)
    echo "启动 LangBot 服务..."
    pm2 start "$ECOSYSTEM_CONFIG"
    pm2 save
    echo "✓ LangBot 已启动"
    pm2 status
    ;;

  stop)
    echo "停止 LangBot 服务..."
    pm2 stop langbot-core
    echo "✓ LangBot 已停止"
    ;;

  restart)
    echo "重启 LangBot 服务..."
    pm2 restart langbot-core
    echo "✓ LangBot 已重启"
    pm2 status
    ;;

  delete|remove)
    echo "删除 LangBot 服务..."
    pm2 delete langbot-core
    pm2 save
    echo "✓ LangBot 已删除"
    ;;

  status)
    echo "LangBot 服务状态:"
    pm2 status
    echo ""
    echo "详细信息:"
    pm2 describe langbot-core
    ;;

  logs)
    echo "LangBot 日志 (退出按 Ctrl+C):"
    pm2 logs langbot-core
    ;;

  monitor)
    echo "LangBot 实时监控 (退出按 q):"
    pm2 monit
    ;;

  startup)
    echo "设置开机自启动..."
    pm2 startup
    echo "请按照上面的提示执行命令，然后运行: pm2 save"
    ;;

  *)
    echo "LangBot PM2 管理脚本"
    echo ""
    echo "用法: $0 {start|stop|restart|status|logs|monitor|delete|startup}"
    echo ""
    echo "命令说明:"
    echo "  start    - 启动 LangBot 服务"
    echo "  stop     - 停止 LangBot 服务"
    echo "  restart  - 重启 LangBot 服务"
    echo "  status   - 查看服务状态"
    echo "  logs     - 查看实时日志"
    echo "  monitor  - 实时监控面板"
    echo "  delete   - 删除服务"
    echo "  startup  - 设置开机自启动"
    echo ""
    echo "示例:"
    echo "  $0 start      # 启动服务"
    echo "  $0 status     # 查看状态"
    echo "  $0 logs       # 查看日志"
    exit 1
    ;;
esac
