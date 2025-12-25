# -*- coding: utf-8 -*-
"""
字符串工具属性测试
"""
import pytest
from hypothesis import given, strategies as st

from util.str_util import remove_chinese


@pytest.mark.pbt
class TestStrUtilPBT:
    """字符串工具属性测试"""

    @given(st.text())
    def test_remove_chinese_never_crashes(self, text):
        """remove_chinese 不应该崩溃"""
        result = remove_chinese(text)
        assert isinstance(result, str)

    @given(st.text(alphabet=st.characters(blacklist_categories=("Lo",))))
    def test_remove_chinese_no_chinese_unchanged(self, text):
        """没有中文的文本应该保持不变"""
        # 过滤掉中文字符
        if not any("\u4e00" <= char <= "\u9fff" for char in text):
            result = remove_chinese(text)
            assert result == text

    @given(st.text())
    def test_remove_chinese_length_property(self, text):
        """移除中文后长度应该小于等于原长度"""
        result = remove_chinese(text)
        assert len(result) <= len(text)

    @given(st.text(), st.text())
    def test_remove_chinese_concatenation(self, text1, text2):
        """测试连接属性"""
        result1 = remove_chinese(text1)
        result2 = remove_chinese(text2)
        combined_result = remove_chinese(text1 + text2)

        # 分别处理再连接应该等于连接后处理
        assert combined_result == result1 + result2

    @given(st.text(alphabet="你好世界测试"))
    def test_remove_chinese_pure_chinese(self, text):
        """纯中文应该被完全移除"""
        result = remove_chinese(text)
        assert result == ""
