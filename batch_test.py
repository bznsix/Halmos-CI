#!/usr/bin/env python3
"""
批量测试脚本
从CSV文件读取合约地址，通过Etherscan API获取creation code，然后批量测试
"""

import argparse
import csv
import json
import os
import sqlite3
import sys
import time
from pathlib import Path
from typing import Optional
import requests
from datetime import datetime

# API配置
API_URL = "http://localhost:8005"
ETHERSCAN_API_BASE = "https://api.etherscan.io/v2/api"

# 结果输出目录
RESULT_DIR = Path("result")
RESULT_DIR.mkdir(exist_ok=True)

# 数据库文件路径
DB_FILE = Path("creation_codes.db")


def init_database():
    """初始化SQLite数据库，创建表结构"""
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    
    # 创建表：存储合约地址、链ID、creation code和时间戳
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS creation_codes (
            address TEXT NOT NULL,
            chain_id INTEGER NOT NULL,
            creation_code TEXT NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            PRIMARY KEY (address, chain_id)
        )
    """)
    
    # 创建索引以提高查询速度
    cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_address_chain 
        ON creation_codes(address, chain_id)
    """)
    
    conn.commit()
    conn.close()


def get_creation_code_from_db(contract_address: str, chain_id: int) -> Optional[str]:
    """
    从本地数据库查询creation code
    
    Args:
        contract_address: 合约地址
        chain_id: 链ID
    
    Returns:
        creation bytecode（如果数据库中没有则为None）
    """
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    
    address_lower = contract_address.lower()
    cursor.execute(
        "SELECT creation_code FROM creation_codes WHERE address = ? AND chain_id = ?",
        (address_lower, chain_id)
    )
    
    result = cursor.fetchone()
    conn.close()
    
    if result:
        return result[0]
    return None


def save_creation_code_to_db(contract_address: str, chain_id: int, creation_code: str):
    """
    将creation code保存到本地数据库
    
    Args:
        contract_address: 合约地址
        chain_id: 链ID
        creation_code: creation bytecode（已去掉0x前缀）
    """
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    
    address_lower = contract_address.lower()
    # 使用INSERT OR REPLACE来更新已存在的记录
    cursor.execute(
        """
        INSERT OR REPLACE INTO creation_codes (address, chain_id, creation_code, created_at)
        VALUES (?, ?, ?, CURRENT_TIMESTAMP)
        """,
        (address_lower, chain_id, creation_code)
    )
    
    conn.commit()
    conn.close()


def get_etherscan_api_key() -> str:
    """从环境变量获取Etherscan API Key"""
    api_key = os.getenv("ETHERSCAN_API_KEY")
    if not api_key:
        print("警告: 未设置 ETHERSCAN_API_KEY 环境变量")
        print("请设置: export ETHERSCAN_API_KEY=YourApiKeyToken")
        sys.exit(1)
    return api_key


def get_single_contract_creation_code(contract_address: str, chain_id: int, api_key: str) -> Optional[str]:
    """
    获取单个合约的creation code（先查数据库，没有则调用API）
    
    Args:
        contract_address: 合约地址
        chain_id: 链ID
        api_key: Etherscan API Key
    
    Returns:
        creation bytecode（如果获取失败则为None），已去掉0x前缀
    """
    # 1. 先查询本地数据库
    creation_code = get_creation_code_from_db(contract_address, chain_id)
    if creation_code:
        print(f"  ✓ 从本地数据库获取成功")
        return creation_code
    
    # 2. 数据库中没有，调用API获取（带重试机制）
    print(f"  → 本地数据库未找到，从Etherscan API获取...")
    result_dict = get_contract_creation_code([contract_address], chain_id, api_key)
    creation_code = result_dict.get(contract_address.lower())
    
    # 3. 如果API获取成功，保存到数据库（get_contract_creation_code内部已保存，这里只显示提示）
    if creation_code:
        print(f"  ✓ 已保存到本地数据库")
    
    return creation_code


def get_contract_creation_code(contract_addresses: list[str], chain_id: int, api_key: str) -> dict[str, Optional[str]]:
    """
    从Etherscan API获取合约的creation code（带重试机制）
    
    Args:
        contract_addresses: 合约地址列表（最多5个）
        chain_id: 链ID
        api_key: Etherscan API Key
    
    Returns:
        字典，key为合约地址，value为creation bytecode（如果获取失败则为None）
    """
    # Etherscan API限制：最多5个地址
    if len(contract_addresses) > 5:
        raise ValueError(f"Etherscan API限制：最多只能同时查询5个地址，当前有{len(contract_addresses)}个")
    
    # 将地址列表编码为URL参数格式（用%2C分隔）
    addresses_param = "%2C".join(contract_addresses)
    
    url = f"{ETHERSCAN_API_BASE}?apikey={api_key}&chainid={chain_id}&module=contract&action=getcontractcreation&contractaddresses={addresses_param}"
    
    # 只在批量获取时显示详细信息
    if len(contract_addresses) > 1:
        print(f"正在从Etherscan获取合约creation code...")
        print(f"  链ID: {chain_id}")
        print(f"  合约数量: {len(contract_addresses)}")
    
    # 重试机制：最多重试5次
    max_retries = 10
    last_error = None
    
    for attempt in range(1, max_retries + 1):
        try:
            response = requests.get(url, timeout=30)
            response.raise_for_status()
            data = response.json()
            
            result_dict = {}
            
            # 检查API返回状态
            if data.get("status") == "1" and data.get("message") == "OK":
                results = data.get("result", [])
                # 创建地址到creation code的映射
                for item in results:
                    address = item.get("contractAddress", "").lower()
                    creation_code = item.get("creationBytecode", "")
                    if address and creation_code:
                        # 去掉0x前缀
                        if creation_code.startswith("0x") or creation_code.startswith("0X"):
                            creation_code = creation_code[2:]
                        result_dict[address] = creation_code
                        # 保存到数据库
                        save_creation_code_to_db(address, chain_id, creation_code)
                        # 只在批量获取时显示详细信息
                        if len(contract_addresses) > 1:
                            print(f"  ✓ 获取成功: {address[:10]}...{address[-8:]}")
                    else:
                        if len(contract_addresses) > 1:
                            print(f"  ✗ 数据不完整: {item}")
                
                # 检查哪些地址没有获取到
                for addr in contract_addresses:
                    addr_lower = addr.lower()
                    if addr_lower not in result_dict:
                        result_dict[addr_lower] = None
                        if len(contract_addresses) > 1:
                            print(f"  ✗ 未找到: {addr}")
                
                # 成功获取，返回结果
                return result_dict
            else:
                # API返回错误状态，需要重试
                error_msg = f"Etherscan API返回错误: {data.get('message', 'Unknown error')}"
                last_error = error_msg
                if len(contract_addresses) > 1:
                    print(f"  ✗ 第{attempt}次尝试失败: {error_msg}")
                else:
                    print(f"  ✗ 第{attempt}次尝试失败: {error_msg}")
                
                # 如果不是最后一次尝试，等待后重试
                if attempt < max_retries:
                    wait_time = 2  # 固定延迟2秒
                    print(f"  → {wait_time}秒后重试...")
                    time.sleep(wait_time)
                    continue
                else:
                    # 最后一次尝试也失败，返回空结果
                    if len(contract_addresses) > 1:
                        print(f"  ✗ 重试{max_retries}次后仍然失败")
                    return {addr.lower(): None for addr in contract_addresses}
        
        except requests.exceptions.Timeout as e:
            last_error = f"请求超时: {str(e)}"
            if len(contract_addresses) > 1:
                print(f"  ✗ 第{attempt}次尝试失败: {last_error}")
            else:
                print(f"  ✗ 第{attempt}次尝试失败: {last_error}")
            
            if attempt < max_retries:
                wait_time = 2  # 固定延迟2秒
                print(f"  → {wait_time}秒后重试...")
                time.sleep(wait_time)
                continue
            else:
                if len(contract_addresses) > 1:
                    print(f"  ✗ 重试{max_retries}次后仍然失败")
                return {addr.lower(): None for addr in contract_addresses}
        
        except requests.exceptions.RequestException as e:
            last_error = f"请求Etherscan API失败: {str(e)}"
            if len(contract_addresses) > 1:
                print(f"  ✗ 第{attempt}次尝试失败: {last_error}")
            else:
                print(f"  ✗ 第{attempt}次尝试失败: {last_error}")
            
            if attempt < max_retries:
                wait_time = 2  # 固定延迟2秒
                print(f"  → {wait_time}秒后重试...")
                time.sleep(wait_time)
                continue
            else:
                if len(contract_addresses) > 1:
                    print(f"  ✗ 重试{max_retries}次后仍然失败")
                return {addr.lower(): None for addr in contract_addresses}
        
        except Exception as e:
            last_error = f"处理响应时出错: {str(e)}"
            if len(contract_addresses) > 1:
                print(f"  ✗ 第{attempt}次尝试失败: {last_error}")
            else:
                print(f"  ✗ 第{attempt}次尝试失败: {last_error}")
            
            if attempt < max_retries:
                wait_time = 2  # 固定延迟2秒
                print(f"  → {wait_time}秒后重试...")
                time.sleep(wait_time)
                continue
            else:
                if len(contract_addresses) > 1:
                    print(f"  ✗ 重试{max_retries}次后仍然失败")
                return {addr.lower(): None for addr in contract_addresses}
    
    # 理论上不会到达这里，但为了安全起见
    if len(contract_addresses) > 1:
        print(f"  ✗ 重试{max_retries}次后仍然失败: {last_error}")
    return {addr.lower(): None for addr in contract_addresses}


def read_csv_addresses(csv_file: str) -> list[str]:
    """
    从CSV文件读取address列
    
    Args:
        csv_file: CSV文件路径
    
    Returns:
        地址列表
    """
    addresses = []
    
    try:
        with open(csv_file, 'r', encoding='utf-8') as f:
            # 读取第一行来检测分隔符
            first_line = f.readline()
            f.seek(0)
            
            # 检测分隔符：优先使用逗号，如果第一行没有逗号则尝试其他分隔符
            delimiter = ','
            if ',' not in first_line:
                if ';' in first_line:
                    delimiter = ';'
                elif '\t' in first_line:
                    delimiter = '\t'
            
            reader = csv.DictReader(f, delimiter=delimiter)
            
            # 查找address列（不区分大小写）
            fieldnames = [name.lower() for name in reader.fieldnames or []]
            if 'address' not in fieldnames:
                raise ValueError(f"CSV文件中未找到'address'列。可用列: {reader.fieldnames}")
            
            # 找到address列的原始名称
            address_col = None
            for col in reader.fieldnames or []:
                if col.lower() == 'address':
                    address_col = col
                    break
            
            for row in reader:
                address = row.get(address_col, "").strip()
                if address:
                    addresses.append(address)
            
            print(f"从CSV文件读取到 {len(addresses)} 个地址")
            return addresses
            
    except FileNotFoundError:
        print(f"错误: CSV文件不存在: {csv_file}")
        sys.exit(1)
    except Exception as e:
        print(f"错误: 读取CSV文件失败: {str(e)}")
        sys.exit(1)


def run_test(deploycode: str, test_case: str, test_id: str) -> dict:
    """
    调用本地API执行测试
    
    Args:
        deploycode: 合约部署代码
        test_case: 测试用例名称
        test_id: 测试ID
    
    Returns:
        API响应字典
    """
    test_data = {
        "deploycode": deploycode,
        "test_case": test_case,
        "test_id": test_id
    }
    
    try:
        response = requests.post(f"{API_URL}/test", json=test_data, timeout=300)
        response.raise_for_status()
        return response.json()
    except requests.exceptions.Timeout:
        return {
            "success": False,
            "message": "请求超时（超过300秒）",
            "output": None,
            "error": None
        }
    except requests.exceptions.ConnectionError:
        return {
            "success": False,
            "message": "无法连接到API服务器，请确保服务器正在运行",
            "output": None,
            "error": None
        }
    except Exception as e:
        return {
            "success": False,
            "message": f"请求失败: {str(e)}",
            "output": None,
            "error": None
        }


def format_output(result: dict) -> str:
    """
    格式化输出结果，提取output字段的内容
    
    Args:
        result: API响应字典
    
    Returns:
        格式化后的字符串
    """
    output = result.get("output", "")
    if output:
        return output
    return ""


def save_result(contract_address: str, result: dict, creation_code: Optional[str] = None):
    """
    将测试结果保存到文件
    
    Args:
        contract_address: 合约地址
        result: API响应结果
        creation_code: 合约creation code（可选）
    """
    # 使用合约地址作为文件名（去除0x前缀，使用小写）
    filename = contract_address.lower().replace("0x", "")
    output_file = RESULT_DIR / f"{filename}.txt"
    
    with open(output_file, 'w', encoding='utf-8') as f:
        f.write("=" * 80 + "\n")
        f.write(f"合约地址: {contract_address}\n")
        f.write(f"测试时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
        f.write("=" * 80 + "\n\n")
        
        # 保存完整响应
        f.write("完整响应:\n")
        f.write(json.dumps(result, indent=2, ensure_ascii=False))
        f.write("\n\n")
        
        # 格式化输出内容
        output_content = format_output(result)
        if output_content:
            f.write("=" * 80 + "\n")
            f.write("输出内容:\n")
            f.write("=" * 80 + "\n")
            f.write(output_content)
            f.write("\n")
        
        # 如果有错误信息，也保存
        if result.get("error") and result.get("error") != output_content:
            f.write("\n" + "=" * 80 + "\n")
            f.write("错误内容:\n")
            f.write("=" * 80 + "\n")
            f.write(result.get("error", ""))
            f.write("\n")
    
    print(f"  ✓ 结果已保存: {output_file}")


def batch_test(chain_id: int, csv_file: str, test_case: str = "uniswap_callback", api_key: Optional[str] = None, batch_size: int = 5):
    """
    批量测试主函数
    
    Args:
        chain_id: 链ID
        csv_file: CSV文件路径
        test_case: 测试用例名称，默认为"uniswap_callback"
        api_key: Etherscan API Key（如果为None则从环境变量读取）
        batch_size: 批量获取creation code时的批次大小（Etherscan API限制：最多5个地址，默认5）
    """
    # 确保批次大小不超过Etherscan API限制
    if batch_size > 5:
        print(f"警告: batch_size ({batch_size}) 超过Etherscan API限制（5），已自动调整为5")
        batch_size = 5
    if api_key is None:
        api_key = get_etherscan_api_key()
    
    # 初始化数据库
    print("初始化数据库...")
    init_database()
    print(f"数据库文件: {DB_FILE.absolute()}")
    print()
    
    print("=" * 80)
    print("批量测试开始")
    print("=" * 80)
    print(f"链ID: {chain_id}")
    print(f"CSV文件: {csv_file}")
    print(f"测试用例: {test_case}")
    print(f"API服务器: {API_URL}")
    print("=" * 80)
    print()
    
    # 1. 读取CSV文件中的地址
    print("步骤1: 读取CSV文件...")
    addresses = read_csv_addresses(csv_file)
    if not addresses:
        print("错误: 未找到任何地址")
        sys.exit(1)
    print(f"共读取到 {len(addresses)} 个合约地址")
    print()
    
    # 2. 逐个处理每个合约：获取creation code -> 执行测试 -> 保存结果
    print("步骤2: 逐个处理合约...")
    test_id_counter = 1
    success_get_count = 0
    success_test_count = 0
    
    for idx, address in enumerate(addresses, 1):
        print(f"\n{'=' * 80}")
        print(f"[{idx}/{len(addresses)}] 处理合约: {address}")
        print(f"{'=' * 80}")
        
        # 2.1 获取creation code
        print(f"\n2.1 获取creation code...")
        creation_code = get_single_contract_creation_code(address, chain_id, api_key)
        
        if creation_code is None:
            print(f"  ✗ 获取失败: 未获取到creation code")
            # 保存失败结果
            result = {
                "success": False,
                "message": "未获取到合约creation code",
                "output": None,
                "error": None
            }
            save_result(address, result)
            print(f"  → 跳过测试，继续下一个合约")
            # 避免请求过快
            time.sleep(0.5)
            continue
        
        success_get_count += 1
        print(f"  ✓ 获取成功")
        print(f"  Creation code长度: {len(creation_code)} 字符")
        
        # 2.2 执行测试
        print(f"\n2.2 执行测试...")
        test_id = str(test_id_counter)
        print(f"  测试ID: {test_id}")
        
        result = run_test(creation_code, test_case, test_id)
        
        # 显示简要结果
        if result.get("success"):
            print(f"  ✓ 测试成功")
            success_test_count += 1
        else:
            print(f"  ✗ 测试失败: {result.get('message', 'Unknown error')}")
        
        # 2.3 保存结果
        print(f"\n2.3 保存结果...")
        save_result(address, result, creation_code)
        
        test_id_counter += 1
        
        # 避免请求过快
        if idx < len(addresses):
            time.sleep(0.5)
    
    print()
    print("=" * 80)
    print("批量测试完成")
    print("=" * 80)
    print(f"总合约数: {len(addresses)}")
    print(f"成功获取creation code: {success_get_count}/{len(addresses)}")
    print(f"成功执行测试: {success_test_count}/{success_get_count}")
    print(f"结果保存在: {RESULT_DIR.absolute()}")


def main():
    parser = argparse.ArgumentParser(
        description="批量测试脚本 - 从CSV文件读取合约地址并批量测试",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
  # 使用环境变量中的API Key
  export ETHERSCAN_API_KEY=YourApiKeyToken
  python3 batch_test.py --chain-id 1 --csv contracts.csv

  # 直接指定API Key
  python3 batch_test.py --chain-id 1 --csv contracts.csv --api-key YourApiKeyToken

  # 指定测试用例
  python3 batch_test.py --chain-id 1 --csv contracts.csv --test-case uniswap_callback

  # 指定批量大小（如果Etherscan API有限制）
  python3 batch_test.py --chain-id 1 --csv contracts.csv --batch-size 5
        """
    )
    
    parser.add_argument(
        "--chain-id",
        type=int,
        required=True,
        help="链ID (例如: 1=以太坊主网, 56=BSC, 137=Polygon)"
    )
    
    parser.add_argument(
        "--csv",
        type=str,
        required=True,
        help="CSV文件路径，必须包含'address'列"
    )
    
    parser.add_argument(
        "--test-case",
        type=str,
        default="uniswap_callback",
        help="测试用例名称 (默认: uniswap_callback)"
    )
    
    parser.add_argument(
        "--api-key",
        type=str,
        default=None,
        help="Etherscan API Key (如果不提供则从环境变量 ETHERSCAN_API_KEY 读取)"
    )
    
    parser.add_argument(
        "--batch-size",
        type=int,
        default=5,
        help="批量获取creation code时的批次大小 (默认: 5, Etherscan API限制最多5个)"
    )
    
    args = parser.parse_args()
    
    # 验证CSV文件存在
    if not os.path.exists(args.csv):
        print(f"错误: CSV文件不存在: {args.csv}")
        sys.exit(1)
    
    # 执行批量测试
    batch_test(
        chain_id=args.chain_id,
        csv_file=args.csv,
        test_case=args.test_case,
        api_key=args.api_key,
        batch_size=args.batch_size
    )


if __name__ == "__main__":
    main()

