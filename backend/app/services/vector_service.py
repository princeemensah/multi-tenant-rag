"""Vector store service placeholder."""


class QdrantVectorService:
    """Coordinates vector store interactions."""

    async def init_collection(self) -> None:
        return None

    async def health_check(self) -> bool:
        return True
