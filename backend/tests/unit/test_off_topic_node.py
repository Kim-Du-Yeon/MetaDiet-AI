from app.agents.off_topic.node import off_topic_node


async def test_off_topic_node_returns_fixed_response_no_llm():
    result = await off_topic_node({"message": "미국 대통령이 누구야?"})

    assert result["agent_used"] == "off_topic"
    assert "식단" in result["response"]
