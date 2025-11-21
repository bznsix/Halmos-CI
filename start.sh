#!/bin/bash
# Halmos CI API 服务器启动脚本

PORT=8005
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"

echo "=========================================="
echo "Halmos CI API 服务器启动脚本"
echo "=========================================="
echo ""

# 检查端口是否被占用
check_port() {
    if lsof -Pi :$PORT -sTCP:LISTEN -t >/dev/null 2>&1 ; then
        echo "⚠️  警告: 端口 $PORT 已被占用"
        
        # 显示占用端口的进程信息
        echo "占用端口的进程信息:"
        lsof -i :$PORT | grep LISTEN
        echo ""
        
        echo "正在终止占用端口 $PORT 的进程..."
        lsof -ti :$PORT | xargs kill -9 2>/dev/null
        sleep 1
        
        # 再次检查端口
        if lsof -Pi :$PORT -sTCP:LISTEN -t >/dev/null 2>&1 ; then
            echo "❌ 错误: 无法终止占用端口的进程"
            exit 1
        else
            echo "✓ 端口 $PORT 已释放"
        fi
    else
        echo "✓ 端口 $PORT 可用"
    fi
}

# 检查 Python 是否安装
check_python() {
    if ! command -v python3 &> /dev/null; then
        echo "❌ 错误: 未找到 python3，请先安装 Python 3"
        exit 1
    fi
    echo "✓ Python3 已安装: $(python3 --version)"
}

# 检查依赖是否安装
check_dependencies() {
    if [ ! -f "$SCRIPT_DIR/requirements.txt" ]; then
        echo "⚠️  警告: 未找到 requirements.txt"
        return
    fi
    
    echo "检查 Python 依赖..."
    if python3 -c "import fastapi, uvicorn, pydantic" 2>/dev/null; then
        echo "✓ Python 依赖已安装"
    else
        echo "⚠️  警告: 部分依赖未安装"
        read -p "是否要安装依赖? (y/N): " -n 1 -r
        echo ""
        if [[ $REPLY =~ ^[Yy]$ ]]; then
            echo "正在安装依赖..."
            pip3 install -q -r "$SCRIPT_DIR/requirements.txt"
            if [ $? -eq 0 ]; then
                echo "✓ 依赖安装完成"
            else
                echo "❌ 依赖安装失败"
                exit 1
            fi
        fi
    fi
}

# 检查 forge 和 halmos 是否安装
check_tools() {
    if ! command -v forge &> /dev/null; then
        echo "⚠️  警告: 未找到 forge，请确保已安装 Foundry"
    else
        echo "✓ Foundry 已安装"
    fi
    
    if ! command -v halmos &> /dev/null; then
        echo "⚠️  警告: 未找到 halmos，请确保已安装 halmos"
    else
        echo "✓ Halmos 已安装"
    fi
}

# 主函数
main() {
    cd "$SCRIPT_DIR" || exit 1
    
    echo "1. 检查端口..."
    check_port
    echo ""
    
    echo "2. 检查 Python..."
    check_python
    echo ""
    
    echo "3. 检查依赖..."
    check_dependencies
    echo ""
    
    echo "4. 检查工具..."
    check_tools
    echo ""
    
    echo "=========================================="
    echo "启动 API 服务器..."
    echo "=========================================="
    echo "服务器地址: http://localhost:$PORT"
    echo "API 文档: http://localhost:$PORT/docs"
    echo "按 Ctrl+C 停止服务器"
    echo ""
    
    # 启动服务器
    python3 api_server.py
}

# 运行主函数
main

