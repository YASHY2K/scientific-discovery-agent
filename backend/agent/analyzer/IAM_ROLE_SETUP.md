# Analyzer Agent - IAM Role Setup Guide

## Overview

The Analyzer Agent uses IAM role assumption to securely access S3 buckets containing processed scientific papers. This provides better security through temporary credentials and fine-grained access control.

## Architecture

```
AgentCore Runtime (Analyzer Agent)
    ↓ (assumes role)
IAM Role: AnalyzerS3AccessRole
    ↓ (grants permissions)
S3 Bucket: scientific-papers-bucket
```

## Setup Instructions

### Step 1: Create the Execution Role for AgentCore

Create an IAM role that AgentCore Runtime will assume to access AWS services.[1][2]

**Role Name:** `AnalyzerS3AccessRole` (or your preferred name)

**Trust Policy:** (allows AgentCore services to assume the role)

```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Principal": {
        "Service": "bedrock-agentcore.amazonaws.com"
      },
      "Action": "sts:AssumeRole",
      "Condition": {
        "StringEquals": {
          "aws:SourceAccount": "YOUR_ACCOUNT_ID"
        },
        "ArnLike": {
          "aws:SourceArn": "arn:aws:bedrock-agentcore:us-east-1:YOUR_ACCOUNT_ID:agent/*"
        }
      }
    }
  ]
}
```

Replace `YOUR_ACCOUNT_ID` with your AWS account ID and `us-east-1` with your region.[3][1]

**Permissions Policy:** (grants S3 read access)

```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Action": ["s3:GetObject", "s3:ListBucket"],
      "Resource": [
        "arn:aws:s3:::scientific-papers-bucket/*",
        "arn:aws:s3:::scientific-papers-bucket"
      ]
    },
    {
      "Effect": "Allow",
      "Action": [
        "logs:CreateLogGroup",
        "logs:CreateLogStream",
        "logs:PutLogEvents"
      ],
      "Resource": "arn:aws:logs:*:*:*"
    }
  ]
}
```

### Step 2: Additional Permissions for AgentCore Features

If your agent uses additional AWS services, add these permissions:[1]

**For Bedrock Model Access:**

```json
{
  "Effect": "Allow",
  "Action": ["bedrock:InvokeModel", "bedrock:InvokeModelWithResponseStream"],
  "Resource": "arn:aws:bedrock:us-east-1::foundation-model/*"
}
```

**For Bedrock Memory:**

```json
{
  "Effect": "Allow",
  "Action": [
    "bedrock:CreateMemory",
    "bedrock:GetMemory",
    "bedrock:UpdateMemory"
  ],
  "Resource": "arn:aws:bedrock:us-east-1:YOUR_ACCOUNT_ID:memory/*"
}
```

### Step 3: Grant Your IAM User/Role Permission to Use AgentCore

Your development IAM user or CI/CD role needs permission to create and manage AgentCore agents:[1]

```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Action": [
        "bedrock-agentcore:CreateAgent",
        "bedrock-agentcore:CreateAgentRuntimeEndpoint",
        "bedrock-agentcore:InvokeAgent",
        "bedrock-agentcore:GetAgent",
        "bedrock-agentcore:DeleteAgent",
        "bedrock-agentcore:ListAgents"
      ],
      "Resource": "*"
    },
    {
      "Effect": "Allow",
      "Action": "iam:PassRole",
      "Resource": "arn:aws:iam::YOUR_ACCOUNT_ID:role/AnalyzerS3AccessRole",
      "Condition": {
        "StringEquals": {
          "iam:PassedToService": "bedrock-agentcore.amazonaws.com"
        }
      }
    }
  ]
}
```

### Step 4: Store Role ARN in SSM Parameter Store

```bash
# Using AWS CLI
aws ssm put-parameter \
  --name "/scientific-agent/config/s3-access-role-arn" \
  --value "arn:aws:iam::YOUR_ACCOUNT_ID:role/AnalyzerS3AccessRole" \
  --type "String" \
  --description "IAM role ARN for Analyzer Agent S3 access"

# Verify the parameter
aws ssm get-parameter \
  --name "/scientific-agent/config/s3-access-role-arn"
```

### Step 5: Deploy Your Agent to AgentCore

When deploying your agent, reference the execution role ARN:[1]

```bash
# Using AgentCore CLI
agentcore deploy \
  --agent-name analyzer-agent \
  --execution-role-arn arn:aws:iam::YOUR_ACCOUNT_ID:role/AnalyzerS3AccessRole \
  --region us-east-1
```

Or programmatically:

```python
import boto3

client = boto3.client('bedrock-agentcore')

response = client.create_agent(
    agentName='analyzer-agent',
    executionRoleArn='arn:aws:iam::YOUR_ACCOUNT_ID:role/AnalyzerS3AccessRole',
    agentResourceRoleArn='arn:aws:iam::YOUR_ACCOUNT_ID:role/AnalyzerS3AccessRole'
)
```

### Step 6: Test the Configuration

```python
# Test role assumption
from backend.agent.analyzer_agent import execute_analysis

# Test with a sample S3 URI
test_uri = "s3://scientific-papers-bucket/papers/test-paper/full_text.txt"
result = execute_analysis(test_uri, verbose=True)
print(result)
```

## Key Differences for AgentCore

### Service Principal

AgentCore uses the **`bedrock-agentcore.amazonaws.com`** service principal, which is distinct from other AWS services.[2][1]

### Condition Keys

Always include **condition keys** in your trust policy to scope the role to specific agents and your account:[3][1]

- `aws:SourceAccount` - Restricts to your AWS account
- `aws:SourceArn` - Restricts to specific AgentCore agents

### PassRole Permission

To deploy agents, your IAM user needs **`iam:PassRole`** permission for the execution role.[1]

## Usage

### Programmatic Usage

```python
from backend.agent.analyzer_agent import execute_analysis

# Analyze a single paper
result = execute_analysis(
    "s3://scientific-papers-bucket/papers/paper1/full_text.txt",
    context="Focus on methodology and results"
)

# Analyze multiple papers
result = execute_analysis(
    [
        "s3://scientific-papers-bucket/papers/paper1/full_text.txt",
        "s3://scientific-papers-bucket/papers/paper2/full_text.txt"
    ],
    context="Compare approaches across papers"
)
```

### Command Line Usage

```bash
# Test mode
python backend/agent/analyzer_agent.py test

# Analyze specific papers
python backend/agent/analyzer_agent.py \
  s3://scientific-papers-bucket/papers/paper1/full_text.txt \
  s3://scientific-papers-bucket/papers/paper2/full_text.txt
```

## Troubleshooting

### Error: "Access denied to s3://..."

**Cause:** The assumed role doesn't have permission to access the S3 bucket.[4]

**Solution:**

1. Verify the S3 permissions policy on the role
2. Check the bucket name and key path are correct
3. Ensure the bucket policy allows access from the role

### Error: "Failed to assume role"

**Cause:** The AgentCore service can't assume the S3 access role.[5]

**Solution:**

1. Verify the trust policy includes `bedrock-agentcore.amazonaws.com` as the service principal[2]
2. Check condition keys match your account ID and region[1]
3. Verify the role ARN is correct in SSM Parameter Store

### Error: "User is not authorized to perform: iam:PassRole"

**Cause:** Your IAM user/role lacks permission to pass the execution role to AgentCore.[1]

**Solution:**

Add the `iam:PassRole` permission to your IAM user or role:

```json
{
  "Effect": "Allow",
  "Action": "iam:PassRole",
  "Resource": "arn:aws:iam::YOUR_ACCOUNT_ID:role/AnalyzerS3AccessRole",
  "Condition": {
    "StringEquals": {
      "iam:PassedToService": "bedrock-agentcore.amazonaws.com"
    }
  }
}
```

### Error: "Missing required SSM parameters"

**Cause:** The S3 role ARN parameter is not set in SSM.[4]

**Solution:**

```bash
aws ssm put-parameter \
  --name "/scientific-agent/config/s3-access-role-arn" \
  --value "arn:aws:iam::YOUR_ACCOUNT_ID:role/AnalyzerS3AccessRole" \
  --type "String"
```

### Using Default Credentials (No Role Assumption)

If you don't configure the S3 role ARN, the agent will use default credentials:

```python
# The agent will log:
# "(IAM) No S3 access role ARN configured. Using default credentials."
```

This is useful for:

- Local development with AWS CLI credentials
- Environments where the execution role already has S3 access
- Testing without role assumption

## Security Best Practices

1. **Principle of Least Privilege:** Only grant read access to specific S3 buckets/prefixes[1]
2. **Use Condition Keys:** Always include `aws:SourceAccount` and `aws:SourceArn` in trust policies[3][1]
3. **Session Duration:** Role sessions expire after 1 hour (configurable in code)
4. **Audit Logging:** Enable CloudTrail to log role assumption events[6]
5. **Separate Roles:** Use different roles for different environments (dev/staging/prod)[7]
6. **Bucket Policies:** Add bucket policies as an additional layer of security[8]
7. **Restrict PassRole:** Scope `iam:PassRole` to specific roles and the AgentCore service[1]

## Configuration Reference

### SSM Parameters

| Parameter Name                                | Type   | Required | Description                |
| --------------------------------------------- | ------ | -------- | -------------------------- |
| `/scientific-agent/config/s3-access-role-arn` | String | Optional | IAM role ARN for S3 access |

### Environment Variables (Alternative)

You can also set the role ARN via environment variable (lower priority than SSM):

```bash
export S3_ACCESS_ROLE_ARN="arn:aws:iam::123456789012:role/AnalyzerS3AccessRole"
```

## Code Reference

### Key Functions

- `assume_s3_access_role(role_arn)` - Assumes the IAM role and returns S3 client
- `initialize_s3_client(role_arn)` - Initializes S3 client with optional role assumption
- `download_s3_document(s3_uri)` - Tool function that downloads documents from S3

### Session Duration

Default session duration is 1 hour. To modify:[4]

```python
# In assume_s3_access_role function
response = sts_client.assume_role(
    RoleArn=role_arn,
    RoleSessionName=session_name,
    DurationSeconds=7200,  # 2 hours (max: 43200 = 12 hours)
)
```

## Additional Resources

- [AWS IAM Roles Documentation](https://docs.aws.amazon.com/IAM/latest/UserGuide/id_roles.html)[9]
- [Amazon Bedrock AgentCore Runtime Permissions](https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/runtime-permissions.html)[1]
- [AWS STS AssumeRole API](https://docs.aws.amazon.com/STS/latest/APIReference/API_AssumeRole.html)[10]
- [S3 Bucket Policies](https://docs.aws.amazon.com/AmazonS3/latest/userguide/bucket-policies.html)[8]
- [How to Use Trust Policies with IAM Roles](https://aws.amazon.com/blogs/security/how-to-use-trust-policies-with-iam-roles/)[6]

[1](https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/runtime-permissions.html)
[2](https://aws.plainenglish.io/getting-started-with-bedrock-agentcore-runtime-3eaae1f517cc)
[3](https://builder.aws.com/content/2jo9g696XrBeJROs6Ep4JZ4lqHT/bedrock-agentcore-understand-agentcore-and-build-your-first-agentcore-ai-agent-in-under-an-hour)
[4](https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/code-interpreter-s3-integration.html)
[5](https://docs.aws.amazon.com/IAM/latest/UserGuide/troubleshoot_roles.html)
[6](https://aws.amazon.com/blogs/security/how-to-use-trust-policies-with-iam-roles/)
[7](https://dev.to/aws-builders/aws-trust-policy-complete-guide-how-to-control-iam-role-access-in-2025-cfi)
[8](https://docs.aws.amazon.com/bedrock/latest/userguide/s3-bucket-access.html)
[9](https://awsfundamentals.com/blog/aws-iam-roles-terms-concepts-and-examples)
[10](https://docs.aws.amazon.com/IAM/latest/UserGuide/id_credentials_temp_control-access_assumerole.html)
[11](https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/security_iam_service-with-iam.html)
[12](https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/security-iam.html)
[13](https://docs.aws.amazon.com/IAM/latest/UserGuide/reference_policies_elements_principal.html)
[14](https://wandb.ai/onlineinference/genai-research/reports/Amazon-Bedrock-AgentCore-observability-guide--VmlldzoxMzc2OTI5Mg)
[15](https://help.alteryx.com/smc/r87/en/admin/admin-tasks/access-management-tasks/insert-trust-relationship-in-aws-iam-role.html)
[16](https://dev.to/aws-builders/building-ai-agents-with-amazon-bedrock-agentcore-runtime-a-complete-setup-guide-50oh)
[17](https://docs.kore.ai/agent-platform/models/external-models/configuring-aws/)
[18](https://www.token.security/blog/iam-role-trust-policies-misconfigurations-hiding-in-plain-sight)
[19](https://stackoverflow.com/questions/60236256/assumerole-action-in-a-roles-trust-relationship-policy)
[20](https://docs.aws.amazon.com/bedrock/latest/userguide/agents-permissions.html)
[21](https://trendmicro.com/cloudoneconformity/knowledge-base/aws/Bedrock/service-role-policy-too-permissive.html)
[22](https://aws.permissions.cloud/iam/bedrock-agentcore)
[23](https://www.elastic.co/guide/en/security/8.19/aws-iam-roles-anywhere-trust-anchor-created-with-external-ca.html)
[24](https://builder.aws.com/content/32HpPjNanKLl7OZTpn48xhV0mSX/run-your-nova-act-workflow-on-amazon-bedrock-agentcore)
