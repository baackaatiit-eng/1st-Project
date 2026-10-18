FROM python:3.11-slim
RUN apt-get update && apt-get install -y --no-install-recommends docker.io && rm -rf /var/lib/apt/lists/*
WORKDIR /srv
COPY ghostide ghostide
ENV GHOSTIDE_DATA_DIR=/data
VOLUME /data
CMD ["python", "-m", "ghostide"]
