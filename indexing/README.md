# Codebase Indexing Module

This module provides functionality to index codebases on Pinecone (vector database) and Neo4j (knowledge graph).

## Features

- **Pinecone Indexing**: Index code files with embeddings using recursive text character splitter
- **Neo4j Knowledge Graph**: Create knowledge graphs representing code structure, dependencies, and relationships
- **Recursive File Scanning**: Automatically scans folders recursively for code files
- **Multiple File Formats**: Supports various programming languages and file types

## Installation

Install the required dependencies:

```bash
pip install pinecone-client neo4j sentence-transformers langchain-text-splitters tqdm
```

Or install from the main requirements.txt which includes these packages.

## Environment Variables

Set the following environment variables in your `.env` file:

### Pinecone
```
PINECONE_API_KEY=your_pinecone_api_key
```

### Neo4j
```
NEO4J_URI=bolt://localhost:7687
NEO4J_USER=neo4j
NEO4J_PASSWORD=your_neo4j_password
```

## Usage

### Command Line

Run the indexing script:

```bash
python -m indexing.main [folder_path]
```

If no folder path is provided, you'll be prompted to enter one.

### Programmatic Usage

#### Index to Pinecone

```python
from indexing.pinecone_indexer import index_to_pinecone

stats = index_to_pinecone(
    folder_path="/path/to/codebase",
    index_name="codebase-index",
    included_extensions=[".py", ".js", ".ts"],
    excluded_patterns=["node_modules", ".git"]
)
```

#### Index to Neo4j

```python
from indexing.neo4j_indexer import index_to_neo4j

stats = index_to_neo4j(
    folder_path="/path/to/codebase",
    database="neo4j",
    included_extensions=[".py", ".js", ".ts"],
    excluded_patterns=["node_modules", ".git"]
)
```

#### Index to Both

```python
from indexing.main import index_codebase

results = index_codebase(
    folder_path="/path/to/codebase",
    index_pinecone=True,
    index_neo4j=True
)
```

### Using the Classes Directly

For more control, use the classes directly:

```python
from indexing.pinecone_indexer import PineconeIndexer
from indexing.neo4j_indexer import Neo4jIndexer

# Pinecone
pinecone_indexer = PineconeIndexer(
    api_key="your_key",
    index_name="codebase-index"
)
stats = pinecone_indexer.index_folder("/path/to/codebase")

# Search in Pinecone
results = pinecone_indexer.search("function to handle authentication", top_k=5)

# Neo4j
with Neo4jIndexer(uri="bolt://localhost:7687", user="neo4j", password="password") as neo4j_indexer:
    stats = neo4j_indexer.index_folder("/path/to/codebase")
```

## Configuration

### Default File Extensions

By default, the following file extensions are indexed:
- `.py`, `.js`, `.ts`, `.jsx`, `.tsx`, `.java`, `.cpp`, `.c`, `.h`
- `.go`, `.rs`, `.rb`, `.php`, `.swift`, `.kt`, `.scala`
- `.md`, `.txt`, `.json`, `.yaml`, `.yml`, `.toml`, `.sh`, `.bash`

### Default Excluded Patterns

The following patterns are excluded by default:
- `.git`, `node_modules`, `__pycache__`, `.venv`, `venv`, `env`
- `target`, `dist`, `build`, `.next`, `.cache`

### Text Splitting

Uses `RecursiveCharacterTextSplitter` from LangChain with:
- Chunk size: 1000 characters
- Chunk overlap: 200 characters
- Separators: `["\n\n", "\n", " ", ""]`

### Embeddings

Uses Sentence Transformers model: `all-MiniLM-L6-v2` (384 dimensions)

## Neo4j Knowledge Graph Structure

The Neo4j index creates the following node types and relationships:

### Node Types
- **File**: Represents code files with metadata (path, extension, size, content preview)
- **Directory**: Represents directory structure
- **Function**: Extracted function definitions (Python)
- **Class**: Extracted class definitions (Python)

### Relationships
- **CONTAINS**: Directory → Directory, Directory → File
- **IMPORTS**: File → File (dependency relationships)
- **DEFINES**: File → Function, File → Class

## Pinecone Index Structure

Each chunk in Pinecone contains:
- **ID**: Unique identifier (`{file_path}__chunk_{index}`)
- **Vector**: Embedding vector (384 dimensions)
- **Metadata**:
  - `file_path`: Relative file path
  - `absolute_path`: Absolute file path
  - `filename`: File name
  - `extension`: File extension
  - `chunk_index`: Chunk index in file
  - `chunk_text`: The actual text chunk
  - `file_size`: Size of the source file

## Examples

### Search in Pinecone

```python
from indexing.pinecone_indexer import PineconeIndexer

indexer = PineconeIndexer(index_name="codebase-index")
results = indexer.search("authentication function", top_k=5)

for result in results:
    print(f"Score: {result['score']}")
    print(f"File: {result['file_path']}")
    print(f"Chunk: {result['chunk_text'][:100]}...")
    print("---")
```

### Query Neo4j

```python
from neo4j import GraphDatabase

driver = GraphDatabase.driver("bolt://localhost:7687", auth=("neo4j", "password"))

with driver.session() as session:
    # Find all files that import a specific module
    result = session.run("""
        MATCH (f:File)-[:IMPORTS]->(target:File)
        WHERE target.filename CONTAINS 'auth'
        RETURN f.path, target.filename
        LIMIT 10
    """)
    
    for record in result:
        print(f"{record['f.path']} imports {record['target.filename']}")
```

## Error Handling

The indexing process includes comprehensive error handling:
- Individual file failures don't stop the indexing process
- Failed files are reported in the statistics
- Connection errors are raised immediately with clear messages

## Performance Considerations

- Files are processed sequentially to avoid memory issues
- Pinecone batches upserts (default batch size: 100)
- Neo4j uses transactions for efficient writes
- Progress bars show indexing status using `tqdm`

## Notes

- Large codebases may take significant time to index
- Ensure sufficient Pinecone pod capacity for large indexes
- Neo4j database should have adequate memory for large graphs
- Text splitting preserves code context with overlapping chunks



