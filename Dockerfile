# Built with the monorepo root as context for compose uniformity
# (event-admin itself has no event-schemas dependency):
#   docker build -f event-admin/Dockerfile .
ARG BASE_IMAGE="python:3.14.0"

FROM ${BASE_IMAGE} AS base

ENV APP_PATH="/app/event-admin"
ENV PATH="${APP_PATH}/.venv/bin:${PATH}"

WORKDIR ${APP_PATH}

FROM base AS deps

RUN pip install --no-cache-dir --upgrade pip \
 && pip install --no-cache-dir --upgrade uv==0.11.3

COPY event-admin/pyproject.toml event-admin/uv.lock ${APP_PATH}/
RUN uv sync --frozen --no-install-project --no-dev

FROM deps AS development

COPY event-admin/event_admin ${APP_PATH}/event_admin
COPY event-admin/scripts ${APP_PATH}/scripts
COPY event-admin/uvicorn_config.json ${APP_PATH}/

EXPOSE 8888

ENTRYPOINT ["uvicorn", "event_admin.main:app", "--host", "0.0.0.0", "--port", "8888", "--log-config", "uvicorn_config.json"]
