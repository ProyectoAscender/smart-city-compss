import struct
import numpy as np
import zmq


def handshake_and_get_info(host_and_port: str):
    """
    - Parse "host:port" from the given string
    - Do a ZeroMQ REQ handshake to get camera info
    - Return a dictionary with { cam_id, height, width, data_path, etc. }
    """
    host, port_str = host_and_port.split(":")
    port = int(port_str)
    handshake_addr = f"tcp://{host}:{port}"

    ctx = zmq.Context()
    req_socket = ctx.socket(zmq.REQ)
    req_socket.connect(handshake_addr)
    print(f"\n\n[zmq_handler] Sending handshake to {handshake_addr}")
    req_socket.send_string("")  # empty request

    # Receive the pipe-delimited camera info
    resp = req_socket.recv_string()
    print(f"[zmq_handler] Got camera info: {resp}\n\n")
    req_socket.close()
    ctx.term()

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
    
    
    
def decode_hex_bboxes(hex_data):
    if not hex_data:
        return []
    dataB = bytes.fromhex(hex_data.decode())
    format_string = ">?4shQhhhhfh"

    unpacked_data = struct.iter_unpack(format_string, dataB)

    return unpacked_data