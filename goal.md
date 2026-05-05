# Goal

## Project
pymobiledevice3 - a pure Python 3 implementation for interacting with iOS devices (iPhone, iPad, etc).

## Description
A library that provides both a CLI and a Python API for communicating with iOS devices over USB (via usbmuxd) or network connections. The core functionality includes:
- Device discovery and enumeration through usbmuxd (USB multiplexer daemon)
- DTX (Data Transfer protocol) for communicating with device services - enables fragmentation, message assembly, and auxiliary argument encoding
- Service connection wrapper for TCP/TLS communication with device services
- Plist-based message encoding/decoding for Apple protocol communication
- Cross-platform support (Windows, Linux, macOS) with OS-specific utilities

## Scope
- 15+ production source files to implement (core protocol and infrastructure)
- 5+ test files to write covering the main functionality
- Focus on core components: USBMux, DTX protocol, ServiceConnection, and supporting utilities
