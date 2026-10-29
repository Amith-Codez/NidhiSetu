"""Original-file storage. Files are kept byte-for-byte unchanged (they are evidence).

  production: any S3-compatible store (MinIO on NIC / MeghRaj cloud) when S3_ENDPOINT is set
  laptop demo: local folder data/uploads
Each object is named by its SHA-256, so the same file is never stored twice and any change is detectable.
"""
import hashlib
import os
import shutil
from pathlib import Path

from .config import UPLOADS

S3 = os.environ.get("S3_ENDPOINT")
BUCKET = os.environ.get("S3_BUCKET", "nidhisetu-evidence")
_client = None


def _s3():
    global _client
    if _client is None:
        import boto3
        _client = boto3.client("s3", endpoint_url=S3, aws_access_key_id=os.environ.get("S3_KEY"),
                               aws_secret_access_key=os.environ.get("S3_SECRET"))
        try:
            _client.head_bucket(Bucket=BUCKET)
        except Exception:
            _client.create_bucket(Bucket=BUCKET)
    return _client


def put(src_path: str, ext: str):
    """Store a file; return (local working path, sha256). Engines always read a local working copy."""
    data = Path(src_path).read_bytes()
    sha = hashlib.sha256(data).hexdigest()
    local = UPLOADS / f"{sha}{ext}"
    if not local.exists():
        shutil.copyfile(src_path, local)
    if S3:
        _s3().put_object(Bucket=BUCKET, Key=f"{sha}{ext}", Body=data,
                         ServerSideEncryption="AES256")
    return str(local), sha


def backend_name():
    return f"S3-compatible ({S3})" if S3 else "Local folder (demo mode)"
