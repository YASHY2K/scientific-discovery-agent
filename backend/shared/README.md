# Shared Lambda Utilities

This module provides standardized utilities for Lambda functions in the research agent tools. It implements common patterns for request parsing, response formatting, error handling, environment variable validation, and logging configuration.

## Features

- **Standardized Logging**: Consistent logging setup across all Lambda functions
- **Environment Validation**: Robust validation of required and optional environment variables
- **Request Parsing**: Unified request body parsing and validation
- **Response Formatting**: Consistent success and error response formats
- **Error Handling**: Standardized exception handling with appropriate HTTP status codes
- **AWS Client Management**: Efficient AWS client initialization and reuse
- **Secrets Management**: Simplified AWS Secrets Manager integration

## Quick Start

### Basic Usage

```python
from shared.lambda_utils import (
    setup_lambda_environment,
    RequestParser,
    ResponseFormatter,
    StandardErrorHandler
)

# Define environment configuration
REQUIRED_ENV_VARS = ["BUCKET_NAME", "API_ENDPOINT"]
OPTIONAL_ENV_VARS = {
    "TIMEOUT": "30",
    "SEARCH_LIMIT": "10",
    "LOG_LEVEL": "INFO"
}

# Setup environment (done outside handler for reuse)
config, logger = setup_lambda_environment(
    required_env_vars=REQUIRED_ENV_VARS,
    optional_env_vars=OPTIONAL_ENV_VARS
)

@StandardErrorHandler.handle_common_exceptions
def lambda_handler(event, context):
    logger.info("Processing request")

    # Parse request
    body = RequestParser.parse_event_body(event)
    RequestParser.validate_required_fields(body, ["query"])

    # Process request
    result = process_query(body["query"])

    # Return response
    return ResponseFormatter.create_success_response(result)
```

### Manual Error Handling

If you need custom error handling logic:

```python
def lambda_handler(event, context):
    try:
        # Your logic here
        result = process_request(event)
        return ResponseFormatter.create_success_response(result)

    except ValueError as e:
        logger.error(f"Validation error: {e}")
        return ResponseFormatter.create_error_response(
            400, "Validation Error", str(e)
        )
    except CustomException as e:
        # Handle custom exceptions
        return ResponseFormatter.create_error_response(
            422, "Processing Error", str(e)
        )
```

## Components

### LambdaLogger

Provides standardized logging configuration:

```python
from shared.lambda_utils import LambdaLogger

logger = LambdaLogger.setup_logger("my-function", "INFO")
logger.info("This is a standardized log message")
```

### EnvironmentValidator

Validates environment variables:

```python
from shared.lambda_utils import EnvironmentValidator

# Validate required variables
config = EnvironmentValidator.validate_required_vars(["API_KEY", "BUCKET_NAME"])

# Get optional variables with defaults
optional_config = EnvironmentValidator.get_optional_vars({
    "TIMEOUT": "30",
    "LIMIT": "10"
})

# Validate both at once
all_config = EnvironmentValidator.validate_environment(
    required_vars=["API_KEY"],
    optional_vars={"TIMEOUT": "30"}
)
```

### RequestParser

Handles request parsing and validation:

```python
from shared.lambda_utils import RequestParser

# Parse event body
body = RequestParser.parse_event_body(event)

# Validate required fields
RequestParser.validate_required_fields(body, ["query", "limit"])
```

### ResponseFormatter

Creates standardized responses:

```python
from shared.lambda_utils import ResponseFormatter

# Success response
return ResponseFormatter.create_success_response({
    "results": data,
    "count": len(data)
})

# Error response
return ResponseFormatter.create_error_response(
    400, "Validation Error", "Missing required field", "Field 'query' is required"
)
```

### AWSClientManager

Manages AWS client instances:

```python
from shared.lambda_utils import AWSClientManager

# Get reusable clients
s3_client = AWSClientManager.get_client('s3')
secrets_client = AWSClientManager.get_client('secretsmanager')

# Retrieve secrets
secret_data = AWSClientManager.get_secret('my-secret-name')
api_key = secret_data.get('API_KEY')
```

### StandardErrorHandler

Decorator for automatic error handling:

```python
from shared.lambda_utils import StandardErrorHandler

@StandardErrorHandler.handle_common_exceptions
def lambda_handler(event, context):
    # Your code here - exceptions are automatically handled
    return process_request(event)
```

## Response Formats

### Success Response

```json
{
  "statusCode": 200,
  "body": "{\"results\": [...], \"metadata\": {...}}"
}
```

### Error Response

```json
{
  "statusCode": 400,
  "body": "{\"error\": \"Validation Error\", \"message\": \"Missing required field\", \"details\": \"Field 'query' is required\", \"timestamp\": \"2024-01-01T12:00:00Z\"}"
}
```

## Error Handling

The utilities provide standardized error handling for common scenarios:

- **400 Bad Request**: Validation errors, missing required fields
- **403 Forbidden**: AWS access denied errors
- **404 Not Found**: AWS resource not found errors
- **500 Internal Server Error**: Unexpected exceptions
- **502 Bad Gateway**: External API failures
- **504 Gateway Timeout**: Request timeouts

## Environment Variables

### Required Variables (example)

- `BUCKET_NAME`: S3 bucket for file storage
- `API_ENDPOINT`: External API endpoint URL

### Optional Variables (with defaults)

- `TIMEOUT`: Request timeout in seconds (default: "30")
- `SEARCH_LIMIT`: Maximum search results (default: "10")
- `LOG_LEVEL`: Logging level (default: "INFO")

## Best Practices

1. **Initialize clients outside the handler** for reuse across invocations
2. **Use the decorator** for automatic error handling unless custom logic is needed
3. **Validate environment variables** at startup, not on each request
4. **Log important events** but avoid logging sensitive information
5. **Use structured responses** for consistent API behavior
6. **Handle timeouts appropriately** for external API calls

## Migration Guide

To migrate existing Lambda functions to use these utilities:

1. **Add import statements**:

   ```python
   from shared.lambda_utils import setup_lambda_environment, RequestParser, ResponseFormatter
   ```

2. **Replace logging setup**:

   ```python
   # Old
   logger = logging.getLogger()
   # ... manual setup ...

   # New
   config, logger = setup_lambda_environment(required_vars=["BUCKET_NAME"])
   ```

3. **Standardize request parsing**:

   ```python
   # Old
   body = json.loads(event.get("body", "{}"))

   # New
   body = RequestParser.parse_event_body(event)
   RequestParser.validate_required_fields(body, ["query"])
   ```

4. **Standardize responses**:

   ```python
   # Old
   return {"statusCode": 200, "body": json.dumps(result)}

   # New
   return ResponseFormatter.create_success_response(result)
   ```

5. **Add error handling decorator**:
   ```python
   @StandardErrorHandler.handle_common_exceptions
   def lambda_handler(event, context):
       # Your existing code
   ```
