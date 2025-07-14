import socket
import struct
import numpy as np
import time


def handshake_and_get_info(udpSock, host, port, max_retries, retry_delay):
    """
    @brief Performs a UDP handshake with a specified server to retrieve camera information.

    This function establishes a handshake process with a UDP server at the given `host` and `port`. 
    The handshake follows these steps:
    
    1. The client sends a "REQ" message to initiate the handshake.
    2. The server responds with either:
       - "NOTREADY": The client waits and retries.
       - "READY": The client proceeds to receive camera information.
    3. If "READY" is received:
       - The client expects a second message containing camera details.
       - If successfully received, the client parses and acknowledges ("ACK") the message.
       - The extracted camera information is returned as a dictionary.
    4. The process is retried up to `max_retries` times with `retry_delay` seconds between attempts.
    5. If all attempts fail, the function raises a `RuntimeError`.

    @param udpSock       A pre-initialized UDP socket for communication.
    @param host          The IP address or hostname of the server to connect to.
    @param port          The port number of the server to connect to.
    @param max_retries   The maximum number of handshake attempts before giving up.
    @param retry_delay   The delay (in seconds) between consecutive handshake retries.

    @return dict Returns a dictionary containing camera information:
                 - "cam_id": Camera ID as a string.
                 - "multicast": Multicast flag (integer).
                 - "neverend": Run continously without end(integer).
                 - "frames_to_process": Total number of frames to process (integer).
                 - "cam_height": Camera frame height (integer).
                 - "cam_width": Camera frame width (integer).
                 - "data_path": Path to the data directory (string).

    @throws RuntimeError If the handshake fails after all retry attempts.
    @throws Exception    If any unexpected error occurs during the handshake process.

    @note The function assumes the server sends the following camera info in the format:
          "Sent  UDP: |<cam_id>|<multicast>|<neverend>|<frames_to_process>|<height>|<width>|<data_path>"
          
    """
    
    # Send an empty packet to initiate handshake
    serverAddr = (host, port)
    
    
    for attempt in range(1, max_retries + 1):
        try:
            print(f"[udp_handler] Handshake attempt {attempt}/{max_retries} to {serverAddr}")
            
            # Send "REQ"
            udpSock.sendto(b"REQ", serverAddr)

            # Read response
            data, address = udpSock.recvfrom(1024)
            response = data.decode("utf-8", errors="ignore").strip()
            print(f"[udp_handler] Got response: '{response}'")
            
            # Check response
            if response == "NOTREADY":
                print(f"[udp_handler] Server not ready. Retrying in {retry_delay} seconds...")
                time.sleep(retry_delay)
                continue
            
            elif response == "READY":
                print(f"[udp_handler] Server is ready. Waiting for camera info...")
                # The next message should be the cam info
                data, address = udpSock.recvfrom(1024)
                resp = data.decode('utf-8', errors='ignore')
                print(f"[udp_handler] Received from: {address}, camera info: {resp}")

                # e.g. "Sent  UDP: |1112|0|1|200|720|1280|/path/to/data"
                parts = resp.split("|")
                cam_id = parts[1]
                multicast = int(parts[2])
                neverend = int(parts[3])
                frames_to_process = int(parts[4])
                height = int(parts[5])
                width  = int(parts[6])
                data_path = parts[7]
                
                # Send an ACK
                udpSock.sendto(b"ACK", serverAddr)
                print(f"[udp_handler] Sent ACK to {serverAddr}")
                
                # Return the content of the camera message
                return {
                    "cam_id": cam_id,
                    "multicast": multicast,
                    "neverend": neverend,
                    "frames_to_process": frames_to_process,
                    "cam_height": height,
                    "cam_width": width,
                    "data_path": data_path
                }
            
            # If the response is something else we don't recognize, treat it as a transient failure
            print(f"[client] Unexpected response '{response}'. Will retry.")
            time.sleep(retry_delay)
            
        except socket.timeout:
            print(f"[udp_handler] Attempt {attempt} timed out. Retrying in {retry_delay} seconds...")

        except Exception as e:
            print(f"[udp_handler] Attempt {attempt} failed with error: {e}")
            time.sleep(retry_delay)

    # If all retries fail, raise an error
    raise RuntimeError(f"[udp_handler] Handshake failed after {max_retries} attempts to {serverAddr}")

    
 
def decode_hex_bboxes(hex_data):
    """
    @brief Decodes a hex-encoded string containing bounding box data into an iterator of unpacked tuples.

    This function processes a hex-encoded binary string that contains bounding box information.
    It decodes the binary data using a specified format and returns an iterator of tuples,
    where each tuple represents a bounding box and its associated attributes.

    @param hex_data: A hex-encoded binary string containing the bounding box data.
                     If the input is empty, the function returns an empty list.

    @return: An iterator of unpacked tuples (using `struct.iter_unpack`), with each tuple containing:
             - `flag` (bool): A flag indicating the state of the bounding box.
             - `id` (bytes): A 4-byte identifier for the bounding box.
             - `frameId` (short): The frame ID associated with the bounding box.
             - `timestamp` (unsigned long long): The timestamp of the bounding box.
             - `x1`, `y1` (short): Coordinates of the top-left corner of the bounding box.
             - `x2`, `y2` (short): Coordinates of the bottom-right corner of the bounding box.
             - `score` (float): Confidence score for the bounding box.
             - `classId` (short): Class ID of the detected object.
    """
    
    if not hex_data:
        return []
    try:
        # Get hex payload
        dataB = bytes.fromhex(hex_data.decode())
    except Exception:
        return [] # this case hex data has failed because of failed format
    
    # Try to decode with or without boxes
    try:
        format_string = ">?4sIQhhhhfh"
        unpacked_data = struct.iter_unpack(format_string, dataB)
    except struct.error as e:
        print(f"Error con formato {format_string}: {e} , trying no boxes format... for {dataB}")
        try:
            format_string = ">?4shQ"
            unpacked_data = struct.iter_unpack(format_string, dataB)
            
        except struct.error as e: 
            print(f"Error con formato {format_string}: {e} , decode_hex_bboxes can't decode {dataB}")
            return []


    return unpacked_data