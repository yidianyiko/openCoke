#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
检查代码格式化问题

检查代码中可能被错误格式化的常量，特别是包含空格的连字符。

运行方式：
    python scripts/check_formatting_issues.py
"""

import os
import re
import sys
from pathlib import Path


def check_file(file_path: Path) -> list[dict]:
    """
    检查单个文件中的格式化问题

    Args:
        file_path: 文件路径

    Returns:
        问题列表，每个问题包含 line_number, line_content, issue_type
    """
    issues = []

    try:
        with open(file_path, "r", encoding="utf-8") as f:
            lines = f.readlines()

        for line_num, line in enumerate(lines, 1):
            # 检查 1: Agent/Model ID 包含空格的连字符
            if re.search(r'id\s*=\s*["\'][^"\']*\s-\s', line):
                issues.append(
                    {
                        "line_number": line_num,
                        "line_content": line.strip(),
                        "issue_type": "ID 包含空格的连字符",
                        "pattern": r'id\s*=\s*["\'][^"\']*\s-\s',
                    }
                )

            # 检查 2: endpoint/region/bucket_name 包含空格
            if re.search(r'(endpoint|region|bucket_name)\s*=\s*["\'][^"\']*\s-\s', line):
                issues.append(
                    {
                        "line_number": line_num,
                        "line_content": line.strip(),
                        "issue_type": "配置项包含空格的连字符",
                        "pattern": r'(endpoint|region|bucket_name)\s*=\s*["\'][^"\']*\s-\s',
                    }
                )

            # 检查 3: URL 包含空格
            if re.search(r'https?://[^\s"\']*\s-\s', line):
                issues.append(
                    {
                        "line_number": line_num,
                        "line_content": line.strip(),
                        "issue_type": "URL 包含空格",
                        "pattern": r'https?://[^\s"\']*\s-\s',
                    }
                )

            # 检查 4: 模型名称包含空格
            if re.search(r'model\s*=\s*[^(]*\([^)]*["\'][^"\']*\s-\s', line):
                issues.append(
                    {
                        "line_number": line_num,
                        "line_content": line.strip(),
                        "issue_type": "模型名称包含空格的连字符",
                        "pattern": r'model\s*=\s*[^(]*\([^)]*["\'][^"\']*\s-\s',
                    }
                )

    except Exception as e:
        print(f"警告：无法读取文件 {file_path}: {e}")

    return issues


def scan_directory(directory: Path, extensions: list[str] = None) -> dict:
    """
    扫描目录中的所有文件

    Args:
        directory: 目录路径
        extensions: 要检查的文件扩展名列表（默认 ['.py', '.json']）

    Returns:
        字典，key 为文件路径，value 为问题列表
    """
    if extensions is None:
        extensions = [".py", ".json"]

    results = {}

    for root, dirs, files in os.walk(directory):
        # 跳过虚拟环境和其他不需要检查的目录
        dirs[:] = [
            d
            for d in dirs
            if d not in [".venv", "venv", "__pycache__", ".git", "node_modules"]
        ]

        for file in files:
            if any(file.endswith(ext) for ext in extensions):
                file_path = Path(root) / file
                issues = check_file(file_path)
                if issues:
                    results[file_path] = issues

    return results


def print_results(results: dict) -> None:
    """
    打印检查结果

    Args:
        results: 扫描结果字典
    """
    if not results:
        print("✓ 未发现格式化问题")
        return

    print(f"✗ 发现 {len(results)} 个文件存在格式化问题\n")

    for file_path, issues in results.items():
        print(f"文件: {file_path}")
        print("-" * 60)

        for issue in issues:
            print(f"  行 {issue['line_number']}: {issue['issue_type']}")
            print(f"    {issue['line_content']}")
            print()

        print()


def main():
    """主函数"""
    print("检查代码格式化问题")
    print("=" * 60)
    print()

    # 获取项目根目录
    script_dir = Path(__file__).parent
    project_root = script_dir.parent

    # 扫描主要代码目录
    directories_to_scan = [
        project_root / "agent",
        project_root / "conf",
        project_root / "dao",
        project_root / "entity",
        project_root / "util",
        project_root / "scripts",
        project_root / "tests",
    ]

    all_results = {}

    for directory in directories_to_scan:
        if directory.exists():
            print(f"扫描目录: {directory.relative_to(project_root)}")
            results = scan_directory(directory)
            all_results.update(results)

    print()
    print("=" * 60)
    print()

    print_results(all_results)

    # 返回退出码
    if all_results:
        print("建议：")
        print("1. 检查上述文件中的格式化问题")
        print("2. 将包含空格的连字符（' - '）替换为连字符（'-'）")
        print("3. 重新运行此脚本确认问题已解决")
        sys.exit(1)
    else:
        print("所有检查通过！")
        sys.exit(0)


if __name__ == "__main__":
    main()
