# -*- coding: utf-8 -*-
"""
向量操作属性测试
"""
import pytest
from hypothesis import given, strategies as st

from dao.mongo import VectorUtils


@pytest.mark.pbt
class TestVectorUtilsPBT:
    """向量工具属性测试"""

    @given(
        st.lists(st.floats(min_value=-1.0, max_value=1.0), min_size=3, max_size=10),
        st.lists(st.floats(min_value=-1.0, max_value=1.0), min_size=3, max_size=10),
    )
    def test_cosine_similarity_range(self, vec_a, vec_b):
        """余弦相似度应该在 [-1, 1] 范围内"""
        if len(vec_a) == len(vec_b):
            similarity = VectorUtils.cosine_similarity(vec_a, vec_b)
            # 允许浮点数精度误差
            assert -1.0-1e-10 <= similarity <= 1.0 + 1e-10

    @given(st.lists(st.floats(min_value=-1.0, max_value=1.0, allow_nan=False, allow_infinity=False), min_size=3, max_size=10))
    def test_cosine_similarity_self(self, vec):
        """向量与自己的余弦相似度应该为 1"""
        # 过滤掉全零或接近全零的向量
        if all(abs(v) < 1e-10 for v in vec):
            return  # 跳过这个测试用例
            
        similarity = VectorUtils.cosine_similarity(vec, vec)
        # 允许浮点数精度误差
        assert abs(similarity-1.0) < 1e-6

    @given(
        st.lists(st.floats(min_value=-10.0, max_value=10.0), min_size=2, max_size=10),
        st.lists(st.floats(min_value=-10.0, max_value=10.0), min_size=2, max_size=10),
    )
    def test_euclidean_distance_non_negative(self, vec_a, vec_b):
        """欧氏距离应该非负"""
        if len(vec_a) == len(vec_b):
            distance = VectorUtils.euclidean_distance(vec_a, vec_b)
            assert distance >= 0

    @given(st.lists(st.floats(min_value=-10.0, max_value=10.0), min_size=2, max_size=10))
    def test_euclidean_distance_self(self, vec):
        """向量与自己的欧氏距离应该为 0"""
        distance = VectorUtils.euclidean_distance(vec, vec)
        assert abs(distance) < 0.001

    @given(st.lists(st.floats(min_value=0.1, max_value=10.0), min_size=2, max_size=10))
    def test_normalize_vector_length(self, vec):
        """归一化后的向量长度应该为 1"""
        import numpy as np

        normalized = VectorUtils.normalize_vector(vec)
        length = np.linalg.norm(normalized)
        assert abs(length-1.0) < 0.001

    @given(
        st.lists(
            st.lists(st.floats(min_value=-1.0, max_value=1.0), min_size=3, max_size=3),
            min_size=1,
            max_size=10,
        )
    )
    def test_average_vectors_length(self, vectors):
        """平均向量的长度应该等于输入向量的长度"""
        if vectors:
            avg = VectorUtils.average_vectors(vectors)
            assert len(avg) == len(vectors[0])
