# Copyright (C) 2021 Alexandre Iooss
# SPDX-License-Identifier: MIT

"""
WebRTC support using Gstreamer.
"""

import asyncio
import json
import logging

import gi

# Specify version, then import gstreamer plugins
gi.require_version("Gst", "1.0")
gi.require_version("GstWebRTC", "1.0")
gi.require_version("GstSdp", "1.0")

# Load Gst and check plugins
from gi.repository import Gst, GstSdp, GstWebRTC

Gst.init(None)
needed = [
    "opus",
    "vpx",
    "nice",
    "webrtc",
    "dtls",
    "srtp",
    "rtp",
    "rtpmanager",
]
missing = list(filter(lambda p: Gst.Registry.get().find_plugin(p) is None, needed))
if len(missing):
    raise RuntimeError(f"Missing gstreamer plugins: {missing}")


log = logging.getLogger(__name__)

PIPELINE_DESC = """
webrtcbin name=send bundle-policy=max-bundle
 uridecodebin uri={input_uri} name=bin ! videoconvert ! queue ! vp8enc deadline=10 ! rtpvp8pay !
 queue ! application/x-rtp,media=video,encoding-name=VP8,payload=97 ! send.
 bin. ! audioconvert ! audioresample ! queue ! opusenc ! rtpopuspay !
 queue ! application/x-rtp,media=audio,encoding-name=OPUS,payload=96 ! send.
"""


class WebRTCClient:
    """WebRTCClient

    Based on <https://gitlab.freedesktop.org/gstreamer/gst-examples/>.
    """

    def __init__(self):
        """Init WebRTCClient."""
        self.event_loop = None
        self.pipe = None
        self.webrtc = None
        self.input_uri = ""

    def on_offer_created(self, promise, _, __):
        """``on-offer-created`` event handler.

        :param promise: promise running this event
        :type promise: Gst.Promise
        """
        # Get offer from the promise calling the event
        promise.wait()
        reply = promise.get_reply()
        offer = reply["offer"]

        # Set local description
        log.info("Setting local description")
        promise = Gst.Promise.new()
        self.webrtc.emit("set-local-description", offer, promise)
        promise.interrupt()

        # Send local SDP offer to remote
        offer = offer.sdp.as_text()
        future = asyncio.run_coroutine_threadsafe(
            self.send_sdp_offer(offer), self.event_loop
        )
        future.result()  # wait

    def on_negotiation_needed(self, element):
        """``on-negotiation-needed`` event handler.

        When receiving ``on-negotiation-needed`` event, create new offer.

        :param element: the webrtcbin
        :type element: object
        """
        # Set up ``on-offer-created`` event when offer is ready
        promise = Gst.Promise.new_with_change_func(self.on_offer_created, element, None)

        # Create new offer
        element.emit("create-offer", None, promise)

    def on_ice_candidate(self, _, mline_index, candidate: str):
        """``on-ice-candidate`` event handler.

        Send ICE candidate message to remote.

        :param mline_index: the index of the media description in the SDP
        :type mline_index: str
        :param candidate: an ICE candidate
        :type candidate: str
        """
        candidate = {"candidate": candidate, "sdpMLineIndex": mline_index}
        future = asyncio.run_coroutine_threadsafe(
            self.send_ice_candidate(candidate), self.event_loop
        )
        future.result()  # wait

    def set_remote_sdp(self, sdp: str):
        """Set remote session description.

        :param sdp: Session description
        :type sdp: str
        """
        log.info("Setting remote session description")
        _, sdp_msg = GstSdp.SDPMessage.new()
        GstSdp.sdp_message_parse_buffer(bytes(sdp.encode()), sdp_msg)
        answer = GstWebRTC.WebRTCSessionDescription.new(
            GstWebRTC.WebRTCSDPType.ANSWER, sdp_msg
        )
        promise = Gst.Promise.new()
        self.webrtc.emit("set-remote-description", answer, promise)
        promise.interrupt()

    def add_ice_candidate(self, mline_index: int, candidate: str):
        """Add new ICE candidate.

        :param mline_index: the index of the media description in the SDP
        :type mline_index: int
        :param candidate: an ice candidate
        :type candidate: str
        """
        self.webrtc.emit("add-ice-candidate", mline_index, candidate)

    def start_pipeline(self, event_loop, ice_servers, input_uri):
        """Start gstreamer pipeline and connect WebRTC events.

        :param event_loop: asyncio event loop
        :type event_loop: EventLoop
        :param ice_servers: list of ICE TURN servers
        :type ice_servers: list of dicts
        :param input_uri: URI for GStreamer uridecodebin
        :type input_uri: str
        """
        log.info("Starting pipeline")
        self.event_loop = event_loop
        self.input_uri = input_uri
        self.pipe = Gst.parse_launch(PIPELINE_DESC.format(input_uri=input_uri))
        self.webrtc = self.pipe.get_by_name("send")
        self.webrtc.connect("on-negotiation-needed", self.on_negotiation_needed)
        self.webrtc.connect("on-ice-candidate", self.on_ice_candidate)
        self.pipe.set_state(Gst.State.PLAYING)

        # Add TURN servers
        try:
            for server in ice_servers:
                username = server.get("username", "")
                credential = server.get("credential", "")
                for url in server.get("urls", []):
                    url = url.replace("turn:", "")  # remove prefix
                    uri = f"turn://{username}:{credential}@{url}"
                    self.webrtc.emit("add-turn-server", uri)
        except TypeError:
            log.warn(
                "add-turn-server signal is missing, maybe your gstreamer "
                "is too old. Skipping TURN servers configuration"
            )

    def close_pipeline(self):
        """Stop gstreamer pipeline."""
        log.info("Closing pipeline")
        self.pipe.set_state(Gst.State.NULL)
        self.pipe = None
        self.webrtc = None
