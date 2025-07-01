# Web Application Template

This template provides a full-stack web application setup with React frontend and Node.js backend.

## Quick Start

```bash
# Use the attach-project script
../../scripts/attach-project.sh

# Or manually configure with this template
cp template.json /path/to/your/project/.mcp/template.json
```

## What's Included

### Frontend (React + TypeScript)
- React 18 with TypeScript
- Redux Toolkit for state management
- Tailwind CSS for styling
- React Router for navigation
- Axios for API calls

### Backend (Node.js + Express)
- Express.js with TypeScript
- Prisma ORM for database
- JWT authentication
- Input validation with Zod
- Error handling middleware

### Development Tools
- ESLint + Prettier
- Jest for testing
- Docker setup
- GitHub Actions CI/CD

## Claude Commands

After attaching this template, you can ask Claude:

### Initial Setup
```
"Set up the initial project structure for my web app"
"Create the database schema for user authentication"
"Configure ESLint and Prettier for the project"
```

### Component Development
```
"Create a new component called UserProfile with TypeScript"
"Add a login form component with validation"
"Create a dashboard layout component"
```

### API Development
```
"Create a REST API endpoint for user registration"
"Add authentication middleware to protect routes"
"Implement pagination for the products endpoint"
```

### Testing
```
"Write unit tests for the UserProfile component"
"Create integration tests for the auth endpoints"
"Set up end-to-end testing with Playwright"
```

### Deployment
```
"Create a Dockerfile for the application"
"Set up GitHub Actions for CI/CD"
"Configure environment variables for production"
```

## Project Structure

```
my-web-app/
├── frontend/
│   ├── src/
│   │   ├── components/    # Reusable components
│   │   ├── pages/        # Page components
│   │   ├── hooks/        # Custom React hooks
│   │   ├── store/        # Redux store
│   │   ├── api/          # API client
│   │   ├── utils/        # Utilities
│   │   └── types/        # TypeScript types
│   ├── public/           # Static assets
│   └── package.json
├── backend/
│   ├── src/
│   │   ├── controllers/  # Request handlers
│   │   ├── models/       # Data models
│   │   ├── routes/       # API routes
│   │   ├── middleware/   # Express middleware
│   │   ├── services/     # Business logic
│   │   └── utils/        # Utilities
│   ├── prisma/           # Database schema
│   └── package.json
├── shared/
│   └── types/           # Shared types
├── docker/              # Docker configs
└── .github/
    └── workflows/       # CI/CD pipelines
```

## Memory Context

This template automatically sets up the following context:

```
project:<your-project>:
- Architecture: React + TypeScript frontend, Express backend
- Database: PostgreSQL with Prisma ORM
- Auth: JWT with refresh tokens
- Styling: Tailwind CSS
- State: Redux Toolkit
- Testing: Jest + React Testing Library
```

## Best Practices

1. **Component Structure**: Use functional components with TypeScript
2. **State Management**: Use Redux Toolkit for global state
3. **API Design**: RESTful endpoints with proper status codes
4. **Error Handling**: Centralized error handling in backend
5. **Testing**: Write tests for critical paths
6. **Security**: Input validation, rate limiting, CORS setup

## Customization

Edit `template.json` to customize:
- Initial memory context
- File structure
- Technology choices
- Common prompts

## Example Session

```
You: "I'm starting a new e-commerce web app"
Claude: "I'll help you set up an e-commerce web application. Let me start by creating the initial project structure..."

You: "Create a product listing component"
Claude: "I'll create a ProductList component with TypeScript that displays products in a grid layout..."

You: "Add an API endpoint to fetch products"
Claude: "I'll create a GET /api/products endpoint with pagination and filtering..."
```