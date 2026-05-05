# Acceptance Criteria

## Task 1: DTX Fragment and Fragmenter

### Acceptance Criteria
- [x] DTXFragment dataclass stores index, count, data_size, identifier, conversation_index, channel_code, flags, and payload fields
- [x] DTXFragment.chunks() returns serializable wire format (header + payload memoryview list)
- [x] DTXFragmenter constructor validates data_size > 0 and raises error on zero data_size
- [x] DTXFragmenter constructor validates total size <= MAX_MESSAGE_SIZE (128 MiB)
- [x] DTXFragmenter constructor validates current_buffered + total <= max_buffered_size
- [x] DTXFragmenter.add() writes fragment payload to pre-allocated buffer and returns True when all fragments received
- [x] DTXFragmenter.add() raises error on duplicate fragment index
- [x] DTXFragmenter.add() raises error when payload would exceed declared size
- [x] DTXFragmenter.assemble() returns zero-copy buffer when fragments arrive in order
- [x] DTXFragmenter.assemble() returns reordered buffer when fragments arrive out of order
- [x] DTXFragmenter.fragment() static method splits large payloads into multiple fragments
- [x] DTXFragmenter.fragment() returns single fragment for payloads <= MAX_FRAGMENT_SIZE (128 KiB)
- [x] DTXFragmenter.fragment() uses zero-copy (memoryview slicing) when possible
- [x] DTXFragmenter.fragment() raises error when payload > MAX_MESSAGE_SIZE
- [x] Protocol constants defined: MAX_MESSAGE_SIZE = 128 MiB, MAX_FRAGMENT_SIZE = 128 KiB
- [x] DTXProtocolError exception for protocol violations

## Task 2: DTX Message Types and NS Types

### Acceptance Criteria
- [ ] Message type enumeration with OK, DATA, DISPATCH, OBJECT, ERROR, etc.
- [ ] NSError class stores code, domain, and user_info dictionary
- [ ] NSError can be encoded to and decoded from NSKeyedArchive format
- [ ] NSUUID wrapper generates random UUIDs and encodes/decodes correctly
- [ ] NSNull decodes to Python None
- [ ] NSURL stores base and relative URL components
- [ ] NSDate stores timestamp relative to Cocoa epoch (2001-01-01) and converts to datetime
- [ ] NSMutableData decodes raw byte data
- [ ] NSMutableString decodes string values
- [ ] All NS types registered with bpylist2 archiver for automatic deserialization
