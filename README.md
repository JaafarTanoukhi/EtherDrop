# EtherDrop

I made EtherDrop because I wanted an easy way to share big folders between friends on the same network. It is a Windows app that transfers files and folders over a direct Ethernet connection or a shared Wi-Fi network, without uploading them to the cloud or setting up Windows file sharing.

## Download

Download **EtherDrop.exe** from the [latest GitHub release](https://github.com/JaafarTanoukhi/EtherDrop/releases/latest), save it in a writable folder, and run it on both laptops. It is a standalone executable: no installation or Python is needed.

EtherDrop 2.0 offers two modes: **Ethernet** for a direct cable or isolated switch without a gateway, and **Wi-Fi** for laptops already connected to the same local wireless network. Wi-Fi mode sends to multiple receivers simultaneously.

## Updates

EtherDrop checks its public GitHub releases automatically each time it opens. You can also click **Check for updates** on the opening screen. If a newer version is available, an update page shows its notes and asks you to approve **Download & restart**. The download page shows downloaded and total MB, current MB/s, and a progress bar. Update checks require internet access, which can use Wi-Fi even while transfers use Ethernet.

After downloading the new EXE, EtherDrop starts a temporary updater, closes, replaces its existing executable, cleans up the temporary files, and reopens. The app remains a single EXE. Updates wait until transfer diagnostics and Ethernet setup are closed. If replacement fails, the updater attempts to restore the previous executable and displays the error.

When a manual check finds no newer version, EtherDrop opens **What's new** with the current version's update notes. The same in-app page appears once on the first launch of each new version, including immediately after a self-update. Notes are bundled in the EXE, so that first-launch page also works offline. The app remembers the acknowledged version in `%LOCALAPPDATA%\EtherDrop\updates.json`.

Automatic checks stay quiet when offline or already up to date. Running from Python can check for updates but cannot replace the Python source with an EXE.

## Publishing a new version

Make changes on **main** first, then advance **release** to publish a new version. Keep `main` equal to or ahead of `release`:

```powershell
git switch main
git pull --ff-only
# Make your changes and commit them.
git push origin main
git switch release
git pull --ff-only
git merge --ff-only main
git push origin release
git switch main
```

The first release is **v1.0.0**. Each subsequent push automatically increments the patch: **1.0.1**, **1.0.2**, and so on. For an explicit minor or major release, set `APP_VERSION` in `etherdrop.py` to a higher version, such as **1.1.0** or **2.0.0**, before pushing. Patch increments then continue from that version. Normal pushes do not require editing a version number.

The GitHub Actions workflow tests the app, prepares the version and notes, builds the standalone Windows EXE, commits the version, manifest, and notes on `release`, merges that commit into `main`, and pushes both branches and the version tag together before publishing **EtherDrop.exe**. Any newer work on `main` is preserved. If a merge conflicts or either branch changes during the build, publication stops so the branches can be reconciled. The source, tag, and EXE have matching versions. Its own push uses GitHub's built-in token and does not trigger another release. Pull the bot's commit after a release finishes before making your next changes.

Edit **RELEASE_NOTES.md** before pushing to provide your own update notes. If you leave it unchanged, the workflow generates notes from commit titles since the previous release. Write meaningful commit titles so those automatic notes are useful. The same notes appear on GitHub and inside the EXE.

Pushes to `main` do not publish releases. You can also build locally and upload **EtherDrop.exe** to a matching GitHub release manually. EtherDrop compares stable `vMAJOR.MINOR.PATCH` versions and never installs an older release.

You can start a build manually from **Actions → Release EtherDrop → Run workflow**, selecting the `release` branch.

## Ethernet mode guarantees

- It never selects a Wi-Fi adapter.
- It only selects an **UP, physical IEEE 802.3 Ethernet adapter**.
- It refuses Ethernet adapters that have a default gateway, because those look like normal LAN connections.
- Discovery uses IPv6 link-local multicast on the chosen Ethernet interface.
- TCP is explicitly bound to the chosen Ethernet adapter's IPv6 link-local address.
- No SMB, Windows sharing, DHCP, static IP, accounts, or cloud service is used.

### Important physical limitation

Software cannot prove that a cable goes **literally laptop-to-laptop** instead of through an unmanaged Ethernet switch containing only those two laptops. Those two topologies look identical at the network layer.

EtherDrop's practical enforcement is therefore:
1. Physical Ethernet only.
2. No Wi-Fi.
3. No Ethernet default gateway.
4. Link-local traffic only.

## Performance

The transfer engine:
- streams files directly; it never ZIPs them first;
- uses 8 MiB reusable buffers;
- avoids per-block allocations;
- uses large TCP socket buffers;
- performs no compression;
- has SHA-256 verification **off by default** for maximum speed.

Typical real-world targets with fast SSDs:
- 1 GbE: about 105-118 MB/s
- 2.5 GbE: about 270-295 MB/s
- 10 GbE: storage/CPU becomes much more important

For 30 GB+ transfers, prefer 2.5 GbE or faster adapters if both laptops support them.

## Run from Python

Install Python 3.12+ on both laptops.

Open PowerShell in this folder:

```powershell
python etherdrop.py
```

No third-party Python packages are required.

## Build an EXE

In PowerShell:

```powershell
python -m pip install --upgrade pyinstaller
.\build.bat
```

The EXE will be:

```text
dist\EtherDrop.exe
```

Copy that EXE to both laptops.

## Use Ethernet mode

1. Connect the laptops directly with a normal Ethernet cable.
2. Keep Wi-Fi on if you want; EtherDrop will not use it.
3. Run EtherDrop on both laptops.
4. Choose **Send** on one laptop and **Receive** on the other.
5. If Windows Firewall prompts you, allow the app.
6. Wait until each laptop shows **Connected to** the other laptop. A missing cable or connection problem appears in the center of the screen with the next step. Open **Connection** for link status and adapter details.
7. On the sender, drag files or folders from Windows Explorer into the selected-files list, or click **Add files** or **Add folder**, then click **Send**. Drops add to the current selection and skip duplicates.
8. On the receiver, review the offer in the main window and click **Choose destination & accept**.
9. Pick the parent folder for the incoming transfer. Canceling the picker declines the transfer.

The receiver always chooses the destination. **Wrap transfer in a folder** is enabled by default in the sender's **Transfer options**, creating a timestamped transfer folder inside the chosen destination. Turn it off to save the selected files and folders directly there, preserving their folder structure. When wrapping is off, the receiver saves the completed download through Windows, which shows its native replace/skip dialog for conflicting names.

If the connection drops, EtherDrop waits and reconnects automatically while both apps remain open. It keeps completed files and continues the interrupted file from its last saved block, using the same approved destination. With SHA-256 enabled, it verifies the whole resumed file. Changed source or received files stop the transfer instead of mixing old and new data. Resume works independently for each Wi-Fi receiver.

**Cancel transfer** removes newly created output. If the sender is disconnected, cancellation waits for reconnection so the receiver can finish cleanup; cancelling on the receiver removes its paused output immediately. Closing either app cancels its pending transfer and waits for cleanup before exiting. Resume does not persist after closing either app.

## Use Wi-Fi mode

1. Connect all laptops to the same Wi-Fi network or an existing hotspot.
2. Open EtherDrop and select **Wi-Fi** on the opening screen. The app uses restrained blue accents for Wi-Fi and slate gray for Ethernet.
3. Choose **Send** on one laptop and **Receive** on the others. If multiple physical Wi-Fi adapters are connected, choose the one to use.
4. Allow EtherDrop through Windows Firewall when prompted. Wait for the sender to show connected receivers. Open **Connection** for their names and addresses.
5. Drag files or folders into the selected-files list, or use **Add files** or **Add folder**, then click **Send**. Every connected receiver receives an offer; later arrivals wait for the next send.
6. Each receiver chooses its destination and approves independently. Approved transfers start without waiting for the other laptops.
7. Select a receiver in the main window to review its progress. Open **Details** for that laptop's diagnostics. Cancel an individual receiver or use **Cancel all**.

A receiver declining, disconnecting, or failing does not stop the other transfers. Each receiver accepts one transfer at a time. Click **Done** after reviewing the results before starting another transfer or changing modes. Ethernet remains the default on every launch.

Wi-Fi uses local IPv4 subnet broadcast discovery (UDP 45670) and separate direct TCP transfers (TCP 45671), bound to the selected Wi-Fi adapter. No files go to the cloud. Windows manages Wi-Fi TCP buffer sizes automatically; Ethernet keeps its fixed large buffers. Transfers share the available wireless bandwidth; sending to more laptops can reduce the speed to each one.

The network must allow laptop-to-laptop traffic and broadcast discovery. Guest networks or client isolation can prevent discovery and transfers. EtherDrop does not create a hotspot, change router settings, or automatically configure Wi-Fi firewall rules. Native Windows file and folder pickers keep the system theme.

## Automatic Ethernet setup

Open **Connection → Set up Ethernet** if Windows or firewall settings prevent the laptops from pairing. Review the setup page and click **Configure Ethernet**. Windows will request administrator permission.

Before making any change, EtherDrop verifies that the target is:

- an active physical IEEE 802.3 Ethernet adapter;
- connected without an IPv4 or IPv6 default gateway;
- therefore consistent with EtherDrop's isolated direct-link requirement.

If that safety check passes, setup:

- enables the adapter's IPv6 binding when necessary;
- confirms Windows created an IPv6 link-local address;
- creates inbound discovery and transfer firewall rules scoped to the EtherDrop executable, the selected wired adapter, and IPv6 link-local peers only;
- disables supported Ethernet selective-suspend settings;
- restarts the Ethernet adapter only when IPv6 had to be enabled.

It does not change Wi-Fi, IPv4 addresses, DNS, DHCP, MTU, speed/duplex, or router settings. It refuses routed Ethernet rather than removing a gateway automatically.

As with EtherDrop's regular connection detection, software cannot distinguish a literal laptop-to-laptop cable from an isolated unmanaged switch containing only those two laptops. Both appear identical at the network layer.

## Transfer diagnostics and cancellation

Transfers stay in the main app window. **Overview** shows the peer, contents, progress, speed, and time remaining. **Details** opens the full diagnostics, file paths, destination, and activity log without interrupting the transfer. In Wi-Fi mode, the sender selects a receiver to see that laptop's independent progress and diagnostics. Click **Done** after a transfer finishes, fails, or is cancelled to return to file selection.

The **Details** view includes:

- live overall and current-file progress;
- current, average, and peak observed speed;
- elapsed time, remaining bytes, and ETA;
- every current source, relative, and destination path available to that laptop;
- file counts, sizes, completion confirmations, and SHA-256 digests when verification is enabled;
- transfer, protocol, session, peer, adapter, IPv6, TCP endpoint, socket-buffer, and link-capacity details;
- receiver disk capacity and estimated space after the transfer;
- precise timestamps and a copyable activity log;
- exact error type, partial-data location, and cancellation state when applicable.

**Cancel transfer** closes the active transfer connection. Cancellation is propagated so both laptops stop and show the final state. The receiver removes the transfer's temporary files and newly created destination files and folders. Existing files and folders are preserved; replacements already completed through Windows remain in place. If Windows prevents cleanup, diagnostics show the error and output location.

The app can be minimized without pausing the background transfer. While a transfer is active, EtherDrop asks Windows to block automatic system sleep; the display may still turn off. Manually forcing sleep or hibernation pauses networking, and no application can continue transferring while the hardware is asleep. A transfer can resume only if Windows preserves the TCP connection across that sleep.

## Transfer options

**Wrap transfer in a folder** is checked by default. Turn it off to place the selected files and folders directly in the receiver's chosen destination. Windows handles name conflicts on the receiver when the download is saved.

Open **Transfer options** on the sender screen to enable **Verify files with SHA-256**. This hashes every file while it is being transferred and compares the final digest on the receiver.

Leave it off for absolute maximum throughput.
Turn it on when end-to-end integrity matters more than a small amount of CPU overhead.

## Troubleshooting

### No Ethernet detected
Make sure:
- the cable is connected directly between the laptops;
- both Ethernet adapters show "Connected" in Windows;
- the adapter is a physical Ethernet adapter, not a virtual/VPN adapter.

### Ethernet is rejected because it has a gateway
EtherDrop thinks that Ethernet adapter is connected to a normal routed LAN. Disconnect it from the router/switch and connect the two laptops directly.

### Laptops do not discover each other
Windows Firewall may be blocking the first run. Allow EtherDrop/Python when prompted, then open **Connection** and click **Rescan** on both laptops.

### Slow transfer
Check the link speed shown in the app. If it says 100 Mbps instead of 1.0/2.5 Gbps, the cable or adapter negotiation is the bottleneck.

Also make sure both source and destination drives can sustain the desired speed.
