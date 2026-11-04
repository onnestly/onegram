package org.onegram.net;

import java.io.*;
import java.net.*;
import java.nio.*;
import java.security.*;
import java.util.*;
import java.util.concurrent.*;
import javax.crypto.Cipher;

public final class LocalProxySelfTest {
    static final SecureRandom RANDOM = new SecureRandom();
    static class Echo implements LocalProxy.Remote {
        final BlockingQueue<byte[]> replies = new LinkedBlockingQueue<>();
        Cipher decode, encode;
        volatile byte[] received;
        public void send(byte[] data) throws Exception {
            if (decode == null) {
                byte[] key = Arrays.copyOfRange(data, 8, 56);
                decode = LocalProxy.aes(Arrays.copyOf(key, 32), Arrays.copyOfRange(key, 32, 48));
                decode.update(new byte[64]);
                byte[] reverse = LocalProxy.reverse(key);
                encode = LocalProxy.aes(Arrays.copyOf(reverse, 32), Arrays.copyOfRange(reverse, 32, 48));
            } else {
                received = decode.update(data);
                replies.put(encode.update(new byte[]{11, 22, 33, 44}));
            }
        }
        public byte[] receive() throws Exception { return replies.take(); }
        public void close() { replies.offer(new byte[0]); }
    }
    static final class Client implements AutoCloseable {
        final Socket socket;
        final Cipher out, in;
        Client(int port, byte[] secret, int protocol) throws Exception {
            socket = new Socket("127.0.0.1", port); socket.setSoTimeout(20000);
            byte[] init = new byte[64]; RANDOM.nextBytes(init);
            ByteBuffer.wrap(init).order(ByteOrder.LITTLE_ENDIAN).putInt(56, protocol).putShort(60, (short) 2);
            byte[] material = Arrays.copyOfRange(init, 8, 56);
            out = LocalProxy.aes(LocalProxy.hash(LocalProxy.concat(Arrays.copyOf(material, 32), secret)), Arrays.copyOfRange(material, 32, 48));
            byte[] encrypted = out.update(init);
            System.arraycopy(encrypted, 56, init, 56, 8);
            byte[] reverse = LocalProxy.reverse(material);
            in = LocalProxy.aes(LocalProxy.hash(LocalProxy.concat(Arrays.copyOf(reverse, 32), secret)), Arrays.copyOfRange(reverse, 32, 48));
            socket.getOutputStream().write(init);
        }
        void send(byte[] packet) throws Exception { socket.getOutputStream().write(out.update(packet)); }
        byte[] receive(int count) throws Exception { return in.update(LocalProxy.read(socket.getInputStream(), count)); }
        public void close() throws IOException { socket.close(); }
    }
    public static void main(String[] args) throws Exception {
        byte[] secret = new byte[16]; RANDOM.nextBytes(secret);
        for (int protocol : new int[]{0xefefefef, 0xeeeeeeee, 0xdddddddd}) {
            Echo echo = new Echo();
            try (LocalProxy proxy = new LocalProxy(secret, (dc, media, test) -> echo);
                 Client client = new Client(proxy.getPort(), secret, protocol)) {
                byte[] packet = protocol == 0xefefefef ? new byte[]{1, 4, 3, 2, 1} : new byte[]{4, 0, 0, 0, 4, 3, 2, 1};
                client.send(packet);
                if (!Arrays.equals(client.receive(4), new byte[]{11, 22, 33, 44})) throw new AssertionError("Reply mismatch");
                if (!Arrays.equals(echo.received, packet)) throw new AssertionError("Outbound corruption");
            }
        }
        System.out.println("Java bridge: all three MTProto transports passed encrypted bidirectional tests");
        if (Arrays.asList(args).contains("--live") || Arrays.asList(args).contains("--cf-only")) {
            boolean reserve=Arrays.asList(args).contains("--cf-only");
            for(int protocol:new int[]{0xefefefef,0xeeeeeeee,0xdddddddd})
            try (LocalProxy proxy = reserve ? new LocalProxy(secret,LocalProxy::connectFallback) : new LocalProxy(secret);
                 Client client = new Client(proxy.getPort(), secret, protocol)) {
                byte[] payload = new byte[40];
                ByteBuffer bytes = ByteBuffer.wrap(payload).order(ByteOrder.LITTLE_ENDIAN);
                bytes.putLong(8, (System.currentTimeMillis() / 1000) << 32);
                bytes.putInt(16, 20); bytes.putInt(20, 0xbe7e8ef1);
                byte[] nonce = new byte[16]; RANDOM.nextBytes(nonce); System.arraycopy(nonce, 0, payload, 24, 16);
                byte[] header = protocol==0xefefefef ? new byte[]{(byte)(payload.length/4)}
                    : ByteBuffer.allocate(4).order(ByteOrder.LITTLE_ENDIAN).putInt(payload.length).array();
                client.send(LocalProxy.concat(header, payload));
                int size;
                if(protocol==0xefefefef){
                    int first=client.receive(1)[0]&255;
                    if(first==0x7f){byte[] more=client.receive(3);size=((more[0]&255)|((more[1]&255)<<8)|((more[2]&255)<<16))*4;}
                    else size=first*4;
                }else size=LocalProxy.little(client.receive(4),0)&0x7fffffff;
                if (size < 24 || size > 65536) throw new AssertionError("Invalid Telegram reply length: " + size);
                byte[] reply = client.receive(size);
                if (LocalProxy.little(reply, 20) != 0x05162463) throw new AssertionError("Expected Telegram resPQ");
                if(!Arrays.equals(nonce,Arrays.copyOfRange(reply,24,40)))throw new AssertionError("Telegram reply nonce mismatch");
                System.out.println("Live Telegram handshake succeeded; protocol="+Integer.toHexString(protocol)+"; WebSocket connections=" + proxy.websocketConnections.get());
                if(reserve && proxy.fallbackConnections.get()==0)throw new AssertionError("Reserve route was not used");
                if(reserve && proxy.activeFallbackWebSockets.get()==0)throw new AssertionError("Active reserve route status is missing");
                if(reserve)System.out.println("Reserve WebSocket route returned a real Telegram resPQ without direct-IP or TCP fallback");
            }
        }
    }
}
