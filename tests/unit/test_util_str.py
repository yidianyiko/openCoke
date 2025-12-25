# -*- coding: utf-8 -*-
"""
util/str_util.py 单元测试
"""
import pytest

from util.str_util import remove_chinese


class TestRemoveChinese:
    """测试中文字符移除功能"""

    def test_pure_chinese(self):
        """测试纯中文字符串"""
        assert remove_chinese("你好世界") == ""
        assert remove_chinese("测试") == ""
        assert remove_chinese("中文字符串") == ""

    def test_mixed_text(self):
        """测试中英文混合"""
        assert remove_chinese("Hello你好World") == "HelloWorld"
        assert remove_chinese("Test测试123") == "Test123"
        assert remove_chinese("Python编程语言") == "Python"

    def test_empty_string(self):
        """测试空字符串"""
        assert remove_chinese("") == ""

    def test_no_chinese(self):
        """测试无中文字符"""
        assert remove_chinese("Hello World") == "Hello World"
        assert remove_chinese("12345") == "12345"
        assert remove_chinese("test@example.com") == "test@example.com"

    def test_special_characters(self):
        """测试特殊字符"""
        assert remove_chinese("Hello!@#$%你好") == "Hello!@#$%"
        assert remove_chinese("测试\n换行") == "\n"
        assert remove_chinese("空格 测试 spaces") == "  spaces"  # 两个空格

    def test_unicode_edge_cases(self):
        """测试 Unicode 边界情况"""
        # 日文假名不应被移除（不在中文 Unicode 范围）
        assert remove_chinese("こんにちは") == "こんにちは"
        # 韩文不应被移除
        assert remove_chinese("안녕하세요") == "안녕하세요"
        # 中文标点（注意：中文标点符号也在中文 Unicode 范围内）
        result = remove_chinese("你好，世界！")
        # 验证中文字符被移除
        assert "你" not in result
        assert "好" not in result
        assert "世" not in result
        assert "界" not in result

    def test_numbers_and_symbols(self):
        """测试数字和符号"""
        result = remove_chinese("价格：100元")
        # 验证中文字符被移除，数字保留
        assert "价" not in result
        assert "格" not in result
        assert "元" not in result
        assert "100" in result
        
        result = remove_chinese("2024年12月25日")
        # 年月日都是中文字符，会被移除
        assert "年" not in result
        assert "月" not in result
        assert "日" not in result
        assert "2024" in result
        assert "12" in result
        assert "25" in result

    @pytest.mark.parametrize(
        "input_text,expected",
        [
            ("", ""),
            ("abc", "abc"),
            ("中文", ""),
            ("a中b文c", "abc"),
            ("123测试456", "123456"),
        ],
    )
    def test_parametrized_cases(self, input_text, expected):
        """参数化测试"""
        assert remove_chinese(input_text) == expected
