FROM python:3.11-slim@sha256:e88e9763f943ec1834f992a4b51e0f24500486803e8bc534e5767af9ea65f6ce

RUN pip install --no-cache-dir \
        pytest==7.1.2 \
        attrs==22.1.0 \
        iniconfig==1.1.1 \
        packaging==26.3 \
        pluggy==1.0.0 \
        py==1.11.0 \
        pyparsing==3.0.9 \
        tomli==2.0.1 \
        certifi==2023.7.22 \
        charset-normalizer==3.2.0 \
        idna==3.4 \
        urllib3==2.0.7 \
    && useradd --create-home --uid 10001 runner

USER 10001:10001
WORKDIR /workspace
