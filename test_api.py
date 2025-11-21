#!/usr/bin/env python3
"""
测试 API 服务器的脚本
"""

import requests
import json
from datetime import datetime

API_URL = "http://localhost:8005"

def test_api():
    """测试 API 端点"""
    # 测试根路径
    print("1. 测试根路径...")
    response = requests.get(f"{API_URL}/")
    print(f"   状态码: {response.status_code}")
    print(f"   响应: {json.dumps(response.json(), indent=2, ensure_ascii=False)}")
    print()
    
    # 测试健康检查
    print("2. 测试健康检查...")
    response = requests.get(f"{API_URL}/health")
    print(f"   状态码: {response.status_code}")
    print(f"   响应: {json.dumps(response.json(), indent=2, ensure_ascii=False)}")
    print()
    
    # 测试执行测试端点（使用一个简单的 deploycode）
    print("3. 测试执行测试端点...")
    test_data = {
        "deploycode": "",
        "test_case": "uniswap_callback",
        "test_id": "1"  # 可选，如果不提供则自动生成
    }
    print(f"   请求数据: {json.dumps(test_data, indent=2, ensure_ascii=False)}")
    print(f"   说明: test_case='uniswap_callback' -> 文件: uniswap_callback_test.t.sol")
    print(f"         合约名: TestUniswapCallback -> Test{test_data['test_id']} (Test1)")
    print(f"         临时文件: C{test_data['test_id']}_test.t.sol")
    
    log_file = "test_log.txt"
    try:
        response = requests.post(f"{API_URL}/test", json=test_data, timeout=120)
        print(f"   状态码: {response.status_code}")
        
        # 将完整响应保存到文件
        with open(log_file, 'w', encoding='utf-8') as f:
            f.write("=" * 80 + "\n")
            f.write(f"测试时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
            f.write("=" * 80 + "\n\n")
            f.write(f"请求数据:\n{json.dumps(test_data, indent=2, ensure_ascii=False)}\n\n")
            f.write(f"状态码: {response.status_code}\n\n")
            
            if response.status_code == 200:
                result = response.json()
                f.write("完整响应:\n")
                f.write(json.dumps(result, indent=2, ensure_ascii=False))
                f.write("\n\n")
                
                # 单独保存 output 和 error
                if result.get('output'):
                    f.write("=" * 80 + "\n")
                    f.write("输出内容:\n")
                    f.write("=" * 80 + "\n")
                    f.write(result.get('output', ''))
                    f.write("\n\n")
                
                if result.get('error'):
                    f.write("=" * 80 + "\n")
                    f.write("错误内容:\n")
                    f.write("=" * 80 + "\n")
                    f.write(result.get('error', ''))
                    f.write("\n")
            else:
                f.write("错误响应:\n")
                f.write(json.dumps(response.json(), indent=2, ensure_ascii=False))
                f.write("\n")
        
        print(f"   ✓ 完整响应已保存到: {log_file}")
        
        if response.status_code == 200:
            result = response.json()
            print(f"   成功: {result.get('success')}")
            print(f"   消息: {result.get('message')}")
            if result.get('output'):
                output_lines = result.get('output', '').split('\n')
                print(f"   输出 (前15行):")
                for line in output_lines[:15]:
                    if line.strip():
                        print(f"     {line[:100]}")
            if result.get('error'):
                error_lines = result.get('error', '').split('\n')
                print(f"   错误 (前5行):")
                for line in error_lines[:5]:
                    if line.strip():
                        print(f"     {line[:100]}")
        else:
            print(f"   错误响应: {json.dumps(response.json(), indent=2, ensure_ascii=False)}")
    except requests.exceptions.Timeout:
        print("   ✗ 请求超时（超过120秒）")
        with open(log_file, 'w', encoding='utf-8') as f:
            f.write(f"请求超时（超过120秒）\n")
            f.write(f"请求数据: {json.dumps(test_data, indent=2, ensure_ascii=False)}\n")
    except Exception as e:
        print(f"   ✗ 请求错误: {str(e)}")
        with open(log_file, 'w', encoding='utf-8') as f:
            f.write(f"请求错误: {str(e)}\n")
            f.write(f"请求数据: {json.dumps(test_data, indent=2, ensure_ascii=False)}\n")
    print()
    
    # 测试多个测试用例
    print("4. 测试多个测试用例（不同 test_id）...")
    test_cases = [
        {
            "deploycode": "",
            "test_case": "uniswap_callback",
            "test_id": "2"
        },
        {
            "deploycode": "",
            "test_case": "uniswap_callback",
            "test_id": "3"
        }
    ]
    
    for i, test_data in enumerate(test_cases, 1):
        print(f"   测试用例 {i}: test_id={test_data['test_id']}")
        print(f"     预期文件: C{test_data['test_id']}_test.t.sol")
        print(f"     预期合约名: Test{test_data['test_id']}")
        try:
            response = requests.post(f"{API_URL}/test", json=test_data, timeout=120)
            if response.status_code == 200:
                result = response.json()
                status = "✓ 成功" if result.get('success') else "✗ 失败"
                print(f"     {status}: {result.get('message', '')[:60]}")
            else:
                print(f"     ✗ HTTP错误: {response.status_code}")
                error_detail = response.json().get('detail', '')
                print(f"       错误: {error_detail[:60]}")
        except requests.exceptions.Timeout:
            print(f"     ✗ 超时")
        except Exception as e:
            print(f"     ✗ 错误: {str(e)[:60]}")
    print()
    
    # 测试不提供 test_id（自动生成）
    print("5. 测试自动生成 test_id...")
    test_data_auto = {
        "deploycode": "",
        "test_case": "uniswap_callback"
        # 不提供 test_id，让服务器自动生成
    }
    print(f"   请求数据: {json.dumps(test_data_auto, indent=2, ensure_ascii=False)}")
    print(f"   说明: 不提供 test_id，服务器将自动生成")
    try:
        response = requests.post(f"{API_URL}/test", json=test_data_auto, timeout=120)
        if response.status_code == 200:
            result = response.json()
            status = "✓ 成功" if result.get('success') else "✗ 失败"
            print(f"   {status}: {result.get('message', '')[:60]}")
        else:
            print(f"   ✗ HTTP错误: {response.status_code}")
            error_detail = response.json().get('detail', '')
            print(f"     错误: {error_detail[:60]}")
    except requests.exceptions.Timeout:
        print("   ✗ 超时")
    except Exception as e:
        print(f"   ✗ 错误: {str(e)[:60]}")
    print()

if __name__ == "__main__":
    try:
        test_api()
    except requests.exceptions.ConnectionError:
        print("错误: 无法连接到 API 服务器，请确保服务器正在运行")
        print("启动服务器: python3 api_server.py")
    except Exception as e:
        print(f"错误: {e}")

