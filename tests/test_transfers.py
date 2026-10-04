import queue
import socket
import tempfile
import threading
import time
import unittest
from pathlib import Path
from unittest.mock import patch

import etherdrop as ed


class TransferPathTests(unittest.TestCase):
    def test_normal_nested_path_is_preserved(self):
        self.assertEqual(ed.safe_relative_path('Photos/nested/a.txt'), Path('Photos/nested/a.txt'))

    def test_unsafe_paths_are_rejected(self):
        for value in ('', '/outside.txt', '../outside.txt', 'Photos/../../outside.txt',
                      r'..\outside.txt', r'Photos\..\..\outside.txt',
                      r'\\server\share\outside.txt', r'C:\outside.txt',
                      'Photos/C:/outside.txt', 'Photos/a.txt:stream'):
            with self.subTest(path=value), self.assertRaises(ValueError):
                ed.safe_relative_path(value)


class ReceiverOutputTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.destination = Path(self.temp.name).resolve()
        self.events = queue.Queue()
        self.receiver = ed.ReceiverService(ed.WifiAdapter('test', 1, '127.0.0.1', 8),
                                           self.events, threading.Lock())
        self.peer, incoming = socket.socketpair()
        self.peer.settimeout(5)
        self.addCleanup(self.peer.close)
        self.worker = threading.Thread(target=self.receiver._handle_connection,
                                       args=(incoming, ('127.0.0.2', 1)))
        self.worker.start()
        self.addCleanup(self.stop_worker)

    def stop_worker(self):
        self.receiver.cancel()
        self.peer.close()
        self.worker.join(5)
        self.assertFalse(self.worker.is_alive())

    def event(self, action):
        while True:
            event = self.events.get(timeout=5)
            if event[0] == 'transfer' and event[2] == action:
                return event[3]

    def offer(self, wrap=True, verify=False, file_count=2):
        self.offer_data = {'magic': ed.MAGIC, 'version': ed.PROTOCOL_VERSION,
                                 'type': 'offer', 'transfer_id': 'test',
                                 'hostname': 'Friend', 'verify': verify, 'wrap': wrap,
                                 'total_bytes': 12, 'file_count': file_count, 'roots': ['Photos']}
        ed.send_frame(self.peer, self.offer_data)
        offer = self.event('incoming_offer')
        self.assertEqual(offer['wrap'], wrap)
        offer['decision'].accept(self.destination)
        accepted = ed.recv_frame(self.peer)
        self.assertEqual(accepted['type'], 'accept')
        return Path(accepted['destination'])

    def send_file(self, name, payload=b'new', verify=False):
        ed.send_frame(self.peer, {'type': 'file', 'path': name, 'size': len(payload)})
        self.peer.sendall(payload)
        if verify:
            ed.send_frame(self.peer, {'type': 'hash', 'sha256': ed.hashlib.sha256(payload).hexdigest()})
        self.assertEqual(ed.recv_frame(self.peer)['type'], 'file_ok')

    def finish(self):
        ed.send_frame(self.peer, {'type': 'done'})
        self.assertEqual(ed.recv_frame(self.peer)['type'], 'done_ok')
        self.event('done')
        self.worker.join(5)

    def reconnect(self):
        self.worker.join(5)
        self.assertFalse(self.worker.is_alive())
        self.peer.close()
        self.peer, incoming = socket.socketpair()
        self.peer.settimeout(5)
        self.worker = threading.Thread(target=self.receiver._handle_connection,
                                       args=(incoming, ('127.0.0.2', 1)))
        self.worker.start()
        self.addCleanup(self.peer.close)
        ed.send_frame(self.peer, {**self.offer_data, 'resume': True})
        return ed.recv_frame(self.peer)

    def sender_cancel(self):
        control, incoming = socket.socketpair()
        control.settimeout(5)
        worker = threading.Thread(target=self.receiver._handle_connection,
                                  args=(incoming, ('127.0.0.2', 2)))
        worker.start()
        try:
            ed.send_frame(control, {'magic': ed.MAGIC, 'version': ed.PROTOCOL_VERSION,
                                   'type': 'cancel', 'transfer_id': 'test'})
            self.assertEqual(ed.recv_frame(control)['type'], 'cancel')
        finally:
            control.close()
            worker.join(5)
        self.assertFalse(worker.is_alive())

    def test_wrapped_transfer_keeps_selected_folder_structure(self):
        root = self.offer(verify=True)
        self.send_file('Photos/nested/a.txt', b'photo', verify=True)
        self.send_file('standalone.txt', b'file', verify=True)
        self.finish()
        self.assertEqual(root.parent, self.destination)
        self.assertEqual((root / 'Photos/nested/a.txt').read_bytes(), b'photo')
        self.assertEqual((root / 'standalone.txt').read_bytes(), b'file')

    def test_receiver_rejects_windows_path_traversal_before_writing(self):
        self.offer(file_count=1)
        ed.send_frame(self.peer, {'type': 'file', 'path': r'..\outside.txt', 'size': 0})
        self.assertEqual(ed.recv_frame(self.peer)['type'], 'error')
        failed = self.event('failed')
        self.assertIn('Unsafe file path', failed['message'])
        self.worker.join(5)
        self.assertFalse((self.destination / 'outside.txt').exists())

    def test_unwrapped_transfer_merges_existing_folder_without_wrapper(self):
        (self.destination / 'Photos').mkdir()
        (self.destination / 'Photos/keep.txt').write_bytes(b'existing')
        root = self.offer(wrap=False)
        self.send_file('Photos/nested/a.txt', b'photo')
        self.send_file('standalone.txt', b'file')
        self.finish()
        self.assertEqual(root, self.destination)
        self.assertEqual((root / 'Photos/nested/a.txt').read_bytes(), b'photo')
        self.assertEqual((root / 'Photos/keep.txt').read_bytes(), b'existing')
        self.assertEqual((root / 'standalone.txt').read_bytes(), b'file')
        self.assertEqual({path.name for path in root.iterdir()}, {'Photos', 'standalone.txt'})

    def assert_cancel_cleanup(self, wrap, local_cancel):
        (self.destination / 'keep.txt').write_bytes(b'existing')
        self.offer(wrap=wrap)
        self.send_file('Photos/complete.txt', b'complete')
        ed.send_frame(self.peer, {'type': 'file', 'path': 'Photos/partial.bin', 'size': 1024})
        self.peer.sendall(b'partial')
        self.event('file_start')
        if local_cancel:
            self.receiver.cancel('test')
        else:
            self.sender_cancel()
        cancelled = self.event('cancelled')
        self.worker.join(5)
        self.assertEqual(cancelled['cleanup'], 'New transfer output removed')
        self.assertEqual(list(self.destination.iterdir()), [self.destination / 'keep.txt'])
        self.assertEqual((self.destination / 'keep.txt').read_bytes(), b'existing')

    def test_receiver_cancel_removes_wrapped_complete_and_partial_files(self):
        self.assert_cancel_cleanup(True, True)

    def test_sender_cancel_removes_wrapped_complete_and_partial_files(self):
        self.assert_cancel_cleanup(True, False)

    def test_receiver_cancel_removes_unwrapped_complete_and_partial_files(self):
        self.assert_cancel_cleanup(False, True)

    def test_sender_cancel_removes_unwrapped_complete_and_partial_files(self):
        self.assert_cancel_cleanup(False, False)

    def test_cancel_during_save_keeps_replacements_and_removes_new_output(self):
        (self.destination / 'Photos').mkdir()
        original = self.destination / 'Photos/existing.txt'
        original.write_bytes(b'old')
        self.offer(wrap=False)
        self.send_file('Photos/existing.txt', b'replaced')
        self.send_file('Photos/new.txt', b'new')

        def save_then_cancel(source, destination, cancel, owner, created):
            original.write_bytes((source / 'Photos/existing.txt').read_bytes())
            new = destination / 'Photos/new.txt'
            new.write_bytes((source / 'Photos/new.txt').read_bytes())
            created.add(new)
            raise ed.TransferCancelled('Cancelled in Windows')

        with patch.object(ed, 'windows_move_transfer', side_effect=save_then_cancel):
            ed.send_frame(self.peer, {'type': 'done'})
            self.assertEqual(ed.recv_frame(self.peer)['type'], 'cancel')
            self.event('cancelled')
            self.worker.join(5)
        self.assertEqual(original.read_bytes(), b'replaced')
        self.assertEqual(list(self.destination.rglob('*')), [self.destination / 'Photos', original])

    def test_sender_cancel_interrupts_receiver_while_waiting_to_save(self):
        self.offer(wrap=False)
        self.send_file('Photos/a.txt')
        self.send_file('Photos/b.txt')
        saving = threading.Event()

        def wait_for_cancel(source, destination, cancel, owner, created):
            saving.set()
            self.assertTrue(cancel.wait(5), 'Sender cancellation did not reach the save operation')
            raise ed.TransferCancelled('Sender cancelled during save')

        with patch.object(ed, 'windows_move_transfer', side_effect=wait_for_cancel):
            ed.send_frame(self.peer, {'type': 'done'})
            self.assertTrue(saving.wait(5))
            self.sender_cancel()
            self.event('cancelled')
            self.worker.join(5)
        self.assertEqual(list(self.destination.iterdir()), [])

    def test_cancel_cleanup_failure_is_reported_with_output_location(self):
        root = self.offer()
        self.send_file('Photos/a.txt')
        with patch.object(ed.ReceivedOutput, 'cancel', side_effect=PermissionError('File locked')):
            self.receiver.cancel('test')
            failed = self.event('failed')
            self.worker.join(5)
        self.assertEqual(failed['cleanup'], 'Incomplete')
        self.assertEqual(failed['destination'], str(root))
        self.assertIn('File locked', failed['message'])

    def test_interruption_preserves_verified_checkpoint_and_resumes_current_file(self):
        root = self.offer(verify=True)
        self.send_file('Photos/complete.txt', b'complete', verify=True)
        payload = b'abcdefgh' * (ed.BLOCK_SIZE // 8) + b'tail'
        ed.send_frame(self.peer, {'type': 'file', 'path': 'Photos/partial.bin', 'size': len(payload)})
        self.peer.sendall(payload[:ed.BLOCK_SIZE])
        while self.event('progress')['done'] < ed.BLOCK_SIZE:
            pass
        self.peer.sendall(b'ta')
        self.peer.close()
        self.event('paused')
        self.assertTrue(self.receiver.coordinator.locked())
        self.assertEqual((root / 'Photos/complete.txt').read_bytes(), b'complete')
        self.assertEqual((root / 'Photos/partial.bin').stat().st_size, ed.BLOCK_SIZE)
        reply = self.reconnect()
        self.assertEqual((reply['index'], reply['offset'], reply['done']), (1, ed.BLOCK_SIZE, ed.BLOCK_SIZE + 8))
        self.event('resumed')
        ed.send_frame(self.peer, {'type': 'file', 'path': 'Photos/partial.bin', 'size': len(payload), 'offset': reply['offset']})
        self.peer.sendall(payload[reply['offset']:])
        ed.send_frame(self.peer, {'type': 'hash', 'sha256': ed.hashlib.sha256(payload).hexdigest()})
        self.assertEqual(ed.recv_frame(self.peer)['type'], 'file_ok')
        self.finish()
        self.assertEqual((root / 'Photos/partial.bin').read_bytes(), payload)
        self.assertEqual(len(list(self.destination.iterdir())), 1)
        self.assertFalse(self.receiver.coordinator.locked())

    def test_disconnect_after_file_ack_skips_completed_file(self):
        self.offer()
        self.send_file('a.txt')
        self.peer.close()
        self.event('paused')
        reply = self.reconnect()
        self.assertEqual((reply['index'], reply['offset'], reply['done']), (1, 0, 3))
        self.send_file('b.txt')
        self.finish()

    def test_local_cancel_while_paused_removes_output(self):
        self.offer(wrap=False)
        self.send_file('Photos/a.txt')
        self.peer.close()
        self.event('paused')
        self.receiver.cancel('test')
        self.event('cancelled')
        self.assertEqual(list(self.destination.iterdir()), [])
        self.assertFalse(self.receiver.coordinator.locked())

    def test_changed_received_file_is_not_resumed(self):
        root = self.offer()
        self.send_file('a.txt')
        self.peer.close()
        self.event('paused')
        (root / 'a.txt').write_bytes(b'edited')
        self.assertEqual(self.reconnect()['type'], 'error')
        failed = self.event('failed')
        self.assertIn('changed during interruption', failed['message'])

    def test_lost_completion_ack_does_not_repeat_native_save(self):
        self.offer(wrap=False)
        self.send_file('a.txt')
        self.send_file('b.txt')
        original_send = ed.TransferChannel.send

        def lose_done_ack(channel, payload):
            if payload['type'] == 'done_ok':
                channel.close()
                raise ed.TransferInterrupted('Lost final acknowledgement')
            original_send(channel, payload)

        with patch.object(ed, 'windows_move_transfer', wraps=ed.windows_move_transfer) as save:
            with patch.object(ed.TransferChannel, 'send', lose_done_ack):
                ed.send_frame(self.peer, {'type': 'done'})
                self.event('done')
                self.worker.join(5)
            self.assertEqual(self.reconnect()['type'], 'done_ok')
            self.assertEqual(save.call_count, 1)
        self.assertEqual({p.name for p in self.destination.iterdir()}, {'a.txt', 'b.txt'})

    def test_stalled_file_data_pauses_without_deleting_output(self):
        # Override the existing channel timeout; no file bytes arrive after metadata.
        self.offer(file_count=1)
        self.receiver.active_socket.settimeout(0.15)
        ed.send_frame(self.peer, {'type': 'file', 'path': 'a.bin', 'size': 100})
        self.event('paused')
        self.worker.join(5)
        self.assertEqual(self.receiver.session.offset, 0)
        self.assertTrue(self.receiver.coordinator.locked())
        self.assertTrue(self.receiver.session.output.root.exists())

    def test_disconnect_during_windows_save_finishes_once(self):
        self.offer(wrap=False)
        self.send_file('a.txt')
        self.send_file('b.txt')
        saving, proceed = threading.Event(), threading.Event()
        original_save = ed.windows_move_transfer

        def delayed_save(*args):
            saving.set()
            self.assertTrue(proceed.wait(5))
            original_save(*args)

        with patch.object(ed, 'windows_move_transfer', side_effect=delayed_save) as save:
            ed.send_frame(self.peer, {'type': 'done'})
            self.assertTrue(saving.wait(5))
            self.peer.close()
            proceed.set()
            self.event('done')
            self.assertEqual(self.reconnect()['type'], 'done_ok')
            self.assertEqual(save.call_count, 1)

    def test_receiver_shutdown_while_paused_cleans_output(self):
        self.offer()
        self.send_file('a.txt')
        self.peer.close()
        self.event('paused')
        self.receiver.stop()
        self.event('cancelled')
        self.assertEqual(list(self.destination.iterdir()), [])


class NativeSaveTests(unittest.TestCase):
    def test_cancel_before_native_save_does_not_change_existing_files(self):
        with tempfile.TemporaryDirectory() as folder:
            destination = Path(folder).resolve()
            (destination / 'keep.txt').write_bytes(b'existing')
            output = ed.ReceivedOutput(destination, 'Friend', False)
            (output.data_root / 'new.txt').write_bytes(b'new')
            cancel = threading.Event()
            cancel.set()
            with self.assertRaises(ed.TransferCancelled):
                output.save(cancel, 0)
            output.cancel()
            self.assertEqual(list(destination.iterdir()), [destination / 'keep.txt'])


class AutomaticResumeTests(unittest.TestCase):
    def run_transfer(self, verify, wrap, outcome='resume'):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            source = root / 'source'
            destination = root / 'destination'
            source.mkdir()
            destination.mkdir()
            (source / 'a.txt').write_bytes(b'already complete')
            payload = bytes(range(256)) * 8192
            large = source / 'b.bin'
            large.write_bytes(payload)
            receiving, sending = queue.Queue(), queue.Queue()
            receiver = ed.ReceiverService(ed.WifiAdapter('test', 10, '127.0.0.10', 8), receiving, threading.Lock())
            sender = ed.Sender(ed.WifiAdapter('test', 1, '127.0.0.1', 8), sending, threading.Lock())
            cut = threading.Event()
            interruptions = [0]
            offers, checkpoints, sender_actions = [], [], []
            original_emit = ed.emit_transfer
            original_send = ed.TransferChannel.send
            original_connect = sender._connect
            unavailable_attempts = [2 if outcome != 'source_changed' else 0]

            def emit(events, tid, action, **details):
                original_emit(events, tid, action, **details)
                limit = 2 if outcome == 'resume_twice' else 1
                if events is receiving and action == 'progress' and details['current'].endswith('b.bin') and interruptions[0] < limit:
                    interruptions[0] += 1
                    cut.set()
                    ed.close_transfer_socket(receiver.active_socket)

            def send(channel, payload):
                if payload['type'] == 'accept':
                    checkpoints.append(payload.copy())
                original_send(channel, payload)

            def connect(peer_ip):
                if cut.is_set() and unavailable_attempts[0]:
                    unavailable_attempts[0] -= 1
                    raise ConnectionRefusedError('Link temporarily unavailable')
                return original_connect(peer_ip)

            receiver.start()
            try:
                deadline = time.monotonic() + 5
                while not receiver.server_socket or receiver.server_socket.getsockname()[1] != ed.TRANSFER_PORT:
                    self.assertLess(time.monotonic(), deadline)
                    time.sleep(0.01)
                with patch.object(ed, 'BLOCK_SIZE', 65536), patch.object(ed, 'RECONNECT_DELAY', 0.05), \
                        patch.object(ed, 'emit_transfer', emit), patch.object(ed.TransferChannel, 'send', send), \
                        patch.object(sender, '_connect', connect):
                    tid = sender.send('127.0.0.10', 'Friend', [source], verify, wrap)
                    finished = False
                    deadline = time.monotonic() + 10
                    while not finished:
                        self.assertLess(time.monotonic(), deadline, sender_actions)
                        for events in (receiving, sending):
                            try:
                                _, _, action, data = events.get(timeout=0.02)
                            except queue.Empty:
                                continue
                            if events is receiving and action == 'incoming_offer':
                                offers.append(data)
                                data['decision'].accept(destination)
                            if events is sending:
                                sender_actions.append((action, data))
                                if action == 'paused':
                                    if outcome == 'source_changed':
                                        large.write_bytes(b'x' * len(payload))
                                    elif outcome == 'cancel':
                                        sender.cancel(tid)
                                if action == 'worker_stopped':
                                    finished = True
                    self.assertTrue(cut.is_set())
                    self.assertEqual(len(offers), 1)
                    self.assertFalse(sender.coordinator.locked())
                    self.assertFalse(receiver.coordinator.locked())
                    actions = [action for action, _ in sender_actions]
                    if outcome in ('resume', 'resume_twice'):
                        self.assertIn('resumed', actions)
                        self.assertIn('done', actions)
                        self.assertEqual(checkpoints[1]['index'], 1)
                        self.assertGreater(checkpoints[1]['offset'], 0)
                        copies = list(destination.rglob('b.bin'))
                        self.assertEqual(len(copies), 1)
                        self.assertEqual(copies[0].read_bytes(), payload)
                        self.assertEqual(copies[0].with_name('a.txt').read_bytes(), b'already complete')
                        if outcome == 'resume_twice':
                            self.assertEqual(actions.count('paused'), 2)
                            self.assertEqual(actions.count('resumed'), 2)
                    else:
                        self.assertIn('failed' if outcome == 'source_changed' else 'cancelled', actions)
                        if outcome == 'source_changed':
                            failure = next(data['message'] for action, data in sender_actions if action == 'failed')
                            self.assertIn('Source file changed', failure)
                        self.assertEqual(list(destination.iterdir()), [])
            finally:
                sender.cancel()
                receiver.stop()
                receiver.thread.join(2)

    def test_sender_automatically_resumes_verified_transfer(self):
        self.run_transfer(True, True)

    def test_sender_automatically_resumes_unwrapped_unverified_transfer(self):
        self.run_transfer(False, False)

    def test_repeated_connection_interruptions_resume_the_same_transfer(self):
        self.run_transfer(True, True, 'resume_twice')

    def test_changed_source_is_rejected_and_new_output_removed(self):
        self.run_transfer(True, True, 'source_changed')

    def test_sender_cancel_waits_for_reconnection_and_receiver_cleanup(self):
        self.run_transfer(False, False, 'cancel')


if __name__ == '__main__':
    unittest.main()
