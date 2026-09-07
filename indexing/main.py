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


def search_codebase(
    query: str,
    top_k: int = 5,
    use_pinecone: bool = True,
    use_neo4j: bool = True,
    pinecone_index_name: str = "codebase-index",
    neo4j_database: str = "neo4j",
):
    """
    Search a text query across Pinecone vectors and Neo4j knowledge graph.

    Args:
        query: Text query to search
        top_k: Number of results to return per backend
        use_pinecone: Whether to search Pinecone
        use_neo4j: Whether to search Neo4j
        pinecone_index_name: Pinecone index name
        neo4j_database: Neo4j database name

    Returns:
        Dict with keys 'pinecone' and/or 'neo4j' containing result lists
    """
    results = {}

    # Pinecone search
    if use_pinecone:
        try:
            print("\n" + "=" * 60)
            print("Searching Pinecone...")
            print("=" * 60)

            # Build indexer (will connect to existing index)
            EMBEDDING_MODEL = os.getenv("EMBEDDING_MODEL", "all-MiniLM-L6-v2")
            EMBEDDING_DIMENSION = int(os.getenv("EMBEDDING_DIMENSION", 384))
            pinecone = PineconeIndexer(
                index_name=pinecone_index_name,
                embedding_model=EMBEDDING_MODEL,
                dimension=EMBEDDING_DIMENSION,
            )
            pc_results = pinecone.search(query=query, top_k=top_k)
            results["pinecone"] = pc_results
        except Exception as e:
            print(f"Pinecone search failed: {e}")
            results["pinecone"] = {"error": str(e)}

    # Neo4j search
    if use_neo4j:
        try:
            print("\n" + "=" * 60)
            print("Searching Neo4j...")
            print("=" * 60)

            neo = Neo4jIndexer(database=neo4j_database)
            try:
                with neo.driver.session(database=neo4j_database) as session:
                    # Search files by filename or content preview; also functions/classes by name
                    cypher = """
                    CALL {
                        WITH $q AS q
                        MATCH (f:File)
                        WHERE toLower(f.filename) CONTAINS toLower(q)
                           OR toLower(coalesce(f.content_preview, '')) CONTAINS toLower(q)
                        RETURN f.path AS location, f.filename AS title, 'file' AS type, 0.9 AS score
                        UNION ALL
                        WITH $q AS q
                        MATCH (f:File)-[:DEFINES]->(func:Function)
                        WHERE toLower(func.name) CONTAINS toLower(q)
                        RETURN f.path AS location, func.name AS title, 'function' AS type, 0.8 AS score
                        UNION ALL
                        WITH $q AS q
                        MATCH (f:File)-[:DEFINES]->(c:Class)
                        WHERE toLower(c.name) CONTAINS toLower(q)
                        RETURN f.path AS location, c.name AS title, 'class' AS type, 0.8 AS score
                    }
                    RETURN location, title, type, score
                    LIMIT $k
                    """
                    rows = session.run(cypher, q=query, k=top_k)
                    neo_results = [
                        {
                            "location": r["location"],
                            "title": r["title"],
                            "type": r["type"],
                            "score": r["score"],
                        }
                        for r in rows
                    ]
                    results["neo4j"] = neo_results
            finally:
                neo.close()
        except Exception as e:
            print(f"Neo4j search failed: {e}")
            results["neo4j"] = {"error": str(e)}

    # Summary print
    print("\n" + "=" * 60)
    print("Search Summary")
    print("=" * 60)
    for svc, vals in results.items():
        print(f"\n{svc.upper()} results:")
        if isinstance(vals, dict) and "error" in vals:
            print(f"  Error: {vals['error']}")
        else:
            print(f"  Returned: {len(vals)} items")

    return results


def main_menu():
    """
    Main menu to select between indexing and searching.
    """
    print("=" * 60)
    print("Codebase Indexing & Search Tool")
    print("=" * 60)
    print()
    
    # Check command line arguments
    if len(sys.argv) > 1:
        mode = sys.argv[1].lower()
    else:
        print("Select an option:")
        print("1. Index codebase")
        print("2. Search codebase")
        print("3. Exit")
        choice = input("\nEnter choice (1/2/3): ").strip()
        
        if choice == "1":
            mode = "index"
        elif choice == "2":
            mode = "search"
        elif choice == "3":
            print("Goodbye!")
            return
        else:
            print("Invalid choice. Exiting.")
            return
    
    try:
        if mode == "index":
            # Index mode
            folder_path = None
            if len(sys.argv) > 2:
                folder_path = sys.argv[2]
            
            index_codebase(folder_path=folder_path)
            
        elif mode == "search":
            # Search mode
            query = None
            if len(sys.argv) > 2:
                query = " ".join(sys.argv[2:])
            else:
                query = input("\nEnter search query: ").strip()
                if not query:
                    print("No query provided. Exiting.")
                    return
            
            # Ask which services to use
            use_pinecone = True
            use_neo4j = True
            print("\nWhich services would you like to search?")
            print("1. Pinecone only")
            print("2. Neo4j only")
            print("3. Both (default)")
            choice = input("Enter choice (1/2/3, default=3): ").strip()
            
            if choice == "1":
                use_neo4j = False
            elif choice == "2":
                use_pinecone = False
            
            # Ask for top_k
            top_k_input = input("Number of results per service (default=5): ").strip()
            top_k = int(top_k_input) if top_k_input.isdigit() else 5
            
            results = search_codebase(
                query=query,
                top_k=top_k,
                use_pinecone=use_pinecone,
                use_neo4j=use_neo4j
            )
            
            # Display results in a more readable format
            print("\n" + "=" * 60)
            print("Detailed Results")
            print("=" * 60)
            
            if "pinecone" in results:
                print("\n🔍 Pinecone Results (Vector Search):")
                if isinstance(results["pinecone"], dict) and "error" in results["pinecone"]:
                    print(f"  Error: {results['pinecone']['error']}")
                else:
                    for idx, result in enumerate(results["pinecone"], 1):
                        print(f"\n  {idx}. Score: {result['score']:.4f}")
                        print(f"     File: {result['file_path']}")
                        print(f"     Chunk preview: {result['chunk_text'][:100]}...")
            
            if "neo4j" in results:
                print("\n🔍 Neo4j Results (Knowledge Graph):")
                if isinstance(results["neo4j"], dict) and "error" in results["neo4j"]:
                    print(f"  Error: {results['neo4j']['error']}")
                else:
                    for idx, result in enumerate(results["neo4j"], 1):
                        print(f"\n  {idx}. Type: {result['type']} | Score: {result['score']:.2f}")
                        print(f"     Location: {result['location']}")
                        print(f"     Title: {result['title']}")
        else:
            print(f"Unknown mode: {mode}")
            print("Usage: python -m indexing.main [index|search] [args...]")
            
    except KeyboardInterrupt:
        print("\n\nOperation interrupted by user.")
    except Exception as e:
        print(f"\nError: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    main_menu()



