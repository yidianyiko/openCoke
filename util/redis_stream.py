def publish_input_event(
    redis_client,
    message_id: str,
    platform: str,
    ts: int,
    stream_key: str = "coke:input",
):
    redis_client.xadd(
        stream_key,
        {"message_id": message_id, "platform": platform, "ts": str(ts)},
    )
