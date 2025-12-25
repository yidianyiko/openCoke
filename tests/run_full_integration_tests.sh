#!/bin/bash
# 运行完整的集成测试套件

set -e

echo "=========================================="
echo "完整集成测试套件"
echo "=========================================="
echo ""

# 检查 MongoDB 连接
echo "检查 MongoDB 连接..."
python -c "
from pymongo import MongoClient
from conf.config import CONF
try:
    client = MongoClient(f\"mongodb://{CONF['mongodb']['mongodb_ip']}:{CONF['mongodb']['mongodb_port']}/\", serverSelectionTimeoutMS=2000)
    client.admin.command('ping')
    print('✓ MongoDB 连接正常')
    client.close()
except Exception as e:
    print(f'✗ MongoDB 连接失败: {e}')
    exit(1)
"
echo ""

# 设置环境变量
export USE_REAL_API=true
export PYTHONPATH="${PYTHONPATH}:$(pwd)"

# 测试模块列表
declare -a test_modules=(
    "tests/test_reminder_crud.py"
    "tests/test_e2e_message_flow.py"
    "tests/test_concurrency_and_errors.py"
    "tests/test_background_tasks.py"
)

# 运行测试的函数
run_test() {
    local test_file=$1
    local test_name=$(basename "$test_file" .py)
    
    echo "=========================================="
    echo "运行: $test_name"
    echo "=========================================="
    
    python -m pytest "$test_file" -v -s --tb=short --color=yes
    
    if [ $? -eq 0 ]; then
        echo "✓ $test_name 通过"
    else
        echo "✗ $test_name 失败"
        return 1
    fi
    echo ""
}

# 主测试流程
main() {
    local failed_tests=()
    local passed_tests=()
    
    echo "开始运行集成测试..."
    echo ""
    
    for test_file in "${test_modules[@]}"; do
        if run_test "$test_file"; then
            passed_tests+=("$test_file")
        else
            failed_tests+=("$test_file")
        fi
    done
    
    # 输出测试摘要
    echo "=========================================="
    echo "测试摘要"
    echo "=========================================="
    echo "总测试模块: ${#test_modules[@]}"
    echo "通过: ${#passed_tests[@]}"
    echo "失败: ${#failed_tests[@]}"
    echo ""
    
    if [ ${#passed_tests[@]} -gt 0 ]; then
        echo "✓ 通过的测试:"
        for test in "${passed_tests[@]}"; do
            echo " -$(basename "$test")"
        done
        echo ""
    fi
    
    if [ ${#failed_tests[@]} -gt 0 ]; then
        echo "✗ 失败的测试:"
        for test in "${failed_tests[@]}"; do
            echo " -$(basename "$test")"
        done
        echo ""
        exit 1
    fi
    
    echo "=========================================="
    echo "✅ 所有集成测试通过！"
    echo "=========================================="
}

# 运行主函数
main
