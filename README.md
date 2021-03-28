# Galène RTMP gateway

Gateway to send RTMP streams to
[Galène videoconference server](https://galene.org/).
It is based on Gstreamer RTMP and WebRTC support and implements the Galène
protocol.

## User guide

Real-time video conversion requires resources. If many users are going to use
this gateway simultaneously, you should scale your machine resources
accordingly.

### Installation using Python Virtualenv

Start by cloning the source code,

```bash
git clone https://github.com/erdnaxe/galene-rtmp
cd galene-rtmp
```

Then create a Python virtualenv and install galene-rtmp inside,

```bash
python -m venv venv --system-site-packages
source venv/bin/activate
pip install -e .
```

You need a NGINX RTMP server, you may remix the provided
[nginx.conf](./docs/nginx.conf).

```
nginx -c nginx.conf -p $PWD
```

You may now launch the gateway using:

```
python -m galene_rtmp --server "wss://galene.example.com/ws" --group test --username bot
```

## Contributing

See [contributing guidelines](./CONTRIBUTING.md).

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
