# main.py
import os
from dotenv import load_dotenv

import cocoindex
# psycopg connection pool (used in many CocoIndex examples)
from psycopg_pool import ConnectionPool

# -------------------------
# 1) Flow and helpers
# -------------------------

@cocoindex.flow_def(name="CodeEmbedding")
def code_embedding_flow(flow_builder: cocoindex.FlowBuilder, data_scope: cocoindex.DataScope):
    """
    Ingest files, chunk with tree-sitter, embed, and collect to export.
    """
    # adjust path to point to the codebase root you want to index
    data_scope["files"] = flow_builder.add_source(
        cocoindex.sources.LocalFile(
            path=os.path.join("..", ".."),
            included_patterns=["*.py", "*.rs", "*.toml", "*.md", "*.mdx"],
            excluded_patterns=[".*", "target", "**/node_modules"],
        )
    )
    code_embeddings = data_scope.add_collector()

    @cocoindex.op.function()
    def extract_extension(filename: str) -> str:
        """Return file extension (like .py, .rs)."""
        return os.path.splitext(filename)[1].lstrip(".")

    with data_scope["files"].row() as file:
        # language/extension used by Tree-sitter
        file["extension"] = file["filename"].transform(extract_extension)
        # split by syntax using Tree-sitter; chunk_size and overlap are adjustable
        file["chunks"] = file["content"].transform(
            cocoindex.functions.SplitRecursively(),
            language=file["extension"],
            chunk_size=1000,
            chunk_overlap=300,
        )

        # embed each chunk and collect
        with file["chunks"].row() as chunk:
            chunk["embedding"] = chunk["text"].call(code_to_embedding)
            code_embeddings.collect(
                filename=file["filename"],
                location=chunk["location"],
                code=chunk["text"],
                embedding=chunk["embedding"],
            )

# -------------------------
# 2) Embedding transform (shared between index + query)
# -------------------------

@cocoindex.transform_flow()
def code_to_embedding(text: cocoindex.DataSlice[str]) -> cocoindex.DataSlice[list[float]]:
    """
    Use a SentenceTransformer model to embed text chunks.
    Swap in any HF SentenceTransformer you prefer.
    """
    return text.transform(
        cocoindex.functions.SentenceTransformerEmbed(
            model="sentence-transformers/all-MiniLM-L6-v2"
        )
    )

# -------------------------
# 3) Export config
# -------------------------

# Export happens when you run the CocoIndex update command.
# The export below is how the blog stores embeddings into Postgres + vector index.
def export_config():
    code_embeddings = cocoindex.DataCollectorRef("code_embeddings")  # placeholder ref
    # when you run `cocoindex update --setup main` the actual collector from the flow
    # will be exported using the same options below (this is illustrative).
    code_embeddings.export(
        "code_embeddings",
        cocoindex.storages.Postgres(),
        primary_key_fields=["filename", "location"],
        vector_indexes=[
            cocoindex.VectorIndex(
                "embedding", cocoindex.VectorSimilarityMetric.COSINE_SIMILARITY
            )
        ],
    )

# -------------------------
# 4) Query helper (SQL against Postgres vector column)
# -------------------------
def search(pool: ConnectionPool, query: str, top_k: int = 5):
    """
    Compute embedding for the query (re-uses the transform flow)
    and run a SQL similarity query against the exported table.
    """
    # get the actual table name the flow exported to
    table_name = cocoindex.utils.get_target_storage_default_name(
        code_embedding_flow, "code_embeddings"
    )

    # evaluate the transform flow to get a vector for the query
    query_vector = code_to_embedding.eval(query)

    # run SQL: this uses the pgvector operator `<=>` returning distance
    with pool.connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                f"""
                SELECT filename, code, embedding <=> %s::vector AS distance
                FROM {table_name}
                ORDER BY distance
                LIMIT %s
                """,
                (query_vector, top_k),
            )
            rows = cur.fetchall()
            return [
                {"filename": r[0], "code": r[1], "score": 1.0 - r[2]} for r in rows
            ]

# -------------------------
# 5) Interactive main
# -------------------------
def main():
    load_dotenv()
    cocoindex.init()  # initialize cocoindex runtime

    db_url = os.getenv("COCOINDEX_DATABASE_URL")
    if not db_url:
        raise RuntimeError(
            "Set COCOINDEX_DATABASE_URL (eg: postgresql://user:pass@host:5432/dbname) in .env"
        )

    # create a simple connection pool for Postgres
    pool = ConnectionPool(conninfo=db_url)

    print("Type a query and press Enter. Empty input to quit.")
    try:
        while True:
            query = input("Search query (or Enter to quit): ").strip()
            if query == "":
                break
            results = search(pool, query, top_k=5)
            print("\nSearch results:")
            for r in results:
                print(f"[{r['score']:.3f}] {r['filename']}")
                print(r["code"])
                print("---")
            print()
    except KeyboardInterrupt:
        print("\nBye!")

if __name__ == "__main__":
    main()
