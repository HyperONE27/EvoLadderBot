"""
Automated script to convert database methods from direct cursor usage to adapter pattern.

This script reads db_reader_writer.py and converts all methods that use:
    with self.db.get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(...)
        
To the new adapter pattern:
    self.adapter.execute_query(...)
"""

import re

def convert_read_method(method_code: str) -> str:
    """Convert a read method to use adapter.execute_query()"""
    
    # Pattern 1: fetchone() with dict conversion
    pattern1 = r'''with self\.db\.get_connection\(\) as conn:
\s+cursor = conn\.cursor\(\)
\s+cursor\.execute\(
\s+"([^"]+)",
\s+(\{[^}]+\})
\s+\)
\s+row = cursor\.fetchone\(\)
\s+return dict\(row\) if row else None'''
    
    def replace1(match):
        query = match.group(1)
        params = match.group(2)
        return f'''results = self.adapter.execute_query(
            "{query}",
            {params}
        )
        return results[0] if results else None'''
    
    method_code = re.sub(pattern1, replace1, method_code)
    
    # Pattern 2: fetchall() with list comprehension
    pattern2 = r'''with self\.db\.get_connection\(\) as conn:
\s+cursor = conn\.cursor\(\)
\s+cursor\.execute\("([^"]+)"(?:,\s+(\{[^}]+\}))?\)
\s+(?:rows = cursor\.fetchall\(\)|return \[dict\(row\) for row in cursor\.fetchall\(\)\])
\s+(?:return \[dict\(row\) for row in rows\])?'''
    
    def replace2(match):
        query = match.group(1)
        params = match.group(2) if match.group(2) else None
        if params:
            return f'return self.adapter.execute_query("{query}", {params})'
        else:
            return f'return self.adapter.execute_query("{query}")'
    
    method_code = re.sub(pattern2, replace2, method_code)
    
    return method_code


def convert_write_method(method_code: str) -> str:
    """Convert a write method to use adapter.execute_write() or execute_insert()"""
    
    # Pattern for INSERT with lastrowid
    insert_pattern = r'''with self\.db\.get_connection\(\) as conn:
\s+cursor = conn\.cursor\(\)
\s+cursor\.execute\(
\s+"(INSERT[^"]+)",
\s+(\{[^}]+\})
\s+\)
\s+conn\.commit\(\)
\s+return cursor\.lastrowid'''
    
    def replace_insert(match):
        query = match.group(1)
        params = match.group(2)
        return f'''return self.adapter.execute_insert(
            "{query}",
            {params}
        )'''
    
    method_code = re.sub(insert_pattern, replace_insert, method_code)
    
    # Pattern for UPDATE/DELETE
    write_pattern = r'''with self\.db\.get_connection\(\) as conn:
\s+cursor = conn\.cursor\(\)
\s+cursor\.execute\(
\s+"(UPDATE|DELETE)[^"]+",
\s+(\{[^}]+\})
\s+\)
\s+conn\.commit\(\)'''
    
    def replace_write(match):
        query_start = match.group(1)
        full_match = match.group(0)
        # Extract full query
        query_match = re.search(r'cursor\.execute\(\s*"([^"]+)",', full_match)
        params_match = re.search(r'cursor\.execute\([^{]+(\{[^}]+\})', full_match)
        
        if query_match and params_match:
            query = query_match.group(1)
            params = params_match.group(1)
            return f'''self.adapter.execute_write(
            "{query}",
            {params}
        )'''
        return full_match
    
    method_code = re.sub(write_pattern, replace_write, method_code)
    
    return method_code


# Read the file
with open('src/backend/db/db_reader_writer.py', 'r', encoding='utf-8') as f:
    content = f.read()

print("Converting database methods...")
print("Original file size:", len(content), "characters")

# Apply conversions
content = convert_read_method(content)
content = convert_write_method(content)

print("Converted file size:", len(content), "characters")

# Write back
with open('src/backend/db/db_reader_writer.py', 'w', encoding='utf-8') as f:
    f.write(content)

print("✓ Conversion complete!")
print("\nNote: This automated conversion handles common patterns.")
print("You should review the file and manually fix any remaining methods.")

