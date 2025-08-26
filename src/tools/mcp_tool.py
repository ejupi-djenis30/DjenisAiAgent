import json
import socket
import time
from typing import Dict, Any, Optional, Union

class MCPTool:
    """
    A tool for interacting with a Model Context Protocol (MCP) server.
    Implements the basic MCP client functionality for connecting to and communicating with an MCP server.
    """
    def __init__(self, host: str = "localhost", port: int = 8080, timeout: float = 30.0):
        """
        Initialize the MCP tool with connection parameters.
        
        Args:
            host: The hostname or IP address of the MCP server
            port: The port number the MCP server is listening on
            timeout: Connection timeout in seconds
        """
        self.host = host
        self.port = port
        self.timeout = timeout
        self.socket = None
        self.connected = False
        self.request_id = 0
    
    def connect_to_server(self) -> bool:
        """
        Establishes a connection to the MCP server.
        
        Returns:
            True if connection was successful, False otherwise
        """
        try:
            self.socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.socket.settimeout(self.timeout)
            self.socket.connect((self.host, self.port))
            self.connected = True
            return True
        except Exception as e:
            print(f"Failed to connect to MCP server: {str(e)}")
            self.connected = False
            return False
    
    def send_command(self, method: str, params: Dict[str, Any]) -> Dict[str, Any]:
        """
        Sends a command to the MCP server and waits for a response.
        
        Args:
            method: The MCP method name to call
            params: Parameters for the method call
            
        Returns:
            The response from the server as a dictionary
        """
        if not self.connected:
            if not self.connect_to_server():
                return {"error": "Not connected to MCP server"}
        
        self.request_id += 1
        request = {
            "jsonrpc": "2.0",
            "id": self.request_id,
            "method": method,
            "params": params
        }
        
        try:
            # Send the request
            request_json = json.dumps(request) + "\n"
            self.socket.sendall(request_json.encode('utf-8'))
            
            # Receive the response
            response_data = b""
            while True:
                chunk = self.socket.recv(4096)
                if not chunk:
                    break
                response_data += chunk
                if b"\n" in chunk:
                    break
            
            # Parse the response
            response_str = response_data.decode('utf-8').strip()
            response = json.loads(response_str)
            
            return response
        except Exception as e:
            print(f"Error during MCP communication: {str(e)}")
            self.connected = False
            return {"error": str(e)}
    
    def receive_response(self) -> Dict[str, Any]:
        """
        Receives a response from the MCP server.
        
        Returns:
            The response as a dictionary
        """
        if not self.connected:
            return {"error": "Not connected to MCP server"}
        
        try:
            data = b""
            while True:
                chunk = self.socket.recv(4096)
                if not chunk:
                    break
                data += chunk
                if b"\n" in chunk:
                    break
            
            response_str = data.decode('utf-8').strip()
            return json.loads(response_str)
        except Exception as e:
            print(f"Error receiving MCP response: {str(e)}")
            self.connected = False
            return {"error": str(e)}
    
    def disconnect(self) -> bool:
        """
        Disconnects from the MCP server.
        
        Returns:
            True if disconnection was successful, False otherwise
        """
        if self.socket:
            try:
                self.socket.close()
                self.connected = False
                return True
            except Exception as e:
                print(f"Error disconnecting from MCP server: {str(e)}")
                return False
        return True