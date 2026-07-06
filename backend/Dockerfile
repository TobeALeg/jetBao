FROM python:3.12-slim

WORKDIR /app

COPY requirements.txt .
ARG PIP_INDEX_URL=
RUN if [ -n "$PIP_INDEX_URL" ]; then \
      pip install --no-cache-dir --index-url "$PIP_INDEX_URL" -r requirements.txt; \
    else \
      pip install --no-cache-dir -r requirements.txt; \
    fi

COPY app ./app

ENV DATA_DIR=/data
ENV UPLOAD_DIR=/data/uploads

EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
