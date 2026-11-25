#!/usr/bin/env python3
import re
import sys

def fix_addtool_pattern(content):
    """Transform addTool calls to registerTool calls"""
    
    # Pattern to match this.addTool({ ... });
    # This handles multi-line content with nested braces
    pattern = r'this\.addTool\(\{([^{}]*(?:\{[^{}]*\}[^{}]*)*)\}\);'
    
    def transform_match(match):
        block_content = match.group(1).strip()
        
        # Extract the individual properties
        name_match = re.search(r"name:\s*['\"`]([^'\"`]+)['\"`]", block_content)
        desc_match = re.search(r"description:\s*['\"`]([^'\"`]+)['\"`]", block_content)
        schema_match = re.search(r"inputSchema:\s*(\w+)", block_content)
        
        if not all([name_match, desc_match, schema_match]):
            return match.group(0)  # Return original if can't parse
        
        name = name_match.group(1)
        description = desc_match.group(1)
        schema = schema_match.group(1)
        
        # Extract handler function
        handler_match = re.search(r"handler:\s*(async\s*\([^)]*\)\s*=>\s*\{.*)", block_content, re.DOTALL)
        if not handler_match:
            return match.group(0)
        
        handler = handler_match.group(1)
        # Remove trailing comma and spaces
        handler = handler.rstrip().rstrip(',')
        
        # Build the new registerTool call
        indent = "    "  # Adjust based on your needs
        return f"""{indent}this.registerTool(
      '{name}',
      '{description}',
      {schema},
      createToolHandler({handler})
    )"""
    
    # Apply transformation
    result = re.sub(pattern, transform_match, content, flags=re.DOTALL | re.MULTILINE)
    return result

if __name__ == "__main__":
    if len(sys.argv) > 1:
        filepath = sys.argv[1]
        with open(filepath, 'r') as f:
            content = f.read()
        
        fixed_content = fix_addtool_pattern(content)
        
        with open(filepath, 'w') as f:
            f.write(fixed_content)
        
        print(f"Fixed: {filepath}")
    else:
        print("Usage: python fix-addtool-pattern.py <filepath>")