import os
from dataclasses import dataclass
from typing import Union
from openai import OpenAI


@dataclass
class LLMResponse:
    content: str
    prompt_tokens: int
    completion_tokens: int
    total_tokens: int
    cost_usd: float


def create_client(engine: str, api_key: str, model: str) -> Union['LLMClient', 'AnthropicClient']:
    """Factory function to create appropriate LLM client based on engine type."""
    if engine == 'claude':
        from anthropic_client import AnthropicClient
        return AnthropicClient(api_key=api_key, model=model)
    else:
        return LLMClient(api_key=api_key, model=model)


class LLMClient:
    # Pricing per 1M tokens (as of Jan 2025, update as needed)
    PRICING = {
        'o3-mini': {'input': 1.10, 'output': 4.40},
        'o1': {'input': 15.00, 'output': 60.00},
        'o1-mini': {'input': 3.00, 'output': 12.00},
        'gpt-4o': {'input': 2.50, 'output': 10.00},
        'gpt-4o-mini': {'input': 0.15, 'output': 0.60},
        'gpt-4-turbo': {'input': 10.00, 'output': 30.00},
    }

    def __init__(self, api_key: str, model: str = 'o3-mini'):
        self.client = OpenAI(api_key=api_key)
        self.model = model

    def generate(self, system_prompt: str, user_prompt: str) -> LLMResponse:
        # o1, o3 모델은 temperature를 지원하지 않음
        is_reasoning_model = self.model.startswith(('o1', 'o3'))

        params = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt}
            ],
            "max_completion_tokens": 4096
        }

        if not is_reasoning_model:
            params["temperature"] = 0.7

        response = self.client.chat.completions.create(**params)

        content = response.choices[0].message.content or ""
        usage = response.usage

        prompt_tokens = usage.prompt_tokens if usage else 0
        completion_tokens = usage.completion_tokens if usage else 0
        total_tokens = prompt_tokens + completion_tokens

        cost = self._calculate_cost(prompt_tokens, completion_tokens)

        return LLMResponse(
            content=content,
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            total_tokens=total_tokens,
            cost_usd=cost
        )

    def _calculate_cost(self, prompt_tokens: int, completion_tokens: int) -> float:
        pricing = self.PRICING.get(self.model, self.PRICING['gpt-4o'])
        input_cost = (prompt_tokens / 1_000_000) * pricing['input']
        output_cost = (completion_tokens / 1_000_000) * pricing['output']
        return round(input_cost + output_cost, 6)

    def format_cost_info(self, response: LLMResponse) -> str:
        return (
            f"입력: {response.prompt_tokens:,} tokens, "
            f"출력: {response.completion_tokens:,} tokens"
            f" | 비용: ${response.cost_usd:.4f}"
        )
