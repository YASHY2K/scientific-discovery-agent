# Multi-Agent Research System: Architecture & Implementation

> **Last Updated:** January 21, 2025  
> **Implementation Status:** Production deployment on AWS Bedrock AgentCore Runtime  
> **Document Version:** 2.0

> **Note:** This document describes the agent architecture and implementation details. For a complete system overview including deployment and infrastructure, see [docs/architecture.md](../../docs/architecture.md) and [docs/comprehensive.md](../../docs/comprehensive.md).

## Executive Summary

This document defines the architecture for an autonomous AI research agent system built for the AWS AI Agent Global Hackathon. The system uses a "Smart Specialists" design pattern where an orchestrator coordinates five intelligent specialist agents, each with distinct responsibilities. The system is built on **AWS Strands Agents SDK** and uses **Amazon Bedrock** for LLM reasoning.

**Deployment Model:** All agents are hosted and executed within **AWS Bedrock AgentCore Runtime** as a single application deployed using the `BedrockAgentCoreApp` framework. Agents access deterministic Lambda tools through the **AWS Bedrock AgentCore Gateway** using the Model Context Protocol (MCP).

## Core Design Principles

### 1. Agent vs Tool Distinction

**Agents (Non-Deterministic, Reasoning Entities):**

- Use LLMs to make decisions
- Have autonomy within their domain
- Can adapt strategies based on context
- Example: SearcherAgent decides which queries to try and when to stop

**Tools (Deterministic Functions):**

- Pure functions with no reasoning
- Same input always produces same output
- No decision-making capability
- Implemented as AWS Lambda functions
- Accessed by agents through the **AWS Bedrock AgentCore Gateway** using MCP (Model Context Protocol)
- Example: `search_arxiv` Lambda function always returns same papers for same query

**Critical Architecture Rule:** Specialist agents are exposed as "tools" to the orchestrator via the `@tool` decorator pattern in the Strands SDK, but internally they remain full agents with reasoning capabilities. Deterministic Lambda tools are accessed through the AgentCore Gateway for secure, authenticated invocation.

### 2. Separation of Concerns

Each agent has a clearly defined domain of expertise:

- **Planner:** Strategic research design
- **Searcher:** Literature discovery tactics
- **Analyzer:** Technical synthesis
- **Critique:** Quality assurance
- **Reporter:** Communication and presentation
- **Orchestrator:** Workflow management

No agent should reason about another agent's domain.

## System Components

### Agent 1: Research Orchestrator

**Role:** Project manager and workflow coordinator

**Responsibilities:**

- Receive and interpret user research queries
- Coordinate specialist agents through `@tool` decorator pattern
- Manage iteration loops based on critique feedback
- Track progress and maintain session state using ToolContext
- Send real-time updates to frontend (Glass Box)

**Tools Available:**

- `planner_tool` (PlannerAgent via `@tool` decorator)
- `searcher_tool` (SearcherAgent via `@tool` decorator)
- `analyzer_tool` (AnalyzerAgent via `@tool` decorator)
- `critique_tool` (CritiqueAgent via `@tool` decorator)
- `reporter_tool` (ReporterAgent via `@tool` decorator)
- `notify_user` (deterministic function)

**System Prompt Key Points:**

```
You are the Chief Research Orchestrator managing a team of specialist agents.

Typical workflow:
1. For complex queries: Engage planner first
2. For simple queries: Go directly to searcher
3. Use searcher to find papers for each sub-topic
4. Have analyzer process papers
5. Get critique for quality validation
6. If critique returns REVISE: loop back to searcher with new queries
7. If critique returns APPROVED: generate final report
8. Stop after 3 revision cycles to prevent infinite loops

Always notify user of progress at each major step.
```

**Decision Logic:**

- Determines if query needs planning or can go straight to search
- Decides when to move between workflow phases
- Handles iteration termination (max 3 cycles or exhausted sources)

---

### Agent 2: Planner Agent

**Role:** Research strategist and decomposition specialist

**Responsibilities:**

- Analyze complex research queries
- Decompose into logical sub-topics
- Provide starting keywords for each sub-topic (suggestions, not commands)
- Define success criteria per sub-topic
- Suggest research approach (comparative, survey, focused deep-dive)

**Tools Available:** None (pure reasoning agent)

**Input Format:**

```json
{
  "user_query": "Impact of transformer models on time-series forecasting"
}
```

**Output Format:**

```json
{
  "research_approach": "comparative_analysis",
  "sub_topics": [
    {
      "id": "baseline_methods",
      "description": "Traditional time-series forecasting (ARIMA, LSTM)",
      "priority": 1,
      "success_criteria": "5-8 papers on pre-transformer methods",
      "suggested_keywords": [
        "ARIMA forecasting",
        "LSTM time series",
        "traditional forecasting methods"
      ]
    },
    {
      "id": "transformer_architectures",
      "description": "How transformers adapted for time-series",
      "priority": 2,
      "success_criteria": "10+ papers on transformer architectures",
      "suggested_keywords": [
        "transformer time series",
        "temporal fusion transformer",
        "attention forecasting"
      ]
    },
    {
      "id": "empirical_comparison",
      "description": "Benchmark studies comparing approaches",
      "priority": 3,
      "success_criteria": "Papers with quantitative results",
      "suggested_keywords": [
        "transformer vs LSTM",
        "forecasting benchmark",
        "time series comparison"
      ]
    }
  ]
}
```

**System Prompt Key Points:**

```
You are a Research Planning Specialist.

When to create sub-topics:
- Query asks about multiple aspects (e.g., "methods AND ethics")
- Query requires comparing approaches
- Topic is broad and needs scoping

When NOT to create sub-topics:
- Simple, focused queries ("latest CRISPR papers")
- Query already specific

Your suggested_keywords are STARTING POINTS only. The SearcherAgent
has autonomy to deviate if those keywords prove unproductive.

Always provide clear success criteria so other agents know when enough work is done.
```

**Key Behavior:**

- Does NOT specify exact search queries (that's SearcherAgent's job)
- Does NOT know about data sources (arXiv vs Semantic Scholar)
- Focuses on WHAT to research, not HOW to search

---

### Agent 3: Searcher Agent

**Role:** Literature discovery and curation specialist

**Responsibilities:**

- Execute searches across academic databases
- Iteratively refine queries based on result quality
- Filter and rank papers by relevance
- Identify seminal papers via citation analysis
- Acquire paper PDFs and trigger text extraction
- Decide when sufficient papers are found

**Tools Available (via AgentCore Gateway):**

- `search_arxiv` - Lambda function for arXiv API queries
- `search_semantic_scholar` - Lambda function for Semantic Scholar API queries
- `acquire_paper` - Lambda function to download and retrieve paper content
- `extract_content` - Lambda function to extract text from PDFs
- `preprocess_text` - Lambda function to clean and preprocess extracted text

> **Note:** These Lambda tools are accessed through the AWS Bedrock AgentCore Gateway using MCP protocol. See [backend/acgw/README.md](../acgw/README.md) for gateway setup and tool registration details.

**Input Format:**

```json
{
  "sub_topic": "transformer architectures for time-series",
  "suggested_keywords": ["transformer time series", "temporal fusion"],
  "success_criteria": "10+ papers on transformer architectures"
}
```

**Output Format:**

```json
{
  "sub_topic_id": "transformer_architectures",
  "papers_found": 12,
  "papers": [
    {
      "id": "arxiv:2023.12345",
      "title": "Temporal Fusion Transformers for Interpretable Multi-horizon Time Series Forecasting",
      "authors": ["Author A", "Author B"],
      "abstract": "...",
      "source": "arxiv",
      "relevance_score": 0.94,
      "citation_count": 523,
      "s3_text_location": "s3://bucket/papers/arxiv-2023-12345.txt",
      "pdf_url": "https://arxiv.org/pdf/2023.12345"
    }
  ],
  "search_strategy_used": "Started with 'transformer time series' (120 results), refined to 'temporal fusion transformer' (45 results), ranked by citations and relevance, selected top 12",
  "notable_papers_excluded": "Excluded 8 papers on stock prediction as out of scope"
}
```

**System Prompt Key Points:**

```
You are a Scientific Literature Search Specialist.

Your autonomy:
- You receive suggested_keywords but treat them as starting points
- If initial searches yield poor results, try different terms
- If you find 200 papers, you need to filter them down
- If you find 3 papers, you need to broaden the search

Your search strategy:
1. Start with most specific keyword first
2. If too many results (>50): add narrowing terms
3. If too few results (<5): remove terms or try synonyms
4. Use search_arxiv and search_semantic_scholar Lambda tools via gateway
5. Rank and filter results based on relevance
6. Call acquire_paper Lambda tool for each selected paper

Stop searching when:
- Success criteria met (e.g., "10+ papers")
- AND high-confidence papers found (relevance_score >0.8)
- OR 5 search iterations completed without improvement

Always explain your search strategy in the output.
```

**Iterative Search Example:**

```
Iteration 1: search_arxiv("transformer time series") → 120 papers (too many)
Iteration 2: search_arxiv("transformer time series forecasting") → 45 papers (better)
Iteration 3: Rank papers by relevance and citation count
Iteration 4: Identify high-impact papers from top 20 results
Iteration 5: Select top 12 papers, call acquire_paper for each
```

---

### Agent 4: Analyzer Agent

**Role:** Technical synthesis and insight extraction specialist

**Responsibilities:**

- Extract key methodologies from papers
- Identify novel contributions and innovations
- Compare and contrast approaches across papers
- Synthesize findings into coherent narrative
- Identify research gaps and unanswered questions
- Request clarification searches for unfamiliar terms

**Tools Available (via AgentCore Gateway):**

- `extract_content` - Lambda function to retrieve and extract text from papers stored in S3
- `preprocess_text` - Lambda function to clean and preprocess extracted text for analysis
- Additional analysis tools as needed for paper processing

> **Note:** The Analyzer primarily works with paper content retrieved and cached in S3 by the Searcher Agent's tool invocations.

**Input Format:**

```json
{
  "sub_topic": "transformer architectures",
  "papers": [
    {
      "id": "arxiv:2023.12345",
      "s3_text_location": "s3://bucket/papers/arxiv-2023-12345.txt",
      "title": "...",
      "abstract": "..."
    }
  ]
}
```

**Output Format:**

```json
{
  "sub_topic_id": "transformer_architectures",
  "analyzed_papers": [
    {
      "paper_id": "arxiv:2023.12345",
      "key_findings": [
        "Introduces Temporal Fusion Transformer (TFT) architecture",
        "Achieves 15% improvement over LSTM on M4 benchmark",
        "Uses variable selection network for interpretability"
      ],
      "methodology": "Multi-horizon forecasting with encoder-decoder architecture, attention mechanisms for temporal relationships",
      "quantitative_results": {
        "benchmark": "M4 Competition",
        "metric": "SMAPE",
        "score": 12.3,
        "comparison": "LSTM: 14.1, ARIMA: 18.7"
      },
      "limitations": [
        "Requires large training datasets (10k+ samples)",
        "Computational cost 3x higher than LSTM"
      ],
      "novelty": "First to combine variable selection with multi-head attention for time-series"
    }
  ],
  "cross_paper_synthesis": {
    "common_themes": [
      "Attention mechanisms enable capturing long-range dependencies",
      "Transformers require more data than traditional methods",
      "Interpretability remains challenge despite attention weights"
    ],
    "contradictions": [
      {
        "issue": "Data efficiency",
        "paper_a": "TFT claims works with 1k samples",
        "paper_b": "Informer requires 10k+ samples",
        "analysis": "Different problem complexity and sequence lengths"
      }
    ],
    "methodological_trends": "Shift from pure attention to hybrid architectures combining CNN/LSTM with transformers",
    "research_gaps": [
      "Limited studies on real-time forecasting latency",
      "No papers address deployment costs in production",
      "Missing comparison with recent foundation models"
    ]
  },
  "technical_summary": "Transformer architectures have revolutionized time-series forecasting by enabling...",
  "clarification_searches_needed": [
    {
      "term": "causal convolution",
      "context": "Multiple papers mention this but assume reader knowledge",
      "importance": "medium"
    }
  ]
}
```

**System Prompt Key Points:**

```
You are a Scientific Paper Analysis Expert.

Focus on extracting:
- WHAT was done (methodology)
- WHY it matters (novelty)
- HOW WELL it worked (quantitative results)
- WHAT'S MISSING (limitations, gaps)

Cross-paper analysis:
- Identify common themes across papers
- Note contradictions and try to explain them
- Synthesize insights that emerge from multiple papers
- Highlight what questions remain unanswered

If you encounter unfamiliar technical terms that are:
- Critical to understanding the work
- Not explained in the papers
- Mentioned in multiple papers
→ Use request_clarification_search tool

Format all quantitative results consistently for easy comparison.
```

**Handling Unfamiliar Terms:**

```
Analyzer reads paper mentioning "optogenetic rescue"
→ Realizes term is critical but not explained
→ Calls request_clarification_search("optogenetic rescue", "mentioned in CRISPR therapy papers")
→ Tool invokes SearcherAgent for mini-search on that term
→ SearcherAgent finds 3 explanatory papers
→ Analyzer incorporates that knowledge into analysis
```

---

### Agent 5: Critique Agent

**Role:** Quality assurance and validation specialist

**Responsibilities:**

- Evaluate completeness of research coverage
- Identify gaps in analysis or missing perspectives
- Verify accuracy of technical summaries
- Assess logical coherence of synthesis
- Provide specific, actionable feedback
- Decide whether to approve or request revisions

**Tools Available:** None (pure reasoning agent)

**Input Format:**

```json
{
  "original_query": "Impact of transformer models on time-series forecasting",
  "plan": {
    /* PlannerAgent output */
  },
  "analyses": [
    {
      /* AnalyzerAgent output for sub_topic_1 */
    },
    {
      /* AnalyzerAgent output for sub_topic_2 */
    }
  ]
}
```

**Output Format:**

```json
{
  "verdict": "REVISE",
  "overall_quality_score": 7,
  "strengths": [
    "Thorough coverage of transformer architectures",
    "Good quantitative comparisons with benchmarks",
    "Clear identification of methodological trends"
  ],
  "critical_issues": [
    {
      "severity": "high",
      "issue": "Missing discussion of computational costs",
      "impact": "Cannot assess practical viability for real-world deployment",
      "required_action": "Add analysis of training time, inference latency, and resource requirements"
    },
    {
      "severity": "medium",
      "issue": "Limited coverage of recent foundation models",
      "impact": "Analysis may be outdated given rapid field development",
      "required_action": "Search for papers from 2024 on foundation models for time-series"
    }
  ],
  "coverage_gaps": [
    {
      "missing_perspective": "Industry adoption and production use cases",
      "why_important": "Academic benchmarks don't reflect real-world constraints",
      "search_suggestion": "transformer time series production deployment"
    }
  ],
  "required_revisions": [
    {
      "action": "search_more_papers",
      "query": "transformer time series computational cost efficiency",
      "reason": "Critical gap in cost analysis",
      "estimated_papers_needed": "5-8"
    },
    {
      "action": "re_analyze",
      "target": "transformer_architectures",
      "reason": "Need to extract computational metrics from existing papers",
      "additional_focus": "Training time, inference latency, parameter count"
    }
  ],
  "approval_conditions": [
    "Computational cost analysis added",
    "At least 3 papers from 2024 included"
  ]
}
```

**Verdict Options:**

- `APPROVED` - Research is complete, proceed to report generation
- `REVISE` - Specific issues need addressing, provide required_revisions
- `INSUFFICIENT` - Fundamental problems, may need to restart with new plan

**System Prompt Key Points:**

```
You are a Research Quality Assurance Specialist.

Evaluation criteria:
1. Completeness: Are all aspects of the query addressed?
2. Accuracy: Are technical details correctly represented?
3. Balance: Are multiple perspectives considered?
4. Depth: Is analysis superficial or substantive?
5. Currency: Are recent developments included?

Be specific in feedback:
- BAD: "Need more papers"
- GOOD: "Missing papers on production deployment. Search 'transformer time series production' to find 5-8 industry case studies"

Approval standards:
- All sub-topics from plan adequately covered
- No major contradictions or errors
- Research gaps identified
- Quantitative evidence provided

You can require up to 2 revision cycles. After that, accept what's available
to prevent infinite loops.
```

**Iteration Triggers:**

```
Common revision scenarios:

1. Missing perspective:
   → required_action: search_more_papers with specific query

2. Insufficient depth:
   → required_action: re_analyze with additional focus areas

3. Outdated information:
   → required_action: search_more_papers filtered by date

4. Unfamiliar term discovered:
   → AnalyzerAgent already handled via request_clarification_search

5. Contradictory results:
   → required_action: search_more_papers to resolve contradiction
```

---

### Agent 6: Reporter Agent

**Role:** Communication and presentation specialist

**Responsibilities:**

- Compile research findings into comprehensive report
- Structure content with clear sections and flow
- Generate executive summary and key findings
- Add proper citations and references
- Create visualizations and summary tables
- Format for readability (markdown)

**Tools Available:**

- `citation_formatter(papers)` - generate bibliography
- `create_comparison_table(data)` - format quantitative results
- `generate_chart(data, type)` - create visualizations

**Input Format:**

```json
{
  "original_query": "...",
  "plan": {
    /* PlannerAgent output */
  },
  "analyses": [
    /* All AnalyzerAgent outputs */
  ],
  "critique_feedback": {
    /* Final CritiqueAgent output with verdict=APPROVED */
  }
}
```

**Output Format:**

```markdown
# Research Report: Impact of Transformer Models on Time-Series Forecasting

## Executive Summary

[3-4 paragraph summary of key findings, suitable for non-technical readers]

## Introduction

### Research Question

[Restate original query in formal terms]

### Methodology

[Explain research approach: papers analyzed, databases searched, selection criteria]

## Background: Traditional Time-Series Methods

[Analysis from baseline_methods sub-topic]

### Key Papers

- Author et al. (2020). "ARIMA approaches..." [Citation]
- ...

### Summary of Findings

[Synthesized insights]

## Transformer Architectures for Time-Series

[Analysis from transformer_architectures sub-topic]

### Architectural Innovations

[Key methodological advances]

### Performance Comparison

| Architecture | Benchmark | Metric | Score | Improvement vs LSTM |
| ------------ | --------- | ------ | ----- | ------------------- |
| TFT          | M4        | SMAPE  | 12.3  | 15%                 |
| Informer     | ETTh1     | MSE    | 0.098 | 22%                 |

[Generated via create_comparison_table tool]

## Empirical Evidence and Benchmarks

[Analysis from empirical_comparison sub-topic]

## Cross-Study Synthesis

### Common Themes

[Patterns identified across all papers]

### Contradictions and Reconciliation

[Conflicting results and explanations]

### Research Gaps Identified

[Unanswered questions from critique]

## Conclusions

### Key Takeaways

[Bullet point summary]

### Practical Implications

[What this means for practitioners]

### Future Research Directions

[Suggested next steps based on gaps]

## References

[Full bibliography in consistent format]

## Appendix: Methodology Details

### Search Queries Used

[Transparency about how papers were found]

### Selection Criteria

[Why certain papers included/excluded]

### Papers Reviewed

- [Count] papers from arXiv
- [Count] papers from Semantic Scholar
- Date range: [Start] to [End]
```

**System Prompt Key Points:**

```
You are a Technical Report Writer.

Report structure:
- Executive Summary: For general audience, focus on impact
- Introduction: Set context and explain methodology
- Body Sections: One per sub-topic from plan
- Cross-Study Synthesis: Higher-level insights
- Conclusions: Actionable takeaways
- References: Consistent citation format

Style guidelines:
- Clear, professional academic tone
- Use active voice where possible
- Define technical terms on first use
- Support claims with citations
- Use tables/charts to summarize quantitative data

The report should stand alone - reader shouldn't need to see intermediate
outputs from other agents.
```

---

## Complete Workflow Example

### User Query

"What are the ethical considerations in using CRISPR for human embryo editing?"

### Step 1: Initial Assessment

```
Orchestrator receives query
→ Determines this is complex (involves ethics AND science)
→ Invokes PlannerAgent
```

### Step 2: Planning

```
PlannerAgent output:
{
  "sub_topics": [
    {
      "id": "technical_capabilities",
      "description": "Current state of CRISPR precision and safety",
      "suggested_keywords": ["CRISPR off-target", "embryo editing accuracy"]
    },
    {
      "id": "ethical_frameworks",
      "description": "Ethical arguments for and against",
      "suggested_keywords": ["CRISPR ethics", "germline editing morality", "bioethics"]
    },
    {
      "id": "regulatory_landscape",
      "description": "Current policies and governance",
      "suggested_keywords": ["CRISPR regulation", "gene editing policy"]
    }
  ]
}
```

### Step 3: Literature Search (Technical Capabilities)

```
Orchestrator → SearcherAgent (sub_topic: technical_capabilities)

SearcherAgent execution:
1. search_arxiv("CRISPR off-target") → 80 papers
2. Filter by date (2023-2025) → 30 papers
3. Rank by relevance → Top 15
4. Identify 3 seminal papers not in results
5. Final selection: 18 papers
6. acquire_paper for all 18 (via AgentCore Gateway)
7. Return paper list to Orchestrator
```

### Step 4: Analysis (Technical Capabilities)

```
Orchestrator → AnalyzerAgent (papers: 18)

AnalyzerAgent execution:
1. Read all 18 papers from S3
2. Extract key findings (off-target rates, safety data)
3. Encounters unfamiliar term: "base editing"
4. request_clarification_search("base editing") → mini-search → 3 papers
5. Incorporate new understanding
6. Generate cross-paper synthesis
7. Return analysis to Orchestrator

Output includes:
- Off-target rates: 0.1%-5% depending on method
- Safety concerns identified: mosaicism, off-target mutations
- Research gaps: long-term effects unknown
```

### Step 5-6: Repeat for Other Sub-topics

```
Orchestrator executes same flow for:
- ethical_frameworks (finds 12 papers)
- regulatory_landscape (finds 10 papers)
```

### Step 7: Quality Check

```
Orchestrator → CritiqueAgent (all 3 analyses)

CritiqueAgent output:
{
  "verdict": "REVISE",
  "critical_issues": [
    {
      "issue": "Missing recent clinical trial data",
      "required_action": "search_more_papers",
      "query": "CRISPR embryo clinical trial 2024"
    }
  ]
}
```

### Step 8: Revision Iteration

```
Orchestrator → SearcherAgent (new query from critique)
SearcherAgent → Finds 5 more papers
Orchestrator → AnalyzerAgent (5 new papers)
AnalyzerAgent → Updates technical_capabilities analysis
Orchestrator → CritiqueAgent (updated analysis)

CritiqueAgent output:
{
  "verdict": "APPROVED"
}
```

### Step 9: Report Generation

```
Orchestrator → ReporterAgent (all approved analyses)

ReporterAgent generates:
- Executive summary
- Technical findings section
- Ethical considerations section
- Regulatory landscape section
- Cross-cutting synthesis
- Conclusions with recommendations
- Bibliography (40 papers total)

Returns final markdown report
```

### Step 10: Delivery

```
Orchestrator:
- Saves report to S3
- Updates DynamoDB (status: completed)
- Sends WebSocket notification to user
- User receives report link
```

---

## Handling Edge Cases

### Case 1: Search Returns No Papers

```
SearcherAgent tries: "very_specific_niche_topic"
→ 0 results

SearcherAgent thinks: "No results, try broader term"
→ Tries variations, still 0 results after 3 attempts

SearcherAgent returns:
{
  "papers_found": 0,
  "explanation": "No papers found matching criteria. Topic may be too new or niche.",
  "search_attempts": ["attempt1", "attempt2", "attempt3"]
}

Orchestrator receives empty results
→ Notifies user: "Insufficient papers found for this sub-topic"
→ Continues with other sub-topics
```

### Case 2: Analyzer Encounters Paywalled Papers

```
acquire_paper Lambda fails for 3 papers (paywall)

SearcherAgent marks those papers:
{
  "paper_id": "doi:...",
  "status": "unavailable",
  "reason": "paywall"
}

AnalyzerAgent works with available papers only
CritiqueAgent notes in feedback: "Some papers unavailable, may affect completeness"
```

### Case 3: Infinite Iteration Loop Prevention

```
Orchestrator tracks revision count:

Iteration 1: Critique says REVISE → continue
Iteration 2: Critique says REVISE → continue
Iteration 3: Critique says REVISE → STOP

Orchestrator overrides:
"Maximum iterations reached. Proceeding to report with current findings."

CritiqueAgent's concerns noted in final report appendix.
```

### Case 4: Clarification Search During Analysis

```
AnalyzerAgent reading paper mentions "optogenetic rescue"
→ Term is unfamiliar but seems important

AnalyzerAgent calls:
request_clarification_search("optogenetic rescue", "CRISPR therapy context")

This tool invokes SearcherAgent as sub-task:
SearcherAgent mini-search → finds 3 explanatory papers
→ acquire_paper → extract key sections (via gateway)
→ Return definition and context to AnalyzerAgent

AnalyzerAgent incorporates understanding:
"Optogenetic rescue refers to [definition]. This is significant because..."
```

---

## Real-Time Transparency (Glass Box)

Every agent action triggers a notification:

```javascript
// Frontend receives WebSocket messages

{
  "timestamp": "2025-09-30T14:23:15Z",
  "agent": "searcher_agent",
  "action": "thinking",
  "thought": "Initial search for 'CRISPR off-target' returned 80 papers. Too broad - will refine with date filter.",
  "data": null
}

{
  "timestamp": "2025-09-30T14:23:18Z",
  "agent": "searcher_agent",
  "action": "tool_call",
  "thought": "Invoking search_arxiv via AgentCore Gateway",
  "data": {
    "tool_name": "search_arxiv",
    "input": {"query": "CRISPR off-target", "date_filter": "2023-2025"}
  }
}

{
  "timestamp": "2025-09-30T14:23:22Z",
  "agent": "searcher_agent",
  "action": "tool_result",
  "thought": "Received 30 papers, will now rank by relevance",
  "data": {"papers_count": 30}
}
```

Users see agents "thinking" in real-time, building trust through transparency.

---

## Implementation Notes

### Agent System Prompts

Each agent needs a carefully crafted system prompt that:

1. Defines its role and responsibilities
2. Specifies decision-making criteria
3. Describes output format
4. Explains when to use tools
5. Sets boundaries (what NOT to do)

### Tool Implementation

All deterministic tools must:

1. Use caching to ensure consistency (same input → same output)
2. Handle errors gracefully
3. Return structured data
4. Log all invocations for debugging

### Orchestrator State Management

Orchestrator must track:

- Current workflow phase
- Which sub-topics completed
- Iteration count per sub-topic
- Cumulative paper count
- Critique feedback history

### Termination Conditions

Clear rules for when to stop:

- Critique approves (normal case)
- Max iterations reached (3 cycles)
- No papers found after multiple search attempts
- User cancels request
- Lambda timeout approaching (graceful degradation)

---

## Technology Stack

- **Agent Hosting:** AWS Bedrock AgentCore Runtime (hosts all Strands agents)
- **Agent Framework:** AWS Strands Agents SDK v1.0+
- **Tool Gateway:** AWS Bedrock AgentCore Gateway (MCP protocol for Lambda tool access)
- **LLM:** Amazon Bedrock (Claude Sonnet 4 for orchestration, Claude 3.5 Sonnet for reporting)
- **Tool Compute:** AWS Lambda (deterministic tools: search_arxiv, search_semantic_scholar, acquire_paper, extract_content, preprocess_text)
- **Storage:** Amazon S3 (paper caching and report storage)
- **Authentication:** Amazon Cognito (OAuth authorizer for gateway)
- **Frontend:** Streamlit (interactive chat interface with real-time agent status)
- **Observability:** Strands SDK built-in observability, CloudWatch + X-Ray

> **For detailed deployment instructions**, see [docs/architecture.md](../../docs/architecture.md) and [backend/acgw/README.md](../acgw/README.md).

---

## Success Metrics

The system should demonstrate:

1. **Autonomy:** Agents make decisions without human intervention
2. **Collaboration:** Clear handoffs between agents via `@tool` decorator pattern
3. **Quality:** Critique-driven iteration improves output
4. **Transparency:** Glass Box shows all agent reasoning through Streamlit interface
5. **Scalability:** Handles multiple concurrent research tasks via AgentCore Runtime

This architecture positions the submission strongly for:

- Best Strands SDK Implementation ($3k)
- Best Amazon Bedrock AgentCore Implementation ($3k)

---

## Implementation Status

### ✅ Implemented Agent Features

- **Orchestrator Agent**: Workflow coordination with Claude Sonnet 4
- **Planner Agent**: Research strategy and sub-topic decomposition
- **Searcher Agent**: Literature discovery with MCP tool access
- **Analyzer Agent**: Deep technical synthesis and cross-paper analysis
- **Critique Agent**: Quality assurance with revision feedback
- **Reporter Agent**: Modular report generation with section-by-section approach
- **State Management**: ToolContext-based workflow state across all agents
- **Agent-to-Agent Communication**: @tool decorator pattern for specialist invocation
- **Tool Integration**: MCP client for secure Lambda tool access via gateway

### 🚧 Future Agent Enhancements

- **Clarification Search**: Automated mini-searches for unfamiliar technical terms
- **Parallel Analysis**: Concurrent paper analysis for improved performance
- **Adaptive Planning**: Dynamic plan adjustment based on search results
- **Citation Validation**: Automated verification of paper citations
- **Multi-Language Analysis**: Support for non-English papers
- **Domain-Specific Agents**: Specialized agents for medical, legal, or technical research
- **Interactive Critique**: User feedback integration during quality review
- **Learning from History**: Agent improvement based on past research sessions

### ❌ Deprecated Patterns

The following patterns were considered but **not implemented**:

- **Lambda-Based Agents**: All agents run in AgentCore Runtime instead
- **Direct Tool Invocation**: All tools accessed via AgentCore Gateway with MCP
- **External State Storage**: In-memory ToolContext sufficient for current workflows
- **Synchronous WebSocket Updates**: CloudWatch logging used instead

## Related Documentation

- **[docs/architecture.md](../../docs/architecture.md)** - Complete system architecture and AWS service integration
- **[docs/comprehensive.md](../../docs/comprehensive.md)** - Detailed implementation guide with code examples
- **[backend/acgw/README.md](../acgw/README.md)** - AgentCore Gateway setup and Lambda tool registration
- **[README.md](../../README.md)** - Project overview and quick start guide
