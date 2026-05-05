# Todo

## Plan
Start by implementing the DTX protocol layer since it has comprehensive tests and represents the core communication mechanism. Then build the USBMux layer for device discovery, followed by the ServiceConnection for general TCP/TLS communication. Finally, add OS utilities and CLI support.

## Tasks
- [x] Task 1: Implement DTX fragment and fragmenter for message assembly and disassembly (allows splitting large messages into fragments and reassembling them, supporting both in-order and out-of-order fragment arrival)
- [x] Task 2: Implement DTX message types and NS types for encoding/decoding payloads (DTXMessage with aux arguments, NSError, NSUUID and other Objective-C type proxies used in NSKeyedArchive serialization)
- [x] Task 3: Implement DTX primitive types and message aux for auxiliary argument encoding (primitive dictionary wire format with type codes for null, string, buffer, int32, int64, double)
- [x] Task 4: Implement DTX sender mixin for outgoing message handling (send reply, notification, dispatch methods with proper message type handling)
- [x] Task 5: Implement USBMux connection for device enumeration and connection (PlistMuxConnection for modern protocol, device state tracking, connect/listen operations)
- [>] Task 6: Implement ServiceConnection for TCP/TLS communication with device services (plist send/recv, SSL upgrade, socket management)
- [ ] Task 7: Implement OS utilities for cross-platform support (Windows/Linux/macOS socket keepalive, usbmux address resolution)
- [ ] Task 8: Implement CLI syslog module with live streaming and filtering capabilities (message filtering, output formatting, process name matching)
