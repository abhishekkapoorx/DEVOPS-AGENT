from .groq_models import groq_models
from .ollama_models import ollama_models


DEFAULT_MODEL = ollama_models["gpt-oss:20b"]

__all__ = ["groq_models", "ollama_models", "DEFAULT_MODEL"]