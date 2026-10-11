"""
Neo4j knowledge graph indexing module for codebase indexing.
"""

import os
import re
import hashlib
from typing import List, Dict, Any, Optional
from neo4j import GraphDatabase
from dotenv import load_dotenv
from tqdm import tqdm

from .utils import get_code_files, get_logger

load_dotenv()


class Neo4jIndexer:
    """Handles indexing of code files to Neo4j knowledge graph."""
    
    def __init__(
        self,
        uri: Optional[str] = None,
        user: Optional[str] = None,
        password: Optional[str] = None,
        database: str = "neo4j"
    ):
        """
        Initialize Neo4j indexer.
        
        Args:
            uri: Neo4j connection URI (defaults to NEO4J_URI env var)
            user: Neo4j username (defaults to NEO4J_USER env var)
            password: Neo4j password (defaults to NEO4J_PASSWORD env var)
            database: Neo4j database name (defaults to "neo4j")
        """
        self.uri = uri or os.getenv("NEO4J_URI", "bolt://localhost:7687")
        self.user = user or os.getenv("NEO4J_USERNAME", "neo4j")
        self.password = password or os.getenv("NEO4J_PASSWORD")
        
        if not self.password:
            raise ValueError("Neo4j password is required. Set NEO4J_PASSWORD environment variable.")
        
        self.database = database
        self.logger = get_logger(__name__)
        
        # Initialize Neo4j driver
        self.driver = GraphDatabase.driver(self.uri, auth=(self.user, self.password))
        
        # Verify connection
        try:
            with self.driver.session(database=self.database) as session:
                session.run("RETURN 1")
            print(f"Connected to Neo4j at {self.uri}")
            self.logger.info(f"Connected to Neo4j at {self.uri}")
        except Exception as e:
            raise ConnectionError(f"Failed to connect to Neo4j: {e}")
        
        # Create constraints and indexes
        self._setup_constraints()
    
    def _setup_constraints(self):
        """Setup constraints and indexes in Neo4j."""
        with self.driver.session(database=self.database) as session:
            # Create constraints for uniqueness
            constraints = [
                "CREATE CONSTRAINT file_id IF NOT EXISTS FOR (f:File) REQUIRE f.id IS UNIQUE",
                "CREATE CONSTRAINT function_id IF NOT EXISTS FOR (func:Function) REQUIRE func.id IS UNIQUE",
                "CREATE CONSTRAINT class_id IF NOT EXISTS FOR (c:Class) REQUIRE c.id IS UNIQUE",
            ]
            
            for constraint in constraints:
                try:
                    session.run(constraint)
                except Exception as e:
                    # Constraint might already exist
                    print(f"Note: {constraint} - {e}")
                    self.logger.info(f"Note: {constraint} - {e}")
            
            # Create indexes for better performance
            indexes = [
                "CREATE INDEX file_path IF NOT EXISTS FOR (f:File) ON (f.path)",
                "CREATE INDEX file_extension IF NOT EXISTS FOR (f:File) ON (f.extension)",
            ]
            
            for index in indexes:
                try:
                    session.run(index)
                except Exception as e:
                    print(f"Note: {index} - {e}")
                    self.logger.info(f"Note: {index} - {e}")
    
    def _generate_file_id(self, file_path: str) -> str:
        """Generate a unique ID for a file."""
        return hashlib.md5(file_path.encode()).hexdigest()
    
    def index_folder(
        self,
        folder_path: str,
        included_extensions: Optional[List[str]] = None,
        excluded_patterns: Optional[List[str]] = None
    ) -> Dict[str, Any]:
        """
        Index all code files in a folder to Neo4j knowledge graph.
        
        Args:
            folder_path: Root directory to index
            included_extensions: File extensions to include
            excluded_patterns: Patterns to exclude
        
        Returns:
            Dictionary with indexing statistics
        """
        print(f"Scanning folder: {folder_path}")
        self.logger.info(f"Scanning folder: {folder_path}")
        files = get_code_files(
            folder_path,
            included_extensions=included_extensions,
            excluded_patterns=excluded_patterns,
            use_gitignore=True,
        )
        print(f"Found {len(files)} files to index")
        self.logger.info(f"Found {len(files)} files to index")
        
        indexed_files = 0
        failed_files = 0
        total_relationships = 0
        
        # Process files
        for file_info in tqdm(files, desc="Indexing to Neo4j"):
            try:
                relationships = self._process_file(file_info, folder_path)
                total_relationships += relationships
                indexed_files += 1
            except Exception as e:
                print(f"Error indexing file {file_info['path']}: {e}")
                self.logger.warning(f"Error indexing file {file_info['path']}: {e}")
                failed_files += 1
                continue
        
        stats = {
            "total_files": len(files),
            "indexed_files": indexed_files,
            "failed_files": failed_files,
            "total_relationships": total_relationships
        }
        
        print(f"\nNeo4j indexing complete!")
        self.logger.info("Neo4j indexing complete!")
        print(f"Total files: {stats['total_files']}")
        self.logger.info(f"Total files: {stats['total_files']}")
        print(f"Indexed: {stats['indexed_files']}")
        self.logger.info(f"Indexed: {stats['indexed_files']}")
        print(f"Failed: {stats['failed_files']}")
        self.logger.info(f"Failed: {stats['failed_files']}")
        print(f"Total relationships: {stats['total_relationships']}")
        self.logger.info(f"Total relationships: {stats['total_relationships']}")
        
        return stats
    
    def _process_file(self, file_info: Dict[str, Any], root_path: str) -> int:
        """Process a file and create nodes and relationships in Neo4j."""
        file_id = self._generate_file_id(file_info['relative_path'])
        relationships_count = 0
        
        with self.driver.session(database=self.database) as session:
            # Create File node
            file_query = """
            MERGE (f:File {id: $file_id})
            SET f.path = $path,
                f.relative_path = $relative_path,
                f.filename = $filename,
                f.extension = $extension,
                f.size = $size,
                f.content_preview = $content_preview
            RETURN f
            """
            
            content_preview = file_info['content'][:500]  # Store preview
            session.run(
                file_query,
                file_id=file_id,
                path=file_info['path'],
                relative_path=file_info['relative_path'],
                filename=file_info['filename'],
                extension=file_info['extension'],
                size=file_info['size'],
                content_preview=content_preview
            )
            
            # Create relationships based on file structure
            # 1. Directory hierarchy
            relationships_count += self._create_directory_hierarchy(session, file_info, root_path)
            
            # 2. File dependencies (imports/requires)
            relationships_count += self._create_dependencies(session, file_info, file_id)
            
            # 3. Code structure (functions, classes) - basic parsing
            relationships_count += self._create_code_structure(session, file_info, file_id)
        
        return relationships_count
    
    def _create_directory_hierarchy(self, session, file_info: Dict[str, Any], root_path: str) -> int:
        """Create directory hierarchy relationships."""
        path_parts = file_info['relative_path'].split(os.sep)
        relationships = 0
        
        current_path = ""
        prev_node_id = None
        
        for part in path_parts[:-1]:  # Exclude filename
            current_path = os.path.join(current_path, part) if current_path else part
            dir_id = self._generate_file_id(current_path)
            
            # Create Directory node
            dir_query = """
            MERGE (d:Directory {id: $dir_id})
            SET d.path = $path,
                d.name = $name
            RETURN d
            """
            session.run(dir_query, dir_id=dir_id, path=current_path, name=part)
            
            # Create CONTAINS relationship
            if prev_node_id:
                contains_query = """
                MATCH (parent:Directory {id: $parent_id})
                MATCH (child:Directory {id: $child_id})
                MERGE (parent)-[:CONTAINS]->(child)
                """
                session.run(contains_query, parent_id=prev_node_id, child_id=dir_id)
                relationships += 1
            
            prev_node_id = dir_id
        
        # Link file to its parent directory
        if prev_node_id:
            file_id = self._generate_file_id(file_info['relative_path'])
            file_dir_query = """
            MATCH (d:Directory {id: $dir_id})
            MATCH (f:File {id: $file_id})
            MERGE (d)-[:CONTAINS]->(f)
            """
            session.run(file_dir_query, dir_id=prev_node_id, file_id=file_id)
            relationships += 1
        
        return relationships
    
    def _create_dependencies(self, session, file_info: Dict[str, Any], file_id: str) -> int:
        """Extract and create import/dependency relationships."""
        relationships = 0
        content = file_info['content']
        extension = file_info['extension']
        
        # Simple pattern matching for imports
        import_patterns = {
            '.py': [r'^import\s+(\w+)', r'^from\s+(\w+)\s+import'],
            '.js': [r'^import\s+.*from\s+["\']([^"\']+)["\']', r'^const\s+\w+\s*=\s*require\(["\']([^"\']+)["\']\)'],
            '.ts': [r'^import\s+.*from\s+["\']([^"\']+)["\']'],
            '.java': [r'^import\s+([\w.]+)'],
            '.go': [r'^import\s+["\']([^"\']+)["\']'],
        }
        
        imports = set()
        
        for line in content.split('\n'):
            line = line.strip()
            if extension in import_patterns:
                for pattern in import_patterns[extension]:
                    match = re.match(pattern, line)
                    if match:
                        imports.add(match.group(1))
                        break
        
        # Create relationships for imports
        for imp in imports:
            # Try to find the imported file
            import_query = """
            MATCH (f:File {id: $file_id})
            MATCH (target:File)
            WHERE target.filename CONTAINS $import_name
               OR target.relative_path CONTAINS $import_name
            MERGE (f)-[:IMPORTS]->(target)
            """
            result = session.run(import_query, file_id=file_id, import_name=imp)
            if result.single():
                relationships += 1
        
        return relationships
    
    def _create_code_structure(self, session, file_info: Dict[str, Any], file_id: str) -> int:
        """Extract code structure (functions, classes) and create nodes."""
        relationships = 0
        content = file_info['content']
        extension = file_info['extension']
        
        # Simple pattern matching for Python functions and classes
        if extension == '.py':
            # Match function definitions
            function_pattern = r'^def\s+(\w+)\s*\('
            # Match class definitions
            class_pattern = r'^class\s+(\w+)'
            
            for match in re.finditer(function_pattern, content, re.MULTILINE):
                func_name = match.group(1)
                func_id = f"{file_id}__func__{func_name}"
                
                func_query = """
                MATCH (f:File {id: $file_id})
                MERGE (func:Function {id: $func_id})
                SET func.name = $func_name,
                    func.file_id = $file_id
                MERGE (f)-[:DEFINES]->(func)
                """
                session.run(func_query, file_id=file_id, func_id=func_id, func_name=func_name)
                relationships += 1
            
            for match in re.finditer(class_pattern, content, re.MULTILINE):
                class_name = match.group(1)
                class_id = f"{file_id}__class__{class_name}"
                
                class_query = """
                MATCH (f:File {id: $file_id})
                MERGE (c:Class {id: $class_id})
                SET c.name = $class_name,
                    c.file_id = $file_id
                MERGE (f)-[:DEFINES]->(c)
                """
                session.run(class_query, file_id=file_id, class_id=class_id, class_name=class_name)
                relationships += 1
        
        return relationships
    
    def close(self):
        """Close the Neo4j driver connection."""
        if self.driver:
            self.driver.close()
    
    def __enter__(self):
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()


def index_to_neo4j(
    folder_path: str,
    uri: Optional[str] = None,
    user: Optional[str] = None,
    password: Optional[str] = None,
    database: str = "neo4j",
    included_extensions: Optional[List[str]] = None,
    excluded_patterns: Optional[List[str]] = None
) -> Dict[str, Any]:
    """
    Convenience function to index a folder to Neo4j.
    
    Args:
        folder_path: Root directory to index
        uri: Neo4j connection URI (defaults to NEO4J_URI env var)
        user: Neo4j username (defaults to NEO4J_USER env var)
        password: Neo4j password (defaults to NEO4J_PASSWORD env var)
        database: Neo4j database name
        included_extensions: File extensions to include
        excluded_patterns: Patterns to exclude
    
    Returns:
        Dictionary with indexing statistics
    """
    indexer = Neo4jIndexer(uri=uri, user=user, password=password, database=database)
    try:
        return indexer.index_folder(folder_path, included_extensions, excluded_patterns)
    finally:
        indexer.close()
