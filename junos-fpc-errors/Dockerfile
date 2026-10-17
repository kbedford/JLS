FROM python:3.12.10-slim-bookworm
ENV PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt && useradd --uid 10001 --create-home jls
COPY jls ./jls
USER 10001:10001
EXPOSE 8080
CMD ["python", "-m", "jls", "serve"]
