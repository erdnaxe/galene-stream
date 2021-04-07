# Copyright (C) 2021 Alexandre Iooss
# SPDX-License-Identifier: MIT

"""
WebRTC support using Gstreamer.
"""

import asyncio
import json
import logging
import os
import sys

import gi

# Specify version, then import gstreamer plugins
gi.require_version("Gst", "1.0")
gi.require_version("GstWebRTC", "1.0")
gi.require_version("GstSdp", "1.0")

from gi.repository import Gst, GstSdp, GstWebRTC

log = logging.getLogger(__name__)


class WebRTCClient:
    """WebRTCClient

    Based on <https://gitlab.freedesktop.org/gstreamer/gst-examples/>.
    """

    def __init__(self, input_uri: str, sdp_offer_callback, ice_candidate_callback, stats_callback):
        """Init WebRTCClient.

        :param input_uri: URI for GStreamer uridecodebin
        :type input_uri: str
        :param sdp_offer_callback: coroutine to send SDP offer
        :type sdp_offer_callback: coroutine
        :param ice_candidate_callback: coroutine to send ICE candidate
        :type ice_candidate_callback: coroutine
        :param stats_callback: coroutine to send statistics as chat message
        :type stats_callback: coroutine
        """
        self.event_loop = None
        self.pipe = None
        self.webrtc = None
        self.sdp_offer_callback = sdp_offer_callback
        self.ice_candidate_callback = ice_candidate_callback
        self.stats_callback = stats_callback

        # webrtcbin latency parameter was added in gstreamer 1.18
        self.pipeline_desc = (
            "webrtcbin name=send bundle-policy=max-bundle latency=500 "
            f"uridecodebin uri={input_uri} name=bin "
            "bin. ! vp8enc deadline=1 keyframe-max-dist=5 target-bitrate=5000000 ! rtpvp8pay pt=97 ! send. "
            "bin. ! audioconvert ! audioresample ! opusenc ! rtpopuspay pt=96 ! send."
        )

        # If gstreamer debug level is undefined, show warnings and errors
        if "GST_DEBUG" not in os.environ:
            os.environ["GST_DEBUG"] = "2"

        # Initialize GStreamer and check available plugins
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
            "x264",
        ]
        missing = filter(lambda p: Gst.Registry.get().find_plugin(p) is None, needed)
        missing = list(missing)
        if len(missing):
            log.error(f"Missing gstreamer plugins: {missing}")
            sys.exit(1)

    def on_offer_created(self, promise, _, __):
        """``on-offer-created`` event handler.

        :param promise: promise running this event
        :type promise: Gst.Promise
        """
        # Get offer from the promise calling the event
        promise.wait()
        reply = promise.get_reply()
        offer = reply.get_value("offer")

        # Set local description
        log.info("Setting local description")
        promise = Gst.Promise.new()
        self.webrtc.emit("set-local-description", offer, promise)
        promise.interrupt()

        # Send local SDP offer to remote
        offer = offer.sdp.as_text()
        future = asyncio.run_coroutine_threadsafe(
            self.sdp_offer_callback(offer), self.event_loop
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
            self.ice_candidate_callback(candidate), self.event_loop
        )
        future.result()  # wait

    def _send_stat(self, _, value):
        """Filter, format then send each statistics."""
        name = value.get_name()
        if name == "remote-outbound-rtp":
            message = value.get_value("round-trip-time")
            asyncio.run_coroutine_threadsafe(
                self.stats_callback(f"round-trip-time: {message}"), self.event_loop
            ).result()
        elif name == "outbound-rtp":
            message = {
                "fir-count": value.get_value("fir-count"),
                "pli-count": value.get_value("pli-count"),
                "nack-count": value.get_value("nack-count"),
                "bytes-sent": value.get_value("bytes-sent"),
                "packets-sent": value.get_value("packets-sent"),
            }
            asyncio.run_coroutine_threadsafe(
                self.stats_callback(f"outbound-rtp: {message}"), self.event_loop
            ).result()
        elif name == "remote-inbound-rtp":
            message = {
                "packets-received": value.get_value("packets-received"),
                "packets-lost": value.get_value("packets-lost"),
                "jitter": value.get_value("jitter"),
            }
            asyncio.run_coroutine_threadsafe(
                self.stats_callback(f"remote-inbound-rtp: {message}"), self.event_loop
            ).result()

        return True  # continue foreach

    def on_get_stats(self, promise):
        """``on-get-stats`` event handler.

        :param promise: promise running this event
        :type promise: Gst.Promise
        """
        # Get stats from the promise calling the event
        promise.wait()
        reply = promise.get_reply()

        # Format statistics
        reply.foreach(self._send_stat)

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

    def get_stats(self):
        """Get WebRTC statistics from GStreamer."""
        promise = Gst.Promise.new_with_change_func(self.on_get_stats)
        self.webrtc.emit("get-stats", None, promise)

    def start_pipeline(self, event_loop, ice_servers):
        """Start gstreamer pipeline and connect WebRTC events.

        :param event_loop: asyncio event loop
        :type event_loop: EventLoop
        :param ice_servers: list of ICE TURN servers
        :type ice_servers: list of dicts
        """
        log.info("Starting pipeline")
        self.event_loop = event_loop
        self.pipe = Gst.parse_launch(self.pipeline_desc)
        self.webrtc = self.pipe.get_by_name("send")
        self.webrtc.connect("on-negotiation-needed", self.on_negotiation_needed)
        self.webrtc.connect("on-ice-candidate", self.on_ice_candidate)

        # Enable WebRTC negative acknowledgement and FEC
        transceiver_count = self.webrtc.emit("get-transceivers").len
        for i in range(transceiver_count):
            transceiver = self.webrtc.emit("get-transceiver", i)
            transceiver.set_property("do-nack", True)
            transceiver.set_property("fec-type", GstWebRTC.WebRTCFECType.ULP_RED)

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

        # Start
        self.pipe.set_state(Gst.State.PLAYING)

    def close_pipeline(self):
        """Stop gstreamer pipeline."""
        log.info("Closing pipeline")
        self.pipe.set_state(Gst.State.NULL)
        self.pipe = None
        self.webrtc = None
