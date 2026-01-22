#!/bin/bash
# Coke Project PM2 统一管理脚本

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

ECOSYSTEM_CONFIG="ecosystem.config.json"

# 显示帮助信息
show_help() {
    echo "Coke Project PM2 管理脚本"
    echo ""
    echo "用法: $0 <command> [service-name]"
    echo ""
    echo "全局命令:"
    echo "  start           - 启动所有服务"
    echo "  stop            - 停止所有服务"
    echo "  restart         - 重启所有服务"
    echo "  status          - 查看所有服务状态"
    echo "  logs            - 查看所有服务日志"
    echo "  delete          - 删除所有服务配置"
    echo "  save            - 保存当前 PM2 配置"
    echo "  list            - 列出所有服务"
    echo ""
    echo "单服务命令:"
    echo "  start <name>    - 启动指定服务"
    echo "  stop <name>     - 停止指定服务"
    echo "  restart <name>  - 重启指定服务"
    echo "  logs <name>     - 查看指定服务日志"
    echo "  delete <name>   - 删除指定服务"
    echo ""
    echo "服务名称:"
    echo "  langbot-core    - LangBot 核心服务"
    echo "  coke-agent      - Agent 服务"
    echo "  ecloud-input    - E云管家 webhook 接收"
    echo "  ecloud-output   - E云管家消息发送"
    echo "  langbot-input   - LangBot webhook 接收"
    echo "  langbot-output  - LangBot 消息发送"
    echo ""
    echo "示例:"
    echo "  $0 start                    # 启动所有服务"
    echo "  $0 restart coke-agent       # 重启 Agent 服务"
    echo "  $0 logs ecloud-input        # 查看 ecloud-input 日志"
    echo "  $0 stop                     # 停止所有服务"
}

# 检查服务是否存在
check_service() {
    local service=$1
    if ! pm2 list | grep -q "$service"; then
        echo "错误: 服务 '$service' 不存在"
        echo "可用服务: langbot-core, coke-agent, ecloud-input, ecloud-output, langbot-input, langbot-output"
        return 1
    fi
    return 0
}

# 主逻辑
case "$1" in
    start)
        if [ -z "$2" ]; then
            echo "启动所有服务..."
            pm2 start "$ECOSYSTEM_CONFIG"
            pm2 save
        else
            echo "启动服务: $2"
            if check_service "$2"; then
                pm2 start "$2"
            fi
        fi
        echo ""
        pm2 status
        ;;

    stop)
        if [ -z "$2" ]; then
            echo "停止所有服务..."
            pm2 stop all
        else
            echo "停止服务: $2"
            if check_service "$2"; then
                pm2 stop "$2"
            fi
        fi
        echo ""
        pm2 status
        ;;

    restart)
        if [ -z "$2" ]; then
            echo "重启所有服务..."
            pm2 restart all
        else
            echo "重启服务: $2"
            if check_service "$2"; then
                pm2 restart "$2"
            fi
        fi
        echo ""
        pm2 status
        ;;

    status)
        pm2 status
        echo ""
        echo "详细信息:"
        if [ -z "$2" ]; then
            echo "使用 'pm2 describe <service-name>' 查看单个服务详情"
        else
            pm2 describe "$2"
        fi
        ;;

    logs)
        if [ -z "$2" ]; then
            echo "查看所有服务日志 (Ctrl+C 退出):"
            pm2 logs --lines 100
        else
            echo "查看 $2 日志 (Ctrl+C 退出):"
            pm2 logs "$2" --lines 100
        fi
        ;;

    delete)
        if [ -z "$2" ]; then
            echo "删除所有服务配置..."
            read -p "确认删除所有服务? (y/n) " -n 1 -r
            echo
            if [[ $REPLY =~ ^[Yy]$ ]]; then
                pm2 delete all
                pm2 save --force
                echo "✓ 所有服务配置已删除"
            else
                echo "取消操作"
            fi
        else
            echo "删除服务: $2"
            if check_service "$2"; then
                pm2 delete "$2"
                pm2 save
            fi
        fi
        ;;

    save)
        echo "保存当前 PM2 配置..."
        pm2 save
        echo "✓ 配置已保存"
        ;;

    list)
        pm2 list
        ;;

    monitor)
        echo "实时监控 (按 q 退出):"
        pm2 monit
        ;;

    flush)
        echo "清空所有日志..."
        pm2 flush
        echo "✓ 日志已清空"
        ;;

    reload)
        if [ -z "$2" ]; then
            echo "重载所有服务（零停机）..."
            pm2 reload all
        else
            echo "重载服务: $2"
            if check_service "$2"; then
                pm2 reload "$2"
            fi
        fi
        echo ""
        pm2 status
        ;;

    help|--help|-h)
        show_help
        ;;

    *)
        echo "错误: 未知命令 '$1'"
        echo ""
        show_help
        exit 1
        ;;
esac
