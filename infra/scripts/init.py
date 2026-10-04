import os
import time
from pathlib import Path
from cryptography.fernet import Fernet
from browsergrid import storage
from browsergrid.config import settings
from alembic import command
from alembic.config import Config

key = Path(settings().key_file)
key.parent.mkdir(parents=True, exist_ok=True)
if not key.exists():
    fd = os.open(key, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, "wb") as out:
        out.write(Fernet.generate_key())
os.chown(key, 10001, 10001)
command.upgrade(Config("alembic.ini"), "head")
for attempt in range(30):
    try:
        client = storage.client()
        try:
            client.head_bucket(Bucket=settings().s3_bucket)
        except client.exceptions.ClientError as e:
            if e.response["ResponseMetadata"]["HTTPStatusCode"] != 404:
                raise
            client.create_bucket(Bucket=settings().s3_bucket)
        break
    except Exception:
        if attempt == 29:
            raise
        time.sleep(1)
