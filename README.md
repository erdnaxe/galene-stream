# Galène streaming gateway

Gateway to send streams such as RTMP or SRT to
[Galène videoconference server](https://galene.org/).
It is based on Gstreamer and implements the Galène protocol.

## User guide

Real-time video conversion requires resources. If many users are going to use
this gateway simultaneously, you should scale your machine resources
accordingly.

### Installation on Debian/Ubuntu

```bash
sudo apt install python3-pip python3-gi python3-gi-cairo python3-websockets gir1.2-gst-plugins-bad-1.0 gstreamer1.0-plugins-good gstreamer1.0-plugins-bad gstreamer1.0-nice
pip3 install --user galene-stream
```

### Installation on ArchLinux

```bash
sudo pacman -S python-setuptools python-pip python-websockets python-gobject gobject-introspection gst-python gst-plugins-base gst-plugins-bad
pip install --user galene-stream
```

### Installation from source code using Python Virtualenv

Start by cloning the source code,

```bash
git clone https://github.com/erdnaxe/galene-stream
cd galene-stream
```

Then create a Python VirtualEnv and install galene-stream inside,

```bash
python -m venv venv --system-site-packages
source venv/bin/activate
pip install -e .
```

### Configuration for RTMP streaming

```
+--------------------+      +----------+      +-------------+        +------+
|Streaming software  | RTMP |NGINX RTMP| RTMP |Galène Stream| WebRTC |Galène|
|(such as OBS-Studio)+------>  Server  <------+   Gateway   +-------->      |
+--------------------+      +----------+      +-------------+        +------+
```

You need a NGINX RTMP server, you may remix the provided
[nginx.conf](./docs/nginx.conf). You can launch NGINX as user using:

```
nginx -c nginx.conf -p $PWD
```

You may launch the gateway after the NGINX server using:

```
galene-stream --output "wss://galene.example.com/ws" --group test --username bot
```

Then you can stream to `rtmp://127.0.0.1:1935/live` with stream key `test`.

### Configuration for SRT streaming

SRT support is still experimental in some Linux distributions.
It has been reported to work on ArchLinux (on 2021/03/30).

Launch the gateway using:

```
galene-stream --input "srt://localhost:9710?mode=listener" --output "wss://galene.example.com/ws" --group test --username bot
```

Then you can stream to `srt://localhost:9710` with no stream key.

### Configuration for file streaming

For debugging purposes you can directly stream a file,

```
galene-stream --input "file://source.webm" --output "wss://galene.example.com/ws" --group test --username bot
```

## Contributing

See [contributing guidelines](./CONTRIBUTING.md).

### Debugging GStreamer pipeline

You may use these environment variables,

```
GST_DEBUG="GST_TRACER:7" GST_TRACERS="latency;stats;rusage" GST_DEBUG_FILE=trace.log
```

Then you may inspect logs using `gst-stats-1.0 trace.log`.

## Authors

This gateway is currently developed by members from
[Crans](https://www.crans.org/)
and [Aurore](https://auro.re/) network organizations to build a self-hosted
free and open-source streaming server.

Main contributors:

-   Alexandre Iooss

## License

We believe in open source software.
This project is licensed under [MIT](./LICENSE.txt).
