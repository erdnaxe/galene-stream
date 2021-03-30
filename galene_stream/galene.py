# Copyright (C) 2021 Alexandre Iooss
# SPDX-License-Identifier: MIT

"""
Galène protocol support.
"""

import json
import logging
import secrets
import ssl

import websockets

from galene_stream.webrtc import WebRTCClient

log = logging.getLogger(__name__)


class GaleneClient(WebRTCClient):
    """Galène protocol implementation."""

    def __init__(
        self, group: str, server: str, username: str, password=None, identifier=None
    ):
        """Create GaleneClient

        :param group: group to join
        :type group: str
        :param server: websocket url to connect to
        :type server: str
        :param username: group user name
        :type username: str
        :param password: group user password if required
        :type password: str, optional
        :param identifier: client id, defaults to random
        :type identifier: str, optional
        """
        super().__init__()
        if identifier is None:
            # Create random client id
            identifier = secrets.token_bytes(16).hex()

        self.group = group
        self.server = server
        self.username = username
        self.password = password
        self.client_id = identifier
        self.conn = None
        self.ice_servers = None

    async def send(self, message: dict):
        """Send message to remote.

        :param message: message to send
        :type message: dict
        """
        message = json.dumps(message)
        await self.conn.send(message)

    async def send_sdp_offer(self, sdp):
        """Send SDP offer to remote.

        :param sdp: session description
        :type sdp: str
        """
        log.info("Sending local SDP offer to remote")
        # We use client_id as stream id, but it can differ
        msg = {
            "type": "offer",
            "id": self.client_id,  # stream id
            "source": self.client_id,
            "username": self.username,
            "sdp": sdp,
            "labels": {
                "video0": "video",
                "audio1": "audio",
            },
        }
        await self.send(msg)

    async def send_ice_candidate(self, candidate: dict):
        """Send ICE candidate to remote.

        :param canditate: ICE candidate
        :type canditate: dict
        """
        log.debug("Sending new ICE candidate to remote")
        msg = {"type": "ice", "id": self.client_id, "candidate": candidate}
        await self.send(msg)

    async def connect(self):
        """Connect to server."""
        # Create WebSocket
        log.info("Connecting to WebSocket")
        ssl_ctx = ssl.create_default_context(purpose=ssl.Purpose.CLIENT_AUTH)
        self.conn = await websockets.connect(self.server, ssl=ssl_ctx)

        # Handshake with server
        log.info("Handshaking")
        msg = {
            "type": "handshake",
            "id": self.client_id,
        }
        await self.send(msg)
        await self.conn.recv()  # wait for handshake

        # Join group
        log.info("Joining group")
        msg = {
            "type": "join",
            "kind": "join",
            "group": self.group,
            "username": self.username,
            "password": self.password,
        }
        await self.send(msg)
        response = None
        while response is None or response["type"] != "joined":
            # The server will send 'user' messages that we ignore
            response = await self.conn.recv()
            response = json.loads(response)
        if response["kind"] != "join":
            raise RuntimeError("failed to join room")
        self.ice_servers = response.get("rtcConfiguration").get("iceServers")

    async def loop(self, event_loop, input_uri: str) -> int:
        """Client loop

        :param event_loop: asyncio event loop
        :type event_loop: EventLoop
        :param input_uri: URI for GStreamer uridecodebin
        :type input_uri: str
        :raises RuntimeError: if client is not connected
        :return: exit code
        :rtype: int
        """
        if self.conn is None:
            raise RuntimeError("client not connected")
        self.start_pipeline(event_loop, self.ice_servers, input_uri)

        async for message in self.conn:
            message = json.loads(message)
            if message["type"] == "ping":
                # Need to answer pong to ping request to keep connection
                await self.send({"type": "pong"})
            elif message["type"] == "abort":
                # Server wants to close our stream
                log.info("Received abort from server")
                await self.send({"type": "close", "id": message.get("id")})
                break
            elif message["type"] == "answer":
                # Server is sending a SDP offer
                sdp = message.get("sdp")
                self.set_remote_sdp(sdp)
            elif message["type"] == "ice":
                # Server is sending trickle ICE candidates
                log.debug("Receiving new ICE candidate from remote")
                mline_index = message.get("candidate").get("sdpMLineIndex")
                candidate = message.get("candidate").get("candidate")
                self.add_ice_candidate(mline_index, candidate)
            elif message["type"] == "renegotiate":
                # Server is asking to renegotiate WebRTC session
                self.on_negotiation_needed(self.webrtc)
            elif message["type"] == "usermessage":
                value = message.get("value")
                if message["kind"] == "error":
                    raise RuntimeError(f"Server returned error: {value}")
                else:
                    log.warn(f"Server sent: {value}")
            elif message["type"] == "user":
                continue  # ignore user events
            elif message["type"] == "close":
                continue  # ignore close events
            elif message["type"] == "chat":
                continue  # ignore chat events
            else:
                # Oh no! We receive something not implemented
                log.warn(f"Not implemented {message}")

        self.close_pipeline()
