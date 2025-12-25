# -*- coding: utf-8 -*-
"""
集成测试配置

用于集成测试的真实 API 配置。
从环境变量读取真实的 API keys，确保测试的可靠性。

使用方法：
1. 确保 .env 文件中配置了所有必要的 API keys
2. 运行集成测试时设置环境变量 USE_REAL_API=true
3. 如果未设置或为 false，则跳过需要真实 API 的测试

环境变量：
- USE_REAL_API: 是否使用真实 API（true/false）
- DEEPSEEK_API_KEY: DeepSeek API key
- DASHSCOPE_API_KEY: 阿里云 DashScope API key
- ARK_API_KEY: 字节跳动火山引擎 API key
- OSS_ACCESS_KEY_ID: 阿里云 OSS Access Key ID
- OSS_ACCESS_KEY_SECRET: 阿里云 OSS Access Key Secret
"""

import os
from pathlib import Path
from typing import Optional

# 尝试加载 .env 文件
try:
    from dotenv import load_dotenv

    # 查找 .env 文件
    env_path = Path(__file__).parent.parent / ".env"
    if env_path.exists():
        load_dotenv(env_path)
except ImportError:
    # 如果没有安装 python-dotenv，跳过
    pass


def should_use_real_api() -> bool:
    """
    判断是否应该使用真实 API

    Returns:
        True 如果应该使用真实 API，否则 False
    """
    use_real_api = os.getenv("USE_REAL_API", "false").lower()
    return use_real_api in ("true", "1", "yes")


def get_deepseek_api_key() -> Optional[str]:
    """获取 DeepSeek API key"""
    key = os.getenv("DEEPSEEK_API_KEY")
    return key.strip('"') if key else None


def get_dashscope_api_key() -> Optional[str]:
    """获取阿里云 DashScope API key"""
    key = os.getenv("DASHSCOPE_API_KEY")
    return key.strip('"') if key else None


def get_ark_api_key() -> Optional[str]:
    """获取字节跳动火山引擎 API key"""
    key = os.getenv("ARK_API_KEY")
    return key.strip('"') if key else None


def get_oss_credentials() -> tuple[Optional[str], Optional[str]]:
    """
    获取阿里云 OSS 凭证

    Returns:
        (access_key_id, access_key_secret) 元组
    """
    access_key_id = os.getenv("OSS_ACCESS_KEY_ID")
    access_key_secret = os.getenv("OSS_ACCESS_KEY_SECRET")
    return (
        access_key_id.strip('"') if access_key_id else None,
        access_key_secret.strip('"') if access_key_secret else None,
    )


def validate_api_keys() -> dict[str, bool]:
    """
    验证所有 API keys 是否已配置

    Returns:
        字典，key 为 API 名称，value 为是否已配置
    """
    return {
        "deepseek": bool(get_deepseek_api_key()),
        "dashscope": bool(get_dashscope_api_key()),
        "ark": bool(get_ark_api_key()),
        "oss": all(get_oss_credentials()),
    }


def get_missing_api_keys() -> list[str]:
    """
    获取未配置的 API keys 列表

    Returns:
        未配置的 API 名称列表
    """
    validation = validate_api_keys()
    return [api for api, configured in validation.items() if not configured]


# 集成测试装饰器
def requires_real_api(api_name: Optional[str] = None):
    """
    装饰器：标记需要真实 API 的测试

    如果 USE_REAL_API 未设置或相应的 API key 未配置，则跳过测试

    Args:
        api_name: 需要的 API 名称（deepseek/dashscope/ark/oss），
                 如果为 None，则只检查 USE_REAL_API 标志

    使用示例：
        @requires_real_api("deepseek")
        def test_with_real_deepseek_api(self):
            ...
    """
    import unittest

    def decorator(test_func):
        def wrapper(*args, **kwargs):
            if not should_use_real_api():
                raise unittest.SkipTest(
                    "跳过真实 API 测试（设置 USE_REAL_API=true 以启用）"
                )

            if api_name:
                validation = validate_api_keys()
                if not validation.get(api_name, False):
                    raise unittest.SkipTest(
                        f"跳过测试：{api_name} API key 未配置"
                    )

            return test_func(*args, **kwargs)

        return wrapper

    return decorator


if __name__ == "__main__":
    # 测试配置
    print("集成测试配置检查")
    print("=" * 50)
    print(f"USE_REAL_API: {should_use_real_api()}")
    print("\nAPI Keys 配置状态:")

    validation = validate_api_keys()
    for api, configured in validation.items():
        status = "✓ 已配置" if configured else "✗ 未配置"
        print(f"  {api}: {status}")

    missing = get_missing_api_keys()
    if missing:
        print(f"\n警告：以下 API keys 未配置: {', '.join(missing)}")
        print("请在 .env 文件中配置相应的环境变量")
    else:
        print("\n✓ 所有 API keys 已配置")
