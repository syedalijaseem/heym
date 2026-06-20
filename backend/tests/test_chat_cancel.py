import unittest
from threading import Event

from app.api import chats


class TestRequestChatCancel(unittest.TestCase):
    def setUp(self) -> None:
        chats._cancel_events.clear()

    def tearDown(self) -> None:
        chats._cancel_events.clear()

    def test_returns_false_when_no_task_registered(self) -> None:
        self.assertFalse(chats.request_chat_cancel("missing-conv"))

    def test_sets_event_for_registered_task(self) -> None:
        conv_id = "conv-123"
        event = Event()
        chats._cancel_events[conv_id] = event

        self.assertFalse(event.is_set())
        result = chats.request_chat_cancel(conv_id)

        self.assertTrue(result)
        self.assertTrue(event.is_set())

    def test_cancel_is_idempotent(self) -> None:
        conv_id = "conv-456"
        event = Event()
        chats._cancel_events[conv_id] = event

        self.assertTrue(chats.request_chat_cancel(conv_id))
        # A second call still finds the task and leaves the event set.
        self.assertTrue(chats.request_chat_cancel(conv_id))
        self.assertTrue(event.is_set())


if __name__ == "__main__":
    unittest.main()
