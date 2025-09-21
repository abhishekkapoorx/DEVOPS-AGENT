from .groq_models import groq_models
from .openai_models import openai_models
from .gemini_models import gemini_models
from .ollama_models import ollama_models

# DEFAULT_MODEL = groq_models["meta-llama/llama-4-scout-17b-16e-instruct"]
primary_model = openai_models["gpt-4o-mini"]
# primary_model = gemini_models["gemini-2.5-pro-deep-think"]
DEFAULT_MODEL = primary_model.with_fallbacks(
    [
        # Most powerful models first
        gemini_models["gemini-2.5-pro"],
        ollama_models["gpt-oss:20b"],
        gemini_models["gemini-2.5-pro-deep-think"],
        openai_models["gpt-5"],
        openai_models["gpt-5-chat"],
        openai_models["gpt-4o"],
        gemini_models["gemini-1.5-pro"],
        openai_models["gpt-5-mini"],
        gemini_models["gemini-2.5-flash"],
        openai_models["gpt-4o-mini"],
        gemini_models["gemini-1.5-flash"],
        openai_models["gpt-5-nano"],
        gemini_models["gemini-2.5-flash-lite"],
        openai_models["gpt-3.5-turbo"],
    ]
)

__all__ = ["groq_models", "openai_models", "gemini_models", "ollama_models", "DEFAULT_MODEL"]