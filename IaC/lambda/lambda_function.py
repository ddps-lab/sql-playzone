from typing import List
import boto3
import json
from datetime import datetime, timedelta, timezone
import pandas as pd
import os

session = boto3.Session()
MAX_API_LOG_LIMIT = 10000
REGION_NAME = os.environ.get('REGION', None)
if REGION_NAME is None:
    raise ValueError("REGION environment variable must be set")

def get_logs_from_cloudwatch(start_time: datetime, end_time: datetime, log_group_name: str, log_stream_name: str):
    global session, REGION_NAME, MAX_API_LOG_LIMIT
    # Initialize a session using Amazon CloudWatch Logs
    cloud_watch = session.client('logs', region_name=REGION_NAME)

    limit_events = MAX_API_LOG_LIMIT

    params = {
        'logGroupName': log_group_name,
        'logStreamName': log_stream_name,
        'startTime': int(start_time.timestamp() * 1000),
        'endTime': int(end_time.timestamp() * 1000),
        'limit': limit_events,
    }

    logs = []

    response = cloud_watch.get_log_events(**params)

    next_backward_token = response['nextBackwardToken']
    for event in response['events']:
        log = event['message']
        logs.append(log)

    while True:
        params['nextToken'] = next_backward_token
        response = cloud_watch.get_log_events(**params)

        if next_backward_token == response['nextBackwardToken']:
            break

        next_backward_token = response['nextBackwardToken']
        for event in response['events']:
            log = event['message']
            logs.append(log)
    
    return logs


def lambda_handler(event, context):
    global session, REGION_NAME
    log_group_name = os.environ.get('LOG_GROUP_NAME', None)
    log_stream_name = os.environ.get('LOG_STREAM_NAME', None)

    if log_group_name is None or log_stream_name is None:
        raise ValueError("LOG_GROUP_NAME and LOG_STREAM_NAME environment variables must be set")

    # 어제 00시부터 23:59:59 까지
    start_time = datetime.now(timezone.utc) - timedelta(days=1)
    start_time = start_time.replace(hour=0, minute=0, second=0, microsecond=0)
    end_time = start_time.replace(hour=23, minute=59, second=59, microsecond=999999)

    logs = get_logs_from_cloudwatch(start_time, end_time, log_group_name, log_stream_name)
    df = pd.DataFrame(map(json.loads, logs))
    
    # csv.gz 파일로 변경. filename 은 start_time 을 day 까지만
    # 경로는 /tmp
    base_dir = "/tmp/" # lambda 의 경우
    filename = start_time.strftime("%Y-%m-%d") + ".csv.gz"
    df.to_csv(base_dir + filename, index=False, compression='gzip')

    # s3 에 업로드
    s3 = session.client('s3', region_name=REGION_NAME)
    bucket_name = os.environ.get('BUCKET_NAME', None)
    if bucket_name is None:
        raise ValueError("BUCKET_NAME environment variable must be set")
    object_name = "raw/behavior/" + start_time.strftime("%Y/%m/%d") + ".csv.gz"
    s3.upload_file(base_dir + filename, bucket_name, object_name)

    return {
        'statusCode': 200,
        'body': json.dumps(f'{len(logs)} Logs processed and uploaded to S3 successfully!')
    }