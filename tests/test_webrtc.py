# Copyright (C) 2021 Alexandre Iooss
# SPDX-License-Identifier: MIT

"""
Test module for galene_stream.webrtc.
"""

import asyncio

from galene_stream.webrtc import WebRTCClient


def test_init_webrtc():
    """Test WebRTC initialization."""
    event_loop = asyncio.get_event_loop()
    client = WebRTCClient("rtmp://localhost:1935/live/test", 1048576, None, None)
    client.start_pipeline(event_loop, [])
    client.close_pipeline()
