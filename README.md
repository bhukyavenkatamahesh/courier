# courier

**Reliable, congestion-controlled file transfer over UDP — and a Mininet testbed to prove two of them share a link fairly.**

### ▶ [Watch the protocol run](https://bhukyavenkatamahesh.github.io/courier/)

An interactive walkthrough: packets and acknowledgements in flight, the window growing and collapsing, loss and recovery as they happen.

A courier guarantees delivery over roads that give no such guarantee. That is exactly the problem here: UDP offers no ordering, no delivery guarantee, and no sense of how fast the network can actually go. Everything that turns it into a transport you can trust with a file — sequence numbers, acknowledgements, retransmission, a window that adapts to the link — is implemented by hand in this repository.

---

## The problem

| What UDP gives you | What a file transfer needs |
| --- | --- |
| Fire a packet and hope. Packets vanish, arrive out of order, or arrive twice. No notion of a safe sending rate. | Every byte, exactly once, in the right order — at a rate that adapts to the network instead of flooding it and starving everyone else on the link. |

The gap between those two columns is the project.

## What's implemented

**Reliability**
- 1400-byte payloads, each tagged with its byte offset, kept under the 1500-byte Ethernet MTU so the network never fragments a packet.
- Cumulative acknowledgements: the receiver acks the next byte it still needs, so one ack confirms many packets and a lost ack is superseded by the next one.
- Out-of-order packets are buffered and flushed to disk the moment the gap is filled, so nothing is written out of order and nothing is discarded.

**Congestion control**
- Slow start: the window doubles each successful round until it reaches the threshold.
- Congestion avoidance: past the threshold, the window grows by one per round rather than doubling.
- Fast retransmit on three duplicate acks — data is still flowing, so the window is halved rather than reset.
- Timeout: silence implies worse trouble, so the sender retransmits and drops the window to 1.
- Adaptive timeout from measured round trips, `timeout = estimatedRTT + 4 × deviation`, with exponentially weighted averages (α = β = 0.25). The deviation term is what makes the sender automatically more patient on a jittery link.

## The experiment

One transfer proves correctness. The harder question is what happens when **two independent transfers share one bottleneck**, and whether backing off on loss actually divides that link fairly when one client sits much further away.

```
Client 1 ─┐                                    ┌─ Server 1
          ├─ sw1 ════ 100 Mbps bottleneck ════ sw2 ─┤
Client 2 ─┘                                    └─ Server 2
                                                  + 0–100 ms extra delay
```

- **Test bed** — Mininet dumbbell topology, two client–server pairs, 100 Mbps bottleneck between the switches.
- **Variable** — extra delay on the second server's link, 0 → 100 ms in 20 ms steps, 5 runs each.
- **Correctness** — MD5 of each received file against the original. The transfer is either byte-perfect or it failed.
- **Fairness** — Jain's index over the two throughputs: 1.0 is a perfectly equal split, 0.5 means one flow took everything.

The far client's feedback is slower, so it grows its window more slowly and is naturally disadvantaged. Fairness under asymmetric delay is the real test.

## Visual walkthrough

**Live at [bhukyavenkatamahesh.github.io/courier](https://bhukyavenkatamahesh.github.io/courier/)**

`index.html` is a self-contained interactive explanation — packets and acknowledgements in flight, the window growing and collapsing, the timeout timer running down. It narrates what the protocol is doing and why, with a plain-English / technical toggle, and buttons to force a packet loss, a lost acknowledgement, a fast retransmit, or a timeout. Open it in any browser; no server or build step.

> Note: the simulation re-acks on every out-of-order arrival, which is standard behaviour and makes fast retransmit observable. `p2_client.py` buffers silently instead, so in the real implementation recovery comes from the timer almost every time — the sender's duplicate-ack path exists but is rarely reached.

## Running it

```bash
# receiver
python3 p2_client.py <server_ip> <server_port> --pref_outfile 1

# sender (expects some_file_of_500kb.txt alongside it)
python3 p2_server.py <server_ip> <server_port>
```

The full fairness sweep needs Mininet and a reachable OpenFlow controller:

```bash
sudo python3 p2_exp.py
```

Results are written to `p2_fairness.csv` as `delay, md5_hash_1, md5_hash_2, ttc1, ttc2, jfi`.

## Files

| File | Role |
| --- | --- |
| `p2_server.py` | Sender: windowing, retransmission, slow start, fast retransmit, adaptive timeout |
| `p2_client.py` | Receiver: in-order writing, buffering of early packets, cumulative acks |
| `p2_exp.py` | Mininet harness: builds the topology, runs both transfers, records MD5 and fairness |
| `index.html` | Interactive visual walkthrough |
