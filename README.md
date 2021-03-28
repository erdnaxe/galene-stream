# Galène RTMP gateway

Gateway to send RTMP streams to
[Galène videoconference server](https://galene.org/).

## User guide

The user guide is WIP.

```bash
git clone https://github.com/erdnaxe/galene-rtmp
cd galene-rtmp

python -m venv venv --system-site-packages
source venv/bin/activate
pip install -e .
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
