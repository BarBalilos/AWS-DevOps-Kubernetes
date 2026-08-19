"""
Minimal smoke test for the worker service.
Only exercises the AWS-free health endpoint so it can run in CI without
live S3/SNS credentials — see the Jenkins repo's README for this trade-off.
"""
import os

# boto3 clients / AWS_REGION+S3_BUCKET are read at import time — set
# harmless placeholders so importing the module doesn't blow up in a
# CI container with no AWS credentials configured.
os.environ.setdefault("AWS_REGION", "us-east-1")
os.environ.setdefault("S3_BUCKET", "test-bucket-placeholder")

import worker as worker_module


def test_health_endpoint_returns_ok():
    client = worker_module.app.test_client()
    response = client.get("/health")
    assert response.status_code == 200