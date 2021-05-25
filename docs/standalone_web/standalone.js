/* eslint-env browser */

class GatewayClient {
  constructor() {
    this.socket = null
    this.pc = null // WebRTC peer connection
  }

  /**
   * Connect to the gateway using WebSocket
   */
  connectSocket() {
    return new Promise((resolve, reject) => {
      // Connect to WebSocket
      try {
        this.socket = new WebSocket('ws://localhost:8081')
      } catch (e) {
        reject(e)
      }

      // Set callbacks
      this.socket.onerror = (e) => reject(e)
      this.socket.onmessage = (e) => this.gotMessage(e)
      this.socket.onclose = () => console.log('Connection closed')
      this.socket.onopen = () => resolve()
    })
  }

  /**
   * Create WebRTC peer connection then start the negotiation
   */
  createPeerConnection() {
    // We need signalling socket to be opened
    if (!this.socket) {
      throw new Error('WebSocket need to be connected')
    }

    // Create peer connection
    // You may add STUN and TURN server to improve negotiation reliability
    this.pc = new RTCPeerConnection()

    // When video track is incoming, attack to document
    this.pc.ontrack = this.gotTrack

    // ICE callbacks
    this.pc.oniceconnectionstatechange = () => console.log(this.pc.iceConnectionState)
    this.pc.onicecandidate = (event) => {
      if (event.candidate !== null) {
        // Send each candidate directly for trickle ICE
        this.socket.send(JSON.stringify({
          type: 'ice',
          candidate: event.candidate,
        }))
      } else {
        // Send full session description
        this.socket.send(JSON.stringify(this.pc.localDescription))
      }
    }

    // Create new offer to receive one audio and video track
    // After offer creation, candidates will be send
    this.pc.addTransceiver('audio', { 'direction': 'recvonly' })
    this.pc.addTransceiver('video', { 'direction': 'recvonly' })
    this.pc.createOffer().then((d) => {
      this.pc.setLocalDescription(d)
    }).catch(console.log)
  }

  /**
   * Event called on new message
   * @param {MessageEvent} event Received message event
   */
  gotMessage(event) {
    // Decode JSON
    const data = JSON.parse(event.data)

    switch (data.type) {
      case 'stats':
        console.log(data.value)
        break
      case 'answer':
        try {
          client.pc.setRemoteDescription(new RTCSessionDescription(data))
        } catch (e) {
          console.error(e)
        }
        break
      case 'ice':
        try {
          client.pc.addIceCandidate(new RTCIceCandidate(data.candidate))
        } catch (e) {
          console.error(e)
        }
        break
    }
  }

  /**
   * Event called on new media track
   * @param {RTCTrackEvent} event New track event
   */
  gotTrack (event) {
    const el = document.createElement(event.track.kind)
    el.srcObject = event.streams[0]
    el.autoplay = true
    el.controls = true
    document.getElementById('remote-videos').appendChild(el)
  }
}

// Run client
const client = new GatewayClient()
client.connectSocket().then(() => {
  console.log('Connection successful, create WebRTC peer connection')
  client.createPeerConnection()
}).catch(console.error)
