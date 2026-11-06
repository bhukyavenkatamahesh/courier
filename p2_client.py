import socket
import argparse
import sys
import logging

ip_to_logfile = {
    "10.0.0.3": "Client1.log",
    "10.0.0.4": "Client2.log"
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
def receive_file(server_ip, server_port , pref_outfile):

    logger = setup_logger_for_ip(server_ip)

    # Initialize UDP socket

    logger.info("Client ---------------------------------->>")

    ## Add logic for handling packet loss while establishing connection
    client_socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)

    server_address = (server_ip, server_port)
    expected_seq_num = 0
    unacked_packets = {}
    output_file_path = f"{pref_outfile}received_file.txt"  # Default file name
    TIMEOUT = 10.0
    client_socket.settimeout(TIMEOUT)
    # count = 0

    start_ack_received = False

    client_socket.sendto(b"START", server_address)
    logger.info(f"Sent START signal to server )")


    with open(output_file_path, 'wb') as file:
        while True:
            try:
                # Receive the packet
                packet, _ = client_socket.recvfrom(MSS + 100)  # Allow room for headers
                if start_ack_received == False:
                    start_ack_received = True

                if packet == b'END':
                    logger.info(f"Length of the unacked_packets : {len(unacked_packets)}")
                    logger.info(f"Expected seq no. at the end : {expected_seq_num}")
                    logger.info("Received END signal from server, file transfer complete")
                    # sys.stdout.flush()
                    client_socket.close()
                    # sys.exit()
                    break

                seq_num, data = parse_packet(packet)

                logger.info(f" Seq no: {seq_num} & Expected seq no : {expected_seq_num}")
                # sys.stdout.flush()


                # If the packet is in order, write it to the file
                if seq_num == expected_seq_num:
                    file.write(data)
                    file.flush()
                    logger.info(f"Data written of seq no : {seq_num}")
                    # counter+=1
                    # Maxlim = min(Maxlim*2, 32)
                    # sys.stdout.flush()
                    expected_seq_num += MSS
                    # send_ack(client_socket, server_address, expected_seq_num)
                    # logger.info(f"Sent cumulative ACK for packet {expected_seq_num}")

                    while expected_seq_num in unacked_packets:
                        file.write(unacked_packets[expected_seq_num])
                        file.flush()
                        del unacked_packets[expected_seq_num]

                        logger.info(f"Data written of seq no : {expected_seq_num}")
                        expected_seq_num += MSS
                        # send_ack(client_socket, server_address, expected_seq_num)
                        # logger.info(f"Sent cumulative ACK for packet {expected_seq_num}")

                        # if expected_seq_num not in unacked_packets:
                        #     send_ack(client_socket, server_address, expected_seq_num)
                        #     logger.info(f"Sent cumulative ACK for packet {expected_seq_num}")

                    send_ack(client_socket, server_address, expected_seq_num)
                    logger.info(f"Sent cumulative ACK for packet {expected_seq_num}")
                elif seq_num<expected_seq_num:
                    send_ack(client_socket, server_address, expected_seq_num)
                    logger.info(f"Sent cumulative ACK for packet {expected_seq_num}")
                else:
                    # Buffer out-of-order packets
                    unacked_packets[seq_num] = data

            except socket.timeout:
                if(start_ack_received == False):
                    client_socket.sendto(b"START", server_address)
                    logger.info("Start signal sent again ")
                    # sys.stdout.flush()
                    continue
                else:
                    TIMEOUT = min(TIMEOUT * 2, 20)
                    client_socket.settimeout(TIMEOUT)
                    logger.info("Timeout waiting for data")
                    # sys.stdout.flush()
                    send_ack(client_socket, server_address, expected_seq_num)
                    logger.info(f"Sent cumulative ACK for packet {expected_seq_num}")

            except Exception as e:
                logger.info(f"An error occurred: {e}")
                break  # Exit loop on any unexpected error

        client_socket.close()
def parse_packet(packet):
    """
    Parse the packet to extract the sequence number and data.
    """
    seq_num, data = packet.split(b'|', 1) #split on the basis of '|' and at most 1 time
    return int(seq_num), data

def send_ack(client_socket, server_address, seq_num):
    """
    Send a cumulative acknowledgment for the received packet.
    """
    ack_packet = str(seq_num).encode()
    client_socket.sendto(ack_packet, server_address)

# Parse command-line arguments
parser = argparse.ArgumentParser(description='Reliable file receiver over UDP.')
parser.add_argument('server_ip', help='IP address of the server')
parser.add_argument('server_port', type=int, help='Port number of the server')
parser.add_argument('--pref_outfile', default='', help='Prefix for the output file')

args = parser.parse_args()
# print(args.pref_outfile)

# Run the client
receive_file(args.server_ip, args.server_port,args.pref_outfile)