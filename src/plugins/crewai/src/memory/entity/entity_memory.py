from src.plugins.crewai.src.memory.entity.entity_memory_item import EntityMemoryItem
from src.plugins.crewai.src.memory.memory import Memory
from src.plugins.crewai.src.memory.storage.rag_storage import RAGStorage


class EntityMemory(Memory):
    """
    EntityMemory class for managing structured information about entities
    and their relationships using SQLite storage.
    Inherits from the Memory class.
    """

    def __init__(self, crew=None, embedder_config=None):
        storage = RAGStorage(
            type="entities", allow_reset=False, embedder_config=embedder_config, crew=crew
        )
        super().__init__(storage)

    def save(self, item: EntityMemoryItem) -> None:  # type: ignore # BUG?: Signature of "save" incompatible with supertype "Memory"
        """Saves an entity item into the SQLite storage."""
        data = f"{item.name}({item.type}): {item.description}"
        super().save(data, item.metadata)
