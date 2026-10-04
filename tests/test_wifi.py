import json
import queue
import tempfile
import threading
import time
import unittest
from pathlib import Path
from unittest.mock import Mock, call, patch

import etherdrop as ed


class WifiDiscoveryTests(unittest.TestCase):
    def setUp(self):
        self.events = queue.Queue()
        self.adapter = ed.WifiAdapter("Wi-Fi", 7, "192.168.5.10", 24)
        self.service = ed.WifiDiscoveryService(self.adapter, self.events, "sender")

    def announcement(self, session="receiver-a", **changes):
        msg = {"magic": ed.MAGIC, "version": ed.PROTOCOL_VERSION, "mode": "wifi",
               "session": session, "hostname": "Laptop", "role": "receiver"}
        msg.update(changes)
        return msg

    def test_adapter_discovery_and_subnet(self):
        data = {"Name": "Wi-Fi", "IfIndex": 7, "Address": "192.168.5.10", "PrefixLength": 24}
        with patch.object(ed, "run_powershell", return_value=json.dumps(data)) as powershell:
            adapters = ed.discover_wifi_adapters()
        self.assertIn("Get-NetAdapter -Physical", powershell.call_args.args[0])
        self.assertIn("NdisPhysicalMedium -in @(1, 9)", powershell.call_args.args[0])
        self.assertEqual(str(adapters[0].network.broadcast_address), "192.168.5.255")
        self.assertEqual(ed.adapter_endpoint(adapters[0], 123), ("192.168.5.10", 123))
        with patch.object(ed, "run_powershell", return_value=""):
            self.assertEqual(ed.discover_wifi_adapters(), [])

    def test_independent_heartbeats_and_session_deduplication(self):
        self.service._accept_announcement(self.announcement(), "192.168.5.20", 1)
        self.service._accept_announcement(self.announcement("receiver-b"), "192.168.5.21", 2)
        self.service._accept_announcement(self.announcement(), "192.168.5.20", 4)
        self.assertEqual(len(self.service.peers), 2)
        self.service._expire_peers(2 + ed.PEER_TIMEOUT + 0.1)
        self.assertEqual(set(self.service.peers), {"receiver-a"})
        self.assertIn(("wifi_peer_lost", self.service.token, "receiver-b"), list(self.events.queue))

    def test_other_modes_subnets_roles_versions_and_self_are_ignored(self):
        for changes in ({"mode": "ethernet"}, {"role": "sender"}, {"version": 0},
                        {"session": ed.SESSION_ID}, {"session": ""}):
            self.service._accept_announcement(self.announcement(**changes), "192.168.5.20", 1)
        self.service._accept_announcement(self.announcement(), "192.168.6.20", 1)
        self.assertFalse(self.service.peers)

    def test_ethernet_endpoint_unchanged(self):
        adapter = ed.EthernetAdapter("Ethernet", 4, "fe80::1", "", "", 0, 0, False)
        self.assertEqual(ed.adapter_endpoint(adapter, 123), ("fe80::1", 123, 0, 4))
        self.assertEqual(ed.adapter_family(adapter), ed.socket.AF_INET6)


class SocketBufferTests(unittest.TestCase):
    def test_wifi_leaves_buffer_sizes_to_windows(self):
        sock = Mock()
        ed.configure_stream_socket(sock, automatic_buffers=True)
        self.assertEqual(sock.setsockopt.call_args_list, [
            call(ed.socket.SOL_SOCKET, ed.socket.SO_KEEPALIVE, 1),
            call(ed.socket.IPPROTO_TCP, ed.socket.TCP_NODELAY, 1),
        ])

    def test_ethernet_keeps_existing_buffer_sizes(self):
        sock = Mock()
        ed.configure_stream_socket(sock)
        self.assertEqual(sock.setsockopt.call_args_list, [
            call(ed.socket.SOL_SOCKET, ed.socket.SO_KEEPALIVE, 1),
            call(ed.socket.SOL_SOCKET, ed.socket.SO_SNDBUF, ed.SOCKET_BUFFER),
            call(ed.socket.SOL_SOCKET, ed.socket.SO_RCVBUF, ed.SOCKET_BUFFER),
            call(ed.socket.IPPROTO_TCP, ed.socket.TCP_NODELAY, 1),
        ])


class GroupTransferTests(unittest.TestCase):
    def run_group(self, modes, cancel_one=False, cancel_all=False, verify=True, wrap=True):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            source = root / "source"
            source.mkdir()
            (source / "data.bin").write_bytes(bytes(range(256)) * 8192)
            (source / "empty.txt").write_bytes(b"")
            events = queue.Queue()
            receivers = []
            for index in range(len(modes)):
                service = ed.ReceiverService(ed.WifiAdapter("test", index + 1, f"127.0.0.{index + 2}", 8),
                                             events, threading.Lock())
                service.start()
                receivers.append(service)
            sender = ed.SenderGroup(ed.WifiAdapter("test", 1, "127.0.0.1", 8), events, threading.Lock())
            peers = [{"name": f"Laptop {i}", "ip": f"127.0.0.{i + 2}"} for i in range(len(modes))]
            outcomes = {}
            offered = set()
            recipients = None
            try:
                def listening(receiver):
                    try:
                        return receiver.server_socket and receiver.server_socket.getsockname()[1] == ed.TRANSFER_PORT
                    except OSError:
                        return False
                deadline = time.monotonic() + 5
                while not all(listening(r) for r in receivers):
                    if time.monotonic() > deadline:
                        self.fail("Receiver listeners did not start")
                    time.sleep(0.01)
                with patch.object(ed, "build_transfer_items", wraps=ed.build_transfer_items) as scan:
                    recipients = sender.send(peers, [source], verify, wrap)
                    self.assertEqual(len(recipients), len(modes))
                    peers.append({"name": "Late laptop", "ip": "127.0.0.99"})
                    ids = list(recipients)
                    if cancel_all:
                        sender.cancel()
                    deadline = time.monotonic() + 15
                    finished = False
                    while not finished:
                        if time.monotonic() > deadline:
                            self.fail(f"Group did not finish: {outcomes}")
                        try:
                            event = events.get(timeout=0.1)
                        except queue.Empty:
                            continue
                        if event[0] != "transfer":
                            continue
                        _, tid, action, data = event
                        if action == "incoming_offer":
                            offered.add(tid)
                            index = ids.index(tid)
                            if modes[index] == "reject":
                                data["decision"].reject("Test decline")
                            elif modes[index] == "disconnect":
                                receivers[index].stop()
                            elif cancel_one and index == 0:
                                sender.cancel(tid)
                            else:
                                destination = root / f"destination-{index}"
                                destination.mkdir(exist_ok=True)
                                data["decision"].accept(destination)
                        elif action == "worker_stopped":
                            finished = sender.worker_stopped(tid)
                        elif action in ("done", "rejected", "failed", "cancelled") and tid in recipients:
                            # Receiver and sender share IDs; later sender outcomes agree on successful transfers.
                            outcomes[tid] = action
                    self.assertEqual(scan.call_count, 1)
                self.assertFalse(sender.coordinator.locked())
                self.assertEqual(len(recipients), len(modes))
                for index, tid in enumerate(ids):
                    if cancel_all or (cancel_one and index == 0):
                        self.assertEqual(outcomes[tid], "cancelled")
                    elif modes[index] == "accept":
                        self.assertEqual(outcomes[tid], "done")
                        copies = list((root / f"destination-{index}").rglob("data.bin"))
                        self.assertEqual(len(copies), 1)
                        self.assertEqual(copies[0].read_bytes(), (source / "data.bin").read_bytes())
                        self.assertEqual(copies[0].with_name("empty.txt").stat().st_size, 0)
                    elif modes[index] == "reject":
                        self.assertEqual(outcomes[tid], "rejected")
                    else:
                        self.assertIn(outcomes[tid], ("failed", "cancelled"))
            finally:
                sender.cancel()
                for receiver in receivers:
                    receiver.stop()
                    receiver.thread.join(timeout=2)

    def test_parallel_approved_transfers_verified(self):
        self.run_group(["accept", "accept"])

    def test_interrupted_receiver_resumes_while_other_receiver_finishes(self):
        interrupted, other_finished = threading.Event(), threading.Event()
        first_id, first_actions = [], []
        original_receive = ed.TransferChannel.receive_bytes
        original_connect = ed.Sender._connect
        original_emit = ed.emit_transfer

        def receive(channel, block):
            n = original_receive(channel, block)
            if channel.sock.getsockname()[0] == '127.0.0.2' and not interrupted.is_set():
                interrupted.set()
                channel.close()
            return n

        def connect(sender, peer_ip):
            if peer_ip == '127.0.0.2' and interrupted.is_set() and not other_finished.is_set():
                raise ConnectionRefusedError('First receiver is temporarily offline')
            return original_connect(sender, peer_ip)

        def emit(events, tid, action, **data):
            if action == 'prepared' and data.get('peer') == 'Laptop 0':
                first_id.append(tid)
            if first_id and tid == first_id[0]:
                first_actions.append(action)
            if action == 'done' and 'destination-1' in data.get('destination', ''):
                other_finished.set()
            original_emit(events, tid, action, **data)

        with patch.object(ed.TransferChannel, 'receive_bytes', receive), patch.object(ed.Sender, '_connect', connect), \
                patch.object(ed, 'emit_transfer', emit), patch.object(ed, 'RECONNECT_DELAY', 0.05):
            self.run_group(['accept', 'accept'])
        self.assertTrue(interrupted.is_set())
        self.assertTrue(other_finished.is_set())
        self.assertIn('paused', first_actions)
        self.assertIn('resumed', first_actions)
        self.assertIn('done', first_actions)

    def test_approval_and_windows_save_waits_are_kept_alive(self):
        original_accept = ed.IncomingTransferDecision.accept
        original_save = ed.ReceivedOutput.save
        actions = []
        original_emit = ed.emit_transfer

        def accept(decision, *args):
            time.sleep(0.5)
            original_accept(decision, *args)

        def save(output, *args):
            time.sleep(0.5)
            original_save(output, *args)

        def emit(events, tid, action, **details):
            actions.append(action)
            original_emit(events, tid, action, **details)

        with patch.object(ed, 'TRANSFER_TIMEOUT', 0.3), patch.object(ed, 'TRANSFER_HEARTBEAT_INTERVAL', 0.05), \
                patch.object(ed.IncomingTransferDecision, 'accept', accept), patch.object(ed.ReceivedOutput, 'save', save), \
                patch.object(ed, 'emit_transfer', emit):
            self.run_group(['accept'], wrap=False)
        self.assertNotIn('paused', actions)

    def test_decline_and_disconnect_do_not_stop_other_receiver(self):
        self.run_group(["reject", "disconnect", "accept"], verify=False)

    def test_cancel_one_while_other_receiver_finishes(self):
        self.run_group(["accept", "accept"], cancel_one=True)

    def test_cancel_all(self):
        self.run_group(["accept", "accept"], cancel_all=True)

    def test_scan_failure_releases_group_when_workers_stop(self):
        events = queue.Queue()
        group = ed.SenderGroup(ed.WifiAdapter("test", 1, "127.0.0.1", 8), events, threading.Lock())
        with patch.object(ed, "build_transfer_items", side_effect=OSError("Missing source")):
            recipients = group.send([{"name": "A", "ip": "127.0.0.2"}], [], False)
            event = events.get(timeout=2)
            self.assertEqual(event[2], "failed")
            stopped = events.get(timeout=2)
            self.assertTrue(group.worker_stopped(stopped[1]))
        self.assertFalse(group.coordinator.locked())


if __name__ == "__main__":
    unittest.main()
