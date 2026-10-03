"""`make doctor`: environment sanity check for the low-RAM development machine.

Prints free RAM, verifies that model/key settings are filled in, and warns
when the configured pipeline is likely to exceed free memory. The per-stage
memory numbers are planning estimates; Phase 8 replaces them with measured
peaks (see docs/PROGRESS.md).
"""

from __future__ import annotations

import sys
from dataclasses import dataclass

import psutil

from app.core.config import (
    ENV_FILE,
    Backend,
    RerankBackend,
    Settings,
    VlmMode,
    get_settings,
)

# Rough resident-memory estimates (MB) per locally loaded stage. Hosted
# backends cost ~0 locally. Stages run one at a time (A3.1), so the pipeline
# peak is the largest single stage plus the base process.
BASE_PROCESS_MB = 450
LOCAL_STAGE_MB: dict[str, int] = {
    "docling_layout_tables": 1800,
    "ocr_rapidocr_onnx": 350,
    "image_embed_siglip2_base_fp32": 1700,
    "text_embed_bge_m3_local": 2400,
    "rerank_bge_v2_m3_local": 2400,
}


@dataclass
class Finding:
    level: str  # OK | WARN | FAIL
    message: str


def _is_placeholder(value: str) -> bool:
    return not value or value.startswith("your-") or value.startswith("change-me")


def check_settings(s: Settings) -> list[Finding]:
    out: list[Finding] = []
    out.append(Finding("OK" if ENV_FILE.is_file() else "WARN", f".env file: {ENV_FILE}"))
    out.append(Finding("OK", f"HARDWARE_PROFILE={s.hardware_profile}  DEV_LITE_MODE={s.dev_lite_mode}"))

    if _is_placeholder(s.jwt_secret.get_secret_value()) or len(s.jwt_secret.get_secret_value()) < 32:
        out.append(Finding("WARN", "JWT_SECRET is a placeholder or shorter than 32 chars"))

    if not s.llm_endpoints:
        out.append(Finding("FAIL", "LLM_CHAIN is empty"))
    for ep in s.llm_endpoints:
        ok = ep.is_configured()
        out.append(
            Finding("OK" if ok else "WARN", f"LLM {ep.index} {ep.label}: {ep.model} @ {ep.base_url}"
                    + ("" if ok else "  (API key missing/placeholder)"))
        )

    def hosted(name: str, model: str, base: str, key: str) -> None:
        if not model or not base:
            out.append(Finding("FAIL", f"{name}: model or base URL not set"))
        elif _is_placeholder(key):
            out.append(Finding("WARN", f"{name}: {model} @ {base}  (API key missing/placeholder)"))
        else:
            out.append(Finding("OK", f"{name}: {model} @ {base}"))

    if s.vlm_mode is VlmMode.OFF:
        out.append(Finding("OK", "VLM: off"))
    elif s.vlm_backend is Backend.API:
        hosted(f"VLM ({s.vlm_mode})", s.vlm_model, s.vlm_base_url, s.vlm_api_key.get_secret_value())
    if s.embed_backend is Backend.API:
        hosted("Text embeddings", s.embed_model, s.embed_base_url, s.embed_api_key.get_secret_value())
    if s.rerank_backend is RerankBackend.API:
        hosted("Reranker", s.rerank_model, s.rerank_base_url, s.rerank_api_key.get_secret_value())
    elif s.rerank_backend is RerankBackend.OFF:
        out.append(Finding("WARN", "Reranker: off (fusion order will be used)"))
    out.append(Finding("OK" if s.image_embed_model else "FAIL",
                       f"Image embeddings ({s.image_embed_backend}): {s.image_embed_model or 'not set'}"
                       f"  mode={s.image_retrieval_mode}"))

    if s.hardware_profile == "cpu_8gb":
        for name, backend in (("VLM_BACKEND", s.vlm_backend), ("EMBED_BACKEND", s.embed_backend)):
            if backend is Backend.LOCAL and not (name == "EMBED_BACKEND" and s.app_env == "test"):
                out.append(Finding("WARN", f"{name}=local on cpu_8gb is out of scope (A3.1)"))
    return out


def estimate_peak_mb(s: Settings) -> tuple[int, dict[str, int]]:
    stages = {"docling_layout_tables": LOCAL_STAGE_MB["docling_layout_tables"],
              "ocr_rapidocr_onnx": LOCAL_STAGE_MB["ocr_rapidocr_onnx"]}
    if s.image_retrieval_mode != "descriptions_only" and s.image_embed_backend is Backend.LOCAL:
        stages["image_embed_siglip2_base_fp32"] = LOCAL_STAGE_MB["image_embed_siglip2_base_fp32"]
    if s.embed_backend is Backend.LOCAL:
        stages["text_embed_bge_m3_local"] = LOCAL_STAGE_MB["text_embed_bge_m3_local"]
    if s.rerank_backend is RerankBackend.LOCAL:
        stages["rerank_bge_v2_m3_local"] = LOCAL_STAGE_MB["rerank_bge_v2_m3_local"]
    return BASE_PROCESS_MB + max(stages.values()), stages


def check_memory(s: Settings) -> list[Finding]:
    vm = psutil.virtual_memory()
    free_mb = vm.available // (1024 * 1024)
    total_mb = vm.total // (1024 * 1024)
    peak, stages = estimate_peak_mb(s)
    out = [Finding("OK", f"RAM: {free_mb} MB available of {total_mb} MB total")]
    out.append(Finding("OK", "Local stages (est. MB, loaded one at a time): "
                       + ", ".join(f"{k}={v}" for k, v in stages.items())))
    budget = free_mb - s.doctor_ram_headroom_mb
    level = "OK" if peak <= budget else "WARN"
    tip = "" if level == "OK" else "  -> close apps / cap Docker memory / use hosted backends"
    out.append(
        Finding(level, f"Estimated pipeline peak {peak} MB vs available-minus-headroom {budget} MB{tip}")
    )
    return out


def main() -> int:
    try:
        s = get_settings()
    except Exception as exc:  # noqa: BLE001
        print(f"[FAIL] settings could not be loaded: {exc}")
        return 2
    findings = check_settings(s) + check_memory(s)
    for f in findings:
        print(f"[{f.level:4}] {f.message}")
    fails = sum(f.level == "FAIL" for f in findings)
    warns = sum(f.level == "WARN" for f in findings)
    print(f"\ndoctor: {fails} fail, {warns} warn")
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
