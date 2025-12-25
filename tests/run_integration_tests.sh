#!/bin/bash
# 集成测试运行脚本
# 
# 用法：
#   ./run_integration_tests.sh              # 运行所有集成测试
#   ./run_integration_tests.sh happy        # 只运行 happy path 测试
#   ./run_integration_tests.sh real         # 只运行真实 API 测试
#   ./run_integration_tests.sh check        # 检查配置状态

set -e

# 颜色输出
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# 打印带颜色的消息
print_info() {
    echo -e "${BLUE}ℹ${NC} $1"
}

print_success() {
    echo -e "${GREEN}✓${NC} $1"
}

print_warning() {
    echo -e "${YELLOW}⚠${NC} $1"
}

print_error() {
    echo -e "${RED}✗${NC} $1"
}

# 检查 .env 文件
check_env_file() {
    if [ ! -f .env ]; then
        print_error ".env 文件不存在"
        print_info "请创建 .env 文件并配置必要的 API keys"
        exit 1
    fi
    print_success ".env 文件存在"
}

# 检查 Python 环境
check_python() {
    if ! command -v python &> /dev/null; then
        print_error "Python 未安装"
        exit 1
    fi
    print_success "Python 已安装: $(python --version)"
}

# 检查依赖
check_dependencies() {
    print_info "检查 Python 依赖..."
    
    if ! python -c "import pytest" 2>/dev/null; then
        print_warning "pytest 未安装，正在安装..."
        pip install pytest
    fi
    
    if ! python -c "import dotenv" 2>/dev/null; then
        print_warning "python-dotenv 未安装，正在安装..."
        pip install python-dotenv
    fi
    
    print_success "依赖检查完成"
}

# 检查 API 配置
check_api_config() {
    print_info "检查 API 配置..."
    python tests/integration_test_config.py
}

# 运行所有集成测试
run_all_tests() {
    print_info "运行所有集成测试..."
    export USE_REAL_API=true
    python -m pytest tests/test_integration_happy_path.py tests/test_real_api_integration.py tests/test_integration_extended.py -v --tb=short
}

# 运行 happy path 测试
run_happy_path_tests() {
    print_info "运行 Happy Path 集成测试..."
    export USE_REAL_API=true
    python -m pytest tests/test_integration_happy_path.py -v --tb=short
}

# 运行真实 API 测试
run_real_api_tests() {
    print_info "运行真实 API 集成测试..."
    export USE_REAL_API=true
    python -m pytest tests/test_real_api_integration.py -v --tb=short
}

# 运行扩展测试
run_extended_tests() {
    print_info "运行扩展集成测试..."
    export USE_REAL_API=true
    python -m pytest tests/test_integration_extended.py -v --tb=short
}

# 运行特定测试
run_specific_test() {
    local test_name=$1
    print_info "运行测试: $test_name"
    export USE_REAL_API=true
    python -m pytest "$test_name" -v --tb=short
}

# 显示帮助信息
show_help() {
    echo "集成测试运行脚本"
    echo ""
    echo "用法："
    echo "  ./run_integration_tests.sh [command]"
    echo ""
    echo "命令："
    echo "  all       运行所有集成测试（默认）"
    echo "  happy     只运行 Happy Path 测试"
    echo "  real      只运行真实 API 测试"
    echo "  extended  只运行扩展测试"
    echo "  check     检查配置状态"
    echo "  help      显示此帮助信息"
    echo ""
    echo "示例："
    echo "  ./run_integration_tests.sh"
    echo "  ./run_integration_tests.sh happy"
    echo "  ./run_integration_tests.sh check"
}

# 主函数
main() {
    local command=${1:-all}
    
    echo ""
    echo "======================================================================"
    echo "  集成测试运行器"
    echo "======================================================================"
    echo ""
    
    # 基础检查
    check_python
    check_env_file
    check_dependencies
    
    echo ""
    
    case $command in
        all)
            run_all_tests
            ;;
        happy)
            run_happy_path_tests
            ;;
        real)
            run_real_api_tests
            ;;
        extended)
            run_extended_tests
            ;;
        check)
            check_api_config
            ;;
        help)
            show_help
            ;;
        *)
            print_error "未知命令: $command"
            show_help
            exit 1
            ;;
    esac
    
    echo ""
    print_success "测试完成！"
}

# 运行主函数
main "$@"
