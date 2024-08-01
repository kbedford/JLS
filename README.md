# Junos FPC Errors

This repository contains a containerized program for scanning logs for Junos FPC errors.

The Junos Log Scanner is a comprehensive containerized solution designed to monitor, analyze, and report syslog messages from Juniper routers. It employs a combination of Python scripts, PostgreSQL databases, Logstash, and Grafana to capture, process, and visualize log data, facilitating the timely identification and resolution of network issues. The current focus of this solution is on FPC Errors as defined by the MX Escalation team.

![image](https://github.com/user-attachments/assets/d24024e4-e8fa-4cfd-986f-707642103726)

## Prerequisites

- Docker and docker-compose needs to be installed on your machine

## Project Structure

- `Dockerfile`: The Docker configuration file for building the container image.
- `entrypoint.sh`: The entrypoint script that initializes the necessary services inside the container.
- `logstash.conf`: Configuration file for Logstash.
- `requirements.txt`: Python dependencies for the project.
- `supervisord.conf`: Configuration file for Supervisord to manage processes.
- `syslog_hits.py`: The main Python script for scanning logs.
- `robot-tests/databse_tests.robot`: Robot Framework test file.

## How to Build and Run

1. **Clone the repository**:
    ```sh
    git clone https://github.com/kbedford/JLS.git
    cd junos-fpc-errors
    ```

2. **Build the Docker image**:
    ```sh
    docker build -t junos-fpc-errors .
    ```

3. **Run the Docker container**:
    ```sh
    docker run -d -p 514:514/udp -p 5514:5514/udp -p 8000:8000 junos-fpc-errors
    ```

## Usage

- The container exposes the following ports:
  - `514/udp`: For syslog
  - `5514/udp`: For another syslog input
  - `8000`: For any web service or API provided by your application

- Once the container is running, the program will start scanning the logs as defined in `syslog_hits.py`.

## Contributing

Please submit any issues or pull requests to the repository.
