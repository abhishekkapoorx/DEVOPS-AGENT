"""
Utility functions for code indexing.
"""

import os
from pathlib import Path
from typing import List, Dict, Any
import mimetypes


def get_code_files(folder_path: str, included_extensions: List[str] = None, excluded_patterns: List[str] = None) -> List[Dict[str, Any]]:
    """
    Recursively get all code files from a folder path.
    
    Args:
        folder_path: Root directory to scan
        included_extensions: List of file extensions to include (e.g., ['.py', '.js'])
        excluded_patterns: List of patterns to exclude (e.g., ['node_modules', '.git'])
    
    Returns:
        List of dictionaries with file info: {'path': str, 'content': str, 'extension': str}
    """
    if included_extensions is None:
        included_extensions = ['.py', '.js', '.ts', '.jsx', '.tsx', '.java', '.cpp', '.c', '.h', '.go', '.rs', '.rb', '.php', '.swift', '.kt', '.scala', '.md', '.txt', '.json', '.yaml', '.yml', '.toml', '.sh', '.bash']
    
    if excluded_patterns is None:
        excluded_patterns = ['.git', 'node_modules', '__pycache__', '.venv', 'venv', 'env', 'target', 'dist', 'build', '.next', '.cache']
    
    files = []
    folder_path = Path(folder_path).resolve()
    
    if not folder_path.exists():
        raise ValueError(f"Folder path does not exist: {folder_path}")
    
    if not folder_path.is_dir():
        raise ValueError(f"Path is not a directory: {folder_path}")
    
    for root, dirs, filenames in os.walk(folder_path):
        # Filter out excluded directories
        dirs[:] = [d for d in dirs if not any(excluded in d or excluded in os.path.join(root, d) for excluded in excluded_patterns)]
        
        for filename in filenames:
            # Skip hidden files
            if filename.startswith('.'):
                continue
            
            file_path = Path(root) / filename
            file_ext = file_path.suffix.lower()
            
            # Check if extension is included
            if included_extensions and file_ext not in included_extensions:
                continue
            
            # Check if file path contains excluded patterns
            file_path_str = str(file_path)
            if any(excluded in file_path_str for excluded in excluded_patterns):
                continue
            
            try:
                # Read file content
                with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
                    content = f.read()
                
                files.append({
                    'path': str(file_path),
                    'relative_path': str(file_path.relative_to(folder_path)),
                    'content': content,
                    'extension': file_ext,
                    'filename': filename,
                    'size': len(content)
                })
            except Exception as e:
                print(f"Warning: Could not read file {file_path}: {e}")
                continue
    
    return files


def get_file_info(file_path: str) -> Dict[str, Any]:
    """
    Get information about a file.
    
    Args:
        file_path: Path to the file
    
    Returns:
        Dictionary with file information
    """
    path = Path(file_path)
    return {
        'path': str(path),
        'filename': path.name,
        'extension': path.suffix,
        'parent': str(path.parent),
        'exists': path.exists(),
        'size': path.stat().st_size if path.exists() else 0
    }



