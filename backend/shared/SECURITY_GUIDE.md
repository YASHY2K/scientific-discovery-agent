# Lambda Security Configuration Guide

This guide outlines security best practices and configuration management for AWS Lambda functions in the research agent project.

## Overview

The security utilities provide comprehensive protection for Lambda functions including:

- Secure API key management with multiple retrieval strategies
- Environment variable validation with security checks
- Sanitized logging to prevent sensitive data exposure
- URL validation for external API calls
- Comprehensive error handling with security context

## Security Components

### 1. SecurityManager

The `SecurityManager` class provides centralized security management:

```python
from shared.security_utils import SecurityManager

# Secure API key retrieval
api_key = SecurityManager.get_api_key_securely(
    secret_name="research-agent/api-keys",
    env_var_name="SEMANTIC_SCHOLAR_API_KEY",
    key_name="SEMANTIC_SCHOLAR_API_KEY",
    required=False
)

# Environment validation with security checks
config = SecurityManager.validate_environment_startup(
    required_vars=["API_BASE_URL"],
    optional_vars={"TIMEOUT": "30"},
    function_name="my_function"
)

# Sanitize data for logging
safe_data = SecurityManager.sanitize_for_logging(sensitive_config)
```

### 2. SecureAPIKeyManager

Simplified API key management with fallback strategies:

```python
from shared.lambda_utils import SecureAPIKeyManager

api_key = SecureAPIKeyManager.get_api_key(
    secret_name="research-agent/api-keys",
    env_var_name="SEMANTIC_SCHOLAR_API_KEY",
    key_name="SEMANTIC_SCHOLAR_API_KEY",
    required=False,
    logger=logger
)
```

### 3. Secure Environment Setup

Use the secure environment setup function for comprehensive validation:

```python
from shared.lambda_utils import setup_secure_lambda_environment

config, logger = setup_secure_lambda_environment(
    required_env_vars=["API_BASE_URL", "S3_BUCKET_NAME"],
    optional_env_vars={"TIMEOUT": "30", "LOG_LEVEL": "INFO"},
    function_name="my_secure_function",
    log_level="INFO"
)
```

## Configuration Best Practices

### Environment Variables

**Required Variables:**

- Always validate required environment variables at startup
- Use descriptive names that indicate their purpose
- Fail fast if required variables are missing

**Optional Variables:**

- Provide secure defaults for all optional variables
- Validate numeric values are within acceptable ranges
- Use consistent naming conventions

**Sensitive Variables:**

- Never store API keys directly in environment variables in production
- Use AWS Secrets Manager for sensitive configuration
- Provide environment variable fallbacks for development only

### API Key Management

**Production (Recommended):**

```json
{
  "SECRET_NAME": "research-agent/api-keys",
  "API_KEY_ENV_VAR": ""
}
```

**Development (Fallback):**

```json
{
  "SECRET_NAME": "",
  "API_KEY_ENV_VAR": "SEMANTIC_SCHOLAR_API_KEY"
}
```

**AWS Secrets Manager Structure:**

```json
{
  "SEMANTIC_SCHOLAR_API_KEY": "your-actual-api-key",
  "ARXIV_API_KEY": "optional-arxiv-key",
  "OTHER_SERVICE_KEY": "another-key"
}
```

### Memory and Timeout Configuration

Each Lambda function includes optimized configuration:

**ArXiv Search (Lightweight):**

- Memory: 256MB
- Timeout: 30 seconds
- Use case: Simple API calls

**Acquire Paper (File Processing):**

- Memory: 1024MB
- Timeout: 300 seconds (5 minutes)
- Use case: File downloads and S3 operations

**Extract Content (PDF Processing):**

- Memory: 2048MB
- Timeout: 180 seconds (3 minutes)
- Use case: PyMuPDF processing

**Preprocess Text (Text Processing):**

- Memory: 1024MB
- Timeout: 120 seconds (2 minutes)
- Use case: Text chunking and cleaning

**Semantic Scholar (API Calls):**

- Memory: 256MB
- Timeout: 60 seconds
- Use case: API calls with retry logic

## Security Validation

### URL Security

All external URLs are validated for security:

```python
# Validate URL security
if not SecurityManager.validate_url_security(api_url, {"https"}):
    raise ValueError(f"Insecure URL: {api_url}")
```

**Security Checks:**

- Ensures HTTPS for production environments
- Prevents localhost/private IP access in production
- Validates URL format and structure

### Input Validation

All user inputs are validated before processing:

```python
# Validate required fields
RequestParser.validate_required_fields(body, ["query", "action"])

# Validate specific parameters
if not query or len(query) > 500:
    raise ValueError("Query must be 1-500 characters")
```

### Logging Security

All logging is sanitized to prevent sensitive data exposure:

```python
# Automatic sanitization
sanitized_config = SecurityManager.sanitize_for_logging(config)
logger.info(f"Configuration: {json.dumps(sanitized_config)}")

# Security event logging
SecurityManager.log_security_event(
    logger,
    "api_key_retrieval",
    {"has_key": api_key is not None, "source": "secrets_manager"}
)
```

**Sensitive Patterns (Automatically Redacted):**

- API keys and tokens
- Passwords and credentials
- Secret names and values
- Authentication headers

## Error Handling

Security-aware error handling prevents information disclosure:

```python
try:
    # Business logic
    result = process_request(data)
    return ResponseFormatter.create_success_response(result)

except ValueError as e:
    # Client errors - safe to expose message
    logger.error(f"Validation error: {e}")
    return ResponseFormatter.create_error_response(400, "Validation Error", str(e))

except Exception as e:
    # Server errors - log details but return generic message
    logger.exception("Unexpected error")
    SecurityManager.log_security_event(
        logger, "unexpected_error",
        {"error_type": type(e).__name__},
        level="ERROR"
    )
    return ResponseFormatter.create_error_response(
        500, "Internal Server Error", "An unexpected error occurred"
    )
```

## Deployment Security

### IAM Permissions

Minimal required permissions for each function:

```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Action": ["secretsmanager:GetSecretValue"],
      "Resource": "arn:aws:secretsmanager:region:account:secret:research-agent/*"
    },
    {
      "Effect": "Allow",
      "Action": ["s3:GetObject", "s3:PutObject"],
      "Resource": "arn:aws:s3:::research-bucket/*"
    },
    {
      "Effect": "Allow",
      "Action": [
        "logs:CreateLogGroup",
        "logs:CreateLogStream",
        "logs:PutLogEvents"
      ],
      "Resource": "arn:aws:logs:region:account:*"
    }
  ]
}
```

### Environment Security

**Production Environment:**

- Use HTTPS for all external APIs
- Store secrets in AWS Secrets Manager
- Enable CloudTrail for audit logging
- Use VPC endpoints for AWS services
- Enable encryption at rest and in transit

**Development Environment:**

- Allow HTTP for local testing only
- Use environment variables for convenience
- Implement additional logging for debugging
- Use separate AWS accounts/regions

## Monitoring and Alerting

Security events are logged for monitoring:

**Security Event Types:**

- `environment_validation_success/failure`
- `api_key_retrieval`
- `security_validation_error`
- `unexpected_error`
- `url_validation_failure`

**CloudWatch Metrics:**

- Function duration and memory usage
- Error rates by error type
- API key retrieval success/failure rates
- Security validation failures

**Recommended Alerts:**

- High error rates (>5% in 5 minutes)
- Security validation failures
- Unexpected errors
- Function timeouts
- Memory usage approaching limits

## Testing Security

### Unit Tests

Test security functions with various scenarios:

```python
def test_api_key_retrieval():
    # Test successful retrieval
    # Test fallback scenarios
    # Test error handling
    # Test required vs optional keys

def test_environment_validation():
    # Test required variable validation
    # Test optional variable defaults
    # Test security checks
    # Test error scenarios

def test_logging_sanitization():
    # Test sensitive data redaction
    # Test nested object sanitization
    # Test various sensitive patterns
```

### Integration Tests

Test complete security workflows:

```python
def test_secure_lambda_handler():
    # Test with valid configuration
    # Test with missing required variables
    # Test with invalid URLs
    # Test with missing API keys
    # Test error handling paths
```

## Compliance and Auditing

### Security Compliance

- All sensitive data is encrypted at rest and in transit
- API keys are never logged or exposed in responses
- Input validation prevents injection attacks
- Error messages don't expose internal system details
- All security events are logged for audit trails

### Regular Security Reviews

- Review IAM permissions quarterly
- Audit Secrets Manager access logs
- Monitor CloudWatch security metrics
- Update dependencies for security patches
- Review and test disaster recovery procedures

## Troubleshooting

### Common Issues

**API Key Not Found:**

- Check Secrets Manager secret exists and is accessible
- Verify IAM permissions for secretsmanager:GetSecretValue
- Check environment variable fallback configuration

**Environment Validation Failures:**

- Review required vs optional variable configuration
- Check variable naming and format
- Verify numeric values are within acceptable ranges

**URL Validation Failures:**

- Ensure HTTPS is used for production APIs
- Check for localhost/private IP usage in production
- Verify URL format and structure

**Logging Issues:**

- Check CloudWatch log group permissions
- Verify log level configuration
- Review sanitization for sensitive data exposure
