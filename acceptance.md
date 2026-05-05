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
- [x] Message type enumeration with OK, DATA, DISPATCH, OBJECT, ERROR, etc.
- [x] NSError class stores code, domain, and user_info dictionary
- [x] NSError can be encoded to and decoded from NSKeyedArchive format
- [x] NSUUID wrapper generates random UUIDs and encodes/decodes correctly
- [x] NSNull decodes to Python None
- [x] NSURL stores base and relative URL components
- [x] NSDate stores timestamp relative to Cocoa epoch (2001-01-01) and converts to datetime
- [x] NSMutableData decodes raw byte data
- [x] NSMutableString decodes string values
- [x] All NS types registered with bpylist2 archiver for automatic deserialization

## Task 3: DTX Primitive Types and Message Aux

### Acceptance Criteria
- [x] Primitive type base class with type code and serialization interface
- [x] PrimitiveNull (type code 10) as positional marker, serializes as just type tag
- [x] PrimitiveString (type code 1) for UTF-8 strings with length prefix
- [x] PrimitiveBuffer (type code 2) for raw bytes with length prefix
- [x] PrimitiveInt32 (type code 3) for 32-bit signed integers
- [x] PrimitiveInt64 (type code 6) for 64-bit signed integers
- [x] PrimitiveDouble (type code 9) for IEEE-754 double values
- [x] PrimitiveDictionary (type code 0xF0) for key-value pairs with body length header
- [x] MessageAux parser extracts list of arguments from primitive dictionary
- [x] MessageAux builder encodes argument list into wire format
- [x] Non-primitive arguments archived using NSKeyedArchive into PrimitiveBuffer
- [x] Empty argument list produces empty bytes (no output)

## Task 4: DTX Sender Mixin

### Acceptance Criteria
- [x] Message dataclass with type, identifier, conversation_index, channel_code, flags, aux_data, payload_data
- [x] Message.chunks() returns wire format header + aux + payload
- [x] Message validates that OK messages have no payload
- [x] Message validates that ERROR messages have payload and no aux
- [x] Message validates that replies have type OK, OBJECT, or ERROR
- [x] Sender tracks pending replies by message identifier
- [x] Sender assigns unique message identifiers to outgoing messages
- [x] send_dispatch() creates DISPATCH message with method name as payload and args as aux
- [x] send_notification() creates OBJECT message with payload
- [x] send_reply() creates OBJECT reply with payload
- [x] send_reply_ack() creates OK reply with no payload
- [x] send_reply_error() creates ERROR reply with NSError payload

## Task 5: USBMux Connection

### Acceptance Criteria
- [ ] MuxDevice represents a connected device with UDID, connection type, and serial number
- [ ] MuxConnection base class for usbmuxd socket communication
- [ ] Plist protocol support for sending and receiving plist messages
- [ ] list_devices() returns all currently connected devices
- [ ] connect() establishes a connection to a device port
- [ ] Device enumeration through usbmuxd daemon
- [ ] Support for both USB and network connection types
- [ ] Proper socket cleanup and error handling
