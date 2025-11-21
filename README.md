# Halmos-CI
这是一个利用Halmos进行的自动化测试框架

https://github.com/a16z/halmos

## 功能说明

这个 API 服务器接受 `deploycode`、`test_id` 和可选的 `function_name`，然后：
1. 复制模板文件 `halmos-sandbox/test/uniswap_callback_test.t.sol` 到新文件 `C{test_id}_test.t.sol`
2. 将合约名从 `UNISWAPCALLBACK` 修改为 `C{test_id}`（例如 C1, C2）
3. 将 `deploycode` 替换到 `bytes memory deploycode = hex"";` 后面
4. 在 `halmos-sandbox` 目录中执行 halmos 测试：`halmos --contract C{test_id} --function {function_name}`
5. 记录执行结果并通过 API 返回给请求者
6. 测试完成后清理临时文件

## 快速开始

### 1. 安装依赖

```bash
pip install -r requirements.txt
```

### 2. 启动服务器

```bash
# 方式1: 使用启动脚本
./start_server.sh

# 方式2: 直接运行
python3 api_server.py
```

服务器将在 `http://localhost:8000` 启动。

### 3. 使用 API

#### 查看 API 文档
访问 `http://localhost:8000/docs` 查看交互式 API 文档。

#### 执行测试

```bash
curl -X POST http://localhost:8005/test \
  -H "Content-Type: application/json" \
  -d '{
    "deploycode": "0x6080604052348015600f57600080fd5b506004361060325760003560e01c8063",
    "test_id": "1",
    "function_name": "test_uniswapV3SwapCallback_k1"
  }'
```

**请求参数说明：**
- `deploycode` (必需): 十六进制字符串，要测试的合约字节码
- `test_id` (必需): 测试ID，合约名将为 `C{test_id}`（例如 "1" -> "C1"）
- `function_name` (可选): 要测试的函数名，默认为 `test_uniswapV3SwapCallback_k1`

#### 响应格式

```json
{
  "success": true,
  "message": "测试执行成功",
  "output": "halmos 执行输出...",
  "error": null
}
```

## 项目结构

- `api_server.py` - FastAPI 服务器主文件
- `halmos-sandbox/` - Halmos 测试环境（基于 halmos-sandbox 模板）
- `requirements.txt` - Python 依赖
- `start_server.sh` - 启动脚本

## 注意事项

- 确保已安装 `forge` 和 `halmos`
- 模板文件：`halmos-sandbox/test/uniswap_callback_test.t.sol`
- 每次测试会创建新文件：`C{test_id}_test.t.sol`（例如 `C1_test.t.sol`）
- 测试完成后会自动清理临时文件
- 合约名格式：`C{test_id}`（例如 C1, C2, C100）
- 默认函数名：`test_uniswapV3SwapCallback_k1`，可通过参数自定义