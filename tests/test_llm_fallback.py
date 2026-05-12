from app.services.llm_client import LLMClient


def test_llm_error_buffer_is_consumable():
    LLMClient.clear_recent_errors()

    LLMClient.record_error("example upstream timeout")

    assert LLMClient.consume_recent_errors() == ["example upstream timeout"]
    assert LLMClient.consume_recent_errors() == []
