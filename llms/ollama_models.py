from langchain_ollama import ChatOllama


ollama_models = {
    "gpt-oss:20b": ChatOllama(model="gpt-oss:20b"),
    "gpt-oss:120b": ChatOllama(model="gpt-oss:120b"),
    "llama3.1-70b-versatile": ChatOllama(model="llama3.1-70b-versatile"),
}