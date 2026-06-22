from node.storage_engine import StorageEngine

with StorageEngine("./data", node_id="node1") as engine:
    engine.write("invoice-1", "jay data")
    print(engine.read("invoice-1"))
    print(engine.get_stats())
