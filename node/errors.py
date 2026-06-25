class StorageError(Exception):
    """Base class for storage engine errors."""


class OplogCorruptionError(StorageError):
    def __init__(self, line_no, cause):
        self.line_no = line_no
        self.cause = cause
        super().__init__(f"oplog corruption at line {line_no}: {cause}")


class DataCorruptionError(StorageError):
    def __init__(self, block_id):
        self.block_id = block_id
        super().__init__(f"data corruption for block {block_id}")


class VersionConflictError(StorageError):
    def __init__(self, block_id, requested, current):
        self.block_id = block_id
        self.requested = requested
        self.current = current
        super().__init__(
            f"version conflict for {block_id}: "
            f"requested {requested}, current {current}"
        )


class ValidationError(StorageError):
    pass


class QuorumNotSatisfiedError(StorageError):
    def __init__(self, block_id, acks, required, failed_nodes=None):
        self.block_id = block_id
        self.acks = acks
        self.required = required
        self.failed_nodes = failed_nodes or []
        super().__init__(
            f"write quorum not satisfied for {block_id}: "
            f"{acks}/{required} acknowledgements"
        )
