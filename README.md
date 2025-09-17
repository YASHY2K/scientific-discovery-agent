# 🔬 The Scientific Discovery Agent

**An autonomous AI research assistant, built on AWS, that automates literature reviews to accelerate the pace of scientific innovation.**

![AWS AI Agent Global Hackathon](https://img.shields.io/badge/Hackathon-AWS%20AI%20Agent%20Global-orange)
![Python](https://img.shields.io/badge/Python-3.11-blue.svg)
![AWS](https://img.shields.io/badge/AWS-Serverless-yellow.svg)
![License](https://img.shields.io/badge/License-MIT-green.svg)

---

### **Table of Contents**

1.  [The Problem: The Information Tsunami](#the-problem-the-information-tsunami)
2.  [Our Solution: An Autonomous Research Partner](#our-solution-an-autonomous-research-partner)
3.  [Key Features](#key-features)
4.  [Live Demo & Video](#live-demo--video)
5.  [How It Works: The Architecture](#how-it-works-the-architecture)
6.  [Technology Stack](#technology-stack)
7.  [Project Setup & Local Development](#project-setup--local-development)
8.  [Directory Structure](#directory-structure)
9.  [Our Team](#our-team)

---

## **The Problem: The Information Tsunami**

Scientific knowledge is expanding at an exponential rate, with millions of research papers published annually. For researchers, conducting a thorough literature review is a foundational step for any new project, but it has become a months-long manual effort. This critical bottleneck slows down the pace of innovation, increases the risk of duplicated work, and makes it difficult to uncover cross-disciplinary insights.

## **Our Solution: An Autonomous Research Partner**

The **Scientific Discovery Agent** is our answer to this challenge. It's an autonomous AI agent built on the AWS generative AI stack that transforms the literature review process. A researcher can provide a high-level research goal in natural language, and our agent will autonomously plan and execute a comprehensive search, analysis, and synthesis of relevant academic literature.

**Example User Prompt:**

> _"I'm researching new CRISPR-Cas9 delivery systems for in-vivo gene editing. Find the latest methodologies, compare their reported efficiencies, and identify any known off-target effect challenges."_

The agent breaks this down, queries multiple public academic databases (like arXiv, PubMed, and Semantic Scholar), analyzes the findings, and generates a cohesive, cited report that outlines the current state of the field and identifies potential research gaps.

## **Key Features**

- **Autonomous Multi-Source Querying:** Intelligently queries multiple academic APIs in parallel to build a comprehensive knowledge base.
- **Advanced Synthesis & Gap Analysis:** Goes beyond summarization to identify themes, compare methodologies, and highlight gaps in existing research.
- **Verifiable & Cited Results:** Every key finding in the final report is meticulously cited and linked to the source paper for trust and verification.
- **Conversational & Iterative:** Capable of asking clarifying questions to refine the research goal, ensuring highly relevant results.
- **Serverless & Scalable:** Built on a 100% serverless AWS architecture for cost-efficiency, scalability, and resilience.

## **Live Demo & Video**

- **Deployed Project URL:** [**LINK TO YOUR DEPLOYED WEBSITE**]
- **Demo Video:** [**LINK TO YOUR 3-MINUTE DEMO VIDEO**]

## **How It Works: The Architecture**

Our solution is an event-driven, serverless application that leverages the power of Amazon Bedrock for orchestration and reasoning.

![Architecture Diagram](assets/architecture.png)
_(You would place your architecture diagram image in an `assets` folder)_

**The workflow is as follows:**

1.  **User Interaction:** A researcher submits a prompt through our React-based frontend, hosted on **Amazon S3** and distributed via **Amazon CloudFront**.
2.  **API Layer:** The request securely hits our backend via **Amazon API Gateway**, which acts as the front door.
3.  **Agent Orchestration:** API Gateway invokes our core agent, which is powered by **Amazon Bedrock AgentCore**.
4.  **Reasoning and Planning:** The Bedrock Agent uses **Amazon Bedrock (Claude 3 Sonnet)** as its foundation model. The LLM interprets the user's goal, breaks it down into a multi-step plan, and decides which tools to use.
5.  **Tool Execution:** The agent's "tools" are serverless **AWS Lambda** functions written in Python. Each function is responsible for a specific task:
    - `query_arxiv`: Connects to the arXiv API.
    - `query_pubmed`: Connects to the PubMed API.
    - `synthesize_findings`: A function to consolidate and analyze results.
6.  **Synthesis and Response:** The results from the Lambda tools are passed back to the agent. The Claude 3 model then performs the final synthesis, generating a structured, cited report which is sent back to the user via the API Gateway.

## **Technology Stack**

- **AI & Orchestration:** Amazon Bedrock, Amazon Bedrock AgentCore
- **Foundation Model:** Anthropic Claude 3 Sonnet
- **Backend:** AWS Lambda (Python), Amazon API Gateway
- **Frontend:** React, Vite, Tailwind CSS
- **Hosting & Storage:** Amazon S3, Amazon CloudFront
- **Infrastructure as Code:** AWS SAM (Serverless Application Model)

## **Project Setup & Local Development**

These instructions will get you a copy of the project up and running on your local machine for development and testing purposes.

### **Prerequisites**

- AWS Account & AWS CLI configured with credentials
- AWS SAM CLI
- Python 3.11+ and Pip
- Node.js 18+ and npm

### **Backend Setup**

### **Frontend Setup**

The frontend is a standard React application.

```bash
# Navigate to the frontend directory
cd frontend/

# Install dependencies
npm install

# Create a .env.local file and add your API Gateway URL
echo "VITE_API_BASE_URL=YOUR_API_GATEWAY_URL" > .env.local

# Run the local development server
npm run dev
```

The application will be available at `http://localhost:5173`.

## **Directory Structure**

```
.
├── backend/
│   ├── .aws-sam/              # SAM build artifacts
│   ├── src/
│   │   ├── lambda_arxiv/
│   │   │   └── app.py         # Lambda function for arXiv API
│   │   ├── lambda_pubmed/
│   │   │   └── app.py         # Lambda function for PubMed API
│   │   └── ...
│   ├── template.yaml          # AWS SAM IaC template
│   └── requirements.txt       # Python dependencies
│
├── frontend/
│   ├── public/
│   │   └── ...
│   └── src/
│       ├── components/
│       ├── App.jsx
│       └── main.jsx
│
├── assets/
│   └── architecture.png       # Project architecture diagram
│
├── .gitignore
└── README.md
```

## **Our Team**

- **[Prathamesh More](https://github.com/Spidey13)**
- **[Yash Panchal](https://github.com/YASHY2K)**
