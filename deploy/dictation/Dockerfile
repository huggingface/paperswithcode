# Voxtral Realtime server image for the voice-dictation HF Inference Endpoint.
# Stock vLLM images lack mistral-common's soundfile extra, which the realtime
# route needs. Built by the public, build-only Space nielsr/pwc-voxtral-vllm and
# pulled by the endpoint as registry.hf.space/nielsr-pwc-voxtral-vllm:latest.
# v0.32+/v0.33 images failed to start on the L4 endpoint (2026-11-10).
FROM vllm/vllm-openai:v0.26.0@sha256:770fe65b2c73ee74a5c42165cf3433de4048cc2cd9c57a937ca4e35aba5aa87b
RUN uv pip install --system --no-cache "mistral-common[soundfile]" soxr librosa \
    && python3 -c "import soundfile, soxr, librosa; print('audio deps ok')"
