# Copyright (C) 2021 Alexandre Iooss
# SPDX-License-Identifier: MIT

"""
WebRTC support using Gstreamer.
"""

import asyncio
import logging
import os
import pprint
import sys
from typing import List

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

    def __init__(
        self, input_uri: str, bitrate: int, sdp_offer_callback, ice_candidate_callback
    ) -> None:
        """Init WebRTCClient.

        :param input_uri: URI for GStreamer uridecodebin
        :type input_uri: str
        :param bitrate: VP8 encoder bitrate in bit/s
        :type bitrate: int
        :param sdp_offer_callback: coroutine to send SDP offer
        :type sdp_offer_callback: coroutine
        :param ice_candidate_callback: coroutine to send ICE candidate
        :type ice_candidate_callback: coroutine
        """
        self.event_loop = None
        self.pipe = None
        self.webrtc = None
        self.sdp_offer_callback = sdp_offer_callback
        self.ice_candidate_callback = ice_candidate_callback

        self.pipeline_desc = (
            "webrtcbin name=send bundle-policy=max-bundle "
            f'uridecodebin uri="{input_uri}" name=bin '
            f"bin. ! videoconvert ! vp8enc deadline=1 target-bitrate={bitrate} ! rtpvp8pay pt=97 ! send. "
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
        missing_list = list(missing)
        if len(missing_list):
            log.error(f"Missing gstreamer plugins: {missing_list}")
            sys.exit(1)

    def on_offer_created(self, promise, _, __) -> None:
        """``on-offer-created`` event handler.

        :param promise: promise running this event
        :type promise: Gst.Promise
        """
        assert self.event_loop is not None
        assert self.webrtc is not None

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

    def on_negotiation_needed(self, element) -> None:
        """``on-negotiation-needed`` event handler.

        When receiving ``on-negotiation-needed`` event, create new offer.

        :param element: the webrtcbin
        :type element: object
        """
        # Set up ``on-offer-created`` event when offer is ready
        promise = Gst.Promise.new_with_change_func(self.on_offer_created, element, None)

        # Create new offer
        element.emit("create-offer", None, promise)

    def on_ice_candidate(self, _, mline_index, candidate: str) -> None:
        """``on-ice-candidate`` event handler.

        Send ICE candidate message to remote.

        :param mline_index: the index of the media description in the SDP
        :type mline_index: str
        :param candidate: an ICE candidate
        :type candidate: str
        """
        assert self.event_loop is not None

        c = {"candidate": candidate, "sdpMLineIndex": mline_index}
        future = asyncio.run_coroutine_threadsafe(
            self.ice_candidate_callback(c), self.event_loop
        )
        future.result()  # wait

    def set_remote_sdp(self, sdp: str) -> None:
        """Set remote session description.

        :param sdp: Session description
        :type sdp: str
        """
        assert self.webrtc is not None

        log.info("Setting remote session description")
        _, sdp_msg = GstSdp.SDPMessage.new()
        GstSdp.sdp_message_parse_buffer(bytes(sdp.encode()), sdp_msg)
        answer = GstWebRTC.WebRTCSessionDescription.new(
            GstWebRTC.WebRTCSDPType.ANSWER, sdp_msg
        )
        promise = Gst.Promise.new()
        self.webrtc.emit("set-remote-description", answer, promise)
        promise.interrupt()

    def add_ice_candidate(self, mline_index: int, candidate: str) -> None:
        """Add new ICE candidate.

        :param mline_index: the index of the media description in the SDP
        :type mline_index: int
        :param candidate: an ice candidate
        :type candidate: str
        """
        assert self.webrtc is not None
        self.webrtc.emit("add-ice-candidate", mline_index, candidate)

    def get_stats(self) -> str:
        """Get RTP statistics from GStreamer.

        :return: statistics as text report
        :rtype: str
        """
        assert self.pipe is not None
        fields = [
            "ssrc",
            "is-sender",
            "clock-rate",
            "octets-sent",
            "packets-sent",
            "octets-received",
            "packets-received",
            "bitrate",
            "packets-lost",
            "recv-pli-count",
            "recv-nack-count",
            "sr-ntptime",
        ]
        rtpbin = self.pipe.get_by_name("rtpsession0")
        message = []
        if rtpbin is None:
            return ""

        # Get statistics for each SSRC
        stats = rtpbin.get_property("stats")
        sources_stats = stats.get_value("source-stats")
        for source_stats in sources_stats:
            if source_stats.get_value("ssrc") != 0:
                message.append({f: source_stats.get_value(f) for f in fields})
        return pprint.pformat(message, sort_dicts=False)

    def start_pipeline(
        self, event_loop: asyncio.AbstractEventLoop, ice_servers: List[str]
    ) -> None:
        """Start gstreamer pipeline and connect WebRTC events.

        :param event_loop: asyncio event loop
        :type event_loop: EventLoop
        :param ice_servers: list of ICE TURN servers
        :type ice_servers: list of str
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
            # ULPFEC is not yet supported by Galène
            # transceiver.set_property("fec-type", GstWebRTC.WebRTCFECType.ULP_RED)

        # Add TURN servers
        try:
            for uri in ice_servers:
                self.webrtc.emit("add-turn-server", uri)
        except TypeError:
            log.warn(
                "add-turn-server signal is missing, maybe your gstreamer "
                "is too old. Skipping TURN servers configuration"
            )

        # Start
        self.pipe.set_state(Gst.State.PLAYING)

    def close_pipeline(self) -> None:
        """Stop gstreamer pipeline."""
        log.info("Closing pipeline")

        # If pipeline is running, then export pipeline graph before closing
        # To use this, set GST_DEBUG_DUMP_DOT_DIR environnement variable
        if self.pipe is not None:
            Gst.debug_bin_to_dot_file_with_ts(
                self.pipe, Gst.DebugGraphDetails.ALL, "pipeline"
            )
            self.pipe.set_state(Gst.State.NULL)

        self.pipe = None
        self.webrtc = None
