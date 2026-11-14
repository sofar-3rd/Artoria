from scripts.mcp_eval.data import Tool

TOOL_CHUNK_MAX_TOKENS = 256


def validate_tool_token_budget(tools: list[Tool], tokenizer) -> list[int]:
    """Count the complete retrieval text, excluding model-added special tokens."""
    lengths = []
    for tool in tools:
        count = len(tokenizer.encode(tool.text, add_special_tokens=False))
        if count > TOOL_CHUNK_MAX_TOKENS:
            raise ValueError(
                f"tool chunk exceeds token budget: {tool.tool_id}: "
                f"{count} tokens > {TOOL_CHUNK_MAX_TOKENS}; shorten the description"
            )
        lengths.append(count)
    return lengths
