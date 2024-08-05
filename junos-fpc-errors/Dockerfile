# Use an official Python runtime as a parent image
FROM python:3.8-slim

# Set the working directory in the container
WORKDIR /app

# Install necessary packages
COPY requirements.txt ./
RUN apt-get update && apt-get install -y \
    supervisor \
    wget \
    tar \
    default-jre-headless \
    netcat-openbsd \
    postgresql-client \
    gcc \
    python3-dev \
    libpq-dev && \
    pip install --no-cache-dir -r requirements.txt

# Install Logstash
RUN wget https://artifacts.elastic.co/downloads/logstash/logstash-7.12.1-linux-x86_64.tar.gz && \
    tar -xzf logstash-7.12.1-linux-x86_64.tar.gz && \
    mv logstash-7.12.1 /usr/share/logstash && \
    rm logstash-7.12.1-linux-x86_64.tar.gz

# Set the timezone to UTC
ENV TZ=UTC

# Create necessary directories
RUN mkdir -p /var/log/supervisor /var/log/logstash /tests /results

# Copy the current directory contents into the container at /app
COPY . /app/

# Copy test files into the container
COPY robot-tests/databse_tests.robot /tests/databse_tests.robot

# Copy supervisord config file
COPY supervisord.conf /etc/supervisor/conf.d/supervisord.conf

# Copy Logstash config file
COPY logstash.conf /usr/share/logstash/pipeline/logstash.conf

# Copy the entrypoint script
COPY entrypoint.sh /usr/local/bin/entrypoint.sh
RUN chmod +x /usr/local/bin/entrypoint.sh

# Expose the necessary ports
EXPOSE 514/udp
EXPOSE 5514/udp
EXPOSE 8000

# Command to run the entrypoint script
ENTRYPOINT ["/usr/local/bin/entrypoint.sh"]

