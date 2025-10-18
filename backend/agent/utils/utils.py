import base64
import hashlib
import hmac
import json
import os
from typing import Optional, List, Dict, Any


import logging
import requests

import boto3
import yaml
from boto3.session import Session
from botocore.exceptions import ClientError


logger = logging.getLogger(__name__)


def get_ssm_parameter(name: str, with_decryption: bool = True) -> str:
    ssm = boto3.client("ssm")

    response = ssm.get_parameter(Name=name, WithDecryption=with_decryption)

    return response["Parameter"]["Value"]


def put_ssm_parameter(
    name: str, value: str, parameter_type: str = "String", with_encryption: bool = False
) -> None:
    ssm = boto3.client("ssm")

    put_params = {
        "Name": name,
        "Value": value,
        "Type": parameter_type,
        "Overwrite": True,
    }

    if with_encryption:
        put_params["Type"] = "SecureString"

    ssm.put_parameter(**put_params)


def get_api_key(secret_name: str, region_name: str = "us-east-1") -> Optional[str]:
    """
    Retrieves a secret from AWS Secrets Manager.

    Args:
        secret_name: The name of the secret to retrieve
        region_name: The AWS region where the secret is stored

    Returns:
        The secret string if successful, otherwise None
    """
    sts_client = boto3.client("sts")

    # Assume the role
    sts_response = sts_client.assume_role(
        RoleArn="arn:aws:iam::047719637619:role/service-role/acquire_paper-role-2d4cvn4a",
        RoleSessionName="SearcherAgentSecretAccess",
        DurationSeconds=3600,  # 1 hour session
    )

    cred = sts_response["Credentials"]
    session = boto3.client(
        aws_access_key_id=cred["AccessKeyId"],
        aws_secret_access_key=cred["SecretAccessKey"],
        aws_session_token=cred["SessionToken"],
    )
    client = session.client(service_name="secretsmanager", region_name=region_name)

    try:
        response = client.get_secret_value(SecretId=secret_name)
        if "SecretString" in response:
            return response["SecretString"]
    except ClientError as e:
        logger.error(f"Error retrieving secret '{secret_name}': {e}")

    return None


def process_id(paper_id: str) -> str:
    """
    Convert paper IDs to arXiv IDs for S3 path generation.

    Examples:
        - "arxiv:1910.04751v3" -> "1910.04751v3"
        - "s2:4a12695287ab959..." -> Look up arXiv ID via Semantic Scholar API

    Args:
        paper_id: Paper identifier from search results

    Returns:
        arXiv ID string, or empty string if not found
    """
    parts = paper_id.split(":", 1)

    if len(parts) != 2:
        logger.warning(f"Invalid paper ID format: {paper_id}")
        return ""

    source, identifier = parts

    if source == "arxiv":
        return identifier

    elif source == "s2":
        # Query Semantic Scholar API to get arXiv ID
        url = f"https://api.semanticscholar.org/graph/v1/paper/{identifier}?fields=externalIds"
        headers = {}

        # Add API key if available
        api_key = get_api_key("SEMANTIC_SCHOLAR_API_KEY")
        if api_key:
            headers["x-api-key"] = api_key

        try:
            response = requests.get(url, headers=headers, timeout=60)
            response.raise_for_status()
            data = response.json()

            external_ids = data.get("externalIds", {})
            if "ArXiv" in external_ids:
                arxiv_id = external_ids["ArXiv"]
                logger.info(f"✅ Found arXiv ID for S2 paper: {arxiv_id}")
                return arxiv_id
            else:
                logger.warning(f"⚠️  No arXiv ID found for S2 paper: {identifier}")

        except Exception as e:
            logger.error(f"❌ Error fetching arXiv ID for {identifier}: {e}")

    else:
        logger.warning(f"Unknown paper source: {source}")

    return ""


def enrich_papers_with_s3_paths(papers: List[Dict]) -> List[Dict]:
    """
    Add S3 paths to papers based on their arXiv IDs.

    Args:
        papers: List of paper dictionaries from search results

    Returns:
        Enriched papers with S3 paths added
    """
    enriched_papers = []

    for paper in papers:
        paper_copy = paper.copy()
        paper_id = paper.get("id", "")

        if paper_id:
            arxiv_id = process_id(paper_id)

            if arxiv_id:
                paper_copy["arxiv_id"] = arxiv_id
                paper_copy["s3_text_path"] = (
                    f"s3://ai-agent-hackathon-processed-pdf-files/{arxiv_id}/full_text.txt"
                )
                paper_copy["s3_chunks_path"] = (
                    f"s3://ai-agent-hackathon-processed-pdf-files/{arxiv_id}/chunks.json"
                )
                logger.debug(f"📦 Enriched: {paper_copy['s3_text_path']}")
            else:
                paper_copy["arxiv_id"] = None
                paper_copy["s3_text_path"] = None
                paper_copy["s3_chunks_path"] = None
                logger.warning(
                    f"⚠️  No arXiv ID for: {paper.get('title', 'Unknown')[:50]}"
                )
        else:
            paper_copy["arxiv_id"] = None
            paper_copy["s3_text_path"] = None
            paper_copy["s3_chunks_path"] = None

        enriched_papers.append(paper_copy)

    return enriched_papers


def assume_role(
    role_arn: str, session_name: str = "AnalyzerAgentS3Access", client: str = ""
) -> boto3.client:
    """
    Assume an IAM role and return an  client with the assumed credentials.

    Args:
        role_arn: ARN of the IAM role to assume
        session_name: Name for the assumed role session

    Returns:
        boto3 S3 client with assumed role credentials
    """
    logger.info(f"(IAM) Assuming role: {role_arn}")

    try:
        if not client:
            return None
        sts_client = boto3.client("sts")

        # Assume the role
        response = sts_client.assume_role(
            RoleArn=role_arn,
            RoleSessionName=session_name,
            DurationSeconds=3600,  # 1 hour session
        )

        # Extract temporary credentials
        credentials = response["Credentials"]
        logger.info(f"(Success) Role assumed successfully. Session: {session_name}")

        # Create S3 client with assumed role credentials
        service_client = boto3.client(
            client,
            aws_access_key_id=credentials["AccessKeyId"],
            aws_secret_access_key=credentials["SecretAccessKey"],
            aws_session_token=credentials["SessionToken"],
        )

        logger.info("(Success) S3 client created with assumed role credentials")
        return service_client

    except ClientError as e:
        logger.error(f"(Error) Failed to assume role: {e}")
        raise
    except Exception as e:
        logger.error(f"(Error) Unexpected error during role assumption: {e}")
        raise
