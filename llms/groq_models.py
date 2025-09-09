from langchain_groq import ChatGroq

from utils import _set_if_undefined

_set_if_undefined("GROQ_API_KEY")


groq_models = {
    "openai/gpt-oss-20b": ChatGroq(model="openai/gpt-oss-20b"),
    "openai/gpt-oss-120b": ChatGroq(model="openai/gpt-oss-120b"),
    "llama-3.1-8b-instant": ChatGroq(model="llama-3.1-8b-instant"),
    "meta-llama/llama-4-scout-17b-16e-instruct": ChatGroq(model="meta-llama/llama-4-scout-17b-16e-instruct"),  
}