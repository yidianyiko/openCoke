# -*- coding: utf-8 -*-
"""
util/file_util.py 单元测试
"""
import os

import pytest


class TestFileUtil:
    """测试文件工具函数"""

    def test_temp_file_creation(self, temp_test_file):
        """测试临时文件创建"""
        assert temp_test_file.exists()
        assert temp_test_file.read_text() == "测试内容"

    def test_temp_dir_creation(self, temp_test_dir):
        """测试临时目录创建"""
        assert temp_test_dir.exists()
        assert temp_test_dir.is_dir()

    def test_file_operations(self, temp_test_dir):
        """测试文件操作"""
        # 创建文件
        test_file = temp_test_dir / "new_file.txt"
        test_file.write_text("新内容")
        assert test_file.exists()

        # 读取文件
        content = test_file.read_text()
        assert content == "新内容"

        # 删除文件
        test_file.unlink()
        assert not test_file.exists()

    def test_directory_operations(self, temp_test_dir):
        """测试目录操作"""
        # 创建子目录
        sub_dir = temp_test_dir / "subdir"
        sub_dir.mkdir()
        assert sub_dir.exists()
        assert sub_dir.is_dir()

        # 在子目录中创建文件
        sub_file = sub_dir / "file.txt"
        sub_file.write_text("子目录文件")
        assert sub_file.exists()

    def test_path_operations(self, temp_test_dir):
        """测试路径操作"""
        test_path = temp_test_dir / "test.txt"
        test_path.write_text("测试")

        # 测试路径属性
        assert test_path.name == "test.txt"
        assert test_path.suffix == ".txt"
        assert test_path.stem == "test"
        assert test_path.parent == temp_test_dir
