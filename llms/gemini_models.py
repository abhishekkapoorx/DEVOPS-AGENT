from langchain_google_genai import ChatGoogleGenerativeAI
from utils import _set_if_undefined

_set_if_undefined("GOOGLE_API_KEY")

gemini_models = {
    #  models
    "gemini-1.5-flash": ChatGoogleGenerativeAI(model="gemini-1.5-flash"),
    "gemini-1.5-pro": ChatGoogleGenerativeAI(model="gemini-1.5-pro"),

    # Gemini 2.5 Models
    "gemini-2.5-pro": ChatGoogleGenerativeAI(model="gemini-2.5-pro"),
    "gemini-2.5-flash": ChatGoogleGenerativeAI(model="gemini-2.5-flash"),
    "gemini-2.5-flash-lite": ChatGoogleGenerativeAI(model="gemini-2.5-flash-lite"),
    "gemini-2.5-pro-deep-think": ChatGoogleGenerativeAI(model="gemini-2.5-pro-deep-think"),


}
