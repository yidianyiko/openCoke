# -*- coding: utf-8 -*-
"""
conf/config.py 单元测试
"""
import pytest


class TestConfig:
    """测试配置加载"""

    def test_config_import(self):
        """测试配置导入"""
        from conf.config import CONF

        assert CONF is not None
        assert isinstance(CONF, dict)

    def test_mongodb_config(self):
        """测试 MongoDB 配置"""
        from conf.config import CONF

        assert "mongodb" in CONF
        assert "mongodb_ip" in CONF["mongodb"]
        assert "mongodb_port" in CONF["mongodb"]
        assert "mongodb_name" in CONF["mongodb"]

    def test_config_values_type(self):
        """测试配置值类型"""
        from conf.config import CONF

        # MongoDB 配置应该是字符串
        assert isinstance(CONF["mongodb"]["mongodb_ip"], str)
        assert isinstance(CONF["mongodb"]["mongodb_port"], str)
        assert isinstance(CONF["mongodb"]["mongodb_name"], str)

    def test_config_not_empty(self):
        """测试配置不为空"""
        from conf.config import CONF

        assert len(CONF) > 0
        assert len(CONF["mongodb"]) > 0
