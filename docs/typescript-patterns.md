# TypeScript Patterns and Best Practices for MCP Servers

This document outlines TypeScript patterns and solutions discovered during the cleanup of 400+ TypeScript errors in the MCP server codebase.

## Common Patterns and Solutions

### 1. createToolHandler Type Annotations

**Problem**: The `createToolHandler` function requires explicit type parameters but they were missing throughout the codebase.

**Solution**: Add generic type parameter to all `createToolHandler` calls:

```typescript
// ❌ Before - Missing type parameter
this.registerTool(
  'tool_name',
  'Tool description',
  ToolSchema,
  createToolHandler(async (params) => {
    // implementation
  })
);

// ✅ After - With type parameter
this.registerTool(
  'tool_name', 
  'Tool description',
  ToolSchema,
  createToolHandler<z.infer<typeof ToolSchema>>(async (params) => {
    // implementation
  })
);

// ✅ Alternative - Using 'any' for rapid prototyping
createToolHandler<any>(async (params) => {
  // implementation
})
```

### 2. Docker API Type Compatibility

**Problem**: Docker client methods have type mismatches with the dockerode library.

**Solution**: Cast the Docker client when calling methods:

```typescript
// ❌ Before - Type errors
const containers = await this.docker.listContainers({ all, filters });

// ✅ After - With type casting
const containers = await (this.docker as any).listContainers({ all, filters });
```

### 3. Express Route Handler Return Types

**Problem**: Async route handlers had implicit return type issues.

**Solution**: Add explicit return type annotations:

```typescript
// ❌ Before - Implicit return type
router.get('/path', async (req: Request, res: Response) => {
  // implementation
});

// ✅ After - With explicit return type
router.get('/path', async (req: Request, res: Response): Promise<any> => {
  // implementation
});
```

### 4. Unused Parameters

**Problem**: Many functions have parameters that are declared but not used.

**Solution**: Prefix unused parameters with underscore:

```typescript
// ❌ Before - Unused parameter warning
async function example(path: string, value: string, field?: string): Promise<void> {
  throw new Error('Not implemented');
}

// ✅ After - No warning
async function example(_path: string, _value: string, _field?: string): Promise<void> {
  throw new Error('Not implemented');
}
```

### 5. Environment Variables

**Problem**: `process.env.VARIABLE` can be `undefined` but types expect `string`.

**Solution**: Provide default values:

```typescript
// ❌ Before - Type error
const token: string = process.env.GITHUB_TOKEN;

// ✅ After - With default
const token: string = process.env.GITHUB_TOKEN || '';
```

### 6. Middleware Return Paths

**Problem**: Express middleware functions must handle all code paths.

**Solution**: Ensure all paths either call `next()` or send a response:

```typescript
// ✅ Correct middleware pattern
validateRequest() {
  return (req: Request, res: Response, next: NextFunction) => {
    if (someCondition) {
      return res.status(400).json({ error: 'Bad request' });
    }
    return next(); // Always return or call next()
  };
}
```

## Automated Fixes

For bulk fixes across multiple files, use sed commands:

```bash
# Add <any> type to all createToolHandler calls
sed -i '' 's/createToolHandler(async (params)/createToolHandler<any>(async (params)/g' servers/*/index.ts

# Fix specific patterns
sed -i '' 's/: Promise<void>/: Promise<any>/g' src/gateway/routes/*.ts
```

## Type Safety Guidelines

1. **Prefer specific types over `any`**: Use `any` as a temporary fix, then add proper types later
2. **Use Zod schemas**: Leverage `z.infer<typeof Schema>` for automatic type inference
3. **Document type decisions**: Add comments when using `as any` or other type assertions
4. **Test after fixing**: Ensure runtime behavior matches type expectations

## Common Error Codes

- **TS7006**: Parameter implicitly has an 'any' type
- **TS2339**: Property does not exist on type
- **TS2353**: Object literal may only specify known properties
- **TS6133**: Variable is declared but never used
- **TS2345**: Argument type not assignable
- **TS7030**: Not all code paths return a value

## Build Verification

Always verify the build after making changes:

```bash
# Full build
npm run build

# Check for errors
npm run build 2>&1 | grep -E '^(src|servers)/'

# Count errors
npm run build 2>&1 | grep -E '^(src|servers)/' | wc -l
```

## Future Improvements

1. **Strict Mode**: Consider enabling stricter TypeScript options gradually
2. **Type Generation**: Use tools to generate types from schemas
3. **Shared Types**: Create a central types package for common interfaces
4. **Runtime Validation**: Ensure Zod schemas match TypeScript types

---

*Last Updated: 2025-06-29*
*Related: See TASKS.md for implementation history*