from api.live import RESYNC, Hub, libpq_dsn, parse_notification


def drain(queue) -> list[dict]:
    messages = []
    while not queue.empty():
        messages.append(queue.get_nowait())
    return messages


def item_change(n: int) -> dict:
    return {"topic": "workflow_item", "id": f"item-{n}", "workflow_id": "wf"}


def test_a_trigger_payload_parses():
    assert parse_notification('{"id": "abc", "topic": "workflow"}') == {"id": "abc", "topic": "workflow"}


def test_a_payload_that_is_not_json_is_ignored():
    assert parse_notification("not json") is None


def test_a_payload_without_a_topic_is_ignored():
    """anyone can NOTIFY the channel, and the listener must not fall over when they do"""
    assert parse_notification('{"id": "abc"}') is None
    assert parse_notification('["workflow"]') is None


def test_the_same_change_twice_in_a_window_is_announced_once():
    hub = Hub()
    client = hub.subscribe()

    hub.publish(item_change(1))
    hub.publish(item_change(1))
    hub.publish(item_change(2))
    hub.flush()

    assert drain(client) == [{"type": "changes", "changes": [item_change(1), item_change(2)]}]


def test_key_order_does_not_defeat_coalescing():
    hub = Hub()
    client = hub.subscribe()

    hub.publish({"topic": "workflow", "id": "a"})
    hub.publish({"id": "a", "topic": "workflow"})
    hub.flush()

    assert len(drain(client)[0]["changes"]) == 1


def test_a_quiet_window_sends_nothing():
    hub = Hub()
    client = hub.subscribe()
    hub.flush()
    assert drain(client) == []


def test_a_burst_too_large_to_name_becomes_a_resync():
    """discovering a large archive inserts thousands of scenes in one go"""
    hub = Hub(max_batch=3)
    client = hub.subscribe()

    for n in range(4):
        hub.publish(item_change(n))
    hub.flush()

    assert drain(client) == [RESYNC]


def test_every_client_hears_every_change():
    hub = Hub()
    first, second = hub.subscribe(), hub.subscribe()

    hub.publish({"topic": "queue"})
    hub.flush()

    assert drain(first) == drain(second) == [{"type": "changes", "changes": [{"topic": "queue"}]}]


def test_a_client_that_falls_behind_is_told_to_resync_rather_than_buffered_for():
    hub = Hub(backlog=2)
    slow = hub.subscribe()

    for n in range(5):
        hub.publish(item_change(n))
        hub.flush()

    messages = drain(slow)
    assert len(messages) <= 2, "the backlog must stay bounded"
    assert RESYNC in messages, "what it missed has to be refetched, not silently lost"


def test_an_unsubscribed_client_hears_nothing_more():
    hub = Hub()
    client = hub.subscribe()
    hub.unsubscribe(client)

    hub.publish({"topic": "queue"})
    hub.flush()

    assert drain(client) == []


def test_the_listener_dsn_drops_the_sqlalchemy_driver():
    assert libpq_dsn("postgresql+asyncpg://u:p@db:5432/geotriage") == "postgresql://u:p@db:5432/geotriage"


def test_the_listener_dsn_keeps_a_password_that_needs_escaping():
    assert libpq_dsn("postgresql+asyncpg://u:p%40ss@db:5432/geotriage") == "postgresql://u:p%40ss@db:5432/geotriage"
