import tempfile
from contextlib import contextmanager
import time
import tkinter as tk
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

import etherdrop as ed


class InterfaceTests(unittest.TestCase):
    def setUp(self):
        self.patches = [
            patch.object(ed.EtherDropApp, 'check_for_updates'),
            patch.object(ed.EtherDropApp, '_show_startup_notes'),
            patch.object(ed, 'load_update_state', return_value={}),
            patch.object(ed, 'save_update_state'),
            patch.object(ed, 'set_system_awake', return_value=(False, 'Test')),
        ]
        for item in self.patches:
            item.start()
            self.addCleanup(item.stop)
        self.app = ed.EtherDropApp()
        self.app.withdraw()
        self.errors = []
        self.app.report_callback_exception = lambda *args: self.errors.append(args)
        self.addCleanup(self.close_app)

    def close_app(self):
        self.app.shutdown_services()
        self.app._closing = True
        for callback in self.app.tk.call('after', 'info'):
            self.app.after_cancel(callback)
        self.app.destroy()

    def sender_screen(self, wifi=False):
        self.app._select_mode('wifi' if wifi else 'ethernet')
        self.app.role = 'sender'
        self.app._build_main_ui()
        self.app.adapter = (ed.WifiAdapter('Wi-Fi', 1, '127.0.0.1', 8) if wifi else
                            ed.EthernetAdapter('Ethernet', 1, 'fe80::1', '', '1 Gbps', 10**9, 10**9, False))
        self.app.sender = Mock()
        self.app.peer_ip = '127.0.0.2' if wifi else 'fe80::2'
        self.app.peer_name = 'Friend'
        self.app._refresh_connection_ui()

    @contextmanager
    def shell_data(self, paths):
        shell32, ole32 = ed.ctypes.windll.shell32, ed.ctypes.windll.ole32
        pointer = ed.ctypes.c_void_p
        shell32.SHParseDisplayName.argtypes = [ed.ctypes.c_wchar_p, pointer, ed.ctypes.POINTER(pointer),
                                               ed.ctypes.c_uint, pointer]
        shell32.SHCreateShellItemArrayFromIDLists.argtypes = [ed.ctypes.c_uint, pointer, ed.ctypes.POINTER(pointer)]
        ole32.CoTaskMemFree.argtypes = [pointer]
        pidls, items_array, data = [], pointer(), pointer()
        try:
            for path in paths:
                pidl = pointer()
                self.assertEqual(shell32.SHParseDisplayName(str(path), None, ed.ctypes.byref(pidl), 0, None), 0)
                pidls.append(pidl)
            items = (pointer * len(pidls))(*pidls)
            iid = ed.ctypes.create_string_buffer(ed.uuid.UUID('0000010e-0000-0000-c000-000000000046').bytes_le, 16)
            handler = ed.ctypes.create_string_buffer(ed.uuid.UUID('b8c0bd9f-ed24-455c-83e6-d5390c4fe8c4').bytes_le, 16)
            self.assertEqual(shell32.SHCreateShellItemArrayFromIDLists(len(pidls), items, ed.ctypes.byref(items_array)), 0)
            table = ed.ctypes.cast(items_array, ed.ctypes.POINTER(ed.ctypes.POINTER(pointer))).contents
            bind = ed.ctypes.WINFUNCTYPE(ed.ctypes.c_long, pointer, pointer, pointer, pointer, pointer)(table[3])
            self.assertEqual(bind(items_array, None, handler, iid, ed.ctypes.byref(data)), 0)
            yield data
        finally:
            for interface in (data, items_array):
                if interface.value:
                    table = ed.ctypes.cast(interface, ed.ctypes.POINTER(ed.ctypes.POINTER(pointer))).contents
                    ed.ctypes.WINFUNCTYPE(ed.ctypes.c_uint, pointer)(table[2])(interface)
            for pidl in pidls:
                ole32.CoTaskMemFree(pidl)

    def point_in(self, widget):
        return ed.WindowsFileDrop.Point(widget.winfo_rootx() + 10, widget.winfo_rooty() + 10)

    def drop_paths(self, widget, paths):
        target = widget.file_drop
        with self.shell_data(paths) as data:
            effect = ed.ctypes.c_uint(1)
            point = self.point_in(widget)
            self.assertEqual(target.callbacks[3](target.interface, data, 0, point, ed.ctypes.byref(effect)), 0)
            self.assertEqual(effect.value, 1)
            self.assertEqual(target.callbacks[6](target.interface, data, 0, point, ed.ctypes.byref(effect)), 0)
            self.assertEqual(effect.value, 1)

    def accepts_files(self, widget):
        target = self.app.listbox.file_drop
        effect = ed.ctypes.c_uint(1)
        target.callbacks[4](target.interface, 0, self.point_in(widget), ed.ctypes.byref(effect))
        return bool(effect.value)

    def test_native_drop_appends_files_and_folders_without_duplicates_in_both_modes(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder).resolve()
            existing = root / 'already selected.txt'
            existing.write_text('Selected')
            file = root / 'ملف 📁 with spaces.txt'
            file.write_text('Dropped')
            directory = root / 'Folder with spaces'
            directory.mkdir()
            for wifi in (False, True):
                with self.subTest(wifi=wifi):
                    self.sender_screen(wifi)
                    self.app.deiconify()
                    self.app.update()
                    self.app.selected_paths = [existing]
                    self.app.refresh_list()
                    self.drop_paths(self.app.listbox, [existing, file, directory, file])
                    self.assertEqual(self.app.selected_paths, [existing])
                    self.app._drain_events()
                    self.assertEqual(self.app.selected_paths, [existing, file, directory])
                    self.assertEqual(self.app.listbox.get(0, tk.END),
                                     ('  already selected.txt', f'  {file.name}', '  Folder with spaces /'))
                    self.assertEqual(self.app.selection_var.get(), '3 items selected')
                    self.assertEqual(str(self.app.send_button.cget('state')), 'normal')
            self.assertFalse(self.errors)

    def test_only_the_visible_sender_list_accepts_drops(self):
        self.sender_screen()
        self.app.deiconify()
        self.app.update()
        with tempfile.TemporaryDirectory() as folder:
            file = Path(folder) / 'example.txt'
            file.write_text('Example')
            with self.shell_data([file]) as data:
                target = self.app.listbox.file_drop
                effect = ed.ctypes.c_uint(1)
                target.callbacks[3](target.interface, data, 0, self.point_in(self.app.listbox), ed.ctypes.byref(effect))
                self.assertEqual(effect.value, 1)
        self.assertTrue(self.accepts_files(self.app.listbox))
        self.assertFalse(self.accepts_files(self.app.screen))
        self.assertFalse(self.accepts_files(self.app))
        self.app._show_transfer_options()
        self.app.update()
        self.assertFalse(self.accepts_files(self.app.listbox))
        self.app._dismiss_page()
        self.app.update()
        self.assertTrue(self.accepts_files(self.app.listbox))
        self.app.transfer_dialog = ed.ttk.Frame(self.app)
        ed.show_view(self.app.transfer_dialog, self.app.screen, animate=False)
        self.app.update()
        self.assertFalse(self.accepts_files(self.app.listbox))
        self.assertFalse(self.accepts_files(self.app.transfer_dialog))
        self.app.transfer_dialog.destroy()
        self.app.transfer_dialog = None
        self.app.role = 'receiver'
        self.app._build_main_ui()
        self.app.update()
        self.assertIsNone(self.app.listbox)
        self.assertFalse(target.enabled)
        self.assertEqual(target.references, 1)
        self.assertFalse(self.errors)

    def test_queued_drop_is_ignored_after_leaving_the_sender_list(self):
        self.sender_screen()
        self.app.deiconify()
        self.app.update()
        with tempfile.TemporaryDirectory() as folder:
            file = Path(folder) / 'example.txt'
            file.write_text('Example')
            self.drop_paths(self.app.listbox, [file])
            self.app._show_transfer_options()
            self.app._drain_events()
            self.assertEqual(self.app.selected_paths, [])
            self.app._dismiss_page()
            self.app.update()
            self.drop_paths(self.app.listbox, [file])
            self.app._build_main_ui()
            self.app._drain_events()
            self.assertEqual(self.app.selected_paths, [])
        self.assertFalse(self.errors)

    def test_receiver_shows_the_current_connection_step_and_recovers(self):
        self.app.role = 'receiver'
        self.app._build_main_ui()
        self.assertIn('Checking', self.app.state_title.cget('text'))
        message = 'No active physical Ethernet cable was detected.\nConnect the two laptops directly with Ethernet, then click Rescan.'
        self.app.events.put(('adapter_error', self.app.scan_token, 'receiver', message))
        self.app._drain_events()
        self.assertEqual(self.app.state_message.cget('text'), message)
        self.assertNotIn('Waiting for files', self.app.state_title.cget('text'))
        self.assertTrue(self.app.state_actions.winfo_manager())
        adapter = ed.EthernetAdapter('Ethernet', 1, 'fe80::1', '', '1 Gbps', 10**9, 10**9, False)
        with patch.object(self.app, '_start_services', side_effect=lambda value: setattr(self.app, 'adapter', value)):
            self.app.events.put(('adapter', self.app.scan_token, 'receiver', adapter))
            self.app._drain_events()
        self.assertIn('Looking for a sender', self.app.state_title.cget('text'))
        self.app.events.put(('peer', 'Friend', 'fe80::2', 'sender'))
        self.app._drain_events()
        self.assertEqual(self.app.state_title.cget('text'), 'Waiting for files')
        self.assertFalse(self.app.state_actions.winfo_manager())
        self.app.events.put(('peer_lost',))
        self.app._drain_events()
        self.assertIn('connection to the other laptop was lost', self.app.state_message.cget('text'))
        self.assertNotIn('Waiting for files', self.app.state_title.cget('text'))

    def test_wifi_peer_addresses_are_in_connection_and_empty_list_is_hidden(self):
        self.sender_screen(wifi=True)
        self.assertIsNone(self.app.peer_tree)
        self.app._show_connection()
        self.assertFalse(self.app.peer_list.winfo_manager())
        self.app.wifi_peers = {'one': {'name': 'Friend', 'ip': '127.0.0.2', 'role': 'receiver'}}
        self.app._refresh_wifi_peers()
        self.assertTrue(self.app.peer_list.winfo_manager())
        self.assertEqual(self.app.peer_tree.item('one', 'values'), ('127.0.0.2',))
        self.assertEqual(self.app.connection_summary_var.get(), '1 receiver connected')
        self.app.wifi_peers.clear()
        self.app._refresh_wifi_peers()
        self.assertFalse(self.app.peer_list.winfo_manager())

    def test_neutral_updates_restore_mode_and_rapid_navigation_finishes(self):
        self.app._select_mode('wifi')
        self.app._show_release_notes("You're up to date", 'Offline notes')
        self.assertTrue(self.app.page_neutral)
        self.assertEqual(ed.COLOR_ACCENT, ed.THEMES['neutral']['COLOR_ACCENT'])
        self.app._dismiss_page()
        self.assertEqual(ed.COLOR_ACCENT, ed.THEMES['wifi']['COLOR_ACCENT'])
        for mode in ('ethernet', 'wifi', 'ethernet'):
            self.app._select_mode(mode)
            self.app._show_help()
            self.app._dismiss_page()
        deadline = time.monotonic() + 2
        while self.app.motion_callback is not None and time.monotonic() < deadline:
            self.app.update()
            time.sleep(.01)
        self.assertEqual(self.app.screen.winfo_manager(), 'pack')
        self.assertIsNone(self.app.motion_callback)
        self.assertFalse(self.errors)

    def test_visible_fades_keep_window_size_and_leave_no_overlay(self):
        self.app.deiconify()
        self.app.update()
        original_size = (self.app.winfo_width(), self.app.winfo_height())
        snapshot = tk.PhotoImage(master=self.app, width=original_size[0], height=original_size[1])
        snapshot.put(ed.COLOR_BG, to=(0, 0, *original_size))
        with patch.object(ed, 'view_snapshot', return_value=snapshot):
            self.app._select_mode('wifi')
            self.assertIs(self.app.motion_parent, self.app)
            self.assertEqual(self.app.motion_overlay.state(), 'normal')
            self.app._show_help()
            self.app._dismiss_page()
            self.app.role = 'receiver'
            self.app._build_main_ui()
        self.assertEqual((self.app.winfo_width(), self.app.winfo_height()), original_size)
        deadline = time.monotonic() + 2
        while self.app.motion_parent is not None and time.monotonic() < deadline:
            self.app.update()
            time.sleep(.01)
        self.assertIsNone(self.app.motion_callback)
        self.assertIsNone(self.app.motion_parent)
        self.assertEqual(self.app.motion_overlay.state(), 'withdrawn')
        self.assertEqual(float(self.app.attributes('-alpha')), 1)
        self.assertFalse(self.errors)

    def test_fade_is_presented_before_the_page_and_palette_change(self):
        self.app.deiconify()
        self.app.update()
        old_screen = self.app.screen
        snapshot = tk.PhotoImage(master=self.app, width=self.app.winfo_width(), height=self.app.winfo_height())
        presented = []
        native_flush = ed.ctypes.windll.dwmapi.DwmFlush
        native_set_attribute = ed.ctypes.windll.dwmapi.DwmSetWindowAttribute
        transitions = []

        def flush():
            presented.append((old_screen.winfo_exists(), ed.COLOR_BG,
                              self.app.motion_overlay.winfo_ismapped(),
                              float(self.app.motion_overlay.attributes('-alpha'))))
            return native_flush()

        def set_attribute(handle, attribute, value, size):
            result = native_set_attribute(handle, attribute, value, size)
            transitions.append((attribute, ed.ctypes.cast(value, ed.ctypes.POINTER(ed.ctypes.c_int)).contents.value, result))
            return result

        with patch.object(ed, 'view_snapshot', return_value=snapshot), \
                patch.object(ed.ctypes.windll.dwmapi, 'DwmFlush', side_effect=flush), \
                patch.object(ed.ctypes.windll.dwmapi, 'DwmSetWindowAttribute', side_effect=set_attribute):
            self.app._select_mode('wifi')
        self.assertEqual(presented, [(1, ed.THEMES['ethernet']['COLOR_BG'], 1, 1)])
        self.assertFalse(old_screen.winfo_exists())
        user32 = ed.ctypes.windll.user32
        handle = user32.GetAncestor(self.app.motion_overlay.winfo_id(), 2)
        user32.GetWindowLongW.argtypes = [ed.ctypes.c_void_p, ed.ctypes.c_int]
        self.assertTrue(user32.GetWindowLongW(handle, -20) & 0x00080000)
        self.assertEqual(transitions, [(3, 1, 0)])
        opacity = 1.0
        deadline = time.monotonic() + 2
        while self.app.motion_parent is not None and time.monotonic() < deadline:
            self.app.update()
            current = float(self.app.motion_overlay.attributes('-alpha'))
            self.assertLessEqual(current, opacity)
            opacity = current
            time.sleep(.01)
        self.assertEqual(opacity, 0)
        self.assertFalse(self.errors)

    def test_reused_fade_cover_is_repainted_while_still_transparent(self):
        self.app.deiconify()
        self.app.update()
        snapshot = tk.PhotoImage(master=self.app, width=self.app.winfo_width(), height=self.app.winfo_height())
        snapshot.put('red', to=(0, 0, snapshot.width(), snapshot.height()))
        with patch.object(ed, 'view_snapshot', return_value=snapshot):
            ed.begin_motion(self.app)
        self.app.update()
        ed.finish_motion(self.app)
        self.app.update()
        snapshot = tk.PhotoImage(master=self.app, width=snapshot.width(), height=snapshot.height())
        snapshot.put('blue', to=(0, 0, snapshot.width(), snapshot.height()))
        presented = []
        native_flush = ed.ctypes.windll.dwmapi.DwmFlush
        user32, gdi32 = ed.ctypes.windll.user32, ed.ctypes.windll.gdi32
        user32.GetWindowDC.argtypes, user32.GetWindowDC.restype = [ed.ctypes.c_void_p], ed.ctypes.c_void_p
        user32.ReleaseDC.argtypes = [ed.ctypes.c_void_p, ed.ctypes.c_void_p]
        gdi32.GetPixel.argtypes = [ed.ctypes.c_void_p, ed.ctypes.c_int, ed.ctypes.c_int]

        def flush():
            handle = self.app.motion_label.winfo_id()
            dc = user32.GetWindowDC(handle)
            presented.append(gdi32.GetPixel(dc, 20, 20))
            user32.ReleaseDC(handle, dc)
            return native_flush()

        with patch.object(ed, 'view_snapshot', return_value=snapshot), \
                patch.object(ed.ctypes.windll.dwmapi, 'DwmFlush', side_effect=flush):
            self.app._select_mode('wifi')
        self.assertEqual(presented, [0xFF0000], 'The cover still contains the previous image when it becomes visible')
        self.assertFalse(self.errors)

    def test_mode_and_options_preserve_selection(self):
        self.sender_screen(wifi=True)
        self.app.selected_paths = [Path(__file__)]
        self.app.refresh_list()
        self.app._show_transfer_options()
        self.assertTrue(self.app.wrap_var.get())
        self.app.wrap_var.set(False)
        self.app.verify_var.set(True)
        self.app._dismiss_page()
        self.assertEqual(self.app.selected_paths, [Path(__file__)])
        self.assertTrue(self.app.verify_var.get())
        self.assertFalse(self.app.wrap_var.get())
        self.assertIsNone(self.app.update_button)
        self.assertEqual(ed.COLOR_ACCENT, ed.THEMES['wifi']['COLOR_ACCENT'])

    def test_transfer_details_cancellation_and_return_to_files(self):
        self.sender_screen()
        self.app.selected_paths = [Path(__file__)]
        panel = self.app._open_transfer_dialog('test', 'Sending', 'Friend', 'fe80::2', True,
                                               self.app.selected_paths, self.app.sender.cancel)
        self.assertIsInstance(panel, tk.Frame)
        self.assertFalse(self.app.screen.winfo_manager())
        panel.apply_event('prepared', {'file_count': 2, 'total': 100, 'roots': ['Photos'], 'verify': True})
        panel._show_transfer_page(True)
        panel.apply_event('progress', {'done': 25, 'total': 100, 'current': 'Photos/a.jpg'})
        self.assertEqual(panel.details['Overall progress'], '25.00%')
        panel.copy_diagnostics()
        self.assertIn('Photos/a.jpg', panel.clipboard_get())
        panel._show_transfer_page(False)
        panel._cancel_or_close()
        self.app.sender.cancel.assert_called_once()
        panel.apply_event('cancelled', {'message': 'Stopped', 'destination': 'C:/partial'})
        self.assertIn('C:/partial', panel.destination_var.get())
        panel._cancel_or_close()
        self.assertIsNone(self.app.transfer_dialog)
        self.assertTrue(self.app.screen.winfo_manager())
        self.assertEqual(self.app.selected_paths, [Path(__file__)])
        self.app.update()
        self.assertFalse(self.errors)

    def test_incoming_offer_requires_destination_and_keeps_full_details(self):
        self.sender_screen()
        self.app.role = 'receiver'
        self.app.receiver = Mock()
        decision = ed.IncomingTransferDecision()
        self.app._handle_transfer_event('incoming', 'incoming_offer', {
            'decision': decision, 'peer': 'Friend', 'peer_ip': 'fe80::2',
            'roots': ['Photos'], 'file_count': 3, 'total': 4096, 'verify': True,
        })
        panel = self.app.transfer_dialog
        self.assertFalse(decision.ready.is_set())
        self.assertFalse(panel.progress_area.winfo_manager())
        self.assertEqual(panel.details['File count'], '3')
        self.assertIn('Photos', panel.contents_var.get())
        with tempfile.TemporaryDirectory() as destination:
            with patch.object(ed.filedialog, 'askdirectory', return_value=destination):
                panel.accept_button.invoke()
            self.assertTrue(decision.ready.is_set())
            self.assertEqual(decision.destination, Path(destination))
        panel.apply_event('start', {'peer': 'Friend', 'file_count': 3, 'total': 4096})
        self.assertFalse(panel.accept_button.winfo_manager())
        self.assertTrue(panel.progress_area.winfo_manager())

    def test_group_selects_independent_diagnostics_and_cancels_one(self):
        self.sender_screen(wifi=True)
        group = ed.GroupTransferDialog(self.app, {
            'a': {'name': 'One', 'ip': '127.0.0.2'},
            'b': {'name': 'Two', 'ip': '127.0.0.3'},
        }, [], False)
        self.app.transfer_dialog = group
        ed.show_view(group, self.app.screen)
        group.apply_transfer('a', 'progress', {'done': 50, 'total': 100})
        group.apply_transfer('b', 'failed', {'message': 'Offline'})
        self.assertEqual(group.rows['a'][1], '50.0%')
        self.assertEqual(group.rows['b'][0], 'Failed')
        group.summary.selection_set('a')
        group._select()
        group.panels['a']._cancel_or_close()
        self.app.sender.cancel.assert_called_once_with('a')
        group.complete()
        group._cancel_or_close()
        self.assertIsNone(self.app.transfer_dialog)
        self.app.update()
        self.assertFalse(self.errors)

    def test_resume_keeps_cancel_available_and_preserves_elapsed_time(self):
        self.sender_screen(wifi=True)
        group = ed.GroupTransferDialog(self.app, {
            'a': {'name': 'One', 'ip': '127.0.0.2'},
            'b': {'name': 'Two', 'ip': '127.0.0.3'},
        }, [], True)
        panel = group.panels['a']
        group.apply_transfer('a', 'start', {'total': 100, 'file_count': 2})
        started = panel.transfer_started_monotonic
        group.apply_transfer('a', 'progress', {'done': 60, 'total': 100})
        group.apply_transfer('a', 'paused', {})
        self.assertFalse(panel.finished)
        self.assertFalse(panel.action_button.instate(['disabled']))
        self.assertEqual(panel.rate_var.get(), 'Waiting')
        self.assertEqual(group.rows['a'][0], 'Waiting to reconnect')
        self.assertEqual(group.rows['b'][0], 'Preparing')
        group.apply_transfer('a', 'resumed', {'done': 50, 'total': 100, 'index': 1})
        self.assertEqual(panel.transfer_started_monotonic, started)
        self.assertEqual(panel.last_progress_bytes, 50)
        self.assertEqual(panel.details['Files completed'], '1')
        self.assertEqual(group.rows['a'][0], 'Transferring')
        self.assertEqual(group.rows['a'][1], '50.0%')
        group.destroy()

    def test_closing_waits_for_transfer_cancellation_and_cleanup(self):
        self.sender_screen()
        self.app.coordinator.acquire()
        with patch.object(self.app, 'destroy') as destroy:
            self.app._close()
            self.app._close()
            self.app.sender.cancel.assert_called_once_with()
            destroy.assert_not_called()
            self.app.coordinator.release()
            self.app._close()
            destroy.assert_called_once_with()

    def test_release_notes_are_in_app_and_acknowledged_on_return(self):
        self.app._show_release_notes('Welcome', 'Offline bundled notes')
        self.assertIsInstance(self.app.release_notes_dialog, ed.ttk.Frame)
        self.assertIsNone(self.app.grab_current())
        self.app._dismiss_page()
        ed.save_update_state.assert_called_once_with({'seen_version': ed.APP_VERSION})
        self.assertIsNone(self.app.release_notes_dialog)

    def test_update_page_waits_for_explicit_download_approval(self):
        release = {'version': 'v9.0.0', 'notes': 'New release'}
        with patch.object(ed.sys, 'frozen', True, create=True), patch.object(self.app, '_download_offered_update') as download:
            self.app._offer_update(release, True)
            download.assert_not_called()
            self.assertFalse(self.app.update_installing)
            button = next(child for child in self.app.page.winfo_children()
                          if isinstance(child, ed.ttk.Button) and child.cget('text') == 'Download & restart')
            button.invoke()
            download.assert_called_once_with(release)

    def test_update_progress_displays_megabytes_speed_and_bar(self):
        self.app.events.put(('update_progress', 24_000_000, 50_000_000, 6_000_000))
        self.app._drain_events()
        self.assertEqual(self.app.update_var.get(), '24.0 / 50.0 MB · 6.0 MB/s')
        self.assertEqual(self.app.update_progress_var.get(), 48)

    def test_ethernet_setup_waits_for_explicit_configuration_approval(self):
        self.sender_screen()
        with patch.object(self.app, '_begin_ethernet_setup') as configure:
            self.app.auto_configure_ethernet()
            configure.assert_not_called()
            self.assertFalse(self.app.setup_in_progress)
            button = next(child for child in self.app.page.winfo_children()
                          if isinstance(child, ed.ttk.Button) and child.cget('text') == 'Configure Ethernet')
            button.invoke()
            configure.assert_called_once()


if __name__ == '__main__':
    unittest.main()
