#!/usr/bin/env python3

import re
import sys
from pathlib import Path

def extract_schemas(content):
    """Extract all schema definitions from the file"""
    schemas = {}
    
    # Find const SchemaName = z.object({ ... })
    schema_pattern = r'const\s+(\w+Schema)\s*=\s*z\.object\s*\(\s*\{([^}]+)\}'
    
    for match in re.finditer(schema_pattern, content, re.DOTALL):
        schema_name = match.group(1)
        schema_body = match.group(2)
        schemas[schema_name] = schema_body
    
    return schemas

def fix_createtoolhandler_types(file_path):
    """Fix createToolHandler type annotations in a TypeScript file"""
    
    with open(file_path, 'r') as f:
        content = f.read()
    
    schemas = extract_schemas(content)
    changes = 0
    
    # Pattern to find registerTool calls with createToolHandler
    pattern = r'(this\.registerTool\s*\(\s*[\'"][^\'"]+"[\'"],\s*[\'"][^\'"]+"[\'"],\s*)(\w+(?:Schema)?)(,\s*createToolHandler)(\s*\()'
    
    def replacer(match):
        nonlocal changes
        prefix = match.group(1)
        schema_name = match.group(2)
        middle = match.group(3)
        suffix = match.group(4)
        
        # Check if already has type annotation by looking ahead
        next_chars_start = match.end()
        next_chars = content[next_chars_start:next_chars_start+10]
        if next_chars.startswith('<'):
            return match.group(0)
        
        # Add type annotation
        if schema_name in schemas:
            changes += 1
            return f"{prefix}{schema_name}{middle}<z.infer<typeof {schema_name}>>{suffix}"
        else:
            return match.group(0)
    
    new_content = re.sub(pattern, replacer, content)
    
    # Also fix inline z.object schemas
    inline_pattern = r'(this\.registerTool\s*\(\s*[\'"][^\'"]+"[\'"],\s*[\'"][^\'"]+"[\'"],\s*)(z\.object\s*\([^)]+\))(,\s*createToolHandler)(\s*\()'
    
    def inline_replacer(match):
        nonlocal changes
        prefix = match.group(1)
        schema = match.group(2)
        middle = match.group(3)
        suffix = match.group(4)
        
        # Check if already has type annotation
        next_chars_start = match.end()
        next_chars = content[next_chars_start:next_chars_start+10]
        if next_chars.startswith('<'):
            return match.group(0)
        
        # Try to extract parameter names from the handler
        handler_start = match.end()
        handler_match = re.search(r'async\s*\(\s*\{([^}]+)\}', new_content[handler_start:handler_start+200])
        
        if handler_match:
            params = [p.strip() for p in handler_match.group(1).split(',')]
            param_types = []
            
            for param in params:
                param_name = param.split(':')[0].strip()
                # Try to find type in schema
                type_match = re.search(rf'{param_name}:\s*z\.(\w+)\(', schema)
                if type_match:
                    zod_type = type_match.group(1)
                    ts_type = {
                        'string': 'string',
                        'number': 'number',
                        'boolean': 'boolean',
                        'array': 'any[]',
                        'object': 'Record<string, any>',
                        'enum': 'string',
                        'optional': 'any'
                    }.get(zod_type, 'any')
                    
                    # Check if optional
                    if re.search(rf'{param_name}:\s*z\.\w+\([^)]*\)\.optional\(\)', schema):
                        param_types.append(f"{param_name}?: {ts_type}")
                    else:
                        param_types.append(f"{param_name}: {ts_type}")
                else:
                    param_types.append(f"{param_name}: any")
            
            if param_types:
                changes += 1
                type_annotation = "{ " + "; ".join(param_types) + " }"
                return f"{prefix}{schema}{middle}<{type_annotation}>{suffix}"
        
        return match.group(0)
    
    new_content = re.sub(inline_pattern, inline_replacer, new_content)
    
    if changes > 0:
        with open(file_path, 'w') as f:
            f.write(new_content)
        print(f"✅ Fixed {changes} createToolHandler calls in {file_path.name}")
    else:
        print(f"✨ No changes needed in {file_path.name}")
    
    return changes

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python fix-types.py <server-file>")
        sys.exit(1)
    
    file_path = Path(sys.argv[1])
    if not file_path.exists():
        print(f"File not found: {file_path}")
        sys.exit(1)
    
    fix_createtoolhandler_types(file_path)