"""
Main entry point for codebase indexing.
"""

import os
import sys
from pathlib import Path
from typing import Optional

from .pinecone_indexer import index_to_pinecone, PineconeIndexer
from .neo4j_indexer import index_to_neo4j, Neo4jIndexer


def get_folder_path() -> str:
    """
    Prompt user for folder path to index.
    
    Returns:
        Validated folder path
    """
    print("=" * 60)
    print("Codebase Indexing Tool")
    print("=" * 60)
    print()
    
    # Try to get path from command line argument
    if len(sys.argv) > 1:
        folder_path = sys.argv[1]
    else:
        folder_path = input("Enter the folder path to index (or press Enter for current directory): ").strip()
        if not folder_path:
            folder_path = os.getcwd()
    
    # Validate path
    path = Path(folder_path).resolve()
    if not path.exists():
        raise ValueError(f"Path does not exist: {folder_path}")
    
    if not path.is_dir():
        raise ValueError(f"Path is not a directory: {folder_path}")
    
    print(f"\nSelected folder: {path}")
    return str(path)


def index_codebase(
    folder_path: Optional[str] = None,
    index_pinecone: bool = True,
    index_neo4j: bool = True,
    pinecone_index_name: str = "codebase-index",
    neo4j_database: str = "neo4j"
):
    """
    Main function to index codebase to Pinecone and/or Neo4j.
    
    Args:
        folder_path: Folder path to index (if None, will prompt user)
        index_pinecone: Whether to index to Pinecone
        index_neo4j: Whether to index to Neo4j
        pinecone_index_name: Name of Pinecone index
        neo4j_database: Neo4j database name
    """
    try:
        # Get folder path
        if folder_path is None:
            folder_path = get_folder_path()
        
        # Get indexing options
        if not folder_path:
            folder_path = get_folder_path()
        
        # Ask which services to use if not specified
        if len(sys.argv) <= 2:
            if index_pinecone and index_neo4j:
                print("\nWhich services would you like to use?")
                print("1. Pinecone only")
                print("2. Neo4j only")
                print("3. Both (default)")
                choice = input("Enter choice (1/2/3, default=3): ").strip()
                
                if choice == "1":
                    index_neo4j = False
                elif choice == "2":
                    index_pinecone = False
        
        # Common file patterns
        included_extensions = ['.py', '.js', '.ts', '.jsx', '.tsx', '.java', '.cpp', '.c', '.h', '.go', '.rs', '.rb', '.php', '.swift', '.kt', '.scala', '.md', '.txt', '.json', '.yaml', '.yml', '.toml', '.sh', '.bash']
        excluded_patterns = ['.git', 'node_modules', '__pycache__', '.venv', 'venv', 'env', 'target', 'dist', 'build', '.next', '.cache']
        
        results = {}
        
        # Index to Pinecone
        if index_pinecone:
            print("\n" + "=" * 60)
            print("Indexing to Pinecone...")
            print("=" * 60)
            try:
                pinecone_stats = index_to_pinecone(
                    folder_path=folder_path,
                    index_name=pinecone_index_name,
                    included_extensions=included_extensions,
                    excluded_patterns=excluded_patterns
                )
                results['pinecone'] = pinecone_stats
                print(f"✓ Pinecone indexing completed successfully!")
            except Exception as e:
                print(f"✗ Pinecone indexing failed: {e}")
                results['pinecone'] = {'error': str(e)}
        
        # Index to Neo4j
        if index_neo4j:
            print("\n" + "=" * 60)
            print("Indexing to Neo4j...")
            print("=" * 60)
            try:
                neo4j_stats = index_to_neo4j(
                    folder_path=folder_path,
                    database=neo4j_database,
                    included_extensions=included_extensions,
                    excluded_patterns=excluded_patterns
                )
                results['neo4j'] = neo4j_stats
                print(f"✓ Neo4j indexing completed successfully!")
            except Exception as e:
                print(f"✗ Neo4j indexing failed: {e}")
                results['neo4j'] = {'error': str(e)}
        
        # Summary
        print("\n" + "=" * 60)
        print("Indexing Summary")
        print("=" * 60)
        for service, stats in results.items():
            print(f"\n{service.upper()}:")
            if 'error' in stats:
                print(f"  Error: {stats['error']}")
            else:
                for key, value in stats.items():
                    print(f"  {key}: {value}")
        
        return results
        
    except KeyboardInterrupt:
        print("\n\nIndexing interrupted by user.")
        return None
    except Exception as e:
        print(f"\nError: {e}")
        import traceback
        traceback.print_exc()
        return None


if __name__ == "__main__":
    index_codebase()



