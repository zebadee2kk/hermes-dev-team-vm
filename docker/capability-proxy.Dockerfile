ARG BASE_IMAGE
FROM ${BASE_IMAGE}

COPY integrations/sandbox/capability_proxy.py /opt/forge/capability_proxy.py

USER 65532:65532
EXPOSE 3128
ENTRYPOINT ["python3", "/opt/forge/capability_proxy.py"]
