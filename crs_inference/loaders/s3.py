import json
import re
from functools import lru_cache
from urllib.parse import urlparse

import boto3


@lru_cache(maxsize=1)
def _init_s3_resources() -> tuple:
    """Establish a boto3 session and return (session, s3_client, s3_resource)."""
    session = boto3.Session()
    return session, session.client("s3"), session.resource("s3")


def split_uri(uri: str) -> tuple[str, str]:
    """Split an s3:// URI into (bucket, key)."""
    parsed = urlparse(uri)
    return parsed.netloc, parsed.path.lstrip("/")


def get_s3_content(uri: str) -> str:
    """Download and decode a text file from S3."""
    bucket, key = split_uri(uri)
    _, client, _ = _init_s3_resources()
    result = client.get_object(Bucket=bucket, Key=key)
    return result["Body"].read().decode()


def get_json_s3(uri: str) -> dict:
    """Download and parse a JSON file from S3."""
    return json.loads(get_s3_content(uri))


def search_s3(uri: str, regex_str: str) -> list[str]:
    """Search S3 for object keys matching regex_str under the given prefix URI."""
    bucket, prefix = split_uri(uri)
    _, s3_client, _ = _init_s3_resources()
    pattern = re.compile(regex_str, re.IGNORECASE)

    results = []
    kwargs: dict = {"Bucket": bucket, "Prefix": prefix}
    while True:
        resp = s3_client.list_objects_v2(**kwargs)
        results += [obj["Key"] for obj in resp.get("Contents", []) if pattern.search(obj["Key"])]
        try:
            kwargs["ContinuationToken"] = resp["NextContinuationToken"]
        except KeyError:
            break
    return results
