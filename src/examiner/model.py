import os


def get_model():
    provider = os.getenv("MODEL_PROVIDER", "google").lower()

    if provider == "google":
        from langchain_google_genai import ChatGoogleGenerativeAI

        return ChatGoogleGenerativeAI(
            model=os.getenv("MODEL_NAME", "gemini-2.0-flash"),
            temperature=0.3,
        )

    if provider == "ollama":
        from langchain_ollama import ChatOllama

        return ChatOllama(
            model=os.getenv("MODEL_NAME", "llama3.1"),
            base_url=os.getenv("OLLAMA_BASE_URL", "http://localhost:11434"),
            temperature=0.3,
        )

    raise ValueError(
        f"Unknown MODEL_PROVIDER={provider!r}. Expected 'google' or 'ollama'."
    )
