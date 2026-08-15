ARG BASE_IMAGE
FROM ${BASE_IMAGE}

ARG CODEX_VERSION
RUN test -n "${CODEX_VERSION}" \
    && apt-get update \
    && apt-get install -y --no-install-recommends bash ca-certificates curl git jq python3 \
    && npm install -g "@openai/codex@${CODEX_VERSION}" \
    && codex --version \
    && npm cache clean --force \
    && rm -rf /var/lib/apt/lists/*

COPY integrations/sandbox/hand_security_probe.py /opt/forge/hand_security_probe.py
COPY integrations/hermes/codex-device-login.py /opt/forge/codex-device-login.py
RUN chmod 0555 /opt/forge/hand_security_probe.py /opt/forge/codex-device-login.py \
    && mkdir -p /workspace \
    && chown 65532:65532 /workspace

WORKDIR /workspace
USER 65532:65532
ENTRYPOINT []
CMD ["codex", "app-server", "--stdio"]
