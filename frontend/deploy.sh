#!/bin/bash

# AWS App Runner Deployment Script for Research Agent Frontend
# This script builds the Docker image and pushes it to Amazon ECR

set -e  # Exit on any error

# Configuration - Update these values for your environment
AWS_REGION="${AWS_REGION:-us-east-1}"
AWS_ACCOUNT_ID="${AWS_ACCOUNT_ID}"
ECR_REPOSITORY_NAME="${ECR_REPOSITORY_NAME:-research-agent-frontend}"
IMAGE_TAG="${IMAGE_TAG:-latest}"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Function to print colored messages
print_info() {
    echo -e "${GREEN}[INFO]${NC} $1"
}

print_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

print_warning() {
    echo -e "${YELLOW}[WARNING]${NC} $1"
}

# Validate required environment variables
if [ -z "$AWS_ACCOUNT_ID" ]; then
    print_error "AWS_ACCOUNT_ID environment variable is not set"
    echo "Usage: AWS_ACCOUNT_ID=123456789012 ./deploy.sh"
    exit 1
fi

# Construct ECR repository URI
ECR_URI="${AWS_ACCOUNT_ID}.dkr.ecr.${AWS_REGION}.amazonaws.com/${ECR_REPOSITORY_NAME}"

print_info "Starting deployment process..."
print_info "AWS Region: ${AWS_REGION}"
print_info "AWS Account ID: ${AWS_ACCOUNT_ID}"
print_info "ECR Repository: ${ECR_REPOSITORY_NAME}"
print_info "Image Tag: ${IMAGE_TAG}"

# Step 1: Authenticate Docker to ECR
print_info "Authenticating Docker to Amazon ECR..."
aws ecr get-login-password --region ${AWS_REGION} | docker login --username AWS --password-stdin ${ECR_URI}

if [ $? -ne 0 ]; then
    print_error "Failed to authenticate with ECR"
    exit 1
fi

# Step 2: Create ECR repository if it doesn't exist
print_info "Checking if ECR repository exists..."
aws ecr describe-repositories --repository-names ${ECR_REPOSITORY_NAME} --region ${AWS_REGION} > /dev/null 2>&1

if [ $? -ne 0 ]; then
    print_warning "ECR repository does not exist. Creating..."
    aws ecr create-repository \
        --repository-name ${ECR_REPOSITORY_NAME} \
        --region ${AWS_REGION} \
        --image-scanning-configuration scanOnPush=true
    
    if [ $? -eq 0 ]; then
        print_info "ECR repository created successfully"
    else
        print_error "Failed to create ECR repository"
        exit 1
    fi
else
    print_info "ECR repository already exists"
fi

# Step 3: Build Docker image
print_info "Building Docker image..."
docker build -t ${ECR_REPOSITORY_NAME}:${IMAGE_TAG} .

if [ $? -ne 0 ]; then
    print_error "Docker build failed"
    exit 1
fi

print_info "Docker image built successfully"

# Step 4: Tag the image for ECR
print_info "Tagging Docker image for ECR..."
docker tag ${ECR_REPOSITORY_NAME}:${IMAGE_TAG} ${ECR_URI}:${IMAGE_TAG}

# Step 5: Push image to ECR
print_info "Pushing Docker image to ECR..."
docker push ${ECR_URI}:${IMAGE_TAG}

if [ $? -ne 0 ]; then
    print_error "Failed to push image to ECR"
    exit 1
fi

print_info "Docker image pushed successfully"

# Step 6: Display next steps
echo ""
print_info "Deployment preparation complete!"
echo ""
echo "Next steps to deploy to AWS App Runner:"
echo "1. Go to AWS App Runner console: https://console.aws.amazon.com/apprunner"
echo "2. Create a new service or update existing service"
echo "3. Select 'Container registry' as source"
echo "4. Use ECR image: ${ECR_URI}:${IMAGE_TAG}"
echo "5. Configure environment variables:"
echo "   - AWS_REGION=${AWS_REGION}"
echo "   - AWS_ACCOUNT_ID=${AWS_ACCOUNT_ID}"
echo "   - AGENT_RUNTIME_ARN=<your-agent-runtime-arn>"
echo "6. Set port to 8501"
echo "7. Configure IAM role with bedrock-agentcore:InvokeAgentRuntime permission"
echo ""
print_info "Image URI: ${ECR_URI}:${IMAGE_TAG}"
