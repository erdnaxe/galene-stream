# Copyright (C) 2021 A. Iooss
# SPDX-License-Identifier: MIT

"""
Main command-line script for Galène stream gateway.
"""

import argparse
import asyncio
import logging
import sys

from galene_stream.galene import GaleneClient


def start(opt: argparse.Namespace):
    """Init Galène client and start gateway

    :param opt: program options
    :type opt: argparse.Namespace
    """
    client = GaleneClient(
        opt.input,
        opt.output,
        opt.bitrate,
        opt.username,
        opt.password,
        opt.insecure,
    )

    # Connect and run main even loop
    event_loop = asyncio.get_event_loop()
    event_loop.run_until_complete(client.connect())
    try:
        event_loop.run_until_complete(client.loop(event_loop))
        event_loop.run_until_complete(client.close())
    except KeyboardInterrupt:
        event_loop.run_until_complete(client.close())
        sys.exit(1)


def main():
    """Entrypoint."""
    # Arguments parser
    parser = argparse.ArgumentParser(
        prog="galene-stream",
        description="Galène stream gateway.",
    )
    parser.add_argument(
        "--debug",
        action="store_true",
        default=False,
        help="debug mode: show debug messages",
    )
    parser.add_argument(
        "-i",
        "--input",
        required=True,
        help=(
            'URI to use as GStreamer "uridecodebin" module input, '
            'e.g. "rtmp://localhost:1935/live/test"'
        ),
    )
    parser.add_argument(
        "-o",
        "--output",
        required=True,
        help="Group URL, of the form https://galene.example.org/group/public/",
    )
    parser.add_argument(
        "-b",
        "--bitrate",
        default=1048576,
        help="VP8 encoder bitrate in bit/s, you should adapt this to your network, default to 1048576",
    )
    parser.add_argument(
        "-u",
        "--username",
        required=True,
        help="Group username",
    )
    parser.add_argument(
        "-p",
        "--password",
        help="Group password",
    )
    parser.add_argument(
        "--insecure",
        action="store_true",
        help="Don't check server certificate",
    )
    options = parser.parse_args()

    # Configure logging
    level = logging.DEBUG if options.debug else logging.INFO
    logging.addLevelName(logging.INFO, "\033[1;36mINFO\033[1;0m")
    logging.addLevelName(logging.WARNING, "\033[1;33mWARNING\033[1;0m")
    logging.addLevelName(logging.ERROR, "\033[1;91mERROR\033[1;0m")
    logging.addLevelName(logging.DEBUG, "\033[1;30mDEBUG")
    logging.basicConfig(
        level=level,
        format="\033[90m%(asctime)s\033[1;0m [%(name)s] %(levelname)s %(message)s\033[1;0m",
    )

    # Breaking change in Galene-stream 0.1.7: output is no longer a WebSocket URI
    if options.output.startswith("ws"):
        raise ValueError(
            "Output must be a group URL of the form https://galene.example.org/group/public/"
        )

    start(options)
