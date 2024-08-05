import os
import re
import psycopg2
import time
import json
from datetime import datetime, timedelta, timezone
import pandas as pd
import logging

# Logging configuration
logging.basicConfig(level=logging.DEBUG, format='%(asctime)s %(levelname)s: %(message)s', handlers=[
    logging.FileHandler("/var/log/syslog-hits.err.log"),
    logging.StreamHandler()
])

# Database configuration
DB_NAME = 'postgres'
DB_USER = 'postgres'
DB_PASSWORD = 'newpassword'
DB_HOST = 'postgres'

# CSV file path from environment variable or default
CSV_FILE_PATH = os.getenv('CSV_FILE_PATH', '/var/tmp/test1.csv')
LOG_FILE_PATH = os.getenv('LOG_FILE_PATH', '/var/log/logstash/syslog.log')

# Scan interval and time threshold
SCAN_INTERVAL = 180 * 60  # 3 hours in seconds
TIME_THRESHOLD_HOURS = 3  # Scan logs from the last 3 hours

# Connect to the PostgreSQL database
def connect_to_db():
    try:
        conn = psycopg2.connect(dbname=DB_NAME, user=DB_USER, password=DB_PASSWORD, host=DB_HOST)
        cur = conn.cursor()
        logging.info("Successfully connected to the database")
        return conn, cur
    except Exception as e:
        logging.error(f"Error connecting to the database: {e}")
        exit(1)

conn, cur = connect_to_db()

def ensure_database_tables_exist(cur, conn):
    try:
        cur.execute("""
            CREATE TABLE IF NOT EXISTS error_patterns (
                pattern VARCHAR(255),
                kb_article VARCHAR(255),
                pr_number VARCHAR(255),
                action VARCHAR(255)
            );
        """)
        cur.execute("""
            CREATE TABLE IF NOT EXISTS syslog_hits (
                id SERIAL PRIMARY KEY,
                log TEXT,
                kb_article VARCHAR(255),
                pr_number VARCHAR(255),
                action VARCHAR(255),
                timestamp TIMESTAMPTZ,
                created_at TIMESTAMPTZ DEFAULT NOW()
            );
        """)
        conn.commit()
    except Exception as e:
        logging.error(f"Error ensuring database tables exist: {e}")
        exit(1)

def load_error_patterns(cur):
    try:
        cur.execute('SELECT pattern, kb_article, pr_number, action FROM error_patterns;')
        patterns = [{'pattern': row[0], 'kb_article': row[1], 'pr_number': row[2], 'action': row[3]} for row in cur.fetchall()]
        logging.debug(f"Loaded patterns: {patterns}")
        return patterns
    except Exception as e:
        logging.error(f"Error loading error patterns: {e}")
        return []

def save_error_patterns(cur, conn, patterns):
    try:
        cur.execute('DELETE FROM error_patterns;')
        for p in patterns:
            cur.execute('INSERT INTO error_patterns (pattern, kb_article, pr_number, action) VALUES (%s, %s, %s, %s);',
                        (p['pattern'], p['kb_article'], p['pr_number'], p['action']))
        conn.commit()
    except Exception as e:
        logging.error(f"Error saving error patterns: {e}")
        conn.rollback()

def upload_patterns_from_csv(cur, conn, csv_file_path):
    if not os.path.exists(csv_file_path):
        logging.error(f"CSV file does not exist at the path: {csv_file_path}")
        return

    try:
        df = pd.read_csv(csv_file_path)
        patterns = df.to_dict(orient='records')
        save_error_patterns(cur, conn, patterns)
        logging.info(f"Uploaded patterns from {csv_file_path}")
    except Exception as e:
        logging.error(f"Failed to upload patterns from CSV file: {str(e)}")

def scan_logs_and_report(cur, conn, patterns):
    compiled_patterns = [{'compiled': re.compile(p['pattern']), 'info': p} for p in patterns]

    try:
        with open(LOG_FILE_PATH, 'r') as log_file:
            log_lines = log_file.readlines()
    except Exception as e:
        logging.error(f"Failed to read log file {LOG_FILE_PATH}: {e}")
        return

    now = datetime.now(timezone.utc)
    time_threshold = now - timedelta(hours=TIME_THRESHOLD_HOURS)

    logging.debug(f"Time threshold: {time_threshold.isoformat()}")
    
    for line in log_lines:
        try:
            logging.debug(f"Processing log line: {line.strip()}")
            try:
                log_entry = json.loads(line)
            except json.JSONDecodeError as e:
                logging.error(f"Failed to decode JSON log entry: {line.strip()} - Error: {e}")
                continue

            log_message = log_entry.get("message", "")
            log_timestamp_str = log_entry.get("@timestamp", "")
            try:
                log_timestamp = datetime.fromisoformat(log_timestamp_str.replace('Z', '+00:00'))
            except ValueError as e:
                logging.error(f"Failed to parse timestamp: {log_timestamp_str} - Error: {e}")
                continue

            if log_timestamp >= time_threshold:
                for pattern in compiled_patterns:
                    if pattern['compiled'].search(log_message):
                        message = {
                            'log': log_message,
                            'kb_article': pattern['info']['kb_article'],
                            'pr_number': pattern['info']['pr_number'],
                            'action': pattern['info']['action'],
                            'timestamp': log_timestamp.isoformat()
                        }
                        logging.info(f"Matched pattern: {message}")
                        try:
                            # Reconnect to the database if necessary
                            if conn.closed:
                                logging.warning("Database connection closed, reconnecting...")
                                conn, cur = connect_to_db()

                            cur.execute("""
                                INSERT INTO syslog_hits (log, kb_article, pr_number, action, timestamp, created_at)
                                VALUES (%s, %s, %s, %s, %s, NOW())
                            """, (log_message, pattern['info']['kb_article'], pattern['info']['pr_number'], pattern['info']['action'], log_timestamp))
                            conn.commit()
                            logging.info(f"Alert inserted into database: {message}")
                        except Exception as e:
                            logging.error(f"Failed to insert message into database: {e}")
                            conn.rollback()
        except Exception as e:
            logging.error(f"Error processing log line: {e}")

def main():
    ensure_database_tables_exist(cur, conn)
    if CSV_FILE_PATH:
        upload_patterns_from_csv(cur, conn, CSV_FILE_PATH)

    patterns = load_error_patterns(cur)
    logging.info("Scanning logs with updated patterns...")
    while True:
        scan_logs_and_report(cur, conn, patterns)
        now = datetime.now(timezone.utc)
        logging.info(f"Scan complete at {now}. Waiting for next scan in 180 minutes...")
        time.sleep(SCAN_INTERVAL)

if __name__ == '__main__':
    main()
