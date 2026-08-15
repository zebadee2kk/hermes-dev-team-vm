ARG BASE_IMAGE
FROM ${BASE_IMAGE}

ENV DEBIAN_FRONTEND=noninteractive

RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        bash \
        ca-certificates \
        curl \
        git \
        jq \
        python3 \
    && rm -rf /var/lib/apt/lists/*

COPY integrations/sandbox/hand_security_probe.py /opt/forge/hand_security_probe.py
RUN chmod 0555 /opt/forge/hand_security_probe.py

WORKDIR /workspace
USER 65532:65532
ENTRYPOINT []
CMD ["bash"]
