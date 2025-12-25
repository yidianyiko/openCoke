#!/bin/bash
# 测试运行脚本

echo "========================================="
echo "AI Agent 测试套件"
echo "========================================="
echo ""

# 颜色定义
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m' # No Color

# 1. 运行单元测试
echo -e "${YELLOW}[1/5] 运行单元测试...${NC}"
python -m pytest tests/unit/ -v --tb=short
UNIT_EXIT=$?

echo ""
echo "========================================="
echo ""

# 2. 运行属性测试
echo -e "${YELLOW}[2/5] 运行属性测试 (PBT)...${NC}"
python -m pytest tests/pbt/ -v --tb=short
PBT_EXIT=$?

echo ""
echo "========================================="
echo ""

# 3. 运行集成测试（如果 MongoDB 可用）
echo -e "${YELLOW}[3/5] 运行集成测试...${NC}"
python -m pytest tests/integration/ -v --tb=short -m integration
INTEGRATION_EXIT=$?

echo ""
echo "========================================="
echo ""

# 4. 运行所有非集成测试
echo -e "${YELLOW}[4/5] 运行所有非集成测试...${NC}"
python -m pytest -m "not integration and not e2e" -q --tb=no
ALL_EXIT=$?

echo ""
echo "========================================="
echo ""

# 5. 生成覆盖率报告
echo -e "${YELLOW}[5/5] 生成覆盖率报告...${NC}"
python -m pytest tests/unit/ tests/pbt/ \
    --cov=util --cov=dao --cov=entity --cov=connector --cov=conf \
    --cov-report=term --cov-report=html \
    -q --tb=no
COV_EXIT=$?

echo ""
echo "========================================="
echo "测试总结"
echo "========================================="

if [ $UNIT_EXIT -eq 0 ]; then
    echo -e "${GREEN}✓ 单元测试通过${NC}"
else
    echo -e "${RED}✗ 单元测试失败${NC}"
fi

if [ $PBT_EXIT -eq 0 ]; then
    echo -e "${GREEN}✓ 属性测试通过${NC}"
else
    echo -e "${RED}✗ 属性测试失败${NC}"
fi

if [ $INTEGRATION_EXIT -eq 0 ]; then
    echo -e "${GREEN}✓ 集成测试通过${NC}"
else
    echo -e "${YELLOW}⚠ 集成测试跳过或失败（可能需要 MongoDB）${NC}"
fi

if [ $ALL_EXIT -eq 0 ]; then
    echo -e "${GREEN}✓ 所有测试通过${NC}"
else
    echo -e "${RED}✗ 部分测试失败${NC}"
fi

echo ""
echo "覆盖率报告已生成: htmlcov/index.html"
echo ""

# 返回总体状态
if [ $UNIT_EXIT -eq 0 ] && [ $PBT_EXIT -eq 0 ]; then
    exit 0
else
    exit 1
fi
