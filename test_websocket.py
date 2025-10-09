"""
Test WebSocket connectivity for DjenisAiAgent web mode.

This script tests the WebSocket connection to the DjenisAiAgent server.
It connects to the server, sends a test command, and receives responses.

Usage:
    1. Start the server: python main.py --web --host 127.0.0.1 --port 8001
    2. Run this test: python test_websocket.py
"""

import asyncio
import sys

import pytest

try:
    import websockets
except ImportError:
    print("Error: websockets library not installed")
    print("Install it with: pip install websockets")
    sys.exit(1)


pytestmark = pytest.mark.skip(
    reason="WebSocket smoke test requires a running server and user confirmation."
)


async def test_websocket_connection():
    """
    Test the WebSocket connection to DjenisAiAgent.
    
    This function:
    1. Connects to the WebSocket endpoint
    2. Sends a test command
    3. Receives and prints the server's response
    4. Closes the connection
    """
    # Configuration
    host = "127.0.0.1"
    port = 8001
    uri = f"ws://{host}:{port}/ws"
    
    print(f"Testing WebSocket connection to {uri}")
    print("=" * 70)
    
    try:
        # Connect to the WebSocket
        print(f"\n1. Connecting to {uri}...")
        async with websockets.connect(uri) as websocket:
            print("✅ Connected successfully!")
            
            # Send a test command
            test_command = "test command"
            print(f"\n2. Sending command: '{test_command}'")
            await websocket.send(test_command)
            print("✅ Command sent!")
            
            # Receive response
            print("\n3. Waiting for server response...")
            response = await websocket.recv()
            print(f"✅ Received response: {response}")
            
            print("\n" + "=" * 70)
            print("✅ WebSocket test completed successfully!")
            print("\nThe WebSocket connection is working correctly.")
            print("You can now build your frontend to interact with the server.")
            
    except websockets.exceptions.WebSocketException as e:
        print(f"\n❌ WebSocket error: {e}")
        print("\nPossible causes:")
        print("  1. Server is not running")
        print("  2. Wrong host or port")
        print("  3. Network connectivity issues")
        print(f"\nMake sure the server is running with:")
        print(f"  python main.py --web --host {host} --port {port}")
        sys.exit(1)
        
    except Exception as e:
        print(f"\n❌ Unexpected error: {e}")
        sys.exit(1)


async def test_multiple_messages():
    """
    Test sending multiple messages through WebSocket.
    
    This function demonstrates:
    - Maintaining a persistent connection
    - Sending multiple commands sequentially
    - Receiving multiple responses
    """
    host = "127.0.0.1"
    port = 8001
    uri = f"ws://{host}:{port}/ws"
    
    print(f"\n\nTesting multiple messages to {uri}")
    print("=" * 70)
    
    try:
        async with websockets.connect(uri) as websocket:
            print("✅ Connected!")
            
            # Send multiple test commands
            commands = [
                "test command 1",
                "test command 2",
                "test command 3"
            ]
            
            for i, cmd in enumerate(commands, 1):
                print(f"\n{i}. Sending: '{cmd}'")
                await websocket.send(cmd)
                
                response = await websocket.recv()
                print(f"   Received: {response}")
            
            print("\n" + "=" * 70)
            print("✅ Multiple messages test completed successfully!")
            
    except Exception as e:
        print(f"\n❌ Error: {e}")
        sys.exit(1)


async def main():
    """
    Main test function that runs all WebSocket tests.
    """
    print("\n" + "=" * 70)
    print("  DjenisAiAgent WebSocket Connectivity Test")
    print("=" * 70)
    print("\nThis script will test the WebSocket connection to the server.")
    print("Make sure the server is running before proceeding!")
    print("\nStart the server with:")
    print("  python main.py --web --host 127.0.0.1 --port 8001")
    print("\n" + "=" * 70)
    
    # Wait for user to confirm
    try:
        input("\nPress ENTER when the server is running (or CTRL+C to cancel)...")
    except KeyboardInterrupt:
        print("\n\nTest cancelled by user.")
        sys.exit(0)
    
    # Run tests
    try:
        # Test 1: Basic connection and single message
        await test_websocket_connection()
        
        # Test 2: Multiple messages
        await test_multiple_messages()
        
        print("\n\n" + "=" * 70)
        print("🎉 All tests passed!")
        print("=" * 70)
        print("\nYour WebSocket server is ready for integration!")
        
    except KeyboardInterrupt:
        print("\n\nTests interrupted by user.")
        sys.exit(0)


if __name__ == "__main__":
    # Run the async main function
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n\nExiting...")
        sys.exit(0)
