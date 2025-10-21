#!/usr/bin/env python3
"""
Code statistics analyzer for EvoLadderBot.

Counts lines and characters for different file types in the src directory.
"""

import os
import sys
from pathlib import Path
from collections import defaultdict
import argparse


def get_file_type(file_path):
    """Determine the file type based on extension and path."""
    ext = file_path.suffix.lower()
    path_str = str(file_path).lower()
    
    # Python files - categorize by purpose
    if ext == '.py':
        if 'command' in path_str:
            return 'Bot Commands'
        elif 'service' in path_str:
            return 'Backend Services'
        elif 'db' in path_str or 'database' in path_str:
            return 'Database Layer'
        elif 'bot' in path_str and ('component' in path_str or 'embed' in path_str):
            return 'Bot Components'
        elif 'bot' in path_str and 'util' in path_str:
            return 'Bot Utilities'
        elif 'api' in path_str:
            return 'API Layer'
        elif 'test' in path_str:
            return 'Tests'
        else:
            return 'Python Other'
    
    # Configuration files
    elif ext in ['.json', '.yaml', '.yml', '.toml', '.ini', '.cfg']:
        return 'Config'
    
    # Documentation
    elif ext in ['.md', '.txt', '.rst']:
        return 'Documentation'
    
    # Database files
    elif ext in ['.db', '.sqlite', '.sqlite3']:
        return 'Database'
    
    # Other common file types
    elif ext in ['.js', '.ts', '.jsx', '.tsx']:
        return 'JavaScript/TypeScript'
    elif ext in ['.html', '.htm', '.css']:
        return 'Web'
    elif ext in ['.xml', '.yaml', '.yml']:
        return 'Markup'
    elif ext in ['.log']:
        return 'Logs'
    elif ext in ['.bat', '.sh', '.ps1']:
        return 'Scripts'
    else:
        return 'Other'


def count_file_stats(file_path):
    """Count lines and characters in a file."""
    try:
        with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
            content = f.read()
            
        lines = content.count('\n') + (1 if content else 0)  # +1 for non-empty files
        chars = len(content)
        
        return lines, chars
    except Exception as e:
        print(f"Error reading {file_path}: {e}")
        return 0, 0


def should_skip_file(file_path):
    """Check if a file should be skipped in analysis."""
    # Skip Python cache files
    if '__pycache__' in str(file_path):
        return True
    
    # Skip compiled Python files
    if file_path.suffix in ['.pyc', '.pyo']:
        return True
    
    # Skip hidden files
    if file_path.name.startswith('.'):
        return True
    
    # Skip common non-source files
    skip_patterns = [
        'node_modules',
        '.git',
        '.vscode',
        '.idea',
        'venv',
        'env',
        '.env'
    ]
    
    for pattern in skip_patterns:
        if pattern in str(file_path):
            return True
    
    return False


def analyze_directory(directory_path, recursive=True):
    """Analyze a directory and return statistics."""
    stats = defaultdict(lambda: {'files': 0, 'lines': 0, 'chars': 0, 'file_list': []})
    
    if recursive:
        pattern = "**/*"
    else:
        pattern = "*"
    
    for file_path in Path(directory_path).glob(pattern):
        if file_path.is_file() and not should_skip_file(file_path):
            file_type = get_file_type(file_path)
            lines, chars = count_file_stats(file_path)
            
            stats[file_type]['files'] += 1
            stats[file_type]['lines'] += lines
            stats[file_type]['chars'] += chars
            stats[file_type]['file_list'].append({
                'path': str(file_path.relative_to(directory_path)),
                'lines': lines,
                'chars': chars
            })
    
    return stats


def format_number(num):
    """Format numbers with commas for readability."""
    return f"{num:,}"


def print_summary(stats, show_files=False):
    """Print a summary of the statistics."""
    print("=" * 80)
    print("CODE STATISTICS SUMMARY")
    print("=" * 80)
    print()
    
    # Sort by total lines for better readability
    sorted_stats = sorted(stats.items(), key=lambda x: x[1]['lines'], reverse=True)
    
    total_files = sum(data['files'] for data in stats.values())
    total_lines = sum(data['lines'] for data in stats.values())
    total_chars = sum(data['chars'] for data in stats.values())
    
    print(f"{'File Type':<20} {'Files':<8} {'Lines':<12} {'Characters':<12} {'Avg Lines/File':<15}")
    print("-" * 80)
    
    for file_type, data in sorted_stats:
        avg_lines = data['lines'] / data['files'] if data['files'] > 0 else 0
        print(f"{file_type:<20} {data['files']:<8} {format_number(data['lines']):<12} "
              f"{format_number(data['chars']):<12} {avg_lines:.1f}")
    
    print("-" * 80)
    print(f"{'TOTAL':<20} {total_files:<8} {format_number(total_lines):<12} "
          f"{format_number(total_chars):<12} {total_lines/total_files:.1f}")
    print()
    
    if show_files:
        print("\nDETAILED FILE LISTING:")
        print("=" * 80)
        
        for file_type, data in sorted_stats:
            if data['files'] > 0:
                print(f"\n{file_type} Files ({data['files']} files, {format_number(data['lines'])} lines):")
                print("-" * 60)
                
                # Sort files by lines (descending)
                sorted_files = sorted(data['file_list'], key=lambda x: x['lines'], reverse=True)
                
                for file_info in sorted_files:
                    print(f"  {file_info['path']:<40} {file_info['lines']:>6} lines, "
                          f"{format_number(file_info['chars']):>8} chars")


def main():
    """Main function."""
    parser = argparse.ArgumentParser(description='Analyze code statistics for EvoLadderBot')
    parser.add_argument('--directory', '-d', default='src', 
                       help='Directory to analyze (default: src)')
    parser.add_argument('--files', '-f', action='store_true',
                       help='Show detailed file listing')
    parser.add_argument('--no-recursive', action='store_true',
                       help='Do not analyze subdirectories recursively')
    
    args = parser.parse_args()
    
    directory = Path(args.directory)
    
    if not directory.exists():
        print(f"Error: Directory '{directory}' does not exist")
        sys.exit(1)
    
    print(f"Analyzing directory: {directory.absolute()}")
    print(f"Recursive: {not args.no_recursive}")
    print()
    
    stats = analyze_directory(directory, recursive=not args.no_recursive)
    print_summary(stats, show_files=args.files)


if __name__ == '__main__':
    main()
