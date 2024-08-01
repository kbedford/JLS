#!/bin/bash
set -e

# Create necessary directories
mkdir -p /var/log/supervisor
mkdir -p /var/log/logstash
mkdir -p /results

# Start supervisord
supervisord -c /etc/supervisor/supervisord.conf &

# Wait for other services to be ready
sleep 60

# Start syslog_hits.py
python3 /app/syslog_hits.py &

# Wait for syslog_hits to initialize
sleep 120

# Run the Robot Framework tests and serve the results
robot --outputdir /results /tests/databse_tests.robot || true
cd /results
python3 -m http.server 8000
