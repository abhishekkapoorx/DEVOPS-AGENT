"""
Pinecone indexing module for codebase indexing.
"""

import os
from typing import List, Dict, Any, Optional
from pinecone import Pinecone, ServerlessSpec
from langchain_text_splitters import RecursiveCharacterTextSplitter
from sentence_transformers import SentenceTransformer
from dotenv import load_dotenv
from tqdm import tqdm

from .utils import get_code_files, get_logger

load_dotenv()


class PineconeIndexer:
    """Handles indexing of code files to Pinecone."""
    
    def __init__(
        self,
        api_key: Optional[str] = None,
        index_name: str = "codebase-index",
        dimension: int = 384,
        environment: str = "us-east-1",
        embedding_model: str = "all-MiniLM-L6-v2"
    ):
        """
        Initialize Pinecone indexer.
        
        Args:
            api_key: Pinecone API key (defaults to PINECONE_API_KEY env var)
            index_name: Name of the Pinecone index
            dimension: Dimension of embeddings (default 384 for all-MiniLM-L6-v2)
            environment: Pinecone environment/region
            embedding_model: Sentence transformer model name
        """
        self.api_key = api_key or os.getenv("PINECONE_API_KEY")
        if not self.api_key:
            raise ValueError("Pinecone API key is required. Set PINECONE_API_KEY environment variable.")

        
        self.index_name = index_name
        self.dimension = dimension
        self.environment = environment
        self.logger = get_logger(__name__)
        
        # Initialize Pinecone
        self.pc = Pinecone(api_key=self.api_key)
        
        # Initialize embedding model
        print(f"Loading embedding model: {embedding_model}")
        self.logger.info(f"Loading embedding model: {embedding_model}")
        self.embedding_model = SentenceTransformer(embedding_model)
        
        # Initialize text splitter
        self.text_splitter = RecursiveCharacterTextSplitter(
            chunk_size=1000,
            chunk_overlap=300,
            length_function=len,
            # separators=["\n\n", "\n", " ", ""]
        )
        
        # Initialize or connect to index
        self._setup_index()
    
    def _setup_index(self):
        """Setup or connect to Pinecone index."""
        existing_indexes = [index.name for index in self.pc.list_indexes()]
        
        if self.index_name not in existing_indexes:
            print(f"Creating new Pinecone index: {self.index_name}")
            self.logger.info(f"Creating new Pinecone index: {self.index_name}")
            self.pc.create_index(
                name=self.index_name,
                dimension=self.dimension,
                metric="cosine",
                spec=ServerlessSpec(
                    cloud="aws",
                    region=self.environment
                )
            )
            # Wait for index to be ready
            import time
            while self.index_name not in [index.name for index in self.pc.list_indexes()]:
                time.sleep(1)
        
        self.index = self.pc.Index(self.index_name)
        print(f"Connected to Pinecone index: {self.index_name}")
        self.logger.info(f"Connected to Pinecone index: {self.index_name}")
    
    def _generate_embedding(self, text: str) -> List[float]:
        """Generate embedding for text."""
        return self.embedding_model.encode(text, show_progress_bar=False).tolist()
    
    def index_folder(
        self,
        folder_path: str,
        included_extensions: Optional[List[str]] = None,
        excluded_patterns: Optional[List[str]] = None,
        batch_size: int = 32
    ) -> Dict[str, Any]:
        """
        Index all code files in a folder to Pinecone.
        
        Args:
            folder_path: Root directory to index
            included_extensions: File extensions to include
            excluded_patterns: Patterns to exclude
            batch_size: Batch size for upsert operations
        
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
        
        total_chunks = 0
        indexed_files = 0
        failed_files = 0
        
        # Process files in batches
        for file_info in tqdm(files, desc="Indexing files"):
            try:
                chunks = self._process_file(file_info)
                if chunks:
                    self._upsert_chunks(chunks, batch_size)
                    total_chunks += len(chunks)
                    indexed_files += 1
                else:
                    failed_files += 1
            except Exception as e:
                print(f"Error indexing file {file_info['path']}: {e}")
                self.logger.warning(f"Error indexing file {file_info['path']}: {e}")
                failed_files += 1
                continue
        
        stats = {
            "total_files": len(files),
            "indexed_files": indexed_files,
            "failed_files": failed_files,
            "total_chunks": total_chunks,
            "index_name": self.index_name
        }
        
        print(f"\nIndexing complete!")
        self.logger.info("Indexing complete!")
        print(f"Total files: {stats['total_files']}")
        self.logger.info(f"Total files: {stats['total_files']}")
        print(f"Indexed: {stats['indexed_files']}")
        self.logger.info(f"Indexed: {stats['indexed_files']}")
        print(f"Failed: {stats['failed_files']}")
        self.logger.info(f"Failed: {stats['failed_files']}")
        print(f"Total chunks: {stats['total_chunks']}")
        self.logger.info(f"Total chunks: {stats['total_chunks']}")
        
        return stats
    
    def _process_file(self, file_info: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Process a file into chunks with metadata."""
        chunks = []
        text_chunks = self.text_splitter.split_text(file_info['content'])
        
        for idx, chunk_text in enumerate(text_chunks):
            chunk_id = f"{file_info['relative_path']}__chunk_{idx}"
            
            chunks.append({
                "id": chunk_id,
                "values": self._generate_embedding(chunk_text),
                "metadata": {
                    "file_path": file_info['relative_path'],
                    "absolute_path": file_info['path'],
                    "filename": file_info['filename'],
                    "extension": file_info['extension'],
                    "chunk_index": idx,
                    "chunk_text": chunk_text,
                    "file_size": file_info['size']
                }
            })
        
        return chunks
    
    def _upsert_chunks(self, chunks: List[Dict[str, Any]], batch_size: int):
        """Upsert chunks to Pinecone in batches."""
        for i in range(0, len(chunks), batch_size):
            batch = chunks[i:i + batch_size]
            self.index.upsert(vectors=batch)
    
    def search(self, query: str, top_k: int = 5, filter_dict: Optional[Dict] = None) -> List[Dict[str, Any]]:
        """
        Search the index.
        
        Args:
            query: Search query text
            top_k: Number of results to return
            filter_dict: Optional metadata filter
        
        Returns:
            List of search results with metadata
        """
        query_embedding = self._generate_embedding(query)
        
        results = self.index.query(
            vector=query_embedding,
            top_k=top_k,
            include_metadata=True,
            filter=filter_dict
        )
        
        formatted_results = []
        for match in results.matches:
            formatted_results.append({
                "score": match.score,
                "file_path": match.metadata.get("file_path"),
                "filename": match.metadata.get("filename"),
                "chunk_text": match.metadata.get("chunk_text"),
                "chunk_index": match.metadata.get("chunk_index")
            })
        
        return formatted_results


def index_to_pinecone(
    folder_path: str,
    api_key: Optional[str] = None,
    index_name: str = "codebase-index",
    included_extensions: Optional[List[str]] = None,
    excluded_patterns: Optional[List[str]] = None
) -> Dict[str, Any]:
    """
    Convenience function to index a folder to Pinecone.
    
    Args:
        folder_path: Root directory to index
        api_key: Pinecone API key (defaults to PINECONE_API_KEY env var)
        index_name: Name of the Pinecone index
        included_extensions: File extensions to include
        excluded_patterns: Patterns to exclude
    
    Returns:
        Dictionary with indexing statistics
    """

    EMBEDDING_MODEL = os.getenv("EMBEDDING_MODEL", "all-MiniLM-L6-v2")
    EMBEDDING_DIMENSION = int(os.getenv("EMBEDDING_DIMENSION", 384))
    indexer = PineconeIndexer(api_key=api_key, index_name=index_name, embedding_model=EMBEDDING_MODEL, dimension=EMBEDDING_DIMENSION)
    return indexer.index_folder(folder_path, included_extensions, excluded_patterns, batch_size=16)


