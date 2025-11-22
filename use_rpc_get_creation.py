import requests

def get_creation_code(tx_hash: str, rpc: str) -> str:
    """
    根据部署交易哈希获取合约 creation code（去掉 0x）
    :param tx_hash: 0x 开头的交易哈希
    :param rpc: 以太坊 RPC 端点
    :return: 十六进制字符串（无 0x 前缀）
    """
    payload = {
        "jsonrpc": "2.0",
        "method": "eth_getTransactionByHash",
        "params": [tx_hash],
        "id": 1
    }
    res = requests.post(rpc, json=payload, timeout=10)
    res.raise_for_status()
    data = res.json()

    if not data.get("result") or data["result"].get("input") is None:
        raise ValueError("交易不存在或非合约部署交易")

    creation_code = data["result"]["input"]
    if creation_code == "0x":
        raise ValueError("creation code 为空")

    return creation_code[2:]  # 去掉 0x


# 示例
if __name__ == "__main__":
    rpc_url = "https://bsc-mainnet.nodereal.io/v1/814c23529df542eab440417905ff18b7"
    deploy_tx = "0x12eee29552222510de6890f1693d6bbe5e443930883debb6814e75b86a3571a7"
    print(get_creation_code(deploy_tx, rpc_url))
