import socket
import struct
import secrets

class VoiceConnection:
    def __init__(self, user_id, ws, token):
        self.user_id = user_id
        self.ws = ws          # WebSocket de voz
        self.token = token
        self.udp_socket = None
        self.ssrc = random.randint(100000, 999999)
        self.sequence = 0
        self.timestamp = 0
        self.is_running = False

    async def start(self):
        # Aguarda a resposta 'READY' do WebSocket de voz
        ready_msg = await self.ws.receive()
        data = json.loads(ready_msg.data)
        if data.get('op') == 2:  # READY
            ip = data['d']['ip']
            port = data['d']['port']
            self.ssrc = data['d']['ssrc']
            modes = data['d']['modes']
            # Escolhe o melhor modo de encriptação (xsalsa20_poly1305)
            mode = modes[0] if modes else 'xsalsa20_poly1305'

            # Conecta UDP
            self.udp_socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            self.udp_socket.settimeout(1.0)

            # Envia pacote de descoberta (contém SSRC)
            packet = bytearray(74)
            struct.pack_into('>I', packet, 0, self.ssrc)
            self.udp_socket.sendto(packet, (ip, port))

            # Recebe resposta com IP e porta externos
            resp, _ = self.udp_socket.recvfrom(74)
            external_ip = resp[8:].decode().split('\x00', 1)[0]
            external_port = struct.unpack('>H', resp[4:6])[0]

            # Envia SELECT_PROTOCOL
            await self.ws.send(json.dumps({
                "op": 1,
                "d": {
                    "protocol": "udp",
                    "data": {
                        "address": external_ip,
                        "port": external_port,
                        "mode": mode
                    }
                }
            }))

            self.is_running = True
            # Inicia tarefa de envio de heartbeats UDP (silence frames)
            asyncio.create_task(self._udp_heartbeat())

    async def _udp_heartbeat(self):
        """Envia pacotes RTP vazios (silêncio) a cada 5 segundos."""
        while self.is_running:
            if self.udp_socket:
                # Cria cabeçalho RTP (versão 2, payload de áudio, SSRC)
                header = bytearray(12)
                header[0] = 0x80  # V=2, P=0, X=0, CC=0
                header[1] = 0x78  # PT=120 (payload tipo opus)
                struct.pack_into('>H', header, 2, self.sequence)
                struct.pack_into('>I', header, 4, self.timestamp)
                struct.pack_into('>I', header, 8, self.ssrc)

                self.sequence += 1
                self.timestamp += 960  # 20ms de áudio (48kHz)

                # Envia o pacote (sem payload, apenas silêncio)
                try:
                    # Para evitar ban, enviamos um pacote de keepalive (não cifrado, só o header)
                    # O Discord aceita headers vazios como "silêncio"
                    self.udp_socket.sendto(header, (self.udp_socket.getpeername()[0], self.udp_socket.getpeername()[1]))
                except:
                    pass

            await asyncio.sleep(random.uniform(4.5, 6.0))

    def stop(self):
        self.is_running = False
        if self.udp_socket:
            self.udp_socket.close()