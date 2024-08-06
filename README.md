# Log Scanner 

This repository contains a containerized program for scanning logs for Junos FPC errors.

The Junos Log Scanner is a comprehensive containerized solution designed to monitor, analyze, and report syslog messages from Juniper routers. It employs a combination of Python scripts, PostgreSQL databases, Logstash, and Grafana to capture, process, and visualize log data, facilitating the timely identification and resolution of network issues. The current focus of this solution is on FPC Errors as defined by the MX Escalation team.



# Components

1.	Logstash: Logstash receives syslog messages from Juniper routers and converts them into a structured JSON format. This allows for easy parsing and pattern matching by the Python   script.

2.	PostgreSQL Database: The database serves two primary tables:
•	Error patterns: Stores predefined error patterns to be matched against incoming syslog messages.
•	Syslog hits: Stores log entries that match the predefined error patterns, including additional metadata for further analysis.

3.	Junos Log Scanner ( Python Script - syslog_hits.py): This script continuously scans the log files within logstash, matches log entries against predefined patterns, and inserts matching entries into the syslog_hits table in the PostgreSQL database.

4.	Grafana: Grafana is used to visualize the data stored in the PostgreSQL database. It provides an intuitive interface to view recent syslog hits and error patterns, as shown in the attached image.

5.	Robot Framework Tests: These tests ensure the system's proper functioning by verifying database connectivity, table existence, and the presence of matched patterns in the database.



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
    cd JLS
    ```

2. **Build the Docker Containers**:
    ```sh
    sudo docker-compose build .
    ```

3. **Run the Docker container**:
    ```sh
    sudo docker-compose up
    ```

## Usage

- The container exposes the following ports:
  - `514/udp`: For syslog
  - `5514/udp`: For another syslog input
  - `8000`: For any web service or API provided by your application

- Once the container is running, the program will start scanning the logs as defined in `syslog_hits.py`.

## Contributing

Please submit any issues or pull requests to the repository.

=======
