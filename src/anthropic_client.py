from dataclasses import dataclass
from anthropic import Anthropic


@dataclass
class LLMResponse:
    content: str
    prompt_tokens: int
    completion_tokens: int
    total_tokens: int
    cost_usd: float


class AnthropicClient:
    # Pricing per 1M tokens (as of Jan 2025)
    PRICING = {
        'claude-3-5-sonnet-20241022': {'input': 3.00, 'output': 15.00},
        'claude-3-5-haiku-20241022': {'input': 1.00, 'output': 5.00},
        'claude-3-opus-20240229': {'input': 15.00, 'output': 75.00},
        'claude-3-sonnet-20240229': {'input': 3.00, 'output': 15.00},
        'claude-3-haiku-20240307': {'input': 0.25, 'output': 1.25},
    }

    def __init__(self, api_key: str, model: str = 'claude-3-5-sonnet-20241022'):
        self.client = Anthropic(api_key=api_key)
        self.model = model

    def generate(self, system_prompt: str, user_prompt: str) -> LLMResponse:
        response = self.client.messages.create(
            model=self.model,
            max_tokens=4096,
            system=system_prompt,
            messages=[
                {"role": "user", "content": user_prompt}
            ]
        )

        content = response.content[0].text if response.content else ""
        usage = response.usage

        prompt_tokens = usage.input_tokens if usage else 0
        completion_tokens = usage.output_tokens if usage else 0
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
        pricing = self.PRICING.get(self.model, self.PRICING['claude-3-5-sonnet-20241022'])
        input_cost = (prompt_tokens / 1_000_000) * pricing['input']
        output_cost = (completion_tokens / 1_000_000) * pricing['output']
        return round(input_cost + output_cost, 6)

    def format_cost_info(self, response: LLMResponse) -> str:
        return (
            f"입력: {response.prompt_tokens:,} tokens, "
            f"출력: {response.completion_tokens:,} tokens"
            f" | 비용: ${response.cost_usd:.4f}"
        )
