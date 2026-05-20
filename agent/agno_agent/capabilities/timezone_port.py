from __future__ import annotations

from agent.agno_agent.capabilities.timezone import TimezoneCapabilityPort


class TimezonePort(TimezoneCapabilityPort):
    def __init__(self, handler=None, **kwargs):
        if handler is not None:
            kwargs["contract_factory"] = lambda _run_context: _HandlerContract(handler)
        super().__init__(**kwargs)


class _HandlerContract:
    def __init__(self, handler):
        self.handler = handler

    def handle_timezone_request(self, run_context, args):
        return self.handler("", run_context, args)
