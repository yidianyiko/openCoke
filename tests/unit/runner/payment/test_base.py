import pytest
from agent.runner.payment.base import PaymentProvider


class TestPaymentProviderInterface:
    @pytest.mark.unit
    def test_base_class_cannot_be_instantiated_directly(self):
        """Base class methods must be overridden"""
        class BrokenProvider(PaymentProvider):
            pass  # 不实现任何方法

        p = BrokenProvider()
        with pytest.raises(NotImplementedError):
            p.create_checkout_url({"_id": "user123"})
