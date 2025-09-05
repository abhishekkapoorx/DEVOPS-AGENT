from langchain_openai import ChatOpenAI
from utils import _set_if_undefined

_set_if_undefined("OPENAI_API_KEY")

openai_models = {
    "gpt-4o-mini": ChatOpenAI(model="gpt-4o-mini"),
    "gpt-4o": ChatOpenAI(model="gpt-4o"),
    "gpt-3.5-turbo": ChatOpenAI(model="gpt-3.5-turbo"),


    "gpt-5": ChatOpenAI(model="gpt-5"),
    "gpt-5-mini": ChatOpenAI(model="gpt-5-mini"),
    "gpt-5-nano": ChatOpenAI(model="gpt-5-nano"),
    "gpt-5-chat": ChatOpenAI(model="gpt-5-chat"),

    # Open-weight OSS variants
    "gpt-oss-120b": ChatOpenAI(model="gpt-oss-120b"),
    "gpt-oss-20b": ChatOpenAI(model="gpt-oss-20b"),

    # o-Series reasoning models
    "o3": ChatOpenAI(model="o3"),
    "o3-mini": ChatOpenAI(model="o3-mini"),
    "o3-pro": ChatOpenAI(model="o3-pro"),
    "o4-mini": ChatOpenAI(model="o4-mini"),

    # GPT-4.1 Series
    "gpt-4.1": ChatOpenAI(model="gpt-4.1"),
    "gpt-4.1-mini": ChatOpenAI(model="gpt-4.1-mini"),
    "gpt-4.1-nano": ChatOpenAI(model="gpt-4.1-nano"),
}
