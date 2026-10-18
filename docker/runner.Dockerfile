FROM python:3.11-slim@sha256:e88e9763f943ec1834f992a4b51e0f24500486803e8bc534e5767af9ea65f6ce

RUN pip install --no-cache-dir pytest==9.1.1 \
    && useradd --create-home --uid 10001 runner

USER 10001:10001
WORKDIR /workspace
