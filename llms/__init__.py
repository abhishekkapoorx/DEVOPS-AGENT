from .groq_models import groq_models
from .ollama_models import ollama_models


DEFAULT_MODEL = groq_models["meta-llama/llama-4-scout-17b-16e-instruct"]
# DEFAULT_MODEL = ollama_models["gpt-oss:20b"]

__all__ = ["groq_models", "ollama_models", "DEFAULT_MODEL"]