import socket
import struct
import numpy as np
import time


def handshake_and_get_info(udpSock, host, port, max_retries, retry_delay):
    """
    @brief Performs a UDP handshake with a specified server to retrieve camera information.

    This function initiates a UDP handshake with the server at the specified `host` and `port`.
    It attempts to send an empty handshake packet, waits for an acknowledgment ("ACK"), and then
    retrieves camera information from the server. The handshake process is retried up to `max_retries`
    times, with a delay of `retry_delay` seconds between attempts. If all retries fail, the function raises
    a `RuntimeError`.

    @param udpSock       A pre-initialized UDP socket for communication.
    @param host          The IP address or hostname of the server to connect to.
    @param port          The port number of the server to connect to.
    @param max_retries   The maximum number of handshake attempts before giving up.
    @param retry_delay   The delay (in seconds) between consecutive handshake retries.

    @return dict Returns a dictionary containing camera information:
                 - "cam_id": Camera ID as a string.
                 - "gstreamer": GStreamer flag (integer).
                 - "frames_to_process": Total number of frames to process (integer).
                 - "cam_height": Camera frame height (integer).
                 - "cam_width": Camera frame width (integer).
                 - "data_path": Path to the data directory (string).

    @throws RuntimeError If the handshake fails after all retry attempts.
    @throws Exception    If any unexpected error occurs during the handshake process.

    @note The function assumes the server sends the following camera info in the format:
          "Sent  UDP: |<cam_id>|<gstreamer>|<frames_to_process>|<height>|<width>|<data_path>"
          
    @note The Socket is switched into blocking mode after ACK.
    """
    
    # Send an empty packet to initiate handshake
    serverAddr = (host, port)
    
    
    for attempt in range(1, max_retries + 1):
        try:
            print(f"[udp_handler] Handshake attempt {attempt}/{max_retries} to {serverAddr}")

            # Send an empty packet to initiate handshake
            udpSock.sendto(b"", serverAddr)

            # Wait for acknowledgment ("ACK")
            data, address = udpSock.recvfrom(1024)
            ack = data.decode('utf-8', errors='ignore')
            if ack != "ACK":
                print(f"[udp_handler] Unexpected response: {ack}. Retrying...")
                continue
            print(f"[udp_handler] Received ACK from {address}. Waiting for camera info...")

            
            # Wait for camera info
            while True:
                try:
                    data, address = udpSock.recvfrom(1024)
                    resp = data.decode('utf-8', errors='ignore')
                    print(f"[udp_handler] Received from: {address}, camera info: {resp}")


                    # Example parse. 
                    # e.g. "Sent  UDP: |1112|1|200|720|1280|/path/to/data"
                    parts = resp.split("|")
                    # parts[0] = "Sent  UDP: "
                    # parts[1] = cam_id
                    # parts[2] = gstreamer
                    # parts[3] = framesToProcess
                    # parts[4] = height
                    # parts[5] = width
                    # parts[6] = dataPath
                    cam_id = parts[1]
                    gstreamer = int(parts[2])
                    frames_to_process = int(parts[3])
                    height = int(parts[4])
                    width  = int(parts[5])
                    data_path = parts[6]

                    return {
                        "cam_id": cam_id,
                        "gstreamer": gstreamer,
                        "frames_to_process": frames_to_process,
                        "cam_height": height,
                        "cam_width": width,
                        "data_path": data_path
                    }
                except socket.timeout:
                    print("[udp_handler] Still waiting for camera info...")
                    continue  # Keep waiting for camera info
            
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
    dataB = bytes.fromhex(hex_data.decode())
    format_string = ">?4shQhhhhfh"

    unpacked_data = struct.iter_unpack(format_string, dataB)

    return unpacked_data