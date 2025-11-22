#!/usr/bin/env python3
"""
批量测试脚本
从CSV文件读取合约地址，通过RPC节点获取creation code，然后批量测试
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
import requestsclear
from datetime import datetime

# 导入RPC获取creation code的方法
from use_rpc_get_creation import get_creation_code as get_creation_code_from_rpc

# 链ID和存档节点RPC的映射
CHAIN_RPC_MAP = {
    1: "https://eth-mainnet.nodereal.io/v1/814c23529df542eab440417905ff18b7",  # 以太坊主网
    56: "https://bsc-mainnet.nodereal.io/v1/814c23529df542eab440417905ff18b7",  # BSC
    137: "https://polygon-mainnet.nodereal.io/v1/814c23529df542eab440417905ff18b7",  # Polygon
    42161: "https://arb-mainnet.nodereal.io/v1/814c23529df542eab440417905ff18b7",  # Arbitrum
    10: "https://opt-mainnet.nodereal.io/v1/814c23529df542eab440417905ff18b7",  # Optimism
    # 可以根据需要添加更多链
}

# API配置
API_URL = "http://localhost:8005"

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


def get_single_contract_creation_code(contract_address: str, tx_hash: str, chain_id: int) -> Optional[str]:
    """
    获取单个合约的creation code（先查数据库，没有则通过RPC获取）
    
    Args:
        contract_address: 合约地址
        tx_hash: 部署交易哈希
        chain_id: 链ID
    
    Returns:
        creation bytecode（如果获取失败则为None），已去掉0x前缀
    """
    # 1. 先查询本地数据库
    creation_code = get_creation_code_from_db(contract_address, chain_id)
    if creation_code:
        print(f"  ✓ 从本地数据库获取成功")
        return creation_code
    
    # 2. 数据库中没有，通过RPC获取
    print(f"  → 本地数据库未找到，通过RPC节点获取...")
    
    # 根据链ID获取对应的RPC节点
    rpc_url = CHAIN_RPC_MAP.get(chain_id)
    if not rpc_url:
        print(f"  ✗ 错误: 链ID {chain_id} 没有配置对应的RPC节点")
        print(f"  请先在 CHAIN_RPC_MAP 中添加该链的RPC节点配置")
        return None
    
    # 重试机制：最多重试5次
    max_retries = 5
    for attempt in range(1, max_retries + 1):
        try:
            creation_code = get_creation_code_from_rpc(tx_hash, rpc_url)
            if creation_code:
                # 保存到数据库
                save_creation_code_to_db(contract_address, chain_id, creation_code)
                print(f"  ✓ 已保存到本地数据库")
                return creation_code
        except ValueError as e:
            print(f"  ✗ 第{attempt}次尝试失败: {str(e)}")
            if attempt < max_retries:
                wait_time = 2
                print(f"  → {wait_time}秒后重试...")
                time.sleep(wait_time)
            else:
                print(f"  ✗ 重试{max_retries}次后仍然失败")
                return None
        except Exception as e:
            print(f"  ✗ 第{attempt}次尝试失败: {str(e)}")
            if attempt < max_retries:
                wait_time = 2
                print(f"  → {wait_time}秒后重试...")
                time.sleep(wait_time)
            else:
                print(f"  ✗ 重试{max_retries}次后仍然失败")
                return None
    
    return None


def read_csv_addresses(csv_file: str) -> list[dict]:
    """
    从CSV文件读取address和tx_hash列
    
    Args:
        csv_file: CSV文件路径
    
    Returns:
        字典列表，每个字典包含address和tx_hash字段
    """
    contracts = []
    
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
            
            # 查找address和tx_hash列（不区分大小写）
            fieldnames = [name.lower() for name in reader.fieldnames or []]
            if 'address' not in fieldnames:
                raise ValueError(f"CSV文件中未找到'address'列。可用列: {reader.fieldnames}")
            if 'tx_hash' not in fieldnames:
                raise ValueError(f"CSV文件中未找到'tx_hash'列。可用列: {reader.fieldnames}")
            
            # 找到列的原始名称
            address_col = None
            tx_hash_col = None
            for col in reader.fieldnames or []:
                if col.lower() == 'address':
                    address_col = col
                elif col.lower() == 'tx_hash':
                    tx_hash_col = col
            
            for row in reader:
                address = row.get(address_col, "").strip()
                tx_hash = row.get(tx_hash_col, "").strip()
                if address and tx_hash:
                    contracts.append({
                        "address": address,
                        "tx_hash": tx_hash
                    })
            
            print(f"从CSV文件读取到 {len(contracts)} 个合约（包含地址和交易哈希）")
            return contracts
            
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


def batch_test(chain_id: int, csv_file: str, test_case: str = "uniswap_callback"):
    """
    批量测试主函数
    
    Args:
        chain_id: 链ID
        csv_file: CSV文件路径
        test_case: 测试用例名称，默认为"uniswap_callback"
    """
    # 检查链ID是否在映射中
    if chain_id not in CHAIN_RPC_MAP:
        print(f"错误: 链ID {chain_id} 没有配置对应的RPC节点")
        print(f"请先在 CHAIN_RPC_MAP 中添加该链的RPC节点配置")
        print(f"当前支持的链ID: {list(CHAIN_RPC_MAP.keys())}")
        sys.exit(1)
    
    # 初始化数据库
    print("初始化数据库...")
    init_database()
    print(f"数据库文件: {DB_FILE.absolute()}")
    print()
    
    print("=" * 80)
    print("批量测试开始")
    print("=" * 80)
    print(f"链ID: {chain_id}")
    print(f"RPC节点: {CHAIN_RPC_MAP[chain_id]}")
    print(f"CSV文件: {csv_file}")
    print(f"测试用例: {test_case}")
    print(f"API服务器: {API_URL}")
    print("=" * 80)
    print()
    
    # 1. 读取CSV文件中的地址和交易哈希
    print("步骤1: 读取CSV文件...")
    contracts = read_csv_addresses(csv_file)
    if not contracts:
        print("错误: 未找到任何合约")
        sys.exit(1)
    print(f"共读取到 {len(contracts)} 个合约")
    print()
    
    # 2. 逐个处理每个合约：获取creation code -> 执行测试 -> 保存结果
    print("步骤2: 逐个处理合约...")
    test_id_counter = 1
    success_get_count = 0
    success_test_count = 0
    
    for idx, contract in enumerate(contracts, 1):
        address = contract["address"]
        tx_hash = contract["tx_hash"]
        
        print(f"\n{'=' * 80}")
        print(f"[{idx}/{len(contracts)}] 处理合约: {address}")
        print(f"交易哈希: {tx_hash}")
        print(f"{'=' * 80}")
        
        # 2.1 获取creation code
        print(f"\n2.1 获取creation code...")
        creation_code = get_single_contract_creation_code(address, tx_hash, chain_id)
        
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
        if idx < len(contracts):
            time.sleep(0.5)
    
    print()
    print("=" * 80)
    print("批量测试完成")
    print("=" * 80)
    print(f"总合约数: {len(contracts)}")
    print(f"成功获取creation code: {success_get_count}/{len(contracts)}")
    print(f"成功执行测试: {success_test_count}/{success_get_count}")
    print(f"结果保存在: {RESULT_DIR.absolute()}")


def main():
    parser = argparse.ArgumentParser(
        description="批量测试脚本 - 从CSV文件读取合约地址并批量测试",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
  # 使用默认测试用例
  python3 batch_test_node.py --chain-id 56 --csv contracts.csv

  # 指定测试用例
  python3 batch_test_node.py --chain-id 56 --csv contracts.csv --test-case uniswap_callback

注意:
  - CSV文件必须包含 'address' 和 'tx_hash' 列
  - 链ID必须在 CHAIN_RPC_MAP 中配置对应的RPC节点
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
        help="CSV文件路径，必须包含'address'和'tx_hash'列"
    )
    
    parser.add_argument(
        "--test-case",
        type=str,
        default="uniswap_callback",
        help="测试用例名称 (默认: uniswap_callback)"
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
        test_case=args.test_case
    )


if __name__ == "__main__":
    main()

