import struct
import time
import socket
import zmq
from collections import namedtuple
from itertools import chain
import traceback


# socket_ip = "172.17.0.3:8885"

# When programs start, they wait each other until: 
def camera_edge_handshake(socket_ip):
    context = zmq.Context()
    sink = context.socket(zmq.REQ)
    sink.connect(f"tcp://{socket_ip}")
    sink.send_string("")
    sink.close()
    # Just at this point camera edge is being waited. 
    # If camera edge arrives where it handshake is, 
    # both continue
    context.term()
    return None


def setAck_socket(serverSocket, socket_ip):
    socket_ip, socket_port = socket_ip.split(":")
    socket_port = int(socket_port)
    print('Sending acknowledgment')
    serverSocket.sendto(b"A", (socket_ip, socket_port))
    return None

def set_socket(socket_ip):
    socket_ip, socket_port = socket_ip.split(":")
    print(f'Socket set at {socket_ip}:{socket_port}')
    socket_port = int(socket_port)
    serverSocket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    print('Receiving cam Info:')
    serverSocket.sendto(b"A", (socket_ip, socket_port))
    data, address = serverSocket.recvfrom(16000)
    print(type(data))
    print(data)
    return serverSocket, data



# From udp we read 1 frame data. All it's boxes.
def read_udp(serverSocket):
    # Variable to control if function continues trying to read
    reading = True
    while(reading):
        try:
            # Blocking until data is recived
            print(f'Waiting for new info. Reading = {reading}')
            data, address = serverSocket.recvfrom(16000)
            buffer_size = len(data)
            print(f'UDP data received with length: {buffer_size}')
            if len(data) > 0: reading = False
            print(f'Length data received {len(data)}')
            print(f'I have read: \n {data}')
            # By now, data is class bytes, but hexadecimal representation with more 
            # length than it should be.
            dataB = bytes.fromhex(data.decode())
            print('-----')
            print(data.decode())
            print('-----')
            print(dataB)

            # format: flag, cam_id , n_frame, timestamp , box_x, box_y, box_w, box_h, score, class
            format_string = ">?4shQhhhhfh"
            format_string = ">?4shQhhhh"

            expected_size = struct.calcsize(format_string)
            assert (buffer_size % expected_size) == 0, \
                f'Wrong input buffer length:  {buffer_size} . Expected multiple by: {expected_size} '


            unpacked_data = struct.iter_unpack(format_string, dataB)

        except socket.error as e:
            reading = True
            traceback.print_exc()
            
    # serverSocket.close()

    return unpacked_data
