import os
from dotenv import load_dotenv

load_dotenv()

BOT_TOKEN = os.getenv("BOT_TOKEN")
OWNER_ID = int(os.getenv("OWNER_ID", 0))

# PostgreSQL connection string – persistent, cloud-based
DATABASE_URL = os.getenv("DATABASE_URL")

# Models grouped for UI
MODELS = {
    "openai": [
        "openai/gpt-5.5-xhigh-codex",
        "openai/gpt-5.4-pro",
        "openai/gpt-4.1",
        "openai/gpt-4o",
        "openai/o3",
        "openai/o4-mini",
    ],
    "anthropic": [
        "anthropic/claude-opus-4.7",
        "anthropic/claude-sonnet-4.6",
        "anthropic/claude-3.7-sonnet",
    ],
    "google": [
        "google/gemini-3.1-pro",
        "google/gemini-2.5-pro",
        "google/gemini-2.5-flash",
        "google/gemini-2.0-flash",
    ],
    "xai": [
        "xai/grok-4.1-fast-reasoning",
        "xai/grok-4",
    ],
    "deepseek": [
        "deepseek-ai/DeepSeek-R1",
        "deepseek-ai/DeepSeek-V3.1",
        "deepseek-ai/DeepSeek-V3",
        "deepseek-ai/DeepSeek-Coder",
    ],
    "qwen": [
        "Qwen/Qwen3-235B",
        "Qwen/Qwen3-32B",
        "Qwen/Qwen3-Coder-480B",
        "Qwen/Qwen3-Coder-30B-A3B",
        "Qwen/Qwen2.5-Coder-32B",
        "Qwen/QwQ-32B",
    ],
    "meta": [
        "meta-llama/Llama-4-Maverick",
        "meta-llama/Llama-4-Scout",
        "meta-llama/Llama-3.3-70B-Instruct",
        "meta-llama/Llama-3.1-405B-Instruct",
    ],
    "moonshot": [
        "moonshot/Kimi-K2",
        "moonshot/Kimi-K2-Thinking",
    ],
    "minimax": [
        "minimax/MiniMax-M2.7",
    ],
    "zhipu": [
        "zhipu/glm-5",
        "zhipu/glm-4.7",
    ],
    "cohere": [
        "cohere/command-a",
        "cohere/command-r-plus",
    ],
    "mistral": [
        "mistralai/Mistral-Large-Instruct-2411",
        "mistralai/Codestral",
    ],
}

FALLBACK_MODELS = [
    "openai/gpt-4o",
    "anthropic/claude-3.7-sonnet",
    "google/gemini-2.5-pro",
    "meta-llama/Llama-3.3-70B-Instruct",
]

DEFAULT_MODEL = "openai/gpt-4.1"
PREMIUM_MODEL = "openai/gpt-5.5-xhigh-codex"
API_URL = os.getenv("API_URL", "https://lithovex.up.railway.app/api/chat/completions")
