import socket
import time
import argparse
import os
import sys
import logging

# logging.basicConfig(filename='server.log', level=logging.DEBUG,
#                     format='%(asctime)s %(levelname)s: %(message)s')
ip_to_logfile = {
    "10.0.0.3": "Server1.log",
    "10.0.0.4": "Server2.log"
    # Add more mappings if needed
}
def setup_logger_for_ip(server_ip):
    log_filename = ip_to_logfile.get(server_ip)
    logger = logging.getLogger(server_ip)  # Use server_ip as logger name to avoid duplicates

    if not logger.hasHandlers():  # Check if logger already has handlers
        handler = logging.FileHandler(log_filename)
        formatter = logging.Formatter('%(asctime)s %(levelname)s: %(message)s')
        handler.setFormatter(formatter)
        logger.setLevel(logging.DEBUG)
        logger.addHandler(handler)
    return logger
# Constants
MSS = 1400
DUP_ACK_THRESHOLD = 3
INITIAL_TIMEOUT = 10.0
A = 0.25  # Alpha for timeout calc
B = 0.25

def send_file(server_ip, server_port):
    #Send a predefined file to the client, ensuring reliability over UDP.
    # Initialize UDP socket

    logger = setup_logger_for_ip(server_ip)


    logger.info("Server ---------------------------------->>")

    window_size = 1
    window_thresh = 1000
    enter_avoidance_phase = False
    try:
        server_socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        server_socket.bind((server_ip, server_port))
        logger.info(f"Server listening on {server_ip}:{server_port}")
    except Exception as e:
        logger.error(f"Failed to bind server on {server_ip}:{server_port} - {e}")
        sys.exit(1)  # Exit if binding fails

    # Wait for client to initiate connection
    client_address = None
    file_path = 'some_file_of_500kb.txt'  # Predefined file name
    estimated_rtt = 1.0
    dev = 0.0
    timeout_interval = INITIAL_TIMEOUT

    file_size = os.path.getsize(file_path)
    logger.info(f"File size: {file_size} bytes")
    remaining_file_size = file_size

    server_socket.settimeout(timeout_interval)

    counter = 0
    pkt_create_allow = True

    with open(file_path, 'rb') as file:
        seq_num = 0
        unacked_packets = {}
        duplicate_ack_count = 1
        last_ack_received = -1
        chunk = b""

        while client_address is None:
            try:
                logger.info("Waiting for client connection...")
                data, client_address = server_socket.recvfrom(1024)
                if data == b"START":
                    logger.info(f"Received START signal from client {client_address} ")
                    break
            except socket.timeout:
                continue

        while True:
            logger.info("Inside the outer while loop ")

            while len(unacked_packets)<window_size and pkt_create_allow: ## Use window-based sending

                if(remaining_file_size == 0):
                    break
                chunk = file.read(MSS) # Everytime it will next MSS bytes of the file

                # Create and send the packet
                packet = create_packet(seq_num, chunk)
                logger.info(f"packet created with seq no : {seq_num}")

                server_socket.sendto(packet, client_address)
                # server_socket.settimeout(timeout_interval)

                remaining_file_size = file_size - file.tell()
                logger.info(f"Remaining file size: {remaining_file_size} bytes")
                unacked_packets[seq_num] = (packet, time.time())  # Track sent packets
                logger.info(f"Sent packet {seq_num}")
                seq_num += MSS

            pkt_create_allow = False

            # Wait for ACKs and retransmit if needed
            try:
                ## Handle ACKs, Timeout, Fast retransmit

                if remaining_file_size == 0 and len(unacked_packets) == 0:  # if not chunk and len(unacked_packets) == 0:
                    server_socket.sendto(b"END", client_address)
                    server_socket.sendto(b"END", client_address)
                    server_socket.sendto(b"END", client_address)
                    logger.info("File transfer complete")
                    break

                server_socket.settimeout(timeout_interval)
                ack_packet, _ = server_socket.recvfrom(1024) # This will run untill a packet is received ( server listening )

                logger.info(f"ACK received : {ack_packet.decode()}")

                # ack_seq_num = get_seq_no_from_ack_pkt()
                if(ack_packet.decode() == 'START'):
                    continue
                ack_seq_num = int(ack_packet.decode())


                if ack_seq_num > last_ack_received and len(unacked_packets)!=0:
                    logger.info(f"Received cumulative ACK for packet {ack_seq_num}")
                    last_ack_received = ack_seq_num
                    duplicate_ack_count = 1
                    # Slide the window forward

                    # Timeout calc
                    if (ack_seq_num > 0):  # only after all ack received
                        sample_rtt = time.time() - unacked_packets[ack_seq_num - MSS][1]  # rtt of the latest acked packet

                    # Remove acknowledged packets from the buffer
                    seq_num_to_delete = [k for k in unacked_packets.keys() if k < ack_seq_num]
                    for k in seq_num_to_delete:
                        del unacked_packets[k]

                    if (len(unacked_packets) == 0):
                        print("All ack received !!")
                        pkt_create_allow = True

                        # Calculate New RTT
                        estimated_rtt = (1 - A) * estimated_rtt + A * sample_rtt
                        dev = (1 - B) * dev + B * abs(sample_rtt - estimated_rtt)
                        timeout_interval = estimated_rtt + 4 * dev
                        logger.info(f"New Timeout Interval: {timeout_interval:.4f} seconds")

                        # Calculate new window size
                        if (window_size < window_thresh):
                            window_size *= 2
                            logger.info("Window doubled ")
                            logger.info(f"Current CWND size : {window_size} ")
                        elif (window_size >= window_thresh) or enter_avoidance_phase:
                            window_size += 1
                            logger.info("Window increased by 1 ")
                            logger.info(f"Current CWND size : {window_size} ")

                else:
                    # Duplicate ACK received
                    duplicate_ack_count += 1

                    logger.info(f"Received duplicate ACK for packet {ack_seq_num}, count={duplicate_ack_count}")

                    if duplicate_ack_count >= DUP_ACK_THRESHOLD:
                        logger.warning("Received 3 duplicate ack")

                        fast_recovery(server_socket, client_address, unacked_packets[last_ack_received][0])
                        duplicate_ack_count = 0
                        if (len(unacked_packets) >= window_size):
                            del unacked_packets[last_ack_received]
                        window_size /= 2
                        window_thresh = max(window_thresh / 2, 2)
                        enter_avoidance_phase = True
                        logger.info(f"Current window size : {window_size}")
                        logger.info(f"Current thresh size : {window_thresh}")

            except socket.timeout:
                # Timeout handling: retransmit all unacknowledged packets

                logger.info(f"Current timeout interval : {timeout_interval} ^^^^^^^^^^^^^")
                logger.info("Timeout occurred, retransmitting unacknowledged packets ^^^^^^^^^^^^^")
                # retransmit_unacked_packets(server_socket, client_address, unacked_packets)
                if(len(unacked_packets)>0 and last_ack_received > -1):
                    fast_recovery(server_socket,client_address,unacked_packets[last_ack_received][0])
                    logger.info(f"Packet no : {last_ack_received} is retransmitted ")

                if len(unacked_packets)>0 and last_ack_received == -1 :
                    for i in unacked_packets:
                        fast_recovery(server_socket,client_address,unacked_packets[i][0])
                        logger.info(f"Packet no : {i} is retransmitted ")
                window_size = 1
                window_thresh = max(window_thresh/2 , 2)
                enter_avoidance_phase = False
                logger.info(f"Current window size : {window_size}")
                logger.info(f"Current thresh size : {window_thresh}")
                server_socket.settimeout(timeout_interval)

            # Check if we are done sending the file
            except Exception as e:
                # Catch any other exception, log, or handle as needed
                logger.error(f"An unexpected error occurred: {e}")
            finally:
                logger.info(f" #Unacked Packets : {len(unacked_packets)} ")
                # chunk = file.read(MSS)
                if remaining_file_size==0 and len(unacked_packets) == 0:
                    server_socket.sendto(b"END", client_address)
                    server_socket.sendto(b"END", client_address)
                    server_socket.sendto(b"END", client_address)
                    logger.info("File transfer complete")
                    break
                continue
        server_socket.close()
        logger.info("Server closed")
def create_packet(seq_num, data):
    return str(seq_num).encode() + b'|' + data


def retransmit_unacked_packets(server_socket, client_address, unacked_packets):
    for i in unacked_packets:
        packet = unacked_packets[i][0]
        server_socket.sendto(packet, client_address)

def fast_recovery(server_socket, client_address, packet):
    """
    Retransmit the earliest unacknowledged packet (fast recovery).
    """
    server_socket.sendto(packet, client_address)


# Parse command-line arguments
parser = argparse.ArgumentParser(description='Reliable file transfer server over UDP.')
parser.add_argument('server_ip', help='IP address of the server')
parser.add_argument('server_port', type=int, help='Port number of the server')
# parser.add_argument('enable_fast_recovery', type=bool, help='Enable fast recovery')

args = parser.parse_args()

# Run the server
send_file(args.server_ip, args.server_port)