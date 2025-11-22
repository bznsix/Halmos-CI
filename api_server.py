#!/usr/bin/env python3
"""
Halmos CI API 服务器
接收 deploycode 和测试用例名字，执行 halmos 测试并返回结果
"""

import os
import re
import subprocess
import tempfile
import time
from pathlib import Path
from typing import Optional

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

app = FastAPI(title="Halmos CI API", description="自动化模糊测试框架 API")

# 测试文件基础路径 - 使用 halmos-sandbox 模板
BASE_DIR = Path("/Users/pengxin/Halmos-CI/halmos-sandbox").resolve()
TEST_DIR = BASE_DIR / "test"

# 确保 BASE_DIR 存在
if not BASE_DIR.exists():
    raise RuntimeError(f"工作目录不存在: {BASE_DIR}")


class TestRequest(BaseModel):
    """测试请求模型"""
    deploycode: str  # 十六进制字符串，例如 "0x6080604052..."
    test_case: str  # 测试用例名字，例如 "uniswap_callback"
    test_id: Optional[str] = None  # 测试ID，如果不提供则自动生成
    debug: Optional[bool] = False  # 调试模式，如果为 True 则保留测试文件不删除


class TestResponse(BaseModel):
    """测试响应模型"""
    success: bool
    message: str
    output: Optional[str] = None
    error: Optional[str] = None


def get_test_file_path(test_case: str) -> Path:
    """根据测试用例名字获取测试文件路径"""
    test_file = TEST_DIR / f"{test_case}_test.t.sol"
    if not test_file.exists():
        raise FileNotFoundError(f"测试文件不存在: {test_file}")
    return test_file


def extract_test_contract_name(file_path: Path) -> str:
    """从测试文件中提取以 Test 开头的合约名"""
    content = file_path.read_text(encoding='utf-8')
    # 查找以 Test 开头的合约名
    match = re.search(r'contract\s+(Test\w+)\s+is', content)
    if match:
        return match.group(1)
    raise ValueError(f"无法从测试文件中找到以 Test 开头的合约名: {file_path}")


def create_test_file_with_id(test_case: str, test_id: str, deploycode: str) -> tuple[Path, str]:
    """
    创建测试文件副本并修改合约名
    返回: (新文件路径, 新合约名)
    """
    # 1. 获取原始测试文件
    original_file = get_test_file_path(test_case)
    
    # 2. 提取原始合约名（以 Test 开头）
    original_contract_name = extract_test_contract_name(original_file)
    
    # 3. 读取文件内容
    content = original_file.read_text(encoding='utf-8')
    
    # 4. 生成新合约名：Test + id
    new_contract_name = f"Test{test_id}"
    
    # 5. 替换合约名
    content = re.sub(
        rf'contract\s+{re.escape(original_contract_name)}\s+is',
        f'contract {new_contract_name} is',
        content
    )
    
    # 6. 清理并替换 deploycode
    deploycode_clean = deploycode.strip()
    if deploycode_clean.startswith('0x'):
        deploycode_clean = deploycode_clean[2:]
    deploycode_clean = deploycode_clean.replace(' ', '').replace('\n', '')
    
    if not re.match(r'^[0-9a-fA-F]*$', deploycode_clean):
        raise ValueError(f"无效的十六进制字符串: {deploycode}")
    
    pattern = r'bytes memory deploycode = hex"";'
    replacement = f'bytes memory deploycode = hex"{deploycode_clean}";'
    
    if not re.search(pattern, content):
        raise ValueError(f"未找到 deploycode 定义: {pattern}")
    
    content = re.sub(pattern, replacement, content)
    
    # 7. 创建新文件（使用编号命名，例如 C1_test.t.sol）
    new_file_path = TEST_DIR / f"C{test_id}_test.t.sol"
    new_file_path.write_text(content, encoding='utf-8')
    
    return new_file_path, new_contract_name


def format_halmos_output(output: str) -> str:
    """格式化 halmos 输出，只保留从 '[console.log]' 开头到 'Symbolic test result' 结尾的内容，并删除 ANSI 颜色代码"""
    import re
    
    lines = output.split('\n')
    
    # 查找 "[console.log]" 开头的行
    start_idx = None
    for i, line in enumerate(lines):
        if '[console.log]' in line:
            start_idx = i
            break
    
    if start_idx is None:
        # 没找到开始位置，返回空字符串
        return ""
    
    # 查找 "Symbolic test result" 结尾的行
    end_idx = None
    for i in range(start_idx, len(lines)):
        if 'Symbolic test result' in lines[i]:
            end_idx = i + 1  # 包含这一行
            break
    
    if end_idx is None:
        # 没找到结束位置，返回从开始到结尾
        result_lines = lines[start_idx:]
    else:
        # 返回从开始到结束的所有行
        result_lines = lines[start_idx:end_idx]
    
    # 合并行并删除 ANSI 颜色代码
    result = '\n'.join(result_lines)
    
    # 删除 ANSI 转义序列（颜色代码）
    # 匹配 \u001b[...m 或 \x1b[...m 格式的 ANSI 转义序列
    ansi_escape = re.compile(r'\x1b\[[0-9;]*m|\u001b\[[0-9;]*m')
    result = ansi_escape.sub('', result)
    
    # 规范化换行符：确保使用 \n，移除多余的换行
    result = result.replace('\r\n', '\n').replace('\r', '\n')
    # 移除末尾的多个换行符
    result = result.rstrip('\n')
    
    return result


def run_halmos(test_file: Path, contract_name: str, function_name: str = "test_uniswapV3SwapCallback_k1") -> tuple[bool, str, Optional[str]]:
    """执行 halmos 命令"""
    try:
        # 确保使用绝对路径
        work_dir = str(BASE_DIR.absolute())
        
        # 打印测试信息
        print("=" * 80)
        print("执行测试信息")
        print("=" * 80)
        print(f"测试文件: {test_file}")
        print(f"文件路径: {test_file.absolute()}")
        print(f"合约名: {contract_name}")
        print(f"函数名: {function_name}")
        print(f"工作目录: {work_dir}")
        print("-" * 80)
        
        # 验证工作目录存在
        if not Path(work_dir).exists():
            return False, f"工作目录不存在: {work_dir}", None
        
        # 先执行 forge build 确保新文件被编译（halmos 需要编译输出）
        print(f"执行编译命令: forge build --force (工作目录: {work_dir})")
        build_result = subprocess.run(
            ["forge", "build", "--force"],
            capture_output=True,
            text=True,
            timeout=120,  # 2分钟超时
            cwd=work_dir
        )
        
        if build_result.returncode != 0:
            build_error = build_result.stderr
            # 检查错误是否与我们的测试文件相关
            test_file_name = test_file.name
            if test_file_name in build_error:
                return False, f"编译失败: {build_error}", build_result.stdout + build_error
        
        print("编译完成")
        print("-" * 80)
        
        # 构建 halmos 命令
        cmd = [
            "halmos",
            "--contract", contract_name,
            # "--function", function_name
        ]
        
        # 打印执行的命令
        print(f"执行 halmos 命令: {' '.join(cmd)}")
        print(f"完整命令: cd {work_dir} && {' '.join(cmd)}")
        print(f"实际工作目录: {work_dir}")
        print("=" * 80)
        
        # 执行命令，确保在 halmos-sandbox 目录下执行
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=300,  # 5分钟超时
            cwd=work_dir
        )
        
        print(f"命令退出码: {result.returncode}")
        print("=" * 80)
        
        success = result.returncode == 0
        raw_output = result.stdout + result.stderr
        
        # 格式化输出：保留从 "Running" 开始到结尾的所有内容（包括 WARNING、console.log、[PASS] 等）
        formatted_output = format_halmos_output(raw_output)
        
        if success:
            return True, "测试执行成功", formatted_output
        else:
            return False, f"测试执行失败 (退出码: {result.returncode})", formatted_output
            
    except subprocess.TimeoutExpired:
        return False, "测试执行超时", None
    except FileNotFoundError as e:
        return False, f"命令未找到，请确保已安装 forge 和 halmos: {str(e)}", None
    except Exception as e:
        return False, f"执行 halmos 时发生错误: {str(e)}", None


@app.post("/test", response_model=TestResponse)
async def run_test(request: TestRequest):
    """执行测试的 API 端点"""
    temp_file = None
    try:
        # 打印请求信息
        print("\n" + "=" * 80)
        print("收到测试请求")
        print("=" * 80)
        print(f"test_case: {request.test_case}")
        print(f"test_id: {request.test_id}")
        print(f"debug: {request.debug}")
        print(f"deploycode 长度: {len(request.deploycode)} 字符")
        print(f"deploycode (前50字符): {request.deploycode[:50]}...")
        
        # 1. 生成或使用提供的 test_id
        if request.test_id is None:
            # 自动生成 test_id（使用时间戳和进程ID）
            test_id = f"{int(time.time())}_{os.getpid()}"
            print(f"自动生成 test_id: {test_id}")
        else:
            test_id = request.test_id
            print(f"使用提供的 test_id: {test_id}")
        
        # 2. 创建测试文件副本，修改合约名为 Test+id，替换 deploycode
        print(f"\n步骤 1: 查找测试文件...")
        original_file = get_test_file_path(request.test_case)
        print(f"  原始文件: {original_file}")
        
        print(f"\n步骤 2: 提取原始合约名...")
        original_contract_name = extract_test_contract_name(original_file)
        print(f"  原始合约名: {original_contract_name}")
        
        print(f"\n步骤 3: 创建测试文件副本...")
        temp_file, contract_name = create_test_file_with_id(
            request.test_case, 
            test_id, 
            request.deploycode
        )
        print(f"  新文件: {temp_file}")
        print(f"  新合约名: {contract_name}")
        print(f"  预期文件: C{test_id}_test.t.sol")
        
        # 3. 执行 halmos 测试
        print(f"\n步骤 4: 执行 halmos 测试...")
        success, message, output = run_halmos(temp_file, contract_name)
        
        return TestResponse(
            success=success,
            message=message,
            output=output,
            error=None if success else output
        )
        
    except FileNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"服务器错误: {str(e)}")
    finally:
        # 7. 清理临时文件（如果 debug=False）
        if temp_file and temp_file.exists():
            if request.debug:
                print(f"\n步骤 5: 调试模式 - 保留测试文件")
                print(f"  文件路径: {temp_file}")
                print(f"  文件已保留，方便检查")
                print(f"  手动删除命令: rm {temp_file}")
            else:
                try:
                    print(f"\n步骤 5: 清理临时文件...")
                    print(f"  删除文件: {temp_file}")
                    temp_file.unlink()
                    print(f"  ✓ 临时文件已删除")
                except Exception as e:
                    print(f"  ✗ 删除临时文件失败: {e}")
        print("=" * 80 + "\n")


@app.get("/")
async def root():
    """根路径，返回 API 信息"""
    return {
        "message": "Halmos CI API 服务器",
        "version": "1.0.0",
        "endpoints": {
            "POST /test": "执行 halmos 测试",
            "GET /": "获取 API 信息"
        }
    }


@app.get("/health")
async def health():
    """健康检查端点"""
    return {"status": "healthy"}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8005)

