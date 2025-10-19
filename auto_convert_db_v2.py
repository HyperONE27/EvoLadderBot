"""
Comprehensive automated conversion - handles more patterns.
"""

import re

with open('src/backend/db/db_reader_writer.py', 'r', encoding='utf-8') as f:
    content = f.read()

conv_count = 0

# Pattern: Multi-line queries with fetchall
pattern_multi = re.compile(
    r'with self\.db\.get_connection\(\) as conn:\s+'
    r'cursor = conn\.cursor\(\)\s+'
    r'cursor\.execute\(\s*\n\s*"([^\n]+)"\s*\n'
    r'([^\n]*\n)*?'
    r'\s*\)\s+'
    r'(?:rows = cursor\.fetchall\(\)\s+return \[dict\(row\) for row in rows\]|'
    r'return \[dict\(row\) for row in cursor\.fetchall\(\)\])',
    re.MULTILINE | re.DOTALL
)

# Simpler approach: find and replace line by line
lines = content.split('\n')
i = 0
new_lines = []

while i < len(lines):
    line = lines[i]
    
    # Check if this is the start of an old-style DB method
    if 'with self.db.get_connection() as conn:' in line:
        # Collect the whole block
        block = [line]
        indent = len(line) - len(line.lstrip())
        i += 1
        
        while i < len(lines) and (lines[i].strip() == '' or len(lines[i]) - len(lines[i].lstrip()) > indent):
            block.append(lines[i])
            i += 1
        
        block_text = '\n'.join(block)
        
        # Try to convert this block
        converted = try_convert_block(block_text, indent)
        if converted:
            new_lines.extend(converted.split('\n'))
            conv_count += 1
        else:
            new_lines.extend(block)
    else:
        new_lines.append(line)
        i += 1

def try_convert_block(block, indent):
    """Try to convert a database block to adapter pattern."""
    spaces = ' ' * indent
    
    # Extract query and params
    query_match = re.search(r'"([^"]+)"', block)
    params_match = re.search(r'(\{[^}]+\})', block)
    
    if not query_match:
        return None
    
    query = query_match.group(1)
    params = params_match.group(1) if params_match else None
    
    # Determine return type
    if 'fetchone()' in block and 'dict(row) if row else None' in block:
        # Single row query
        if params:
            return (f'{spaces}results = self.adapter.execute_query(\n'
                    f'{spaces}    "{query}",\n'
                    f'{spaces}    {params}\n'
                    f'{spaces})\n'
                    f'{spaces}return results[0] if results else None')
        else:
            return (f'{spaces}results = self.adapter.execute_query("{query}")\n'
                    f'{spaces}return results[0] if results else None')
    
    elif 'fetchall()' in block:
        # Multiple rows query
        if params:
            return f'{spaces}return self.adapter.execute_query(\n{spaces}    "{query}",\n{spaces}    {params}\n{spaces})'
        else:
            return f'{spaces}return self.adapter.execute_query("{query}")'
    
    elif 'lastrowid' in block:
        # INSERT query
        if params:
            return (f'{spaces}return self.adapter.execute_insert(\n'
                    f'{spaces}    "{query}",\n'
                    f'{spaces}    {params}\n'
                    f'{spaces})')
        return None
    
    elif 'commit()' in block:
        # UPDATE/DELETE query
        if params:
            return (f'{spaces}self.adapter.execute_write(\n'
                    f'{spaces}    "{query}",\n'
                    f'{spaces}    {params}\n'
                    f'{spaces})')
        return None
    
    return None

# Actually just use simpler bulk replace
content = re.sub(
    r'with self\.db\.get_connection\(\) as conn:\s+cursor = conn\.cursor\(\)',
    '# CONVERTED',
    content
)

print(f"Marked {content.count('# CONVERTED')} blocks for conversion")

# Don't write - let me do manual inspection first

