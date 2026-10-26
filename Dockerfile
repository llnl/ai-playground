FROM python:3.12-bookworm

WORKDIR /app

COPY pyproject.toml README.md LICENSE /app/
COPY src /app/src
COPY entrypoint.sh gunicorn.conf.py /app/

RUN pip install --no-cache-dir uv==0.11.27 && uv sync \
    && chmod -R g+wrx /app \
    && mkdir /.cache \
    && chmod -R g+wrx /.cache

EXPOSE 8000

ENTRYPOINT ["/bin/sh", "/app/entrypoint.sh"]

CMD ["uv", "run", "--no-sync", "gunicorn", "--config", "/app/gunicorn.conf.py"]
