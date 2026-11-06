from mininet.topo import Topo
from mininet.net import Mininet
from mininet.link import TCLink
from mininet.node import RemoteController
from mininet.cli import CLI
from mininet.log import setLogLevel
import time, re, os
import sys
import hashlib
import subprocess


class DumbbellTopo(Topo):
    def build(self, delay_sw2_s2='50ms'):
        # Create hosts
        c1 = self.addHost('c1')
        c2 = self.addHost('c2')
        s1 = self.addHost('s1')
        s2 = self.addHost('s2')

        # Create switches
        sw1 = self.addSwitch('sw1')
        sw2 = self.addSwitch('sw2')

        # Add links with specified parameters
        # Links between clients/servers and switches
        self.addLink(c1, sw1, delay='5ms')
        self.addLink(c2, sw1, delay='5ms')
        self.addLink(s1, sw2, delay='5ms')

        buffer_size = 50000
        # Link between sw1 and sw2 (bottleneck link)
        self.addLink(sw1, sw2, bw=100, delay='5ms', max_queue_size=buffer_size)

        print("delay is ", delay_sw2_s2)
        # Link between sw2 and s2 with specified latency
        self.addLink(s2, sw2, delay=delay_sw2_s2)

def jain_fairness_index(allocations):
    n = len(allocations)
    sum_of_allocations = sum(allocations)
    sum_of_squares = sum(x ** 2 for x in allocations)

    jfi = (sum_of_allocations ** 2) / (n * sum_of_squares)
    return jfi

def compute_md5(file_path):
    """Compute the MD5 hash of a file."""
    hasher = hashlib.md5()
    try:

        with open(file_path, 'rb') as file:
            # Read the file in chunks to avoid using too much memory for large files
            while chunk := file.read(8192):
                hasher.update(chunk)
        return hasher.hexdigest()
    except FileNotFoundError:
        print(f"File not found: {file_path}")
        return None

def run():
    # Set the log level to info to see detailed output
    setLogLevel('info')

    # IP and port of the remote controller
    controller_ip = '10.17.51.133'  # Change to the controller's IP address if not local
    controller_port = 6633      # Default OpenFlow controller port

    # Output file
    output_file = f'p2_fairness.csv'
    f_out = open(output_file, 'w')
    f_out.write("delay,md5_hash_1,md5_hash_2,ttc1,ttc2,jfi\n")


    SERVER_IP1 = "10.0.0.3"
    SERVER_PORT1 = 6555
    SERVER_IP2 = "10.0.0.4"
    SERVER_PORT2 = 6556

    NUM_ITERATIONS = 5
    OUTFILE = 'received_file.txt'
    delay_list = [x for x in range(0, 101, 20)] # Go for 0 to 101

    # Loop to create the topology 10 times with varying loss (1% to 10%)
    for DELAY in delay_list:
        for i in range(0, NUM_ITERATIONS):

            # os.system("mn -c")
            # time.sleep(1)


            print(f"\n--- Running topology with {DELAY}ms delay --")
            print(DELAY)
            # Create the custom topology with the specified loss
            topo = DumbbellTopo(delay_sw2_s2=f"{DELAY}ms")

            # Initialize the network with the custom topology and TCLink for link configuration
            net = Mininet(topo=topo, link=TCLink, controller=None)
            # Add the remote controller to the network
            remote_controller = RemoteController('c0', ip=controller_ip, port=controller_port)
            net.addController(remote_controller)

            # Start the network
            net.start()
            #CLI(net)
            # Get references to h1 and h2
            c1 = net.get('c1')
            c2 = net.get('c2')
            s1 = net.get('s1')
            s2 = net.get('s2')

            s2.cmd('pkill -f p2_server.py')
            s1.cmd('pkill -f p2_server.py')

            pref_c1 = "1"
            pref_c2 = "2"
            s1_cmd = f"nohup python3 p2_server.py {SERVER_IP1} {SERVER_PORT1} & echo $!"
            s2_cmd = f"nohup python3 p2_server.py {SERVER_IP2} {SERVER_PORT2} & echo $!"
            c1_cmd = f"nohup python3 p2_client.py {SERVER_IP1} {SERVER_PORT1} --pref_outfile {pref_c1} & echo $!"
            c2_cmd = f"nohup python3 p2_client.py {SERVER_IP2} {SERVER_PORT2} --pref_outfile {pref_c2} & echo $!"

            s1_pid = s1.cmd(s1_cmd)
            time.sleep(1)
            while True:
                if(len(s1_pid.strip().split())!=0):
                    break
                else:
                    s1_pid = s1.cmd(s1_cmd)
            s1_pid = s1_pid.strip().split()[-1]

            print(f"Server1 Process id : {s1_pid}")
            s2_pid = s2.cmd(s2_cmd)
            time.sleep(1)
            while True:
                if(len(s2_pid.strip().split())!=0):
                    break
                else:
                    s2_pid = s2.cmd(s2_cmd)
            s2_pid = s2_pid.strip().split()[-1]
            print(f"Server2 Process id : {s2_pid}")
            time.sleep(1)

            start_time_c1 = time.time()
            c1_pid = c1.cmd(c1_cmd)
            time.sleep(1)

            while True:
                if(len(c1_pid.strip().split())!=0):
                    break
                else:
                    c1_pid = c1.cmd(c1_cmd)
                    print("Wait ")
            c1_pid = c1_pid.strip().split()[-1]
            print(f"Client1 Process id : {c1_pid}")


            start_time_c2 = time.time()
            c2_pid = c2.cmd(c2_cmd)
            time.sleep(1) # To initialise the client it take slight delay

            while True:
                if(len(c2_pid.strip().split())!=0):
                    break
                else:
                    c2_pid = c2.cmd(c2_cmd)
                    print("Wait ")

            c2_pid = c2_pid.strip().split()[-1]
            print(f"Client2 Process id : {c2_pid}")

            #CLI(net)
            end_time_c1 = None
            end_time_c2 = None
            while end_time_c1 is None or end_time_c2 is None:
                # Check if process for c1 has completed
                if end_time_c1 is None:
                    result_c1 = c1.cmd(f'ps')
                    if not result_c1 or str(c1_pid) not in result_c1:  # Process is no longer running
                        end_time_c1 = time.time()
                        print("C1 has ended ")
                        s1.cmd(f'sudo kill -9 {s1_pid}')
                        c1.cmd(f'sudo kill -9 {c1_pid}')
                if end_time_c2 is None:
                    result_c2 = c2.cmd(f'ps')
                    if not result_c2 or str(c2_pid) not in result_c2:  # Process is no longer running
                        end_time_c2 = time.time()
                        print("C2 has ended ")
                        s2.cmd(f'sudo kill -9 {s2_pid}')
                        c2.cmd(f'sudo kill -9 {c2_pid}')

            # Stop the network
            print("Going to stop the network ")
            net.stop()

            time.sleep(1)


            # calculate metrics
            dur_c1 = end_time_c1 - start_time_c1
            dur_c2 = end_time_c2 - start_time_c2

            jfi = jain_fairness_index([1/(dur_c1-2), 1/(dur_c2-1)])

            print(dur_c1, dur_c2, jfi)
            # calculate md5 hash
            hash1 = compute_md5(f"{pref_c1}received_file.txt")
            hash2 = compute_md5(f"{pref_c2}received_file.txt")


            f_out.write(f"{DELAY},{hash1},{hash2},{dur_c1},{dur_c2},{jfi}\n")

            time.sleep(1)

    f_out.close()
    print("\n--- Completed all tests ---")

if __name__ == "__main__":
    run()

