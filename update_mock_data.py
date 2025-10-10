import json
import re

# Read the mock data file
with open('src/backend/db/mock_data.json', 'r') as f:
    content = f.read()

# Count decimal MMR values before
decimal_count = len(re.findall(r'"mmr": \d+\.\d+,', content))
print(f'Found {decimal_count} decimal MMR values')

# Replace all decimal MMR values with integers
content = re.sub(r'"mmr": (\d+)\.(\d+),', r'"mmr": \1,', content)

# Count decimal MMR values after
decimal_count_after = len(re.findall(r'"mmr": \d+\.\d+,', content))
print(f'After replacement: {decimal_count_after} decimal MMR values remaining')

# Write back to file
with open('src/backend/db/mock_data.json', 'w') as f:
    f.write(content)

print('Updated all MMR values to integers')