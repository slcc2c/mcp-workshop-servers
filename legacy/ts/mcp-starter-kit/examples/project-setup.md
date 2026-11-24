# MCP Project Setup Examples

## Example 1: Web Application Project

```bash
# Initial setup
export MCP_PROJECT=my-webapp
export MCP_SESSION=$(date +%Y-%m-%d)

# Store project architecture decisions
./scripts/memory-helper.sh store "Frontend: React 18 with TypeScript" architecture
./scripts/memory-helper.sh store "Backend: Node.js with Express" architecture
./scripts/memory-helper.sh store "Database: PostgreSQL with Prisma ORM" architecture
./scripts/memory-helper.sh store "Auth: JWT with refresh tokens" security

# In Claude, you can now ask:
# "What's the tech stack for project:my-webapp?"
# "Show all architecture decisions for project:my-webapp"
```

## Example 2: Microservices Project

```bash
export MCP_PROJECT=microservices-platform
export MCP_SESSION=$(date +%Y-%m-%d)

# Store service information
./scripts/memory-helper.sh context "Building e-commerce microservices"
./scripts/memory-helper.sh store "Auth Service: Port 3001, handles JWT" service
./scripts/memory-helper.sh store "Product Service: Port 3002, MongoDB" service
./scripts/memory-helper.sh store "Order Service: Port 3003, PostgreSQL" service
./scripts/memory-helper.sh store "API Gateway: Port 3000, Kong" service

# Store shared conventions
./scripts/memory-helper.sh store "All services use gRPC for internal communication" architecture
./scripts/memory-helper.sh store "Kubernetes for orchestration" infrastructure
```

## Example 3: Data Science Project

```bash
export MCP_PROJECT=ml-pipeline
export MCP_SESSION=$(date +%Y-%m-%d)

# Store project specifics
./scripts/memory-helper.sh store "Dataset: Customer behavior data, 2M records" data
./scripts/memory-helper.sh store "Model: XGBoost for churn prediction" model
./scripts/memory-helper.sh store "Framework: Python 3.10, scikit-learn, pandas" tech
./scripts/memory-helper.sh store "GPU: Using CUDA 12.0 on RTX 4090" infrastructure

# Store experiment results
./scripts/memory-helper.sh store "Baseline model: 0.76 AUC" experiment
./scripts/memory-helper.sh store "With feature engineering: 0.83 AUC" experiment
```

## Example 4: Mobile App Project

```bash
export MCP_PROJECT=fitness-tracker-app
export MCP_SESSION=$(date +%Y-%m-%d)

# Platform decisions
./scripts/memory-helper.sh store "Platform: React Native for iOS/Android" architecture
./scripts/memory-helper.sh store "State: Redux Toolkit with RTK Query" architecture
./scripts/memory-helper.sh store "Backend: Firebase (Auth, Firestore, Storage)" backend

# Feature tracking
./scripts/memory-helper.sh store "TODO: Implement workout history view" todo
./scripts/memory-helper.sh store "TODO: Add social sharing features" todo
./scripts/memory-helper.sh store "BUG: Step counter inaccurate on iOS 16" bug
```

## Example 5: API Development

```bash
export MCP_PROJECT=payment-api
export MCP_SESSION=$(date +%Y-%m-%d)

# API design decisions
./scripts/memory-helper.sh store "API Style: RESTful with OpenAPI 3.0 spec" api
./scripts/memory-helper.sh store "Versioning: URL path (/v1, /v2)" api
./scripts/memory-helper.sh store "Auth: OAuth2 with Stripe-style API keys" security

# Integration notes
./scripts/memory-helper.sh store "Stripe: Payment processing integration" integration
./scripts/memory-helper.sh store "Plaid: Bank account verification" integration
./scripts/memory-helper.sh store "Webhook timeout: 30 seconds max" config
```

## Claude Interaction Examples

After setting up project context, you can interact naturally:

### Asking About Project Status
```
"What's the current architecture for project:my-webapp?"
"List all TODOs for project:fitness-tracker-app"
"Show bugs in project:fitness-tracker-app"
```

### Storing New Information
```
"Remember for project:payment-api: Added rate limiting at 100 req/min per user"
"Remember for project:ml-pipeline: New experiment with neural network achieved 0.87 AUC"
```

### Cross-Reference Information
```
"What authentication method does project:microservices-platform use?"
"Compare the tech stacks of project:my-webapp and project:payment-api"
```

### Session Planning
```
"Based on what we know about project:fitness-tracker-app, what should we work on today?"
"Show all decisions made in the last week for project:ml-pipeline"
```

## Best Practices in Action

### 1. Start of Day Routine
```bash
# Set context
export MCP_PROJECT=my-webapp
export MCP_SESSION=$(date +%Y-%m-%d)

# Check status
./scripts/memory-helper.sh list

# Create session plan
./scripts/memory-helper.sh context "Working on user authentication flow"
```

### 2. End of Day Routine
```
# In Claude
"Summarize today's progress on project:my-webapp"
"Update TODOs for project:my-webapp based on today's work"
```

### 3. Code Review Context
```bash
# Before review
./scripts/memory-helper.sh store "PR #123: Adds user profile feature" review

# After review
./scripts/memory-helper.sh store "PR #123: Approved, needs minor CSS fixes" review
```

### 4. Debugging Sessions
```bash
# Track debugging context
./scripts/memory-helper.sh store "Bug: Memory leak in image upload, occurs after 50+ uploads" bug

# After fixing
./scripts/memory-helper.sh store "Fixed: Memory leak was due to unclosed streams" bugfix
```

## Project Templates

### Web App Template
```bash
./scripts/memory-helper.sh store "Frontend: [React/Vue/Angular]" architecture
./scripts/memory-helper.sh store "State Management: [Redux/Vuex/Context]" architecture
./scripts/memory-helper.sh store "CSS: [Tailwind/Material-UI/Custom]" architecture
./scripts/memory-helper.sh store "Backend: [Node/Python/Go]" architecture
./scripts/memory-helper.sh store "Database: [PostgreSQL/MongoDB/MySQL]" architecture
./scripts/memory-helper.sh store "Hosting: [AWS/Vercel/Heroku]" infrastructure
```

### API Template
```bash
./scripts/memory-helper.sh store "Language: [Node/Python/Go/Rust]" tech
./scripts/memory-helper.sh store "Framework: [Express/FastAPI/Gin]" tech
./scripts/memory-helper.sh store "Auth: [JWT/OAuth2/API-Keys]" security
./scripts/memory-helper.sh store "Docs: [OpenAPI/GraphQL/Custom]" api
./scripts/memory-helper.sh store "Testing: [Jest/Pytest/Go-test]" testing
```

Use these templates as starting points and customize for your specific needs!