from ingestion.pipeline.load_qdrant import COLLECTION_NAME, collection_name_for_dim


def test_offline_embedding_keeps_legacy_collection_name():
    assert collection_name_for_dim(128) == COLLECTION_NAME


def test_online_embedding_uses_dimension_specific_collection():
    assert collection_name_for_dim(1536) == "biology_chunks_1536"
