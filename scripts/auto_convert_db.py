"""
Automated conversion of database methods to use adapter pattern.
"""

import re

# Read the file
with open('src/backend/db/db_reader_writer.py', 'r', encoding='utf-8') as f:
    content = f.read()

original_length = len(content)
conversions = 0

# Pattern 1: Simple SELECT with fetchone() returning dict
pattern1 = re.compile(
    r'with self\.db\.get_connection\(\) as conn:\s+'
    r'cursor = conn\.cursor\(\)\s+'
    r'cursor\.execute\(\s*'
    r'"([^"]+)",\s*'
    r'(\{[^}]+\})\s*'
    r'\)\s+'
    r'row = cursor\.fetchone\(\)\s+'
    r'return dict\(row\) if row else None',
    re.MULTILINE | re.DOTALL
)

def replace1(match):
    global conversions
    conversions += 1
    query = match.group(1)
    params = match.group(2)
    return (f'results = self.adapter.execute_query(\n'
            f'            "{query}",\n'
            f'            {params}\n'
            f'        )\n'
            f'        return results[0] if results else None')

content = pattern1.sub(replace1, content)

# Pattern 2: Simple SELECT with fetchall() returning list
pattern2 = re.compile(
    r'with self\.db\.get_connection\(\) as conn:\s+'
    r'cursor = conn\.cursor\(\)\s+'
    r'cursor\.execute\(\s*'
    r'"([^"]+)"(?:,\s*(\{[^}]+\}))?\s*'
    r'\)\s+'
    r'return \[dict\(row\) for row in cursor\.fetchall\(\)\]',
    re.MULTILINE | re.DOTALL
)

def replace2(match):
    global conversions
    conversions += 1
    query = match.group(1)
    params = match.group(2)
    if params:
        return f'return self.adapter.execute_query(\n            "{query}",\n            {params}\n        )'
    else:
        return f'return self.adapter.execute_query("{query}")'

content = pattern2.sub(replace2, content)

# Pattern 3: INSERT with lastrowid
pattern3 = re.compile(
    r'with self\.db\.get_connection\(\) as conn:\s+'
    r'cursor = conn\.cursor\(\)\s+'
    r'cursor\.execute\(\s*'
    r'"(INSERT[^"]+)",\s*'
    r'(\{[^}]+\})\s*'
    r'\)\s+'
    r'conn\.commit\(\)\s+'
    r'return cursor\.lastrowid',
    re.MULTILINE | re.DOTALL
)

def replace3(match):
    global conversions
    conversions += 1
    query = match.group(1)
    params = match.group(2)
    return (f'return self.adapter.execute_insert(\n'
            f'            "{query}",\n'
            f'            {params}\n'
            f'        )')

content = pattern3.sub(replace3, content)

# Pattern 4: UPDATE/DELETE with commit
pattern4 = re.compile(
    r'with self\.db\.get_connection\(\) as conn:\s+'
    r'cursor = conn\.cursor\(\)\s+'
    r'cursor\.execute\(\s*'
    r'"(UPDATE|DELETE)[^"]+",\s*'
    r'(\{[^}]+\})\s*'
    r'\)\s+'
    r'conn\.commit\(\)',
    re.MULTILINE | re.DOTALL
)

def replace4(match):
    global conversions
    conversions += 1
    full_query = match.group(0)
    # Extract the full query more carefully
    query_match = re.search(r'"([^"]+)"', full_query)
    params_match = re.search(r'(\{[^}]+\})', full_query)
    if query_match and params_match:
        query = query_match.group(1)
        params = params_match.group(1)
        return (f'self.adapter.execute_write(\n'
                f'            "{query}",\n'
                f'            {params}\n'
                f'        )')
    return full_query

content = pattern4.sub(replace4, content)

print(f"Conversions made: {conversions}")
print(f"Original length: {original_length}")
print(f"New length: {len(content)}")

# Write back
with open('src/backend/db/db_reader_writer.py', 'w', encoding='utf-8') as f:
    f.write(content)

print("✓ Conversion complete!")

