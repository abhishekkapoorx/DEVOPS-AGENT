"""
Utility functions for code indexing.
"""

import os
from pathlib import Path
from typing import List, Dict, Any, Optional
import mimetypes
import logging
from contextlib import suppress

try:
    import pathspec
except Exception:
    pathspec = None


def get_logger(name: str) -> logging.Logger:
    """
    Create or get a module logger with sane defaults.
    Respects LOG_LEVEL env (default INFO). Avoids duplicate handlers.
    """
    logger = logging.getLogger(name)
    if not logger.handlers:
        level = os.getenv("LOG_LEVEL", "INFO").upper()
        logger.setLevel(getattr(logging, level, logging.INFO))
        handler = logging.StreamHandler()
        handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(name)s - %(message)s"))
        logger.addHandler(handler)
        logger.propagate = False
    return logger


def get_code_files(
    folder_path: str,
    included_extensions: Optional[List[str]] = None,
    excluded_patterns: Optional[List[str]] = None,
    use_gitignore: bool = True,
) -> List[Dict[str, Any]]:
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
    
    # Load .gitignore if requested
    gitignore_spec = None
    gitignore_path = folder_path / ".gitignore"
    if use_gitignore and gitignore_path.exists():
        if pathspec is None:
            print("Warning: pathspec not installed; .gitignore will be ignored. Install 'pathspec' to enable.")
        else:
            with suppress(Exception):
                with open(gitignore_path, 'r', encoding='utf-8', errors='ignore') as f:
                    gitignore_patterns = f.read().splitlines()
                    gitignore_spec = pathspec.PathSpec.from_lines('gitwildmatch', gitignore_patterns)

    def is_ignored(rel_path: str) -> bool:
        if gitignore_spec is not None and gitignore_spec.match_file(rel_path):
            return True
        if excluded_patterns and any(pat in rel_path for pat in excluded_patterns):
            return True
        return False

    for root, dirs, filenames in os.walk(folder_path):
        # Filter out excluded directories
        pruned_dirs = []
        for d in dirs:
            abs_dir = Path(root) / d
            rel_dir = str(abs_dir.relative_to(folder_path))
            if not is_ignored(rel_dir):
                pruned_dirs.append(d)
        dirs[:] = pruned_dirs
        
        for filename in filenames:
            # Skip hidden files
            if filename.startswith('.'):
                continue
            
            file_path = Path(root) / filename
            file_ext = file_path.suffix.lower()
            rel_path = str(file_path.relative_to(folder_path))
            
            # Check if extension is included
            if included_extensions and file_ext not in included_extensions:
                continue
            
            # Check if file path contains excluded patterns
            if is_ignored(rel_path):
                continue
            
            try:
                # Read file content
                with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
                    content = f.read()
                
                files.append({
                    'path': str(file_path),
                    'relative_path': rel_path,
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



