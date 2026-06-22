from node.errors import ValidationError

MAX_BLOCK_ID_LEN = 256
MAX_DATA_BYTES = 1_048_576


def validate_block_id(block_id):
    if not block_id or not isinstance(block_id, str):
        raise ValidationError("block_id must be a non-empty string")
    if len(block_id) > MAX_BLOCK_ID_LEN:
        raise ValidationError("block_id too long")


def validate_write(block_id, data, version):
    validate_block_id(block_id)
    if not isinstance(data, str):
        raise ValidationError("data must be str")
    if len(data.encode("utf-8")) > MAX_DATA_BYTES:
        raise ValidationError("data exceeds max size")
    if version is not None and version < 1:
        raise ValidationError("version must be >= 1")


def validate_delete(block_id):
    validate_block_id(block_id)
