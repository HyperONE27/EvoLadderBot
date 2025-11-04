"""
Script to count lines and characters in Python and JSON files in src and data directories.
"""
import os
from pathlib import Path
from typing import Dict, Tuple


def count_file_stats(file_path: Path) -> Tuple[int, int]:
    """
    Count lines and characters in a file.
    
    Args:
        file_path: Path to the file
        
    Returns:
        Tuple of (line_count, char_count)
    """
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            content = f.read()
            lines = content.count('\n') + (1 if content and not content.endswith('\n') else 0)
            chars = len(content)
            return lines, chars
    except Exception as e:
        print(f"Error reading {file_path}: {e}")
        return 0, 0


def scan_directory(directory: str, extensions: set) -> Dict[str, Dict[str, int]]:
    """
    Scan a directory for files with specific extensions.
    
    Args:
        directory: Directory to scan
        extensions: Set of file extensions to include (e.g., {'.py', '.json'})
        
    Returns:
        Dictionary with statistics by extension
    """
    stats = {ext: {'files': 0, 'lines': 0, 'chars': 0} for ext in extensions}
    base_path = Path(directory)
    
    if not base_path.exists():
        print(f"Directory {directory} does not exist")
        return stats
    
    for file_path in base_path.rglob('*'):
        if file_path.is_file() and file_path.suffix in extensions:
            lines, chars = count_file_stats(file_path)
            ext = file_path.suffix
            stats[ext]['files'] += 1
            stats[ext]['lines'] += lines
            stats[ext]['chars'] += chars
    
    return stats


def main():
    """Main function to run the statistics collection."""
    directories = ['src', 'data']
    extensions = {'.py', '.json'}
    
    print("=" * 80)
    print("FILE STATISTICS FOR SRC AND DATA DIRECTORIES")
    print("=" * 80)
    print()
    
    grand_total_files = 0
    grand_total_lines = 0
    grand_total_chars = 0
    
    for directory in directories:
        print(f"\n{directory.upper()} DIRECTORY:")
        print("-" * 80)
        
        stats = scan_directory(directory, extensions)
        
        dir_total_files = 0
        dir_total_lines = 0
        dir_total_chars = 0
        
        for ext in sorted(extensions):
            ext_stats = stats[ext]
            if ext_stats['files'] > 0:
                print(f"\n  {ext} files:")
                print(f"    Files:      {ext_stats['files']:>10,}")
                print(f"    Lines:      {ext_stats['lines']:>10,}")
                print(f"    Characters: {ext_stats['chars']:>10,}")
                
                dir_total_files += ext_stats['files']
                dir_total_lines += ext_stats['lines']
                dir_total_chars += ext_stats['chars']
        
        if dir_total_files > 0:
            print(f"\n  {directory} TOTAL:")
            print(f"    Files:      {dir_total_files:>10,}")
            print(f"    Lines:      {dir_total_lines:>10,}")
            print(f"    Characters: {dir_total_chars:>10,}")
        
        grand_total_files += dir_total_files
        grand_total_lines += dir_total_lines
        grand_total_chars += dir_total_chars
    
    print("\n" + "=" * 80)
    print("GRAND TOTAL (SRC + DATA):")
    print("=" * 80)
    print(f"  Total Files:      {grand_total_files:>10,}")
    print(f"  Total Lines:      {grand_total_lines:>10,}")
    print(f"  Total Characters: {grand_total_chars:>10,}")
    print("=" * 80)


if __name__ == "__main__":
    main()

