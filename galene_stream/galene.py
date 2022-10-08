# Copyright (C) 2021 Alexandre Iooss
# SPDX-License-Identifier: MIT

"""
Galène protocol support.
"""

import json
import logging
import secrets
from typing import List

import websockets

from galene_stream.webrtc import WebRTCClient

log = logging.getLogger(__name__)


class GaleneClient:
    """Galène protocol implementation."""

    def __init__(
        self,
        input_uri: str,
        server: str,
        bitrate: int,
        group: str,
        username: str,
        password: str = "",
    ) -> None:
        """Create GaleneClient

        :param input_uri: URI for GStreamer uridecodebin
        :type input_uri: str
        :param server: websocket url to connect to
        :type server: str
        :param bitrate: VP8 encoder bitrate in bit/s
        :type bitrate: int
        :param group: group to join
        :type group: str
        :param username: group user name
        :type username: str
        :param password: group user password if required
        :type password: str, optional
        """
        self.server = server
        self.group = group
        self.username = username
        self.password = password

        self.conn = None
        self.ice_servers: List[str] = []
        self.client_id = secrets.token_bytes(16).hex()
        self.webrtc = WebRTCClient(
            input_uri, bitrate, self.send_sdp_offer, self.send_ice_candidate
        )

    async def send(self, message: dict) -> None:
        """Send message to remote.

        :param message: message to send
        :type message: dict
        """
        msg = json.dumps(message)
        if self.conn is None:
            log.error("Connection is closed, cannot send message")
            return
        await self.conn.send(msg)

    async def send_sdp_offer(self, sdp: str) -> None:
        """Send SDP offer to remote.

        :param sdp: session description
        :type sdp: str
        """
        log.debug(f"Sending local SDP offer to remote: {sdp}")
        # We use client_id as stream id, but it can differ
        msg = {
            "type": "offer",
            "id": self.client_id,  # stream id
            "source": self.client_id,
            "username": self.username,
            "sdp": sdp,
            "label": "video",
        }
        await self.send(msg)

    async def send_ice_candidate(self, candidate: dict) -> None:
        """Send ICE candidate to remote.

        :param canditate: ICE candidate
        :type canditate: dict
        """
        log.debug("Sending new ICE candidate to remote")
        msg = {"type": "ice", "id": self.client_id, "candidate": candidate}
        await self.send(msg)

    async def send_chat(self, message: str) -> None:
        """Send chat message.

        :param message: content of the message
        :type message: str
        """
        await self.send(
            {
                "type": "chat",
                "source": self.client_id,
                "username": self.username,
                "noecho": True,
                "value": message,
            }
        )

    async def connect(self) -> None:
        """Connect to server."""
        # Create WebSocket
        log.info("Connecting to WebSocket")
        self.conn = await websockets.connect(self.server, ssl=True)

        # Handshake with server
        log.info("Handshaking")
        msg = {
            "type": "handshake",
            "version": ["1"],  # since Galene 0.6.0
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
        response = {"type": "none"}
        while response["type"] != "joined":
            # The server will send 'user' messages that we ignore
            raw_response = await self.conn.recv()
            response = json.loads(raw_response)
        if response["kind"] != "join":
            raise RuntimeError("failed to join room")

        # Get ICE servers
        rtc_configuration = response.get("rtcConfiguration", {})
        assert isinstance(rtc_configuration, dict)
        self.ice_servers = []
        for server in rtc_configuration.get("iceServers", []):
            username = server.get("username", "")
            credential = server.get("credential", "")
            for url in server.get("urls", []):
                url = url.replace("turn:", "")  # remove prefix
                uri = f"turn://{username}:{credential}@{url}"
                self.ice_servers.append(uri)

    async def close(self) -> None:
        """Close connection."""
        log.info("Closing WebSocket connection")
        self.webrtc.close_pipeline()
        if self.conn is None:
            log.warn("Connection is already closed")
            return
        await self.conn.close()
        self.conn = None

    async def loop(self, event_loop) -> None:
        """Client loop

        :param event_loop: asyncio event loop
        :type event_loop: EventLoop
        :raises RuntimeError: if client is not connected
        """
        if self.conn is None:
            raise RuntimeError("client not connected")
        self.webrtc.start_pipeline(event_loop, self.ice_servers)
        log.info("Waiting for incoming stream...")

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
                log.debug(f"Receiving SDP from remote: {sdp}")
                self.webrtc.set_remote_sdp(sdp)
            elif message["type"] == "ice":
                # Server is sending trickle ICE candidates
                log.debug("Receiving new ICE candidate from remote")
                mline_index = message.get("candidate").get("sdpMLineIndex")
                candidate = message.get("candidate").get("candidate")
                self.webrtc.add_ice_candidate(mline_index, candidate)
            elif message["type"] == "renegotiate":
                # Server is asking to renegotiate WebRTC session
                self.webrtc.on_negotiation_needed(self.webrtc.webrtc)
            elif message["type"] == "usermessage":
                value = message.get("value")
                if message["kind"] == "error":
                    log.error(f"Server returned error: {value}")
                    break
                else:
                    log.warn(f"Server sent: {value}")
            elif message["type"] == "user":
                continue  # ignore user events
            elif message["type"] == "close":
                continue  # ignore close events
            elif message["type"] == "chat":
                # User might request statistics using `!webrtc` chat command
                if message.get("value") == "!webrtc":
                    m = self.webrtc.get_stats()
                    if m:
                        await self.send_chat(m)
            elif message["type"] == "chathistory":
                continue  # ignore chat history events
            else:
                # Oh no! We receive something not implemented
                log.warn(f"Not implemented {message}")
