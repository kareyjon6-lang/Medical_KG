import os
from functools import lru_cache
from typing import Any, Dict, Optional

from common.tcm_extractor_schema import normalize_extraction_payload


DEFAULT_EXTRACTOR_MODEL = "Qwen/Qwen2.5-1.5B-Instruct"

SYSTEM_PROMPT = """你是一个中医知识图谱结构化抽取模型。请从输入文本中抽取实体和关系，并只输出严格 JSON。
实体类型只能是：Symptom, Disease, Formula, Herb, Effect, Source。
关系类型只能是：TREATS_DISEASE, ALLEVIATES_SYMPTOM, HAS_EFFECT, HAS_INGREDIENT, HAS_SYMPTOM, FROM_SOURCE。
输出格式必须是 {"entities": [...], "relations": [...]}，不要输出解释、Markdown 或额外文本。"""


class LocalTCMExtractor:
    def __init__(
        self,
        model_name: Optional[str] = None,
        adapter_path: Optional[str] = None,
        device_map: str = "auto",
    ):
        self.model_name = model_name or os.getenv("TCM_EXTRACTOR_BASE_MODEL", DEFAULT_EXTRACTOR_MODEL)
        self.adapter_path = adapter_path or os.getenv("TCM_EXTRACTOR_ADAPTER_PATH", "")
        self.device_map = device_map
        self._tokenizer = None
        self._model = None

    def extract(self, text: str, max_new_tokens: int = 2048) -> Dict[str, Any]:
        tokenizer, model = self._load()
        messages = [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": "请从以下中医文本中抽取知识图谱结构，包括实体与关系。\n\n输入文本：\n{}".format(text)},
        ]
        prompt = tokenizer.apply_chat_template(messages, tokenize=False, add_generation_prompt=True)
        inputs = tokenizer(prompt, return_tensors="pt").to(model.device)
        outputs = model.generate(
            **inputs,
            max_new_tokens=max_new_tokens,
            do_sample=False,
            eos_token_id=tokenizer.eos_token_id,
            pad_token_id=tokenizer.pad_token_id or tokenizer.eos_token_id,
        )
        generated_ids = outputs[0][inputs["input_ids"].shape[-1] :]
        raw_text = tokenizer.decode(generated_ids, skip_special_tokens=True)
        return normalize_extraction_payload(raw_text)

    def _load(self):
        if self._model is not None and self._tokenizer is not None:
            return self._tokenizer, self._model

        import torch
        from transformers import AutoModelForCausalLM, AutoTokenizer

        tokenizer = AutoTokenizer.from_pretrained(self.model_name, trust_remote_code=True)
        if tokenizer.pad_token is None:
            tokenizer.pad_token = tokenizer.eos_token

        model = AutoModelForCausalLM.from_pretrained(
            self.model_name,
            torch_dtype=torch.float16 if torch.cuda.is_available() else torch.float32,
            device_map=self.device_map,
            trust_remote_code=True,
        )
        if self.adapter_path:
            from peft import PeftModel

            model = PeftModel.from_pretrained(model, self.adapter_path)
        model.eval()

        self._tokenizer = tokenizer
        self._model = model
        return tokenizer, model


@lru_cache(maxsize=1)
def get_local_tcm_extractor() -> LocalTCMExtractor:
    return LocalTCMExtractor()
