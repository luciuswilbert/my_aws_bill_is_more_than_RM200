import boto3
 
AWS_REGION = "us-east-1"
 
def get_bedrock_client():
    """
    Returns a boto3 client for Amazon Bedrock Runtime.
    Make sure your AWS credentials are configured (via environment, CLI, or IAM role).
    """
    return boto3.client(
        service_name="bedrock-runtime",
        region_name=AWS_REGION
    )