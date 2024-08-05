*** Settings ***
Library           DatabaseLibrary
Library           OperatingSystem
Library           Process
Library           Collections

*** Variables ***
${DB_NAME}        postgres
${DB_USER}        postgres
${DB_PASSWORD}    newpassword
${DB_HOST}        postgres
${DB_PORT}        5432
${LOG_FILE}       /var/log/logstash/syslog.log
${CSV_FILE_PATH}  /var/tmp/test1.csv

*** Test Cases ***
Connect To Database
    [Documentation]    Test database connectivity
    Connect To Database    psycopg2    ${DB_NAME}    ${DB_USER}    ${DB_PASSWORD}    ${DB_HOST}    ${DB_PORT}
    @{result}    Query    SELECT 1
    Should Be Equal As Numbers    ${result[0][0]}    1
    Disconnect From Database

Ensure Tables Exist
    [Documentation]    Ensure necessary tables are created in the database
    Connect To Database    psycopg2    ${DB_NAME}    ${DB_USER}    ${DB_PASSWORD}    ${DB_HOST}    ${DB_PORT}
    @{result}    Query    SELECT table_name FROM information_schema.tables WHERE table_name IN ('error_patterns', 'syslog_hits')
    Should Be Equal As Strings    ${result[0][0]}    error_patterns
    Should Be Equal As Strings    ${result[1][0]}    syslog_hits
    Disconnect From Database

Verify Matched Patterns Written to Database
    [Documentation]    Verify that matched patterns are written to the database
    Connect To Database    psycopg2    ${DB_NAME}    ${DB_USER}    ${DB_PASSWORD}    ${DB_HOST}    ${DB_PORT}
    @{result}    Query    SELECT * FROM syslog_hits ORDER BY timestamp DESC LIMIT 10
    Should Not Be Empty    ${result}
    Disconnect From Database
