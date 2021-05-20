# Copyright (C) 2021 Alexandre Iooss
# SPDX-License-Identifier: MIT

"""
Web server with WebRTC peer.
"""

import asyncio
import json
import logging

import websockets

from galene_stream.webrtc import WebRTCClient

log = logging.getLogger(__name__)


class StandaloneServer:
    """WebSocket server for WebRTC signalling."""

    def __init__(
        self,
        input_uri: str,
        bitrate: int,
        ice_servers=[],
    ):
        """Create WebServer

        :param input_uri: URI for GStreamer uridecodebin
        :type input_uri: str
        :param bitrate: VP8 encoder bitrate in bit/s
        :type bitrate: int
        :param ice_servers: TURN/STUN servers to use, default to those announced
            by the server
        :type ice_servers: [str]
        """
        super().__init__()

        self.conn = None
        self.ice_servers = None
        self.webrtc = WebRTCClient(input_uri, bitrate)

    async def websocket_handler(websocket, _):
        """WebSocket handler

        :param websocket: current WebSocket opened with client
        :type websocket: WebSocketServerProtocol
        """
        async for message in websocket:
            # Wait for new message and decode as JSON
            message = json.loads(message)

            if message["type"] == "offer":
                # Peer is sending a SDP offer
                sdp = message.get("sdp")
                log.debug(f"Receiving SDP from peer: {sdp}")
                self.webrtc.set_remote_sdp(sdp)
            elif message["type"] == "ice":
                # Server is sending trickle ICE candidates
                log.debug("Receiving new ICE candidate from peer")
                mline_index = message.get("candidate").get("sdpMLineIndex")
                candidate = message.get("candidate").get("candidate")
                self.webrtc.add_ice_candidate(mline_index, candidate)
            elif message["type"] == "stats":
                # User request statistics
                m = self.webrtc.get_stats()
                if m:
                    message = json.dumps({"type": "stats", "value": m})
                    await websocket.send(message)
            else:
                # Oh no! We receive something not implemented
                log.warn(f"Not implemented {message}")

    def run(self):
        """Init WebSocket server and start event loop."""
        event_loop = asyncio.get_event_loop()

        # Start GStreamer pipeline
        self.webrtc.start_pipeline(event_loop, self.ice_servers)

        # Run main event loop
        start_server = websockets.serve(self.websocket_handler, "localhost", 8081)
        try:
            event_loop.run_until_complete(start_server)
            event_loop.run_forever()
        except KeyboardInterrupt:
            # Properly close GStreamer
            self.webrtc.close_pipeline()
