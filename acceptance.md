# Acceptance Criteria

## Task 1: DTX Fragment and Fragmenter

### Acceptance Criteria
- [ ] DTXFragment dataclass stores index, count, data_size, identifier, conversation_index, channel_code, flags, and payload fields
- [ ] DTXFragment.chunks() returns serializable wire format (header + payload memoryview list)
- [ ] DTXFragmenter constructor validates data_size > 0 and raises error on zero data_size
- [ ] DTXFragmenter constructor validates total size <= MAX_MESSAGE_SIZE (128 MiB)
- [ ] DTXFragmenter constructor validates current_buffered + total <= max_buffered_size
- [ ] DTXFragmenter.add() writes fragment payload to pre-allocated buffer and returns True when all fragments received
- [ ] DTXFragmenter.add() raises error on duplicate fragment index
- [ ] DTXFragmenter.add() raises error when payload would exceed declared size
- [ ] DTXFragmenter.assemble() returns zero-copy buffer when fragments arrive in order
- [ ] DTXFragmenter.assemble() returns reordered buffer when fragments arrive out of order
- [ ] DTXFragmenter.fragment() static method splits large payloads into multiple fragments
- [ ] DTXFragmenter.fragment() returns single fragment for payloads <= MAX_FRAGMENT_SIZE (128 KiB)
- [ ] DTXFragmenter.fragment() uses zero-copy (memoryview slicing) when possible
- [ ] DTXFragmenter.fragment() raises error when payload > MAX_MESSAGE_SIZE
- [ ] Protocol constants defined: MAX_MESSAGE_SIZE = 128 MiB, MAX_FRAGMENT_SIZE = 128 KiB
- [ ] DTXProtocolError exception for protocol violations
