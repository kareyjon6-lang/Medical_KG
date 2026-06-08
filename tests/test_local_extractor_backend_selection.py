from common.extractor_backend import get_extractor_backend_name


def test_prefers_local_extractor_when_adapter_path_is_set(monkeypatch):
    monkeypatch.delenv("TCM_EXTRACTOR_BACKEND", raising=False)
    monkeypatch.setenv("TCM_EXTRACTOR_ADAPTER_PATH", "models/tcm_extractor_lora")

    assert get_extractor_backend_name() == "local"


def test_explicit_api_backend_wins_over_adapter_path(monkeypatch):
    monkeypatch.setenv("TCM_EXTRACTOR_BACKEND", "api")
    monkeypatch.setenv("TCM_EXTRACTOR_ADAPTER_PATH", "models/tcm_extractor_lora")

    assert get_extractor_backend_name() == "api"
