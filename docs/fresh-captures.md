# Fresh video capture pilot

The completed evaluation of five YouTube and five Twitch sessions, including the final
selection protocol and confusion matrices, is in the [video report notebook](../notebooks/02_video_services.ipynb).
The audit and planning notes below describe the collection decisions leading up to that batch.

The recorder saves one session per directory under
`data/fresh_video/<condition>/<service>/` (gitignored). The default condition is `natural`;
use `--condition ipv4_tcp` for controlled captures. The original pilot predates these
condition folders and remains at its original path.
It records traffic for up to 120 seconds by default, stopping earlier at 250 MB, and saves
`traffic.pcapng` plus `session.json`. Wireshark supplies `dumpcap` and `tshark`; no new Python
dependency is needed. Captures stay local and may include unrelated device traffic.

## Record a session

Choose the interface shown by `dumpcap -D` and verify its current route. On this Mac the
Wi-Fi interface was `en0` during setup; a VPN or another connection may change that.

```bash
.venv/bin/netleak capture --label youtube --interface en0 --seconds 120 \
  --content-url 'https://www.youtube.com/watch?v=VIDEO_ID' \
  --notes 'device, browser/version, network, content, login state, warm/cold browser'
```

Wait for the recorder's `File:` message before navigating to the video. Start capture
before navigation so connection setup is included. Browser automation in Codex can open
the video, click play, and check that the displayed playback time advances. The command
itself only records; it does not automate the browser or assume playback succeeded.
An ordinary private/incognito window can still reuse connections inside that window;
define and record a consistent browser-reset procedure before a full experiment.

Close or pause unrelated network activity when practical. Do not disable QUIC or IPv6
for the natural-traffic pilot. Inspect protocol coverage first. If a controlled TCP-only
experiment is later needed, give it a separate condition and record the settings.

## What the pilot proves

The summary counts all observed packets, IPv4/IPv6, TCP/UDP, packets dissected as QUIC,
IPv4 SYN/SYN-ACK packets, truncation and observed capture duration. These counts overlap
and are **not service-specific**. Zero dissected QUIC packets does not prove QUIC is absent.
The interface capture can contain background applications, other tabs and control traffic.
The service name records the intended activity, not a verified label for every packet.

Keep `benchmark_ready: false` until service attribution and sample construction are
reviewed. Verify actual content playback at two advancing timestamps, record ads/errors,
and retain failed sessions with their reason. Warm connections and browser cache can
remove connection-start packets; finding ten SYN packets anywhere in a capture does not
make a valid benchmark sample.

Before a full study, establish service attribution and consistent session boundaries,
match the historical first-ten IPv4 SYN/SYN-ACK sampling rule, and track sessions that
cannot supply that representation. Do not silently discard QUIC/IPv6-only sessions.
Rotate services across devices and days. Keep complete sessions together in evaluation.
Freeze training feature columns and preprocessing before scoring fresh samples; separately
built caches currently choose their own varying columns and cannot be compared directly.

This recorder does not add a new benchmark dataset, alter rungs or models, or regenerate
historical results. One pilot demonstrates collection feasibility, not temporal drift.

## Packet-selection audit and compact collection: planning notes

The September 21 YouTube audit found that restricting connections to visible YouTube TLS
hostnames changes the first ten packets and can change a fixed model's prediction. The
public historical collector starts an interface capture before playback without that
hostname restriction. Its downstream release boundary remains partly uncertain.

For the next batch, isolate a dedicated playback browser from unrelated activity and
record from before session start. Keep the first ten IPv4/TCP packets with the SYN bit
set, including SYN-ACKs, ECN flags and repeated attempts. Include page, player, media,
support and ad connections attributable to the session. Treat TLS names as annotations,
not a requirement for admission; failed or unnamed connections must not silently vanish.
Socket polling can miss brief connections and shared Chrome processes can serve several
tabs, so process ownership alone is not proof of session ownership. Keep uncertain
ownership explicit until isolation or independent evidence resolves it.

Use a fixed 60-second observation window for the next compact pilot and report it as a
shorter window than historical multi-minute recordings. Retain short sessions using the
existing encoder padding, and log zero-eligible-packet and failed-playback sessions as
coverage outcomes. Do not force reconnections, discard slow/short sessions, or rewrite
headers to obtain a historical-looking sample. Fix the protocol independently of model
predictions. A complete-only view may be reported as a separate sensitivity analysis.

The compact recorder can retain SYN packets plus initial client TLS evidence without
saving bulk video. Two independent live checks retained all 132 SYN packets in their
comparison windows. A replay of a full capture retained all 152 SYNs and all 67 visible
TLS-name flows in about 138 KB instead of 229 MB. These checks cover the tested traffic;
they do not guarantee TLS attribution for every future connection.

The local audit is at `data/fresh_video/filter_audit/README.md`, with the exact selections,
playback evidence, header comparisons and historical-model sensitivity results. The
earlier exports under `data/fresh_video/ipv4_tcp_syn10/` are hostname-filtered diagnostics,
not an established primary dataset for measuring temporal drift. The next primary batch
still requires an isolated session boundary; broad Google-domain or whole-interface
selections on an active desktop are only sensitivity checks.

## Controlled IPv4/TCP capture

1. Record the original browser and network settings. In Chrome, manually set
   `chrome://flags/#enable-quic` (Experimental QUIC protocol) to Disabled and relaunch
   after saving work. Browser automation may be prohibited from accessing this page.
2. On macOS, open System Settings → Wi-Fi → Details → TCP/IP. Set Configure IPv6 to
   Link-Local Only and apply it. This restricts internet traffic on this connection to
   IPv4; local IPv6 discovery traffic can remain. A system authentication prompt may
   need approval. Check that no alternate VPN/interface supplies an IPv6 internet route.
3. Start the recorder with `--condition ipv4_tcp`, then open and play the selected video.
   Record whether browser connections were fresh or reused. Verify playback by reading
   the video element's advancing `currentTime`; hidden player controls can show stale time.
4. Inspect the captured packets, not just the settings: check service/CDN connections for
   IPv4, TCP, SYN/SYN-ACK packets, and TLS. Check the full capture for QUIC and globally
   routed IPv6. Keep background and local discovery traffic distinct from service evidence.
5. Restore the original macOS IPv6 setting after collection and verify it. Restore Chrome's
   QUIC flag to its original value and relaunch when finished with the controlled condition.

An IPv4/TCP display or capture filter alone does **not** force the browser to use those
protocols. Do not use filtering as evidence that the controlled condition was achieved.
