import json
import os
import re
from functools import lru_cache
from pathlib import Path
from urllib.parse import urlparse

import boto3
import botocore
import geopandas as gpd
from obstore.store import S3Store


@lru_cache
def get_ras_crs() -> list:
    """Load the HEC-RAS db and convert all crs to pyproj crs."""
    proj_gpkg_path = Path(__file__).parent.joinpath("data/proj.gpkg")
    return gpd.read_file(proj_gpkg_path)


@lru_cache
def load_counties():
    """Load the county geopackage."""
    counties_gpkg_path = Path(__file__).parent.joinpath("data/counties.gpkg")
    return gpd.read_file(counties_gpkg_path, layer="counties")


def count_intersections(geom):
    """Count how many times a geometry intersects NHD."""
    filtered = gpd.read_file("NHD_H_National_GPKG.gpkg", layer="NHDFlowline", mask=geom)
    if len(filtered) == 0:
        return 0
    intersections = filtered.intersection(geom).explode()
    return len(intersections)


### S3 Utilities ###


def init_s3_resources() -> tuple:
    """Establish a boto3 (AWS) session and return the session, S3 client, and S3 resource handles."""
    # Instantitate S3 resources
    session = boto3.Session(
        aws_access_key_id=os.environ.get("aws_access_key_id"),
        aws_secret_access_key=os.environ.get("aws_secret_access_key"),
    )

    s3_client = session.client("s3")
    s3_resource = session.resource("s3")
    return session, s3_client, s3_resource


def get_s3_content(uri: str):
    bucket, prefix = split_uri(uri)
    _, client, _ = init_s3_resources()
    result = client.get_object(Bucket=bucket, Key=prefix)
    return result["Body"].read().decode()


def get_json_boto3(uri: str):
    text = get_s3_content(uri)
    json_content = json.loads(text)
    return json_content


def split_uri(uri: str) -> tuple:
    """Split a uri into bucket and prefix."""
    parsed = urlparse(uri)
    bucket = parsed.netloc
    prefix = parsed.path.lstrip("/")
    return bucket, prefix


def find_metadata(uri: str) -> list:
    """Search a prefix for metadata jsons."""
    # Parse uri
    bucket, prefix = split_uri(uri)

    # Get paginator
    _, s3_client, _ = init_s3_resources()
    paginator = s3_client.get_paginator("list_objects_v2")
    result = paginator.paginate(Bucket=bucket, Prefix=prefix, Delimiter="/")

    # Find subdirectories
    sub_prefixes = set()
    for page in result:
        for cp in page.get("CommonPrefixes", []):
            sub_prefixes.add(cp["Prefix"])

    # Search for meta in subdirectory
    results = []
    for i in list(sub_prefixes):
        try:
            prefix = i + "mip_package_geolocation_metadata.json"
            s3_client.head_object(Bucket=bucket, Key=prefix)
            results.append(f"s3://{bucket}/{prefix}")
        except botocore.exceptions.ClientError:
            pass
    return results


def search_s3_boto3(uri: str, regex_str: str) -> list:
    """Search S3 for files matching regex at a certain prefix."""
    _, s3_client, _ = init_s3_resources()

    # Parse uri
    bucket, prefix = split_uri(uri)

    # Compile a regex for ".g##" where # is 0-9
    pattern = re.compile(regex_str)

    # Search
    results = []
    kwargs = {"Bucket": bucket, "Prefix": prefix}
    while True:
        resp = s3_client.list_objects_v2(**kwargs)
        results += [obj["Key"] for obj in resp["Contents"] if pattern.search(obj["Key"])]
        try:
            kwargs["ContinuationToken"] = resp["NextContinuationToken"]
        except KeyError:
            break
    return results


def search_s3_obstore(uri: str, regex_str: str) -> list:
    """Search S3 for files matching regex at a certain prefix."""
    # Parse uri
    bucket, prefix = split_uri(uri)

    # Compile a regex for ".g##" where # is 0-9
    pattern = re.compile(regex_str)

    # Search
    store = S3Store(bucket)

    results = []
    for key in store.list(prefix=prefix):
        if pattern.search(key):
            results.append(key)

    return results
