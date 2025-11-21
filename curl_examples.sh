#!/bin/bash
# Halmos CI API curl 测试示例

API_URL="http://localhost:8005"

echo "=========================================="
echo "Halmos CI API curl 测试示例"
echo "=========================================="
echo ""

# 示例 1: 基本测试（test_id=3，对应 test_api.py 118-122 行）
echo "1. 基本测试（test_id=3）:"
echo "----------------------------------------"
curl -X POST "http://localhost:8005/test" \
  -H "Content-Type: application/json" \
  -d '{
    "deploycode": "",
    "test_case": "uniswap_callback",
    "test_id": "3",
    "debug": true
  }'

# 示例 3: 不提供 test_id（自动生成）
echo "3. 自动生成 test_id:"
echo "----------------------------------------"
curl -X POST "${API_URL}/test" \
  -H "Content-Type: application/json" \
  -d '{
    "deploycode": "0x6080604052348015600f57600080fd5b506004361060325760003560e01c8063",
    "test_case": "uniswap_callback"
  }' | python3 -m json.tool | head -20

echo ""
echo ""

# 示例 4: 只显示关键信息
echo "4. 只显示关键信息:"
echo "----------------------------------------"
curl -s -X POST "${API_URL}/test" \
  -H "Content-Type: application/json" \
  -d '{
    "deploycode": "0x6080604052348015600f57600080fd5b506004361060325760003560e01c8063",
    "test_case": "uniswap_callback",
    "test_id": "3"
  }' | python3 -c "import sys, json; d=json.load(sys.stdin); print(f\"成功: {d.get('success')}\n消息: {d.get('message')}\")"

echo ""
echo ""

# 示例 5: 使用变量（便于修改）
echo "5. 使用变量:"
echo "----------------------------------------"
DEPLOYCODE="0x6080604052348015600f57600080fd5b506004361060325760003560e01c8063"
TEST_CASE="uniswap_callback"
TEST_ID="3"

curl -X POST "${API_URL}/test" \
  -H "Content-Type: application/json" \
  -d "{
    \"deploycode\": \"${DEPLOYCODE}\",
    \"test_case\": \"${TEST_CASE}\",
    \"test_id\": \"${TEST_ID}\"
  }" | python3 -m json.tool | head -30

echo ""
echo "=========================================="
echo "测试完成"
echo "=========================================="

