import logging
import boto3
from botocore.exceptions import ClientError
from typing import Optional


# Enable debug logs
logging.getLogger("strands").setLevel(logging.DEBUG)
logging.basicConfig(
    format="%(levelname)s | %(name)s | %(message)s", handlers=[logging.StreamHandler()]
)

logger = logging.getLogger(__name__)

# S3 client will be initialized after role assumption
s3_client = None

# ============================================================================
# SSM PARAMETER STORE CONFIGURATION
# ============================================================================

SSM_PARAMETERS_MAP = {
    "S3_ACCESS_ROLE_ARN": "/scientific-agent/config/s3-access-role-arn",
}


def assume_s3_access_role(
    role_arn: str, session_name: str = "AnalyzerAgentS3Access"
) -> boto3.client:
    """
    Assume an IAM role and return an S3 client with the assumed credentials.

    Args:
        role_arn: ARN of the IAM role to assume
        session_name: Name for the assumed role session

    Returns:
        boto3 S3 client with assumed role credentials
    """
    logger.info(f"(IAM) Assuming role: {role_arn}")

    try:
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
        s3_client = boto3.client(
            "s3",
            aws_access_key_id=credentials["AccessKeyId"],
            aws_secret_access_key=credentials["SecretAccessKey"],
            aws_session_token=credentials["SessionToken"],
        )

        logger.info("(Success) S3 client created with assumed role credentials")
        return s3_client

    except ClientError as e:
        logger.error(f"(Error) Failed to assume role: {e}")
        raise
    except Exception as e:
        logger.error(f"(Error) Unexpected error during role assumption: {e}")
        raise


def initialize_s3_client(role_arn: Optional[str] = None) -> boto3.client:
    """
    Initialize S3 client, optionally with role assumption.

    Args:
        role_arn: Optional IAM role ARN to assume. If None, uses default credentials.

    Returns:
        boto3 S3 client
    """
    if role_arn:
        logger.info("(IAM) Initializing S3 client with role assumption")
        return assume_s3_access_role(role_arn)
    else:
        logger.info("(IAM) Initializing S3 client with default credentials")
        return boto3.client("s3")
