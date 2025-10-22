# 🔬 The Autonomous Research Agent

> **Last Updated:** January 21, 2025  
> **Status:** Production Deployment  
> **Version:** 1.0

**A collaborative multi-agent AI system that automates comprehensive literature reviews to accelerate scientific innovation, built on AWS Strands Agents and Amazon Bedrock.**

![AWS AI Agent Global Hackathon](https://img.shields.io/badge/Hackathon-AWS%20AI%20Agent%20Global-orange)
![Python](https://img.shields.io/badge/Python-3.11-blue.svg)
![AWS](https://img.shields.io/badge/AWS-Serverless-yellow.svg)
![Strands Agents](https://img.shields.io/badge/Strands%20Agents-v1.0-red)
![Claude 3.5 Sonnet](https://img.shields.io/badge/Claude%203.5%20Sonnet-Bedrock-blueviolet)
![License](https://img.shields.io/badge/License-MIT-green.svg)

---

### **Table of Contents**

1.  [Introduction: The Problem & Our Solution](#1-introduction-the-problem--our-solution)
2.  [Key Features & Requirements](#2-key-features--requirements)
3.  [The Glass Box: Real-time Transparency](#3-the-glass-box-real-time-transparency)
4.  [How It Works: The Multi-Agent Architecture](#4-how-it-works-the-multi-agent-architecture)
5.  [Technology Stack](#5-technology-stack)
6.  [Project Setup & Local Development (Copilot Instructions)](#6-project-setup--local-development-copilot-instructions)
7.  [Deployment Steps (Copilot Instructions)](#7-deployment-steps-copilot-instructions)
8.  [Running a Research Task](#8-running-a-research-task)
9.  [Directory Structure](#9-directory-structure)
10. [Live Demo & Video](#10-live-demo--video)
11. [Team](#11-team)

---

## **1. Introduction: The Problem & Our Solution**

The exponential growth of scientific literature presents a formidable challenge to researchers. Conducting a thorough literature review, a foundational step for any scientific endeavor, has become a months-long, labor-intensive manual effort. This bottleneck significantly impedes the pace of innovation, increases the risk of redundant work, and obscures crucial cross-disciplinary insights.

Our solution, **The Autonomous Research Agent**, is designed to revolutionize this process. It's a sophisticated, collaborative multi-agent AI system built on **AWS Strands Agents SDK** and **Amazon Bedrock**. Researchers can provide a high-level query (e.g., "Summarize recent advances in mRNA vaccine stabilization techniques"), and the system will autonomously:

- Formulate a research plan.
- Search multiple academic databases.
- Analyze and synthesize findings from relevant papers.
- Critique its own analysis for completeness and accuracy.
- Generate a comprehensive, properly cited research report, all within minutes.

This system aims to transform the tedious literature review into an automated, transparent, and academically rigorous workflow, accelerating scientific discovery.

## **2. Key Features & Requirements**

This project addresses key requirements for autonomous research, focusing on both the research outcome and the user experience:

- **Autonomous & Comprehensive Research (Req 1, 3):**
  - Submits a query, receives a full literature review automatically.
  - Generates structured research plans and makes reasonable assumptions for ambiguous queries.
  - Queries multiple academic databases (arXiv, Semantic Scholar) and analyzes full-text content.
  - Filters irrelevant papers and identifies key methodologies, novel contributions, and comparative insights.
- **Self-Critique & Iterative Refinement (Req 4):**
  - Automatically critiques its own analysis for completeness and accuracy.
  - Conducts additional research to fill identified gaps and revises analysis until quality standards are met.
- **Verifiable & Professional Reports (Req 5):**
  - Generates well-structured reports including executive summary, methodology review, comparative analysis, and future directions.
  - Provides proper academic citations with links to original papers.
  - Reports are stored in a downloadable Markdown format with metadata on the research process.
- **Scalable, Resilient & Cost-Optimized (Req 6, 7):**
  - Fully serverless AWS architecture, scaling automatically for concurrent research sessions.
  - Maintains state persistence for long-running tasks, recovering from failures.
  - Caches processed content (e.g., extracted PDF text) for faster, cost-effective reuse.
  - Scales down to zero when idle to minimize costs.
- **Secure & Private (Req 8):**
  - Encrypts all data at rest and in transit.
  - Uses secure access controls (e.g., presigned URLs) and implements authentication/authorization.
  - Maintains session-based data isolation with automatic cache expiration.

## **3. The Glass Box: Real-time Transparency (Req 2)**

A cornerstone of our design is the **"Glass Box" transparency system**. As a researcher, you'll have real-time visibility into the agent workflow.

- **Live Activity Stream:** See a timeline of agent activities in the Streamlit sidebar as the workflow progresses.
- **Phase Tracking:** Watch as the system moves through Planning → Search → Analysis → Critique → Reporting phases.
- **Execution Summary:** View metrics including papers found, analysis iterations, agents executed, and quality scores.
- **Complete Audit Trail:** The orchestrator maintains full state history using Strands' `ToolContext`, preserving all decisions and results.

The transparency system leverages **Bedrock AgentCore's built-in observability** combined with Streamlit's real-time UI updates to provide visibility into the multi-agent workflow.

## **4. How It Works: The Multi-Agent Architecture**

Our system employs a sophisticated **hierarchical multi-agent architecture** managed by **AWS Strands Agents SDK** and hosted on **AWS Bedrock AgentCore Runtime**.

```mermaid
graph TB
    User[User via Streamlit] --> Runtime[AgentCore Runtime]
    Runtime --> Orch[Orchestrator Agent]
    Orch --> Gateway[AgentCore Gateway]
    Gateway --> Tools[Lambda Tools]
    Tools --> S3[S3 Storage]

    subgraph "Specialist Agents (via @tool decorators)"
        Planner[Planner Agent]
        Searcher[Searcher Agent]
        Analyzer[Analyzer Agent]
        Critique[Critique Agent]
        Reporter[Reporter Agent]
    end

    Orch -.->|@tool calls| Planner
    Orch -.->|@tool calls| Searcher
    Orch -.->|@tool calls| Analyzer
    Orch -.->|@tool calls| Critique
    Orch -.->|@tool calls| Reporter

    subgraph "Lambda Tools (via MCP)"
        SearchArxiv[search_arxiv]
        SearchSS[search_semantic_scholar]
        AcquirePaper[acquire_paper]
        ExtractContent[extract_content]
        PreprocessText[preprocess_text]
    end

    Gateway --> SearchArxiv
    Gateway --> SearchSS
    Gateway --> AcquirePaper
    Gateway --> ExtractContent
    Gateway --> PreprocessText
```

**Key Architectural Principles:**

- **AgentCore Runtime (The Execution Platform):** All agents run within AWS Bedrock AgentCore Runtime, a fully managed service that handles agent hosting, state management, and execution. The runtime is deployed using `BedrockAgentCoreApp` and provides built-in observability and scaling.

- **Orchestrator Agent (The Research Lead):** This primary agent, powered by Claude Sonnet 4, receives user queries via the runtime's entrypoint. It acts as a project manager, dynamically delegating tasks to specialist agents using the `@tool` decorator pattern. The orchestrator manages the overall workflow through five phases: Planning → Search → Analysis → Critique → Reporting.

- **Specialist Agents (The Experts):** Five dedicated agents, each implemented as a separate Python module with its own system prompt and execution logic:

  - **Research Planner Agent:** Develops the research strategy and decomposes queries into sub-topics
  - **Paper Searcher Agent:** Executes searches across academic databases (arXiv, Semantic Scholar)
  - **Paper Analyzer Agent:** Performs deep technical analysis of paper content
  - **Research Critique Agent:** Acts as quality assurance, evaluating completeness and accuracy
  - **Report Generator Agent:** Compiles findings into the final, structured markdown report

  The orchestrator exposes each specialist agent as a callable tool using Strands' `@tool(context=True)` decorator, enabling agent-to-agent communication with shared state via `ToolContext`.

- **Deterministic Tools (The Reliable Workers):** These are serverless AWS Lambda functions that perform specific, reliable tasks without reasoning. Agents access these tools through the **AgentCore Gateway** using the **Model Context Protocol (MCP)**. Each tool is a separate Lambda for isolation and independent scaling:

  - `search_arxiv` - Search arXiv database
  - `search_semantic_scholar` - Search Semantic Scholar API
  - `acquire_paper` - Download paper PDFs
  - `extract_content` - Extract text from PDFs
  - `preprocess_text` - Clean and prepare text for analysis

- **State Management:** The orchestrator maintains workflow state using Strands' `ToolContext.agent.state` system, tracking research plans, paper metadata, analyses, critique results, and revision counts across the entire workflow.

- **Serverless Architecture:** The system leverages fully managed AWS services for maximum scalability and cost-efficiency:
  - **AgentCore Runtime** hosts all agents
  - **AgentCore Gateway** provides secure MCP endpoints for tools
  - **Lambda** executes deterministic tools
  - **S3** stores paper cache and reports
  - **Cognito** handles OAuth authentication for gateway access

## **5. Technology Stack**

- **AI & Orchestration:** AWS Strands Agents SDK (v1.0+), AWS Bedrock AgentCore Runtime (agent hosting platform), AWS Bedrock AgentCore Gateway (MCP tool access)
- **Foundation Models:**
  - Anthropic Claude Sonnet 4 (`us.anthropic.claude-sonnet-4-20250514-v1:0`) - Orchestrator Agent
  - Anthropic Claude 3.5 Sonnet (`anthropic.claude-3-5-sonnet-20240620-v1:0`) - Reporter Agent
- **Backend Compute:**
  - AWS Bedrock AgentCore Runtime (hosts all Strands agents)
  - AWS Lambda (Python 3.11) - Deterministic tools only (search_arxiv, search_semantic_scholar, acquire_paper, extract_content, preprocess_text)
- **Data Storage:** Amazon S3 (paper cache, research reports)
- **Authentication:** Amazon Cognito (OAuth authorizer for AgentCore Gateway)
- **Frontend:** Streamlit (Python-based web interface)
- **Monitoring & Observability:** Amazon CloudWatch, AWS X-Ray, Bedrock AgentCore built-in observability

## **6. Project Setup & Local Development**

This section guides you through setting up the project locally for development and testing.

### **6.1. Prerequisites**

- **AWS Account & AWS CLI:** Configured with credentials and sufficient permissions to deploy Bedrock AgentCore, Lambda, S3, and Cognito.
  - Verify: `aws configure` is set up and `aws sts get-caller-identity` returns your user/role.
- **Bedrock Model Access:** Ensure your AWS account has access to:
  - `us.anthropic.claude-sonnet-4-20250514-v1:0` (Orchestrator)
  - `anthropic.claude-3-5-sonnet-20240620-v1:0` (Reporter)
  - Request access in the Bedrock console if needed.
- **Python 3.11+ & Pip:**
  - Verify: `python --version` and `pip --version`
- **bedrock_agentcore_starter_toolkit:**
  - Install: `pip install bedrock-agentcore-starter-toolkit`

### **6.2. AgentCore Gateway Setup**

The AgentCore Gateway provides secure MCP endpoints for Lambda tools. Follow the setup guide in `backend/acgw/README.md`:

1. **Create Gateway with Cognito Authorizer:**

   ```python
   from bedrock_agentcore_starter_toolkit.operations.gateway.client import GatewayClient

   client = GatewayClient(region_name="us-east-1")

   # Create Cognito authorizer
   cognito_response = client.create_oauth_authorizer_with_cognito("ResearchAgentGW")

   # Create MCP Gateway
   gateway = client.create_mcp_gateway(
       authorizer_config=cognito_response["authorizer_config"]
   )
   ```

2. **Register Lambda Tools as Gateway Targets:**

   For each Lambda tool (search_arxiv, search_semantic_scholar, acquire_paper, extract_content, preprocess_text):

   ```python
   lambda_target = client.create_mcp_gateway_target(
       gateway=gateway,
       target_type="lambda"
   )
   ```

3. **Grant Lambda Invoke Permissions:**

   Each Lambda must allow the Gateway's IAM role to invoke it:

   ```bash
   aws lambda add-permission \
     --function-name search_arxiv \
     --statement-id AllowAgentCoreGateway \
     --action lambda:InvokeFunction \
     --principal bedrock.amazonaws.com
   ```

   Repeat for all tool Lambda functions.

### **6.3. AgentCore Runtime Deployment**

Deploy the agent system to AgentCore Runtime:

1. **Navigate to Agent Directory:**

   ```bash
   cd backend/agent
   ```

2. **Deploy to AgentCore Runtime:**

   The `orchestrator.py` file contains the `BedrockAgentCoreApp` definition:

   ```python
   app = BedrockAgentCoreApp()

   @app.entrypoint
   def invoke(payload):
       user_query = payload.get("user_query", "No query provided.")
       orchestrator_agent = Agent(
           model=model,
           system_prompt=ORCHESTRATOR_PROMPT,
           tools=[planner_tool, searcher_tool, analyzer_tool,
                  critique_tool, write_report_section_tool, finalize_report_tool]
       )
       response = orchestrator_agent(user_query)
       return response
   ```

   Deploy using the AgentCore deployment tools or AWS CLI. Note the **Agent Runtime ARN** for frontend configuration.

3. **Configure Gateway Access:**

   Update the agent configuration to use your deployed Gateway's MCP endpoint for tool access.

### **6.4. Lambda Tool Deployment**

Deploy each deterministic tool as a separate Lambda function:

1. **Package Tool Dependencies:**

   ```bash
   cd backend/tools
   pip install -r requirements.txt -t package/
   cd package && zip -r ../tool_layer.zip .
   ```

2. **Deploy Lambda Functions:**

   Deploy each tool (search_arxiv, search_semantic_scholar, acquire_paper, extract_content, preprocess_text) as a separate Lambda function with Python 3.11 runtime.

3. **Configure S3 Access:**

   Ensure Lambda execution roles have permissions to read/write to the S3 cache bucket.

### **6.5. Frontend Setup (Streamlit)**

1. **Navigate to Frontend Directory:**

   ```bash
   cd frontend
   ```

2. **Install Dependencies:**

   ```bash
   pip install -r requirements.txt
   ```

3. **Configure Environment Variables:**

   Create a `.env` file in the frontend directory:

   ```bash
   # For local testing with middleware
   USE_LOCAL_MODE=true
   LOCAL_API_URL=http://localhost:8000

   # For production deployment
   # USE_LOCAL_MODE=false
   # AWS_REGION=us-east-1
   # AGENT_RUNTIME_ARN=arn:aws:bedrock:us-east-1:ACCOUNT:agent-runtime/RUNTIME_ID
   ```

4. **Run Local Development Server:**

   ```bash
   streamlit run app.py
   ```

   The application will be available at `http://localhost:8501`.

### **6.6. Local Testing with Middleware (Optional)**

For local development without deploying to AWS:

1. **Start the FastAPI middleware:**

   ```bash
   cd backend
   python middleware.py
   ```

2. **Configure frontend for local mode:**

   Set `USE_LOCAL_MODE=true` in `frontend/.env`

3. **Run Streamlit:**

   ```bash
   cd frontend
   streamlit run app.py
   ```

## **7. Deployment Steps**

This section provides instructions to deploy the entire Autonomous Research Agent system to your AWS account.

### **7.1. Deploy AgentCore Gateway**

1. **Run Gateway Setup Script:**

   Follow the instructions in `backend/acgw/README.md` to create the Gateway with Cognito authentication.

2. **Register Lambda Tools:**

   Register each tool Lambda as a Gateway target using the `bedrock_agentcore_starter_toolkit`.

3. **Note Gateway Endpoint:**

   Save the Gateway's MCP endpoint URL for agent configuration.

### **7.2. Deploy Lambda Tools**

1. **Package and Deploy Each Tool:**

   Deploy the following Lambda functions:

   - `search_arxiv`
   - `search_semantic_scholar`
   - `acquire_paper`
   - `extract_content`
   - `preprocess_text`

2. **Configure IAM Permissions:**

   Grant Gateway invoke permissions to each Lambda (see Section 6.2).

3. **Create S3 Buckets:**

   Create S3 buckets for paper cache and research reports. Update Lambda environment variables with bucket names.

### **7.3. Deploy AgentCore Runtime**

1. **Deploy Agent Application:**

   Deploy the `orchestrator.py` application to AgentCore Runtime using the Bedrock console or AWS CLI.

2. **Configure Gateway Access:**

   Update the agent configuration with your Gateway's MCP endpoint.

3. **Note Runtime ARN:**

   Save the Agent Runtime ARN for frontend configuration.

### **7.4. Deploy Frontend (Streamlit)**

**Option A: Deploy to AWS (EC2, ECS, or App Runner)**

1. **Build Docker Image:**

   ```bash
   cd frontend
   docker build -t research-agent-frontend .
   ```

2. **Deploy to AWS:**

   Deploy the container to your preferred AWS compute service (EC2, ECS, App Runner).

3. **Configure Environment:**

   Set environment variables:

   ```bash
   USE_LOCAL_MODE=false
   AWS_REGION=us-east-1
   AGENT_RUNTIME_ARN=<your-runtime-arn>
   ```

**Option B: Run Locally**

1. **Configure Production Mode:**

   Update `frontend/.env`:

   ```bash
   USE_LOCAL_MODE=false
   AGENT_RUNTIME_ARN=<your-runtime-arn>
   ```

2. **Run Streamlit:**

   ```bash
   cd frontend
   streamlit run app.py
   ```

## **8. Running a Research Task**

1. **Access Frontend:** Open your deployed frontend application via the CloudFront URL.
2. **Submit Query:** Enter a research query in the input field, e.g., "Summarize recent advances in quantum computing architectures and their error correction mechanisms."
3. **Observe Glass Box:** Watch the real-time timeline display the agents' thoughts, tool calls, and results.
4. **Review Report:** Once complete, the final report will be displayed and available for download.

## **9. Directory Structure**

```
.
├── backend/                       # Backend Python source code
│   ├── agent/                     # Agent implementations (deployed to AgentCore Runtime)
│   │   ├── orchestrator.py        # Main orchestrator with BedrockAgentCoreApp
│   │   ├── planner/               # Planner agent module
│   │   ├── searcher/              # Searcher agent module
│   │   ├── analyzer/              # Analyzer agent module
│   │   ├── critique/              # Critique agent module
│   │   └── reporter/              # Reporter agent module (integrated in orchestrator)
│   ├── acgw/                      # AgentCore Gateway setup
│   │   └── README.md              # Gateway configuration guide
│   ├── tools/                     # Lambda tool implementations
│   │   ├── search_arxiv/          # ArXiv search Lambda
│   │   ├── search_semantic_scholar/ # Semantic Scholar search Lambda
│   │   ├── acquire_paper/         # Paper download Lambda
│   │   ├── extract_content/       # PDF extraction Lambda
│   │   └── preprocess_text/       # Text preprocessing Lambda
│   ├── shared/                    # Shared utilities
│   └── misc/                      # Miscellaneous scripts
├── frontend/                      # Streamlit frontend application
│   ├── app.py                     # Main Streamlit application
│   ├── utils.py                   # Frontend utilities
│   ├── requirements.txt           # Python dependencies
│   ├── Dockerfile                 # Container configuration
│   └── test_*.py                  # Frontend tests
├── docs/                          # Documentation
│   ├── architecture.md            # High-level architecture
│   └── comprehensive.md           # Detailed implementation guide
├── .kiro/                         # Kiro IDE configuration
│   └── specs/                     # Feature specifications
├── .gitignore
├── README.md                      # Project README
├── requirements.txt               # Top-level Python dependencies
└── LICENSE
```

## **10. Live Demo & Video**

- **Deployed Project URL:** [LINK TO YOUR DEPLOYED WEBSITE]
- **Demo Video:** [LINK TO YOUR 3-MINUTE DEMO VIDEO]

## **11. Team**

- **Prathamesh More**
- **Yash Panchal**

---

## **12. Implementation Status & Roadmap**

### ✅ Current Implementation (v1.0)

**Core Features:**

- Multi-agent orchestration with AWS Bedrock AgentCore Runtime
- Five specialist agents (Planner, Searcher, Analyzer, Critique, Reporter)
- Secure tool access via AgentCore Gateway with MCP protocol
- Lambda-based deterministic tools (search, acquire, extract, preprocess)
- S3 caching for processed papers
- Streamlit web interface with phase tracking
- Cognito OAuth authentication
- CloudWatch observability

**Production Services:**

- ✅ AWS Bedrock AgentCore Runtime (agent hosting)
- ✅ AWS Bedrock AgentCore Gateway (MCP tool access)
- ✅ AWS Lambda (5 tool functions)
- ✅ Amazon S3 (paper cache and reports)
- ✅ Amazon Cognito (OAuth authentication)
- ✅ Amazon CloudWatch (logging and monitoring)
- ✅ AWS Systems Manager (configuration storage)
- ✅ Streamlit (frontend interface)

### 🚧 Planned Enhancements (v2.0)

**Real-Time Transparency:**

- WebSocket API for live agent thought streaming
- Interactive visualization of agent decision-making
- SNS event publishing for workflow milestones

**Advanced Features:**

- DynamoDB persistent state for long-running tasks
- Multi-region deployment for global scale
- Batch processing queue for multiple queries
- Cost analytics dashboard
- Customizable report templates
- Interactive mid-execution feedback

**Quality Improvements:**

- Automated fact-checking integration
- Citation verification system
- Multi-language support
- Enhanced error recovery

### ❌ Not Implemented

The following features were considered but **not implemented** in v1.0:

- **API Gateway REST API**: Direct AgentCore invocation used instead
- **DynamoDB State Tables**: In-memory ToolContext sufficient for current use cases
- **SNS/WebSocket Real-Time Updates**: CloudWatch logs and Streamlit polling used instead
- **React Frontend**: Streamlit chosen for rapid development
- **CloudFront CDN**: Single-endpoint deployment sufficient
- **Step Functions**: AgentCore Runtime handles orchestration

These may be reconsidered for future versions based on user feedback and scale requirements.
