FROM python:3.11-slim

WORKDIR /app

# The release workflow supplies this value from its Git tag. Keeping a default
# also makes local Docker builds possible outside a Git checkout.
ARG SETUPTOOLS_SCM_PRETEND_VERSION=0.0.0
ENV SETUPTOOLS_SCM_PRETEND_VERSION_FOR_BLOCKY_BLOCKING_EDITOR=${SETUPTOOLS_SCM_PRETEND_VERSION}

COPY pyproject.toml README.md LICENSE app.py ./
RUN pip install --no-cache-dir .

EXPOSE 8080

# Force Streamlit to run in the port 8080 and disable telemetry
ENTRYPOINT ["streamlit", "run", "app.py", "--server.port=8080", "--server.address=0.0.0.0", "--browser.gatherUsageStats=false"]
