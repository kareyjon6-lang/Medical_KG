import os


def get_extractor_backend_name() -> str:
    configured = os.getenv("TCM_EXTRACTOR_BACKEND", "auto").strip().lower()
    if configured in {"api", "local"}:
        return configured
    adapter_path = os.getenv("TCM_EXTRACTOR_ADAPTER_PATH", "").strip()
    return "local" if adapter_path else "api"
