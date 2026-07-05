"""
Context-aware model configuration. Dynamically adjusts data retrieval scope
based on the model's context window limit to prevent overflow errors.
"""
import os
from typing import Dict, Any


# Model context window mapping (in tokens, approximate)
MODEL_CONTEXT_SIZES = {
    # Small models
    "qwen-turbo": 8192,
    "qwen-plus": 32768,
    "qwen-long": 1000000,
    "deepseek-chat": 64000,
    "deepseek-reasoner": 64000,
    "glm-4-plus": 128000,
    "glm-4-0520": 128000,
    # Medium models
    "gpt-4o": 128000,
    "gpt-4o-mini": 128000,
    "gpt-4-turbo": 128000,
    "claude-3-5-sonnet": 200000,
    "agnes-2.0-flash": 128000,
    # Large models
    "claude-3-opus": 200000,
    "gpt-4": 8192,
    "o1": 128000,
    "o1-mini": 128000,
}


def get_context_window(model_name: str) -> int:
    """Get the context window size for a given model name."""
    if not model_name:
        return 32768  # Default safe fallback

    model_lower = model_name.lower()

    # Exact match
    if model_lower in MODEL_CONTEXT_SIZES:
        return MODEL_CONTEXT_SIZES[model_lower]

    # Partial match (e.g., "agnes-2.0-flash-v2" should match "agnes-2.0-flash")
    for key, size in MODEL_CONTEXT_SIZES.items():
        if key in model_lower:
            return size

    # Default: assume 32k if unknown
    return 32768


def estimate_token_length(text: str) -> int:
    """Rough token count estimation (1 token ~ 2 Chinese chars or 1 English word)."""
    chinese_chars = sum(1 for c in text if '一' <= c <= '鿿')
    non_chinese = len(text) - chinese_chars
    return chinese_chars // 2 + non_chinese


def get_agent_max_tokens(model_name: str, agent_type: str) -> int:
    """
    Calculate the appropriate max_tokens for each agent type
    based on the model's context window.

    The 3 agents share context, so each gets a portion:
    - fundamental: 30% of remaining budget
    - technical: 20% of remaining budget
    - value: 30% of remaining budget

    But also cap each to prevent overflow.
    """
    context_window = get_context_window(model_name)

    # Reserve 20% of context for system prompts, summary agent, and overhead
    available_tokens = int(context_window * 0.8)

    # Each agent is independent (parallel), so they each get their own budget
    # But the LLM sees all tool responses cumulatively in one ReAct loop
    # So each agent's max_tokens should prevent a single agent from consuming too much

    agent_budgets = {
        "fundamental": int(available_tokens * 0.3),
        "technical": int(available_tokens * 0.2),
        "value": int(available_tokens * 0.3),
    }

    # Hard caps to prevent any single agent from consuming too many tokens
    hard_caps = {
        "fundamental": 2000,
        "technical": 1500,
        "value": 2000,
    }

    return min(agent_budgets.get(agent_type, 1000), hard_caps.get(agent_type, 1000))


def get_data_retrieval_limit(model_name: str, agent_type: str) -> Dict[str, Any]:
    """
    Generate agent-specific constraints based on context window.

    Returns a dict of constraints to inject into the agent's prompt:
    - max_data_points: How many data points to fetch per tool
    - time_range_months: How many months of historical data to fetch
    - additional_instructions: Extra instructions for the agent
    """
    context_window = get_context_window(model_name)

    # Small context (< 32k): be very conservative
    if context_window < 32768:
        return {
            "max_data_points": 1,
            "time_range_months": 3,
            "additional_instructions": (
                "IMPORTANT: Only fetch the most recent single data point per tool call. "
                "Do NOT fetch historical data or multiple quarters. "
                "Keep all responses extremely concise. "
                "If a tool returns too much data, stop calling it immediately."
            ),
        }

    # Medium context (32k - 64k): moderate limits
    if context_window < 64768:
        return {
            "max_data_points": 1,
            "time_range_months": 3,
            "additional_instructions": (
                "IMPORTANT: Only fetch the most recent quarter's data. "
                "Do NOT fetch multiple quarters or years of historical data. "
                "Keep responses concise and focused on key metrics."
            ),
        }

    # Large context (64k - 128k): standard limits
    if context_window < 128768:
        return {
            "max_data_points": 2,
            "time_range_months": 6,
            "additional_instructions": (
                "IMPORTANT: Focus on the most recent quarter's data only. "
                "Do NOT fetch more than 2 data points per metric. "
                "Avoid unnecessary historical data retrieval."
            ),
        }

    # Very large context (> 128k): generous but still bounded
    return {
        "max_data_points": 4,
        "time_range_months": 12,
        "additional_instructions": (
            "IMPORTANT: Focus on the most recent data. "
            "Do NOT fetch more than 4 data points per metric. "
            "Prioritize recent quarters over historical ones."
        ),
    }
