# Research Multi-Agent System - Frontend

A Streamlit-based chat interface for interacting with the multi-agent research system. This interface provides real-time transparency into agent execution through a "glassbox" sidebar, allowing researchers to see exactly how the AI agents work together to conduct comprehensive literature reviews.

## Features

- 🔬 **Simple Chat Interface** - Submit research questions through an intuitive chat UI
- 🤖 **Real-Time Agent Status** - Watch agents work in real-time through the sidebar
- 📊 **Execution Transparency** - See papers found, analysis iterations, and agents used
- 📝 **Professional Reports** - Receive well-formatted research reports with proper citations
- 💾 **Session Management** - Conversation context maintained during your session

## Architecture

The frontend is built with:

- **Streamlit** - Python web framework for rapid UI development
- **AWS Bedrock Agent Runtime** - Integration with the multi-agent research system
- **boto3** - AWS SDK for Python

### Configuration Management

The application uses a hybrid configuration approach:

- **Local Development**: Configuration via environment variables for simplicity
- **Production (App Runner)**: Configuration via AWS Systems Manager (SSM) Parameter Store for security and centralized management

The `utils.py` module provides a `get_config_value()` function that:

1. Checks for environment variables first (for local development)
2. Falls back to SSM Parameter Store if environment variables are not set (for production)
3. Returns `None` if configuration is not found in either location

This approach allows seamless local development without AWS SSM access while enabling secure, centralized configuration management in production.

## Prerequisites

- Python 3.11 or higher
- AWS Account with Bedrock Agent Runtime deployed
- AWS credentials configured (via AWS CLI or environment variables)

## Setup Instructions

### 1. Install Dependencies

```bash
cd frontend
pip install -r requirements.txt
```

### 2. Configure Environment Variables for Local Development

For local development, set environment variables in your shell:

```bash
export AWS_REGION=us-east-1
export AGENT_RUNTIME_ARN=arn:aws:bedrock-agent:us-east-1:123456789012:agent/AGENT_ID
```

The application checks environment variables first, then falls back to AWS Systems Manager (SSM) Parameter Store for production deployments.

### 3. Configure AWS Credentials

Configure your AWS credentials for local development:

```bash
aws configure
```

## Local Development

### Running the Application

Start the Streamlit development server:

```bash
streamlit run app.py
```

The application will be available at `http://localhost:8501`

### Development Tips

- **Auto-reload**: Streamlit automatically reloads when you save changes to `app.py`
- **Session State**: Use the sidebar to see your current session ID
- **Error Debugging**: Errors are displayed in the chat with expandable details
- **Cache Management**: The AWS client is cached using `@st.cache_resource` for performance

### Testing Locally

1. Start the application: `streamlit run app.py`
2. Submit a research question (e.g., "Find papers on transformer architectures")
3. Watch the agent status in the sidebar
4. Verify the report is displayed with proper formatting
5. Check that chat history persists during the session

## Deployment to AWS App Runner

### Prerequisites: Configure SSM Parameter Store

Before deploying to App Runner, create the required SSM parameters:

```bash
# Create AWS region parameter
aws ssm put-parameter \
  --name "/app/config/AWS_REGION" \
  --value "us-east-1" \
  --type "String" \
  --description "AWS region for Bedrock agent"

# Create agent runtime ARN parameter
aws ssm put-parameter \
  --name "/app/config/AGENT_RUNTIME_ARN" \
  --value "arn:aws:bedrock-agent:us-east-1:123456789012:agent/AGENT_ID" \
  --type "String" \
  --description "Bedrock agent runtime ARN"
```

Replace the values with your actual AWS region and agent ARN.

### Option 1: Using the Deployment Script

The easiest way to deploy is using the provided deployment script:

```bash
# Set your AWS account ID
export AWS_ACCOUNT_ID=123456789012
export AWS_REGION=us-east-1

# Run the deployment script
chmod +x deploy.sh
./deploy.sh
```

The script will:

1. Authenticate Docker with Amazon ECR
2. Create ECR repository if it doesn't exist
3. Build the Docker image
4. Push the image to ECR
5. Display next steps for App Runner configuration

### Option 2: Manual Deployment

#### Step 1: Build and Push Docker Image

```bash
# Set variables
AWS_REGION=us-east-1
AWS_ACCOUNT_ID=123456789012
ECR_REPOSITORY_NAME=research-agent-frontend

# Authenticate Docker to ECR
aws ecr get-login-password --region ${AWS_REGION} | \
  docker login --username AWS --password-stdin \
  ${AWS_ACCOUNT_ID}.dkr.ecr.${AWS_REGION}.amazonaws.com

# Create ECR repository (if it doesn't exist)
aws ecr create-repository \
  --repository-name ${ECR_REPOSITORY_NAME} \
  --region ${AWS_REGION}

# Build Docker image
docker build -t ${ECR_REPOSITORY_NAME}:latest .

# Tag for ECR
docker tag ${ECR_REPOSITORY_NAME}:latest \
  ${AWS_ACCOUNT_ID}.dkr.ecr.${AWS_REGION}.amazonaws.com/${ECR_REPOSITORY_NAME}:latest

# Push to ECR
docker push ${AWS_ACCOUNT_ID}.dkr.ecr.${AWS_REGION}.amazonaws.com/${ECR_REPOSITORY_NAME}:latest
```

#### Step 2: Create App Runner Service

1. Go to [AWS App Runner Console](https://console.aws.amazon.com/apprunner)
2. Click "Create service"
3. Configure the service:

**Source:**

- Repository type: Container registry
- Provider: Amazon ECR
- Container image URI: `<your-ecr-uri>:latest`
- Deployment trigger: Manual

**Deployment settings:**

- Service name: `research-agent-frontend`
- Port: `8501`
- CPU: 1 vCPU
- Memory: 2 GB

**Environment variables:**

No environment variables are required in App Runner. The application retrieves configuration from SSM Parameter Store using the instance role.

**IAM Instance Role:**
Create or select an IAM role with the following permissions:

```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Action": "ssm:GetParameter",
      "Resource": "arn:aws:ssm:*:*:parameter/app/config/*"
    },
    {
      "Effect": "Allow",
      "Action": "bedrock-agent-runtime:InvokeAgent",
      "Resource": "arn:aws:bedrock-agent:*:*:agent/*"
    }
  ]
}
```

This role grants the App Runner service permission to:

- Read configuration parameters from SSM Parameter Store under `/app/config/*`
- Invoke the Bedrock agent runtime

4. Click "Create & deploy"

### Post-Deployment

After deployment, App Runner will provide a public URL (e.g., `https://xxxxx.us-east-1.awsapprunner.com`). Access this URL to use the application.

## Configuration Reference

### Local Development (Environment Variables)

For local development, set these environment variables:

| Variable            | Required | Description                             | Example                                                       |
| ------------------- | -------- | --------------------------------------- | ------------------------------------------------------------- |
| `AWS_REGION`        | Yes      | AWS region where your agent is deployed | `us-east-1`                                                   |
| `AGENT_RUNTIME_ARN` | Yes      | Full ARN of your Bedrock agent          | `arn:aws:bedrock-agent:us-east-1:123456789012:agent/AGENT_ID` |

AWS credentials are managed through the AWS CLI (`aws configure`) or IAM roles.

### Production (SSM Parameter Store)

For App Runner deployments, configuration is stored in SSM Parameter Store:

| Parameter Name                  | Type   | Description                             | Example                                                       |
| ------------------------------- | ------ | --------------------------------------- | ------------------------------------------------------------- |
| `/app/config/AWS_REGION`        | String | AWS region where your agent is deployed | `us-east-1`                                                   |
| `/app/config/AGENT_RUNTIME_ARN` | String | Full ARN of your Bedrock agent          | `arn:aws:bedrock-agent:us-east-1:123456789012:agent/AGENT_ID` |

The application automatically retrieves these values using the App Runner instance role.

## Project Structure

```
frontend/
├── app.py                    # Main Streamlit application
├── utils.py                  # Configuration utilities (SSM integration)
├── requirements.txt          # Python dependencies
├── Dockerfile               # Container configuration
├── deploy.sh                # Deployment automation script
├── .streamlit/
│   └── config.toml          # Streamlit configuration
└── README.md                # This file
```

## Configuration Files

### Streamlit Configuration (.streamlit/config.toml)

The application uses custom Streamlit configuration:

- **Port**: 8501 (standard Streamlit port)
- **CORS**: Disabled for security
- **XSRF Protection**: Enabled
- **Theme**: Custom color scheme matching the research theme

### Docker Configuration (Dockerfile)

The Docker image:

- Uses Python 3.11-slim base image
- Installs all dependencies from requirements.txt
- Exposes port 8501
- Includes health check endpoint
- Runs Streamlit with proper server configuration

## Troubleshooting

### AWS Credentials Not Found

**Error**: `NoCredentialsError: Unable to locate credentials`

**Solution**:

1. For local development: Run `aws configure` to set up credentials
2. For App Runner: Ensure the IAM instance role is properly attached with SSM and Bedrock permissions

### Agent Runtime ARN Invalid

**Error**: `ClientError: Invalid parameter: agentId`

**Solution**:

1. For local development: Verify `AGENT_RUNTIME_ARN` environment variable
2. For App Runner: Verify the `/app/config/AGENT_RUNTIME_ARN` parameter in SSM Parameter Store
3. Ensure the ARN format is correct: `arn:aws:bedrock-agent:region:account:agent/AGENT_ID`
4. Confirm the agent is deployed and accessible

### Connection Timeout

**Error**: Request times out after several minutes

**Solution**:

1. Check that your agent is running and healthy
2. Verify network connectivity to AWS Bedrock
3. Ensure IAM permissions are correctly configured
4. Check CloudWatch logs for agent errors

### Port Already in Use

**Error**: `OSError: [Errno 48] Address already in use`

**Solution**:

1. Stop other Streamlit instances: `pkill -f streamlit`
2. Or use a different port: `streamlit run app.py --server.port=8502`

## How It Works

### Agent Workflow

When you submit a research question, the system executes a multi-agent workflow:

1. **📋 Planner Agent** - Creates a research plan based on your query
2. **🔍 Searcher Agent** - Searches arXiv and Semantic Scholar for relevant papers
3. **📊 Analyzer Agent** - Analyzes paper content and extracts key findings
4. **⚖️ Critique Agent** - Reviews the analysis quality and suggests improvements
5. **📝 Reporter Agent** - Generates the final research report with citations

### Session Management

- Each browser session gets a unique UUID
- Chat history is maintained in Streamlit's session state
- Session context is passed to agents for conversation continuity
- Sessions are cleared on page refresh (no persistence in MVP)

### Real-Time Transparency

The sidebar provides "glassbox" visibility into agent execution:

- Shows which agent is currently working
- Displays progress through the 5-agent workflow
- Updates status when workflow completes
- Shows execution summary (papers found, iterations, agents used)

## Performance Considerations

- **Agent Execution Time**: Research tasks typically take 5-10 minutes
- **UI Responsiveness**: Streamlit handles UI updates efficiently
- **AWS API Latency**: < 500ms for API calls
- **Caching**: AWS client is cached to improve performance

## Security Notes

- **Authentication**: No authentication in MVP (public access)
- **HTTPS**: Enforced by AWS App Runner
- **Credentials**: Never commit `.env` file to version control
- **IAM**: Use least-privilege permissions for the App Runner role
- **Input Validation**: Streamlit handles basic XSS protection

## Future Enhancements

- **Streaming Responses**: Real-time updates as agents work
- **Session Persistence**: Store chat history in DynamoDB
- **Authentication**: Add AWS Cognito integration
- **Export Reports**: Download as PDF or BibTeX
- **Advanced UI**: Paper previews, interactive citations

## Support

For issues or questions:

1. Check the troubleshooting section above
2. Review CloudWatch logs for detailed error messages
3. Verify all environment variables are correctly set
4. Ensure your AWS credentials have proper permissions

## License

This project is part of the Research Multi-Agent System and follows the same license as the parent project.
