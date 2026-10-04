import boto3
from botocore.config import Config
from browsergrid.config import settings


def client(public=False):
    s = settings()
    return boto3.client(
        "s3",
        endpoint_url=s.s3_public_endpoint if public else s.s3_endpoint,
        aws_access_key_id=s.s3_access_key,
        aws_secret_access_key=s.s3_secret_key,
        region_name="us-east-1",
        config=Config(
            connect_timeout=5,
            read_timeout=10,
            retries={"max_attempts": 2},
            signature_version="s3v4",
            s3={"addressing_style": "path"},
        ),
    )


def put(key, data, mime):
    client().put_object(Bucket=settings().s3_bucket, Key=key, Body=data, ContentType=mime)


def get(key):
    response = client().get_object(Bucket=settings().s3_bucket, Key=key)
    body = response["Body"]
    try:
        data = body.read(settings().max_bundle_bytes + 1)
        if len(data) > settings().max_bundle_bytes:
            raise ValueError("Stored bundle exceeds limit")
        return data
    finally:
        body.close()


def delete(key):
    client().delete_object(Bucket=settings().s3_bucket, Key=key)


def signed(key, name):
    return client(public=True).generate_presigned_url(
        "get_object",
        Params={
            "Bucket": settings().s3_bucket,
            "Key": key,
            "ResponseContentDisposition": 'attachment; filename="'
            + name.replace('"', "").replace("\r", "").replace("\n", "")[-100:]
            + '"',
        },
        ExpiresIn=120,
    )
