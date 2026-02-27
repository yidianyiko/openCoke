from agent.runner.message_processor import get_queue_mode


def test_queue_mode_defaults_to_poll():
    assert get_queue_mode() == "poll"
